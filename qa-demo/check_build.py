"""Read-only checks of the QA build database (counts + Tally reconciliation)."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seed_qa_demo as s   # sets env + guards (build DB only)
from app.database import AsyncSessionLocal
from app.services import tally_reconciliation
async def main():
    async with AsyncSessionLocal() as ses:
        rep = await tally_reconciliation.build_report(ses, limit=5)
        print(json.dumps({k: rep[k] for k in ("totals","counts","debtors_reconciled","debtors_with_difference","unallocated_total")}, indent=1, default=str))
        print("differences:", rep["differences"][:3])
    con = await __import__("asyncpg").connect(s._e["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://"))
    rows = await con.fetch("""select relname, n_live_tup from pg_stat_user_tables where n_live_tup>0 order by relname""")
    for tb in ("users","employees","territories","areas","customers","employee_customer_assignments","invoices","payments","tally_ledger_adjustments","tally_open_bills","tally_debtor_ledgers","visits","orders","customer_requirements"):
        print(tb, await con.fetchval(f"select count(*) from {tb}"), end=" | ")
    print()
    print("outlets with ledger:", await con.fetchval("select count(distinct customer_id) from tally_debtor_ledgers where is_debtor"))
    print("outstanding total (open bills):", await con.fetchval("select sum(pending_amount) from tally_open_bills"))
    await con.close()
    from app.database import engine; await engine.dispose()
asyncio.run(main())
