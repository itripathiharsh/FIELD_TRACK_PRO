"""
LOCAL API-level test of the outlet GPS onboarding rules (fieldtrackpro_dev, TEST-QA outlets only).

Run from the (feature-branch) backend dir:
    cd "F:\\Field track pro v2 for test\\_wt_android_ui\\fieldtrackpro-backend"
    python -I "F:\\Field track pro v2 for test\\qa-dataset\\gps_workflow_test.py"

IMPORTANT: this simulates the phone's requests with FICTIONAL coordinates and synthetic photos. It proves the SERVER
rules. It is NOT a device GPS/camera test and verifies nothing about a real phone.
Admin review steps call the same service functions the admin API uses (no admin password is needed or used).
"""
import asyncio
import io
import json
import os
import random
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as qc  # noqa: E402

sys.path.insert(0, os.getcwd())
import asyncpg  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import settings  # noqa: E402

u = make_url(str(settings.database_url))
qc.check_url(qc.db_url())
if (u.host, u.port, u.database) != ("127.0.0.1", 5432, "fieldtrackpro_dev") or str(settings.environment).lower() != "dev":
    qc.abort("backend settings do not point at the local dev database")
if not os.path.abspath(os.getcwd()).lower().endswith("fieldtrackpro-backend"):
    qc.abort("run from the backend directory")

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from PIL import Image  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.services import outlet_proof_service  # noqa: E402

RNG = random.Random()  # unique photos per run (the server rejects a photo reused for another outlet)
# Fictional spot (not a real outlet, not the user's location).
BASE_LAT, BASE_LON = 26.5000, 80.5000
M_PER_DEG_LAT = 111_320.0


def offset(lat, lon, north_m=0.0, east_m=0.0):
    import math
    return lat + north_m / M_PER_DEG_LAT, lon + east_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def photo_bytes() -> bytes:
    img = Image.new("RGB", (900, 600))
    img.putdata([(RNG.randrange(256), RNG.randrange(256), RNG.randrange(256)) for _ in range(900 * 600)])
    out = io.BytesIO()
    img.save(out, "JPEG", quality=70)
    return out.getvalue()


def multipart(fields: dict, file_bytes: bytes):
    boundary = "----qa" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="live.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                 + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_proof(auth, customer_id, lat, lon, acc=10.0, mock=False, captured=None, key=None):
    body, ctype = multipart(dict(
        latitude=lat, longitude=lon, accuracy_m=acc, is_mock_location=str(mock).lower(),
        captured_at=(captured or datetime.now(timezone.utc)).isoformat(), idempotency_key=key or f"TEST-QA-{uuid.uuid4()}",
        device_info="TEST-QA api simulation", customer_id=customer_id), photo_bytes())
    req = urllib.request.Request(qc.LOCAL_API + "/customers/outlet-proofs", method="POST", data=body)
    req.add_header("Content-Type", ctype)
    req.add_header("Authorization", auth["Authorization"])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300]


def err_code(body):
    return (body or {}).get("error", {}).get("code") if isinstance(body, dict) else None


