"""Snapshot the computed account positions of unrelated (non-QA) local outlets, to prove the QA dataset leaves
them unchanged.  Run from the backend dir:  python -I <this> before|after"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as qc  # noqa: E402

sys.path.insert(0, os.getcwd())
from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.services import account_position  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unrelated_positions_{}.json")


async def main(tag):
    qc.check_url(qc.db_url())
    async with AsyncSessionLocal() as s:
        r = (await s.execute(text("select current_database(), inet_server_addr()::text"))).one()
        if r[0] != qc.EXPECTED_DB or not str(r[1]).startswith("127.0.0.1"):
            qc.abort("not the local dev database")
        ids = [x[0] for x in (await s.execute(text(
            "select distinct customer_id from tally_debtor_ledgers where tally_guid not like 'TEST-QA-%' "
            "and closing_balance_at is not null order by customer_id limit 60"))).all()]
        ids += [x[0] for x in (await s.execute(text(
            "select distinct customer_id from invoices where source='TALLY' and source_reference not like 'TEST-QA-%' "
            "order by customer_id limit 40"))).all()]
        pos = await account_position.load_outlet_positions(s, list(dict.fromkeys(ids)))
        data = {str(k): {"outstanding": str(v.outlet.outstanding), "overdue": str(v.outlet.overdue),
                         "invoiced": str(v.outlet.invoiced), "paid": str(v.outlet.paid_in_tally)} for k, v in pos.items()}
    json.dump(data, open(OUT.format(tag), "w"), indent=1, sort_keys=True)
    print(tag, "outlets:", len(data))
    if tag == "after" and os.path.exists(OUT.format("before")):
        before = json.load(open(OUT.format("before")))
        diff = [k for k in before if before[k] != data.get(k)]
        print("unrelated outlets changed:", len(diff), diff[:5])


asyncio.run(main(sys.argv[1]))
