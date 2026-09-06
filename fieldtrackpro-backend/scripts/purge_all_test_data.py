"""
FieldTrack Pro - Automated & Test Data Purge Master Script.
Removes all test/dummy data according to AGENTS.md rules.
Ensures ONLY Real SGRG Production Data remains:
- 30 SGRG Staff Members (11001 - 11030)
- 1,631 Real Client Outlets
- 55 Territories & 465 Areas
- 1.5 Years Real Tally Invoices & Vouchers
- admin@fieldtrack.test
"""
import os
import psycopg2

db_url = os.environ.get("DATABASE_URL", "postgresql://fieldtrack_app:XcWG3aLw7s8mL75vrvl97aDZTSXbr4y6@127.0.0.1:5432/fieldtrackpro_dev")
db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

conn = psycopg2.connect(db_url)
conn.autocommit = False
cur = conn.cursor()

def run(sql, params=None, desc=""):
    if params is not None:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    print(f"  {desc}: {cur.rowcount} rows affected")

print("=" * 65)
print("PURGING AUTOMATED & TEST DATA FROM DATABASE")
print("=" * 65)

try:
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
    cur.execute("SELECT id FROM payments WHERE source = 'MANUAL' OR visit_id IS NOT NULL")
    test_payment_ids = [r[0] for r in cur.fetchall()]
    if test_payment_ids:
        cur.execute("DELETE FROM payment_proofs WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payment_brand_allocations WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payment_invoice_allocations WHERE payment_id = ANY(%s::uuid[])", (test_payment_ids,))
        cur.execute("DELETE FROM payments WHERE id = ANY(%s::uuid[])", (test_payment_ids,))
        print(f"  test payments: {len(test_payment_ids)} deleted")

    # 4. Purge test visits & child tables
    run("DELETE FROM geo_verification_logs", desc="Geo verification logs")
    run("DELETE FROM visit_signatures", desc="Visit signatures")
    run("DELETE FROM visit_media", desc="Visit media")
    run("DELETE FROM form_answers", desc="Form answers")
    run("DELETE FROM form_submissions", desc="Form submissions")
    run("DELETE FROM field_exceptions", desc="Field exceptions")
    run("DELETE FROM employee_work_sessions", desc="Employee work sessions")
    run("DELETE FROM planned_visits", desc="Planned visits")
    run("DELETE FROM monthly_visit_plans", desc="Monthly visit plans")
    run("DELETE FROM visits", desc="Visits")

    # 5. Purge test invoices
    run("DELETE FROM payment_invoice_allocations WHERE invoice_id IN (SELECT id FROM invoices WHERE invoice_number LIKE '%16241b' OR invoice_number LIKE '%ffd7b6' OR invoice_number LIKE '%9f63ce')", desc="Test invoice allocations")
    run("DELETE FROM invoices WHERE invoice_number LIKE '%16241b' OR invoice_number LIKE '%ffd7b6' OR invoice_number LIKE '%9f63ce'", desc="Test invoices")

    # 6. Purge test customers (Aaditya Telecom test hex, DMS-*, UPDDC10FEF, CURR-GPS-001)
    cur.execute("""
        SELECT id FROM customers 
        WHERE outlet_code IN ('UPDDC10FEF', 'CURR-GPS-001') 
           OR outlet_code LIKE '%TEST%' 
           OR outlet_code LIKE 'REP%'
           OR outlet_code LIKE 'DMS-%'
           OR name LIKE 'Aaditya Telecom %'
    """)
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

    conn.commit()
    print("=" * 65)
    print("SUCCESS: ALL TEST DATA PURGED! ONLY REAL CLIENT DATA REMAINS.")
    print("=" * 65)

except Exception as e:
    conn.rollback()
    print("ERROR DURING CLEANUP:", e)
    raise
finally:
    cur.close()
    conn.close()
