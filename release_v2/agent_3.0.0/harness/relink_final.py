"""Post-run step: apply the backend relink fix (relink_receipts_of_invoices) to the final harness database.

The full replay ran its backend from code taken before the fix, so receipts whose invoice was later
cancelled or deleted kept pointing at the retired row. This script runs the FIXED backend code on the
harness DB (never production), then diffs every TALLY receipt -> TALLY invoice link before and after.

Usage: python relink_final.py <expected_pair_payment_guid> <expected_pair_invoice_guid> <amount>
"""
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2] / "field track pro" / "fieldtrackpro-backend"
sys.path.insert(0, str(HERE))
from setup_backend import harness_env  # noqa: E402

env = harness_env()
os.environ["DATABASE_URL"] = env["DATABASE_URL"]
os.environ["MIGRATION_DATABASE_URL"] = env["MIGRATION_DATABASE_URL"]
assert "harness" in env["DATABASE_URL"].rsplit("/", 1)[-1], "refusing: not the harness database"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.services.tally_v2_sync import relink_receipts_of_invoices  # noqa: E402

LINKS = """SELECT p.source_reference pk, i.source_reference ik, i.source isrc, x.allocated_amount m
           FROM payment_invoice_allocations x JOIN payments p ON p.id = x.payment_id JOIN invoices i ON i.id = x.invoice_id
           WHERE p.source = 'TALLY'"""


async def snapshot(s):
    links, retired = {}, 0
    for pk, ik, isrc, m in (await s.execute(text(LINKS))).all():
        if isrc == "TALLY":
            links[(pk, ik)] = links.get((pk, ik), Decimal("0")) + Decimal(m)
        else:
            retired += 1
    return links, retired


async def main(pg, ig, amount):
    async with AsyncSessionLocal() as s:
        before, rb = await snapshot(s)
        ids = [r[0] for r in (await s.execute(text(
            """SELECT DISTINCT i.id FROM payment_invoice_allocations x JOIN payments p ON p.id = x.payment_id
               JOIN invoices i ON i.id = x.invoice_id WHERE p.source = 'TALLY' AND i.source <> 'TALLY'"""))).all()]
        n = await relink_receipts_of_invoices(s, ids)
        await s.commit()
    async with AsyncSessionLocal() as s:
        after, ra = await snapshot(s)
    added = {f"{k[0]}->{k[1]}": str(v) for k, v in after.items() if before.get(k) != v}
    removed = {f"{k[0]}->{k[1]}": str(v) for k, v in before.items() if k not in after}
    expected = {f"{pg}->{ig}": str(Decimal(amount).quantize(Decimal("0.01")))}
    ok = added == expected and not removed and ra == 0
    out = {"retired_invoices": len(ids), "receipts_relinked": n, "links_before": len(before), "links_after": len(after),
           "links_to_retired_before": rb, "links_to_retired_after": ra, "added_or_changed": added, "removed": removed,
           "expected_change": expected, "PASS": ok}
    print(json.dumps(out, indent=1))
    (HERE.parent / "harness_relink_result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    sys.exit(0 if ok else 1)


asyncio.run(main(*sys.argv[1:4]))
