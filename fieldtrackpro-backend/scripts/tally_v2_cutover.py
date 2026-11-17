"""
FieldTrack Pro - Tally v2 cut-over data step (run once, after migration g1a2b3c4d5e6 or later,
BEFORE agent 2.0 performs its first full load).

What it changes (nothing is deleted):
  1. Clears the due dates the old agent invented (invoice_date + 21 days on Tally
     invoices). Tally gives no credit period on these bills; the real due date of
     every open bill is set by the first Bills Receivable snapshot afterwards.

Everything else in the cut-over is done by agent 2.0's first full load through
the normal, idempotent sync endpoints (and is shown in the reconciliation report):
receipts whose party is a bank / supplier ledger, vouchers later changed into
other types, cancelled / optional / deleted vouchers are RETIRED (never deleted);
non-debtor ledgers are flagged tally_is_debtor = false and leave outlet lists.

Safety model (scripts/_script_env.destructive_script_main):
  * DEFAULT IS DRY-RUN - the update runs in a transaction that is ROLLED BACK.
  * Real execution needs --execute AND env CONFIRM_PURGE_DATABASE=<database name>.
  * ENVIRONMENT=production additionally needs --i-understand-production.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _script_env

SUPPORTED_REVISIONS = ("g1a2b3c4d5e6", "h1b2c3d4e5f6")

DEFAULTED_DUE_DATES = """
    SELECT count(*), COALESCE(sum(amount), 0) FROM invoices
     WHERE source = 'TALLY' AND due_date IS NOT NULL AND due_date = invoice_date + 21
"""


def run_cutover(cur) -> None:
    cur.execute("SELECT version_num FROM alembic_version")
    head = cur.fetchone()[0]
    print(f"Database revision: {head}")
    # The cut-over needs the Tally v2 schema (g1a2b3c4d5e6) or a later revision that includes it:
    # release 2.1.0's head h1b2c3d4e5f6 (production migrates b9c0d1e2f3a4 -> h1b2c3d4e5f6 in one run).
    if head not in SUPPORTED_REVISIONS:
        raise SystemExit(f"REFUSING: database is at {head}; run `alembic upgrade head` first "
                         f"(expected one of {', '.join(SUPPORTED_REVISIONS)}).")

    cur.execute("SELECT count(*), count(due_date) FROM invoices WHERE source = 'TALLY'")
    total, with_due = cur.fetchone()
    cur.execute(DEFAULTED_DUE_DATES)
    n, amount = cur.fetchone()
    print(f"Tally invoices: {total}; with a due date: {with_due}; due date = invoice date + 21: {n} (amount {amount})")
    cur.execute(
        "UPDATE invoices SET due_date = NULL "
        "WHERE source = 'TALLY' AND due_date IS NOT NULL AND due_date = invoice_date + 21"
    )
    print(f" - due dates cleared: {cur.rowcount}")
    cur.execute(DEFAULTED_DUE_DATES)
    left = cur.fetchone()[0]
    print(f" - defaulted due dates remaining: {left} (expected 0)")


if __name__ == "__main__":
    sys.exit(_script_env.destructive_script_main("TALLY V2 CUT-OVER", run_cutover))
