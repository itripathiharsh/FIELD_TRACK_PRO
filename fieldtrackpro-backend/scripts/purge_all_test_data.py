"""
FieldTrack Pro - Automated & Test Data Purge Master Script.

DESTRUCTIVE. Removes test/dummy data according to AGENTS.md rules so ONLY real
SGRG data remains (30 staff 11001-11030, ~1,631 outlets, 55 territories /
465 areas, real Tally invoices & vouchers, the admin account).

Safety model:
  * DEFAULT IS DRY-RUN: the whole purge is executed inside a transaction that
    is ROLLED BACK; row counts are printed so you can review them.
  * Real execution needs ALL of:  --execute
                                  CONFIRM_PURGE_DATABASE=<exact database name>  (env)
  * ENVIRONMENT=production additionally needs --i-understand-production.
  * The database comes from DATABASE_URL / app settings - there is no
    hardcoded fallback connection string.
  * Take a backup first (pg_dump). This script cannot be undone once committed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg2

import _script_env


# --- Test-entity markers (AGENTS.md) ---------------------------------------------------------
# Payments are only ever deleted when they belong to a TEST employee or a TEST outlet matched by
# these markers. A real field collection (real SGRG employee 110xx on a real outlet) is never
# selected, even if it is MANUAL or carries a visit_id.
TEST_EMPLOYEE_IDS_SQL = r"""
    SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id
    WHERE e.employee_code LIKE 'REP-%'
       OR e.employee_code LIKE 'FT%'
       OR e.employee_code LIKE 'RFX%'
       OR e.employee_code LIKE '\_\_itest\_\_%'
       OR u.email LIKE 'emp\_wb\_%@fieldtrack.test'
       OR u.email LIKE '\_\_itest\_\_%'
       OR (u.email LIKE '%@fieldtrack.test' AND u.email <> 'admin@fieldtrack.test')
       OR e.full_name IN ('Browser Test', 'Alert Store/Rep')
"""

TEST_CUSTOMER_IDS_SQL = r"""
    SELECT id FROM customers
    WHERE outlet_code IN ('UPDDC10FEF', 'CURR-GPS-001')
       OR outlet_code LIKE '%TEST%'
       OR outlet_code LIKE 'REP%'
       OR outlet_code LIKE 'DMS-%'
       OR outlet_code LIKE 'FT%'
       OR outlet_code LIKE 'RFX%'
       OR name LIKE 'Aaditya Telecom %'
       OR name LIKE '\_\_itest\_\_%'
       OR name IN ('Browser Test', 'Alert Store/Rep')
