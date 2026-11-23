"""Follow-up for two cases of gps_workflow_test.py (needs 2 more TEST-QA outlets without GPS). Run from the backend dir."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gps_workflow_test as g  # noqa: E402
import qa_common as qc  # noqa: E402
import asyncpg  # noqa: E402


async def main():
    con = await asyncpg.connect(qc.db_url())
    await qc.assert_local(con)
    st, tok, _ = qc.http("POST", "/auth/login", dict(mobile_number=qc.TEST_MOBILE, password=qc.secret("local-test-employee.txt", "Password")))
    auth = {"Authorization": "Bearer " + tok["access_token"]}
    free = await con.fetch("select id, outlet_code from customers where outlet_code ~ '^TEST-QA-OUT-0(2[1-5])$' and location is null "
                           "and not exists (select 1 from outlet_proofs p where p.customer_id=customers.id) order by outlet_code")
    if len(free) < 2:
        qc.abort("need 2 free TEST-QA outlets")
    now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731
    ok = True

    st, v, _ = qc.http("POST", "/visits/ad-hoc", dict(customer_id=str(free[0]["id"]), adhoc_reason="Customer Requested", adhoc_notes="TEST-QA follow-up"), auth)
    st, b, _ = qc.http("POST", f"/visits/{v['id']}/check-in", dict(latitude=26.5, longitude=80.5, accuracy_m=10.0, is_mock_location=False, captured_at=now()), auth)
    c = g.err_code(b)
    r1 = st == 422 and c == "OUTLET_LOCATION_NOT_CONFIGURED"
    print(("PASS" if r1 else "FAIL"), "1 outlet without GPS: check-in rejected ->", st, c)

    lat0, lon0 = 26.55, 80.55
    st, p = g.upload_proof(auth, str(free[1]["id"]), lat0, lon0, 10.0)
    assert st == 201 and p["auto_accepted"], p
    st, v2, _ = qc.http("POST", "/visits/ad-hoc", dict(customer_id=str(free[1]["id"]), adhoc_reason="Customer Requested", adhoc_notes="TEST-QA follow-up"), auth)
    far = g.offset(lat0, lon0, 0, 500)
    st, b, _ = qc.http("POST", f"/visits/{v2['id']}/check-in", dict(latitude=far[0], longitude=far[1], accuracy_m=10.0, is_mock_location=False, captured_at=now()), auth)
    c = g.err_code(b)
    r2 = st == 422 and c == "GEO_VERIFICATION_FAILED"
    print(("PASS" if r2 else "FAIL"), "3 check-in ~500 m from the outlet: rejected ->", st, c, (b.get("error", {}).get("message") if isinstance(b, dict) else ""))
    near = g.offset(lat0, lon0, 30, 0)
    st, b, _ = qc.http("POST", f"/visits/{v2['id']}/check-in", dict(latitude=near[0], longitude=near[1], accuracy_m=10.0, is_mock_location=False, captured_at=now()), auth)
    r3 = st == 200
    print(("PASS" if r3 else "FAIL"), "3 same visit from ~30 m: accepted ->", st)

    import json
    man = json.load(open(qc.MANIFEST, encoding="utf-8"))
    man["gps_test_outlet_ids"] += [str(free[0]["id"]), str(free[1]["id"])]
    man["visit_ids"] = list(dict.fromkeys(man["visit_ids"] + [v["id"], v2["id"]]))
    json.dump(man, open(qc.MANIFEST, "w", encoding="utf-8"), indent=2)
    await con.close()
    sys.exit(0 if (r1 and r2 and r3) else 1)


asyncio.run(main())
