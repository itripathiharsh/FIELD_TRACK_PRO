"""Outlet Mapping work queues (19-Nov-2026 fix).

* missing_brand / new_unreviewed rows are LEDGERS and carry their outlet's name / address / code.
* missing_code rows are OUTLETS (the code is stored on the outlet): one row per shop even with several ledgers,
  and a saved code takes the outlet off the list (before the fix the list checked the ledger's Tally code, so a
  saved code never left it).
"""
from __future__ import annotations

import pytest

from tests.conftest import requires_db
from tests.test_outlet_ledgers_v21 import _ledger
from tests.test_tally_v2_sync import _post, _snapshot, env  # noqa: F401  (env is a fixture)


async def _queues(env):
    r = await env["c"].get("/api/v1/outlet-mapping/queues", headers=env["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


@requires_db
@pytest.mark.asyncio
async def test_queue_rows_carry_outlet_details_and_codes_are_per_outlet(env):
    t = env["tag"]
    res = await _snapshot(env, [
        {"guid": f"QA-{t}", "name": f"Queue Shop {t} (ZBR)", "is_debtor": True, "parent": "Sundry Debtors",
         "address": f"12 Mall Road {t}", "brand": None},
        {"guid": f"QB-{t}", "name": f"Queue Shop {t} (RR)", "is_debtor": True, "parent": "Sundry Debtors"},
    ])
    assert res["failed_count"] == 0, res
    a, b = await _ledger(f"QA-{t}"), await _ledger(f"QB-{t}")
    # put both brand ledgers on one shop
    r = await env["c"].post("/api/v1/outlet-mapping/link", json={"ledger_id": str(b.id), "target_customer_id": str(a.customer_id)},
                            headers=env["admin_h"])
    assert r.status_code == 200, r.text

    q = await _queues(env)
    brand_rows = [x for x in q["missing_brand"] if x["id"] in (str(a.id), str(b.id))]
    assert len(brand_rows) == 2, "a brand is per ledger"
    for row in brand_rows:
        assert row["outlet_name"] and row["name"] and row["customer_id"] == str(a.customer_id)
        assert row["brand_source"] == "NONE" and row["outlet_code"] is None
    assert any(row["outlet_address"] == f"12 Mall Road {t}" for row in brand_rows)

    code_rows = [x for x in q["missing_code"] if x["customer_id"] == str(a.customer_id)]
    assert len(code_rows) == 1, "one row per OUTLET, not per ledger"
    assert sorted(l["name"] for l in code_rows[0]["ledgers"]) == sorted([a.name, b.name])
    assert code_rows[0]["outlet_code"] is None and code_rows[0]["outlet_name"]

    # saving the outlet code takes the outlet off the list
    code = f"UPDDQ{t[:6].upper()}"
    r = await env["c"].post("/api/v1/outlet-mapping/outlet-code", json={"customer_id": str(a.customer_id), "outlet_code": code},
                            headers=env["admin_h"])
    assert r.status_code == 200, r.text
    q = await _queues(env)
    assert str(a.customer_id) not in [x["customer_id"] for x in q["missing_code"]]
    # the merged (former) outlet of ledger b never appears as a separate row
    assert all(x["customer_id"] != str(b.customer_id) or b.customer_id == a.customer_id for x in q["missing_code"])

    # saving a brand takes that one ledger off the brand list
    r = await env["c"].post("/api/v1/outlet-mapping/brand", json={"ledger_id": str(a.id), "brand": "Zebronics"},
                            headers=env["admin_h"])
    assert r.status_code == 200, r.text
    q = await _queues(env)
    ids = [x["id"] for x in q["missing_brand"]]
    assert str(a.id) not in ids and str(b.id) in ids