"""

TEST_PAYMENT_IDS_SQL = (
    "SELECT id FROM payments WHERE employee_id IN (" + TEST_EMPLOYEE_IDS_SQL + ") "
    "OR customer_id IN (" + TEST_CUSTOMER_IDS_SQL + ")"
)

# Visits still referenced by a payment that is being KEPT must survive (FK + audit trail).
KEPT_PAYMENT_VISITS_SQL = (
    "SELECT visit_id FROM payments WHERE visit_id IS NOT NULL AND id NOT IN (" + TEST_PAYMENT_IDS_SQL + ")"
)


def purge(cur) -> None:
    def run(sql, params=None, desc=""):
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        print(f"  {desc}: {cur.rowcount} rows affected")

    # 0. Super-admin ID
    cur.execute("SELECT id FROM users WHERE email = 'admin@fieldtrack.test'")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Super admin not found!")
    admin_id = row[0]

    # 1. Purge Tally writeback queue
    run("DELETE FROM tally_writeback_queue", desc="Tally writeback queue records")

    # 2. Purge test customer requirements
    run("DELETE FROM customer_requirements", desc="Customer requirements records")

    # 3. Purge test payments and allocations
    cur.execute(TEST_PAYMENT_IDS_SQL)
    test_payment_ids = [r[0] for r in cur.fetchall()]
    if test_payment_ids:
        cur.execute("DELETE FROM payment_proofs WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payment_brand_allocations WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payment_invoice_allocations WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payments WHERE id = ANY(%s::uuid[])", (test_payment_ids,))
        print(f"  test payments: {len(test_payment_ids)} deleted")

    # 4. Purge test visits & child tables
    keep = f"visit_id NOT IN ({KEPT_PAYMENT_VISITS_SQL})"
    run(f"DELETE FROM geo_verification_logs WHERE {keep}", desc="Geo verification logs")
    run(f"DELETE FROM visit_signatures WHERE {keep}", desc="Visit signatures")
    run(f"DELETE FROM visit_media WHERE {keep}", desc="Visit media")
    run("DELETE FROM form_answers", desc="Form answers")
    run("DELETE FROM form_submissions", desc="Form submissions")
    run("DELETE FROM field_exceptions", desc="Field exceptions")
    run("DELETE FROM employee_work_sessions", desc="Employee work sessions")
    run("DELETE FROM planned_visits", desc="Planned visits")
    run("DELETE FROM monthly_visit_plans", desc="Monthly visit plans")
    run(f"DELETE FROM visits WHERE id NOT IN ({KEPT_PAYMENT_VISITS_SQL})", desc="Visits")

    # 5. Purge test invoices
    run("DELETE FROM payment_invoice_allocations WHERE invoice_id IN (SELECT id FROM invoices WHERE invoice_number LIKE '%16241b' OR invoice_number LIKE '%ffd7b6' OR invoice_number LIKE '%9f63ce')", desc="Test invoice allocations")
    run("DELETE FROM invoices WHERE invoice_number LIKE '%16241b' OR invoice_number LIKE '%ffd7b6' OR invoice_number LIKE '%9f63ce'", desc="Test invoices")

    # 6. Purge test customers (Aaditya Telecom test hex, DMS-*, UPDDC10FEF, CURR-GPS-001)
    cur.execute(TEST_CUSTOMER_IDS_SQL)
    test_cust_ids = [r[0] for r in cur.fetchall()]
    if test_cust_ids:
        cur.execute("DELETE FROM customer_brands WHERE customer_id = ANY(%s::uuid[])", (test_cust_ids,))
        cur.execute("DELETE FROM employee_customer_assignments WHERE customer_id = ANY(%s::uuid[])", (test_cust_ids,))
        cur.execute("DELETE FROM customers WHERE id = ANY(%s::uuid[])", (test_cust_ids,))
        print(f"  test customers: {len(test_cust_ids)} deleted")

    # 7. Purge test employees
    cur.execute("""
        SELECT id FROM employees 
        WHERE employee_code NOT SIMILAR TO '110[0-9]{2}' OR employee_code IS NULL
    """)
    test_emp_ids = [r[0] for r in cur.fetchall()]
    if test_emp_ids:
        cur.execute("DELETE FROM employee_customer_assignments WHERE employee_id = ANY(%s::uuid[])", (test_emp_ids,))
        cur.execute("DELETE FROM employee_area_assignments WHERE employee_id = ANY(%s::uuid[])", (test_emp_ids,))
        cur.execute("DELETE FROM employee_territory_assignments WHERE employee_id = ANY(%s::uuid[])", (test_emp_ids,))
        cur.execute("DELETE FROM fos_employee_mappings WHERE employee_id = ANY(%s::uuid[])", (test_emp_ids,))
        cur.execute("DELETE FROM employees WHERE id = ANY(%s::uuid[])", (test_emp_ids,))
        print(f"  test employees: {len(test_emp_ids)} deleted")

    # 8. Reassign foreign keys & purge test users
    sgrg_users = "(SELECT id FROM users WHERE email = 'admin@fieldtrack.test' OR email LIKE '%%@sgrgservices.com')"
    run(f"UPDATE customers SET created_by = %s WHERE created_by NOT IN {sgrg_users}", (admin_id,), "Reassign customers.created_by")
    run(f"UPDATE invoices SET created_by = %s WHERE created_by NOT IN {sgrg_users}", (admin_id,), "Reassign invoices.created_by")
    run(f"UPDATE payments SET created_by = %s WHERE created_by NOT IN {sgrg_users}", (admin_id,), "Reassign payments.created_by")

    cur.execute("""
        SELECT id FROM users 
        WHERE email != 'admin@fieldtrack.test' AND email NOT LIKE '%@sgrgservices.com'
    """)
    test_user_ids = [r[0] for r in cur.fetchall()]
    if test_user_ids:
        cur.execute("DELETE FROM refresh_tokens WHERE user_id = ANY(%s::uuid[])", (test_user_ids,))
        cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ANY(%s::uuid[])", (test_user_ids,))
        cur.execute("DELETE FROM user_devices WHERE user_id = ANY(%s::uuid[])", (test_user_ids,))
        cur.execute("DELETE FROM notifications WHERE user_id = ANY(%s::uuid[])", (test_user_ids,))
        cur.execute("DELETE FROM users WHERE id = ANY(%s::uuid[])", (test_user_ids,))
        print(f"  test users: {len(test_user_ids)} deleted")



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Purge automated/test data (dry-run by default).")
    parser.add_argument("--execute", action="store_true", help="really commit the purge (default: dry-run + rollback)")
    parser.add_argument("--i-understand-production", action="store_true", help="required when ENVIRONMENT=production")
    args = parser.parse_args(argv)

    from app.config import settings

    db_url = _script_env.db_url()
    db_name = urlparse(db_url).path.lstrip("/")

    if settings.environment == "production" and not args.i_understand_production:
        print("REFUSING: ENVIRONMENT=production requires --i-understand-production.")
        return 2
    if args.execute and os.environ.get("CONFIRM_PURGE_DATABASE") != db_name:
        print(f"REFUSING: --execute requires env CONFIRM_PURGE_DATABASE set to the exact database name ({db_name!r}).")
        return 2

    mode = "EXECUTE (will COMMIT)" if args.execute else "DRY-RUN (will ROLL BACK)"
    print("=" * 65)
    print(f"PURGE AUTOMATED & TEST DATA - database={db_name} - {mode}")
    print("=" * 65)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        purge(cur)
        if args.execute:
            conn.commit()
            print("COMMITTED: test data purged.")
        else:
            conn.rollback()
            print("DRY-RUN complete: everything rolled back, nothing was changed.")
        return 0
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ERROR during purge, rolled back:", type(exc).__name__, exc)
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