async def main():
    qc.backend_is_local_and_up()
    con = await asyncpg.connect(qc.db_url())
    await qc.assert_local(con)
    results = []

    def check(label, cond, detail=""):
        results.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail else ""))

    st, tok, _ = qc.http("POST", "/auth/login", dict(mobile_number=qc.TEST_MOBILE, password=qc.secret("local-test-employee.txt", "Password")))
    assert st == 200, "login failed"
    auth = {"Authorization": "Bearer " + tok["access_token"]}
    emp = uuid.UUID(qc.TEST_EMPLOYEE_ID)

    # Pick TEST-QA outlets that currently have NO location and are assigned to the test employee.
    free = await con.fetch("""select c.id, c.outlet_code from customers c
        where c.outlet_code ~ '^TEST-QA-OUT-0(1[5-9]|2[0-5])$' and c.location is null and c.location_status in ('MISSING','PENDING_APPROVAL')
          and not exists (select 1 from outlet_proofs p where p.customer_id=c.id) order by c.outlet_code""")
    if len(free) < 6:
        qc.abort(f"need 6 TEST-QA outlets without GPS and without proofs, found {len(free)}")
    A, B, C, D, E, F = [(str(r["id"]), r["outlet_code"]) for r in free[:6]]
    print("outlets:", [x[1] for x in (A, B, C, D, E, F)])

    async def outlet(cid):
        r = await con.fetchrow("select location_status, ST_Y(location::geometry) lat, ST_X(location::geometry) lon from customers where id=$1", uuid.UUID(cid))
        return r["location_status"], r["lat"], r["lon"]

    # ------------------------------------------------------------------ 1. no GPS -> check-in cannot work yet
    await qc.assert_local(con)
    st, visitA, _ = qc.http("POST", "/visits/ad-hoc", dict(customer_id=A[0], adhoc_reason="Customer Requested", adhoc_notes="TEST-QA gps workflow"), auth)
    assert st in (200, 201), visitA
    n_visits_before = await con.fetchval("select count(*) from visits where employee_id=$1 and customer_id=$2", emp, uuid.UUID(A[0]))
    ci = dict(latitude=BASE_LAT, longitude=BASE_LON, accuracy_m=10.0, is_mock_location=False, captured_at=datetime.now(timezone.utc).isoformat())
    st, body, _ = qc.http("POST", f"/visits/{visitA['id']}/check-in", ci, auth)
    check("1 outlet without GPS: check-in rejected with OUTLET_LOCATION_NOT_CONFIGURED", st == 422 and err_code(body) == "OUTLET_LOCATION_NOT_CONFIGURED", f"{st} {err_code(body)}")

    # ------------------------------------------------------------------ 2. FIRST valid suggestion -> auto-accepted
    await qc.assert_local(con)
    st, p1 = upload_proof(auth, A[0], BASE_LAT, BASE_LON, acc=12.0)
    check("2 first suggestion accepted at once (201, APPROVED, INITIAL, auto_accepted, primary)",
          st == 201 and p1["status"] == "APPROVED" and p1["kind"] == "INITIAL" and p1["auto_accepted"] is True and p1["is_primary"] is True,
          f"{st} {p1.get('status') if isinstance(p1, dict) else p1}")
    ls, lat, lon = await outlet(A[0])
    check("2 coordinates saved on the outlet and it is marked GPS configured (VERIFIED)",
          ls == "VERIFIED" and abs(lat - BASE_LAT) < 1e-6 and abs(lon - BASE_LON) < 1e-6, f"{ls} {lat:.6f},{lon:.6f}")
    row = await con.fetchrow("select submitted_by_employee_id, reviewed_by, reviewed_at, received_at, auto_accepted, is_primary from outlet_proofs where id=$1", uuid.UUID(p1["id"]))
    check("2 evidence kept: employee, time and photo recorded; no admin involved",
          row["submitted_by_employee_id"] == emp and row["reviewed_by"] is None and row["reviewed_at"] is not None and row["auto_accepted"] and p1["size_bytes"] > 1000)
    n_after = await con.fetchval("select count(*) from visits where employee_id=$1 and customer_id=$2", emp, uuid.UUID(A[0]))
    v = await con.fetchrow("select status, check_in_at from visits where id=$1", uuid.UUID(visitA["id"]))
    check("2 registering the location did NOT create a visit or a check-in", n_after == n_visits_before and v["check_in_at"] is None and v["status"] == "PENDING")

    # ------------------------------------------------------------------ 3. normal check-in: GPS only, geofence
    ci_in = dict(latitude=offset(BASE_LAT, BASE_LON, 20)[0], longitude=BASE_LON, accuracy_m=15.0, is_mock_location=False, captured_at=datetime.now(timezone.utc).isoformat())
    await qc.assert_local(con)
    st, body, _ = qc.http("POST", f"/visits/{visitA['id']}/check-in", ci_in, auth)
    check("3 check-in inside the radius succeeds with GPS only (request has no photo field)", st == 200 and body["status"] == "IN_PROGRESS" and "photo" not in ci_in, f"{st}")

    # outside radius on outlet B (register B first, then try from ~500 m away)
    await qc.assert_local(con)
    st, pB = upload_proof(auth, B[0], BASE_LAT + 0.01, BASE_LON, acc=10.0)
    assert st == 201 and pB["auto_accepted"], pB
    st, visitB, _ = qc.http("POST", "/visits/ad-hoc", dict(customer_id=B[0], adhoc_reason="Customer Requested", adhoc_notes="TEST-QA gps outside"), auth)
    far = offset(BASE_LAT + 0.01, BASE_LON, 0, 500)
    st, body, _ = qc.http("POST", f"/visits/{visitB['id']}/check-in", dict(latitude=far[0], longitude=far[1], accuracy_m=10.0, is_mock_location=False, captured_at=datetime.now(timezone.utc).isoformat()), auth)
    check("3 check-in ~500 m away is rejected (outside the outlet radius)", st == 422 and err_code(body) == "GEO_VERIFICATION_FAILED", f"{st} {err_code(body)}")
    st, body, _ = qc.http("POST", f"/visits/{visitB['id']}/check-in", dict(latitude=BASE_LAT + 0.01, longitude=BASE_LON, accuracy_m=10.0, is_mock_location=True, captured_at=datetime.now(timezone.utc).isoformat()), auth)
    check("3 mock-location check-in is rejected", st == 422, f"{st} {err_code(body)}")

    # ------------------------------------------------------------------ 4. subsequent suggestion -> admin approval
    far_lat, far_lon = offset(BASE_LAT, BASE_LON, 300, 0)
    await qc.assert_local(con)
    st, p2 = upload_proof(auth, A[0], far_lat, far_lon, acc=10.0)
    check("4 a different location for an outlet that already has GPS becomes a PENDING change request",
          st == 201 and p2["kind"] == "CHANGE_REQUEST" and p2["status"] == "PENDING" and p2["auto_accepted"] is False, f"{st} {p2.get('kind') if isinstance(p2, dict) else p2}/{p2.get('status') if isinstance(p2, dict) else ''}")
    ls, lat, lon = await outlet(A[0])
    check("4 outlet coordinates are unchanged while the request is pending", abs(lat - BASE_LAT) < 1e-6 and abs(lon - BASE_LON) < 1e-6)
    async with AsyncSessionLocal() as s:
        admin = (await s.execute(select(User).where(User.role.in_([Role.SUPER_ADMIN, Role.ADMIN]), User.is_active.is_(True)).order_by(User.created_at))).scalars().first()
        await qc.assert_local(con)
        await outlet_proof_service.reject_outlet_proof(uuid.UUID(p2["id"]), "TEST-QA: storefront not matching", admin, s)
    ls, lat, lon = await outlet(A[0])
    prow = await con.fetchrow("select status, rejection_reason, is_primary from outlet_proofs where id=$1", uuid.UUID(p2["id"]))
    primary = await con.fetchval("select count(*) from outlet_proofs where customer_id=$1 and is_primary", uuid.UUID(A[0]))
    check("4 admin REJECT keeps the previous coordinates, keeps the rejected proof and its reason",
          abs(lat - BASE_LAT) < 1e-6 and prow["status"] == "REJECTED" and prow["rejection_reason"] and primary == 1)

    # approve path on outlet C
    await qc.assert_local(con)
    st, pC1 = upload_proof(auth, C[0], BASE_LAT - 0.01, BASE_LON, acc=10.0)
    assert st == 201 and pC1["auto_accepted"], pC1
    new_lat, new_lon = offset(BASE_LAT - 0.01, BASE_LON, 0, 250)
    st, pC2 = upload_proof(auth, C[0], new_lat, new_lon, acc=8.0)
    assert st == 201 and pC2["status"] == "PENDING", pC2
    async with AsyncSessionLocal() as s:
        admin = await s.get(User, admin.id)
        await qc.assert_local(con)
        await outlet_proof_service.approve_outlet_proof(uuid.UUID(pC2["id"]), admin, s)
    ls, lat, lon = await outlet(C[0])
    old = await con.fetchval("select status from outlet_proofs where id=$1", uuid.UUID(pC1["id"]))
    check("4 admin APPROVE updates the outlet coordinates and supersedes the old proof",
          abs(lat - new_lat) < 1e-6 and abs(lon - new_lon) < 1e-6 and old == "SUPERSEDED", f"{lat:.6f},{lon:.6f} old={old}")

    # ------------------------------------------------------------------ 5. concurrency: only ONE auto-acceptance
    await qc.assert_local(con)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(upload_proof, auth, D[0], BASE_LAT + 0.02 + i * 1e-6, BASE_LON, 10.0) for i in range(4)]
        outs = [f.result() for f in futs]
    n_auto = await con.fetchval("select count(*) from outlet_proofs where customer_id=$1 and auto_accepted", uuid.UUID(D[0]))
    n_primary = await con.fetchval("select count(*) from outlet_proofs where customer_id=$1 and is_primary", uuid.UUID(D[0]))
    check("5 four concurrent first registrations: exactly ONE auto-accepted and ONE primary pin", n_auto == 1 and n_primary == 1,
          f"auto={n_auto} primary={n_primary} codes={[o[0] for o in outs]}/{[err_code(o[1]) for o in outs]}")

    # ------------------------------------------------------------------ 6. unusable GPS is never accepted
    await qc.assert_local(con)
    cases = [
        ("accuracy 80 m", dict(acc=80.0), "OUTLET_PROOF_ACCURACY_TOO_LOW"),
        ("mock location", dict(mock=True), "OUTLET_PROOF_MOCK_LOCATION"),
        ("outside India (0,0)", dict(lat=0.0, lon=0.0), None),
        ("stale capture time", dict(captured=datetime(2026, 1, 1, tzinfo=timezone.utc)), None),
    ]
    for label, kw, code in cases:
        lat_, lon_ = kw.pop("lat", BASE_LAT + 0.03), kw.pop("lon", BASE_LON)
        st, body = upload_proof(auth, E[0], lat_, lon_, **kw)
        check(f"6 {label}: rejected, nothing accepted", st >= 400 and (code is None or err_code(body) == code), f"{st} {err_code(body)}")
    ls, lat, lon = await outlet(E[0])
    check("6 after the failed attempts the outlet still has no coordinates", lat is None and lon is None)
    body, ctype = multipart(dict(latitude=BASE_LAT, longitude=BASE_LON, accuracy_m=10, is_mock_location="false", captured_at=datetime.now(timezone.utc).isoformat(),
                                 idempotency_key=f"TEST-QA-{uuid.uuid4()}", customer_id=E[0]), b"")
    req = urllib.request.Request(qc.LOCAL_API + "/customers/outlet-proofs", method="POST", data=body)
    req.add_header("Content-Type", ctype); req.add_header("Authorization", auth["Authorization"])
    try:
        urllib.request.urlopen(req, timeout=30); code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    ls, lat, lon = await outlet(E[0])
    check("6 GPS without a real photo is rejected (empty photo)", code >= 400 and lat is None, f"{code}")

    # ------------------------------------------------------------------ 7. access control
    other = await con.fetchrow("""select c.id from customers c where c.outlet_code is not null and c.outlet_code not like 'TEST-QA-%'
        and c.location is null and c.territory_id is not null and c.tally_is_debtor is not false and c.merged_into_customer_id is null
        and not exists (select 1 from employee_customer_assignments x where x.customer_id=c.id and x.employee_id=$1)
        and c.territory_id <> (select territory_id from employees where id=$1) limit 1""", emp)
    if other:
        st, body = upload_proof(auth, str(other["id"]), BASE_LAT, BASE_LON, 10.0)
        still = await con.fetchval("select count(*) from outlet_proofs where customer_id=$1", other["id"])
        check("7 an outlet outside the employee's scope cannot be located (404) and nothing is written", st == 404 and still == 0, f"{st} {err_code(body)}")
    else:
        print("SKIP 7 no unrelated outlet without GPS in the local DB")

    # ------------------------------------------------------------------ idempotent replay returns the same proof
    k = f"TEST-QA-{uuid.uuid4()}"
    st, pF1 = upload_proof(auth, F[0], BASE_LAT + 0.04, BASE_LON, 10.0, key=k)
    st2, pF2 = upload_proof(auth, F[0], BASE_LAT + 0.04, BASE_LON, 10.0, key=k)
    check("8 replaying the same upload (retry after a network drop) returns the same proof, no duplicate",
          st == 201 and st2 in (200, 201) and pF1["id"] == pF2["id"] and await con.fetchval("select count(*) from outlet_proofs where customer_id=$1", uuid.UUID(F[0])) == 1)

    # remember what was created so the cleanup script removes it
    man = json.load(open(qc.MANIFEST, encoding="utf-8"))
    man.setdefault("gps_test_outlet_ids", [])
    man["gps_test_outlet_ids"] = [x[0] for x in (A, B, C, D, E, F)]
    man["visit_ids"] = list(dict.fromkeys(man["visit_ids"] + [visitA["id"], visitB["id"]]))
    json.dump(man, open(qc.MANIFEST, "w", encoding="utf-8"), indent=2)
    await con.close()
    print(f"\n{sum(results)}/{len(results)} checks passed", "- ALL PASSED" if all(results) else "- FAILURES")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
