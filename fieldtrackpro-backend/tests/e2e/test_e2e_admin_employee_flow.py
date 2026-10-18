"""
End-to-end Admin <-> Employee workflow against the REAL routers and REAL PostGIS DB.

Run against the isolated database only (fieldtrackpro_e2e):
    DATABASE_URL / MIGRATION_DATABASE_URL -> .../fieldtrackpro_e2e, ENABLE_SCHEDULER=false

Scenarios run in definition order and share state through module-level ``S``.
All data is synthetic and tagged (``__itest__`` emails/outlet names, ``__itest__E2E``
brands/agents) so teardown removes exactly what this module created. No app code is
modified; every assertion on persistence uses an independent psycopg2 connection.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from tests.integration.conftest import (  # noqa: E402
    DB_AVAILABLE,
    TEST_MARKER,
    VALID_JPEG,
    _purge_test_artifacts,
    db_cursor,
)

pytestmark = pytest.mark.skipif(not DB_AVAILABLE, reason="needs migrated PostGIS DB (fieldtrackpro_e2e)")

API = "/api/v1"
PW = "E2eFlow!Pass2026"
RUN = uuid.uuid4().hex[:8]

# Synthetic outlet coordinates (Kanpur area) and a point ~1.5 km away.
LAT, LNG = 26.4499, 80.3319
FAR_LAT, FAR_LNG = 26.4640, 80.3319

ADMIN_EMAIL = f"{TEST_MARKER}e2e_admin_{RUN}@fieldtrack.test"
EMP_A_EMAIL = f"{TEST_MARKER}e2e_empa_{RUN}@fieldtrack.test"
EMP_B_EMAIL = f"{TEST_MARKER}e2e_empb_{RUN}@fieldtrack.test"
EMP_C_EMAIL = f"{TEST_MARKER}e2e_empc_{RUN}@fieldtrack.test"
CUST_NAME = f"{TEST_MARKER}E2E Outlet {RUN}"
BRAND_A = f"{TEST_MARKER}E2E-Alpha-{RUN}"
BRAND_B = f"{TEST_MARKER}E2E-Beta-{RUN}"
AGENT_NAME = f"{TEST_MARKER}e2e-agent-{RUN}"

S: dict = {}


def now_iso(delta_s: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


def body(r) -> str:
    return f"{r.status_code} {r.text[:400]}"


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def q1(sql: str, params: tuple = ()):
    with db_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return dict(row) if row else None


def qall(sql: str, params: tuple = ()):
    with db_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def qcount(sql: str, params: tuple = ()) -> int:
    return int(q1(f"SELECT count(*) AS c FROM ({sql}) t", params)["c"])


async def login(client, email: str, password: str = PW):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


async def login_ok(client, email: str) -> dict:
    r = await login(client, email)
    assert r.status_code == 200, f"login {email}: {body(r)}"
    return r.json()


def checkin_payload(key: str | None, lat=LAT, lng=LNG, acc=10.0, mock=False) -> dict:
    return {
        "latitude": lat,
        "longitude": lng,
        "accuracy_m": acc,
        "is_mock_location": mock,
        "captured_at": now_iso(-5),
        "idempotency_key": key,
    }


# ---------------------------------------------------------------------------
# Infrastructure: client, engine disposal, setup/teardown
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://e2e") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine():
    yield
    from app.database import engine

    await engine.dispose()


def _teardown() -> None:
    like = f"{TEST_MARKER}E2E%"
    cust = "SELECT id FROM customers WHERE name LIKE %s"
    pay = f"SELECT id FROM payments WHERE customer_id IN ({cust})"
    jobs = f"SELECT id FROM tally_writeback_queue WHERE entity_id IN ({pay})"
    with db_cursor(privileged=True) as cur:
        steps = [
            (
                f"DELETE FROM tally_audit_logs WHERE agent_name LIKE %s OR writeback_job_id IN ({jobs}) "
                f"OR EXISTS (SELECT 1 FROM ({pay}) p WHERE tally_audit_logs.details::text LIKE '%%'||p.id::text||'%%')",
                (like, like, like),
            ),
            (f"DELETE FROM tally_writeback_queue WHERE entity_id IN ({pay})", (like,)),
            ("DELETE FROM sync_agents WHERE name LIKE %s", (like,)),
            (f"DELETE FROM payment_brand_allocations WHERE payment_id IN ({pay})", (like,)),
            (f"DELETE FROM payment_proofs WHERE payment_id IN ({pay})", (like,)),
            (f"DELETE FROM payments WHERE customer_id IN ({cust})", (like,)),
            (f"DELETE FROM geo_verification_logs WHERE visit_id IN (SELECT id FROM visits WHERE customer_id IN ({cust}))", (like,)),
            (f"DELETE FROM visit_media WHERE visit_id IN (SELECT id FROM visits WHERE customer_id IN ({cust}))", (like,)),
            (f"DELETE FROM customer_requirements WHERE customer_id IN ({cust})", (like,)),
            (f"DELETE FROM visits WHERE customer_id IN ({cust})", (like,)),
        ]
        for sql, params in steps:
            try:
                cur.execute(sql, params)
            except Exception as exc:  # pragma: no cover - best-effort, reported below
                print(f"[teardown warn] {sql[:60]}... -> {exc}")
    # Generic marker purge (users/employees/customers/refresh tokens/login attempts ...).
    _purge_test_artifacts()
    ids = [v for k, v in S.items() if k.endswith("_user_id") and v]
    with db_cursor(privileged=True) as cur:
        for sql, params in [
            ("DELETE FROM employees WHERE user_id = ANY(%s::uuid[])", (ids,)),
            ("DELETE FROM notifications WHERE user_id = ANY(%s::uuid[])", (ids,)),
            ("DELETE FROM user_devices WHERE user_id = ANY(%s::uuid[])", (ids,)),
            ("DELETE FROM refresh_tokens WHERE user_id = ANY(%s::uuid[])", (ids,)),
            ("DELETE FROM users WHERE id = ANY(%s::uuid[])", (ids,)),
            ("DELETE FROM brands WHERE name ILIKE %s", (like,)),
            ("DELETE FROM login_attempts WHERE identifier ILIKE %s", (f"{TEST_MARKER}e2e%",)),
        ]:
            try:
                cur.execute(sql, params)
            except Exception as exc:  # pragma: no cover
                print(f"[teardown warn] {sql[:60]}... -> {exc}")
    for key in S.get("proof_keys", []):
        path = os.path.abspath(os.path.join(os.getcwd(), "media_storage", key))
        if os.path.isfile(path):
            try:
                os.remove(path)
                os.rmdir(os.path.dirname(path))  # per-payment directory, now empty
            except OSError:
                pass


@pytest.fixture(scope="module", autouse=True)
def _world():
    _teardown()  # self-heal after an interrupted run
    admin_id = str(uuid.uuid4())
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'ADMIN',true,now(),now())",
            (admin_id, ADMIN_EMAIL, hash_password(PW)),
        )
    S["admin_user_id"] = admin_id
    yield
    _teardown()
    leftovers = {
        "users": qcount("SELECT 1 FROM users WHERE id = ANY(%s::uuid[])", ([v for k, v in S.items() if k.endswith("_user_id")],)),
        "customers": qcount("SELECT 1 FROM customers WHERE name LIKE %s", (f"{TEST_MARKER}E2E%",)),
        "brands": qcount("SELECT 1 FROM brands WHERE name ILIKE %s", (f"{TEST_MARKER}E2E%",)),
    }
    print(f"\n[cleanup] leftovers after teardown: {leftovers}")
    assert all(v == 0 for v in leftovers.values()), leftovers


async def _register_employee(client, admin_h, email: str, name: str, code: str) -> tuple[str, str]:
    r = await client.post(
        f"{API}/employees/register",
        headers=admin_h,
        json={
            "user": {"email": email, "password": PW, "role": "EMPLOYEE"},
            "full_name": name,
            "employee_code": code,
        },
    )
    assert r.status_code == 201, f"register {email}: {body(r)}"
    j = r.json()
    emp_id = j["id"]
    user_id = j.get("user_id") or (j.get("user") or {}).get("id")
    assert user_id, j
    return emp_id, user_id


async def _admin_headers(client) -> dict:
    if "admin_h" not in S or S.get("admin_h_ts", 0) < datetime.now().timestamp() - 600:
        S["admin_h"] = hdr((await login_ok(client, ADMIN_EMAIL))["access_token"])
        S["admin_h_ts"] = datetime.now().timestamp()
    return S["admin_h"]


# ---------------------------------------------------------------------------
# 1  Admin creates employee + outlet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_01_admin_login_creates_employee_and_outlet(client):
    r = await login(client, ADMIN_EMAIL)
    assert r.status_code == 200, body(r)
    assert r.json()["access_token"] and r.json()["refresh_token"]
    admin_h = await _admin_headers(client)

    me = await client.get(f"{API}/auth/me", headers=admin_h)
    assert me.status_code == 200 and me.json()["role"] == "ADMIN", body(me)

    for brand, key in ((BRAND_A, "brand_a"), (BRAND_B, "brand_b")):
        rb = await client.post(f"{API}/brands", headers=admin_h, json={"name": brand})
        assert rb.status_code == 201, body(rb)
        S[key] = rb.json()["name"]

    S["emp_a_id"], S["emp_a_user_id"] = await _register_employee(client, admin_h, EMP_A_EMAIL, "E2E Employee A", f"E2EA{RUN}")
    S["emp_b_id"], S["emp_b_user_id"] = await _register_employee(client, admin_h, EMP_B_EMAIL, "E2E Employee B", f"E2EB{RUN}")

    rc = await client.post(
        f"{API}/customers",
        headers=admin_h,
        json={
            "name": CUST_NAME,
            "contact_number": "+919999900123",
            "address": "1 Synthetic Road, Test City",
            "location": {"latitude": LAT, "longitude": LNG},
            "geofence_radius_m": 100,
            "outlet_code": f"E2E{RUN}".upper(),
        },
    )
    assert rc.status_code == 201, body(rc)
    S["customer_id"] = rc.json()["id"]

    # DB-level proof
    u = q1("SELECT role::text AS role, is_active FROM users WHERE id=%s", (S["emp_a_user_id"],))
    assert u == {"role": "EMPLOYEE", "is_active": True}
    e = q1("SELECT user_id::text AS uid, full_name FROM employees WHERE id=%s", (S["emp_a_id"],))
    assert e["uid"] == S["emp_a_user_id"]
    c = q1(
        "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng, geofence_radius_m FROM customers WHERE id=%s",
        (S["customer_id"],),
    )
    assert abs(c["lat"] - LAT) < 1e-6 and abs(c["lng"] - LNG) < 1e-6 and c["geofence_radius_m"] == 100
    print(f"\n[01] employee_a={S['emp_a_id']} customer={S['customer_id']} coords=({c['lat']},{c['lng']})")


# ---------------------------------------------------------------------------
# 2  Admin assigns a visit for today
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_02_admin_assigns_visit(client):
    admin_h = await _admin_headers(client)
    r = await client.post(
        f"{API}/visits",
        headers=admin_h,
        json={"customer_id": S["customer_id"], "employee_id": S["emp_a_id"], "scheduled_at": now_iso(60)},
    )
    assert r.status_code == 201, body(r)
    v = r.json()
    assert v["status"] == "PENDING" and v["employee_id"] == S["emp_a_id"] and v["customer_id"] == S["customer_id"]
    S["visit_id"] = v["id"]
    row = q1("SELECT status::text AS s, employee_id::text AS e FROM visits WHERE id=%s", (S["visit_id"],))
    assert row == {"s": "PENDING", "e": S["emp_a_id"]}
    print(f"\n[02] visit={S['visit_id']} status={v['status']}")


# ---------------------------------------------------------------------------
# 3  Employee sees visit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_03_employee_sees_visit(client):
    lg = await login_ok(client, EMP_A_EMAIL)
    S["emp_a_h"] = hdr(lg["access_token"])
    r = await client.get(f"{API}/visits/me/today", headers=S["emp_a_h"])
    assert r.status_code == 200, body(r)
    ids = [v["id"] for v in r.json()]
    assert S["visit_id"] in ids, ids
    assert r.headers.get("X-Total-Count") == str(len(ids))
    r2 = await client.get(f"{API}/visits", headers=S["emp_a_h"])
    assert r2.status_code == 200 and S["visit_id"] in [v["id"] for v in r2.json()], body(r2)
    r3 = await client.get(f"{API}/visits/{S['visit_id']}", headers=S["emp_a_h"])
    assert r3.status_code == 200 and r3.json()["id"] == S["visit_id"], body(r3)
    print(f"\n[03] /visits/me/today -> {len(ids)} visit(s), contains assigned visit")


# ---------------------------------------------------------------------------
# 4  Check-in: far rejected, mock rejected, correct accepted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_04_checkin_geofence_and_mock(client):
    h, vid = S["emp_a_h"], S["visit_id"]

    far = await client.post(f"{API}/visits/{vid}/check-in", headers=h, json=checkin_payload(f"far-{RUN}", FAR_LAT, FAR_LNG))
    print(f"\n[04] far check-in -> {body(far)}")
    assert far.status_code == 422 and "GEO_VERIFICATION_FAILED" in far.text and "exceeds allowed radius" in far.text

    mock = await client.post(f"{API}/visits/{vid}/check-in", headers=h, json=checkin_payload(f"mock-{RUN}", mock=True))
    print(f"[04] mock check-in -> {body(mock)}")
    assert mock.status_code == 422 and "GEO_VERIFICATION_FAILED" in mock.text and "Mock location" in mock.text
    assert q1("SELECT status::text AS s FROM visits WHERE id=%s", (vid,))["s"] == "PENDING"

    ok = await client.post(f"{API}/visits/{vid}/check-in", headers=h, json=checkin_payload(f"in-{RUN}"))
    print(f"[04] correct check-in -> {ok.status_code} status={ok.json().get('status')}")
    assert ok.status_code == 200, body(ok)
    assert ok.json()["status"] == "IN_PROGRESS" and ok.json()["check_in_at"]

    logs = qall(
        "SELECT verification_type::text AS t, is_valid, distance_from_customer_m AS d, idempotency_key AS k, failure_reason AS f "
        "FROM geo_verification_logs WHERE visit_id=%s ORDER BY attempted_at",
        (vid,),
    )
    print(f"[04] geo logs: {[(l['t'], l['is_valid'], round(float(l['d']), 1), l['k']) for l in logs]}")
    assert [l["is_valid"] for l in logs] == [False, False, True]
    assert float(logs[0]["d"]) > 1000 and float(logs[2]["d"]) < 5


# ---------------------------------------------------------------------------
# 5  Payments (cash + cheque w/ proof), idempotency, checkout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_05_payments_and_checkout(client):
    h, vid = S["emp_a_h"], S["visit_id"]
    today = date.today().isoformat()

    cash_body = {
        "visit_id": vid,
        "amount": "1000.00",
        "payment_method": "CASH",
        "payment_date": today,
        "allocations": [{"brand": S["brand_a"], "amount": "600.00"}, {"brand": S["brand_b"], "amount": "400.00"}],
        "idempotency_key": f"pay-cash-{RUN}",
    }
    r1 = await client.post(f"{API}/payments", headers=h, json=cash_body)
    assert r1.status_code == 201, body(r1)
    p1 = r1.json()
    assert p1["status"] == "PENDING_VERIFICATION" and len(p1["allocations"]) == 2
    S["cash_id"] = p1["id"]

    r1b = await client.post(f"{API}/payments", headers=h, json=cash_body)
    print(f"\n[05] duplicate cash submit -> {r1b.status_code} same_id={r1b.json().get('id') == S['cash_id']}")
    assert r1b.status_code in (200, 201) and r1b.json()["id"] == S["cash_id"]

    chq_body = {
        "visit_id": vid,
        "amount": "500.00",
        "payment_method": "CHEQUE",
        "payment_date": today,
        "cheque_number": f"{RUN[:6]}",
        "cheque_bank_name": "Synthetic Bank",
        "allocations": [{"brand": S["brand_a"], "amount": "500.00"}],
        "idempotency_key": f"pay-chq-{RUN}",
    }
    r2 = await client.post(f"{API}/payments", headers=h, json=chq_body)
    assert r2.status_code == 201, body(r2)
    S["cheque_id"] = r2.json()["id"]

    up = await client.post(
        f"{API}/payments/{S['cheque_id']}/proof", headers=h, files={"file": ("cheque.jpg", VALID_JPEG, "image/jpeg")}
    )
    assert up.status_code == 201, body(up)
    S["proof_id"] = up.json()["id"]
    S["proof_keys"] = [up.json()["storage_key"]]
    # same file again -> checksum de-dup returns same proof
    up2 = await client.post(
        f"{API}/payments/{S['cheque_id']}/proof", headers=h, files={"file": ("cheque.jpg", VALID_JPEG, "image/jpeg")}
    )
    assert up2.status_code == 201 and up2.json()["id"] == S["proof_id"], body(up2)
    dl = await client.get(f"{API}/payments/proofs/{S['proof_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.json()["download_url"], body(dl)

    out = await client.post(
        f"{API}/visits/{vid}/check-out", headers=h, json={**checkin_payload(f"out-{RUN}"), "notes": "e2e done"}
    )
    print(f"[05] checkout -> {out.status_code} status={out.json().get('status')}")
    assert out.status_code == 200 and out.json()["status"] == "COMPLETED", body(out)
    assert out.json()["check_out_at"]


# ---------------------------------------------------------------------------
# 6  Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_06_persistence_in_db(client):
    vid = S["visit_id"]
    v = q1("SELECT status::text AS s, check_in_at, check_out_at, notes, employee_id::text AS e FROM visits WHERE id=%s", (vid,))
    assert v["s"] == "COMPLETED" and v["check_in_at"] and v["check_out_at"] and v["notes"] == "e2e done"
    assert v["e"] == S["emp_a_id"]
    logs = qall("SELECT verification_type::text AS t, is_valid FROM geo_verification_logs WHERE visit_id=%s", (vid,))
    types = sorted((l["t"], l["is_valid"]) for l in logs)
    print(f"\n[06] geo logs: {types}")
    assert types == sorted([("CHECK_IN", False), ("CHECK_IN", False), ("CHECK_IN", True), ("CHECK_OUT", True)])
    pays = qall(
        "SELECT id::text AS id, amount, payment_method::text AS m, status::text AS s, idempotency_key AS k, visit_id::text AS v, "
        "employee_id::text AS e, customer_id::text AS c FROM payments WHERE visit_id=%s ORDER BY amount DESC",
        (vid,),
    )
    print(f"[06] payments: {[(p['m'], str(p['amount']), p['s']) for p in pays]}")
    assert len(pays) == 2 and all(p["s"] == "PENDING_VERIFICATION" and p["e"] == S["emp_a_id"] and p["c"] == S["customer_id"] for p in pays)
    alloc = qall("SELECT brand, allocated_amount FROM payment_brand_allocations WHERE payment_id=%s ORDER BY allocated_amount DESC", (S["cash_id"],))
    assert [(a["brand"], str(a["allocated_amount"])) for a in alloc] == [(S["brand_a"], "600.00"), (S["brand_b"], "400.00")]
    assert qcount("SELECT 1 FROM payment_proofs WHERE payment_id=%s", (S["cheque_id"],)) == 1


# ---------------------------------------------------------------------------
# 7  Admin visibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_07_admin_sees_everything(client):
    ah = await _admin_headers(client)
    vid = S["visit_id"]
    v = await client.get(f"{API}/visits/{vid}", headers=ah)
    assert v.status_code == 200 and v.json()["status"] == "COMPLETED", body(v)
    lst = await client.get(f"{API}/visits", headers=ah, params={"employee_id": S["emp_a_id"]})
    assert lst.status_code == 200 and vid in [x["id"] for x in lst.json()], body(lst)
    gl = await client.get(f"{API}/visits/{vid}/geo-logs", headers=ah)
    assert gl.status_code == 200 and len(gl.json()) == 4, body(gl)
    p = await client.get(f"{API}/payments/{S['cash_id']}", headers=ah)
    assert p.status_code == 200 and p.json()["status"] == "PENDING_VERIFICATION" and p.json()["employee_name"], body(p)
    pc = await client.get(f"{API}/payments/{S['cheque_id']}", headers=ah)
    assert pc.status_code == 200 and len(pc.json()["proofs"]) == 1, body(pc)
    qu = await client.get(f"{API}/payments/queue", headers=ah, params={"status": "PENDING_VERIFICATION"})
    assert qu.status_code == 200 and {S["cash_id"], S["cheque_id"]} <= {x["id"] for x in qu.json()}, body(qu)
    co = await client.get(f"{API}/collections/overview", headers=ah)
    assert co.status_code == 200, body(co)
    rep = await client.get(f"{API}/reports/collections", headers=ah)
    assert rep.status_code == 200, body(rep)
    emp = await client.get(f"{API}/employees/{S['emp_a_id']}/activity", headers=ah)
    assert emp.status_code == 200, body(emp)
    print(f"\n[07] admin: visit ok, {len(gl.json())} geo logs, queue has both payments, collections overview/report/activity 200")


# ---------------------------------------------------------------------------
# 8  Unverified payment => no Tally job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_08_unverified_has_no_tally_job(client):
    ah = await _admin_headers(client)
    pids = [S["cash_id"], S["cheque_id"]]
    n = qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id = ANY(%s::uuid[])", (pids,))
    assert n == 0, f"{n} jobs exist for unverified payments"

    ra = await client.post(f"{API}/integrations/tally/agents", headers=ah, json={"name": AGENT_NAME})
    assert ra.status_code == 201, body(ra)
    S["agent_id"], S["agent_key"] = ra.json()["agent"]["id"], ra.json()["api_key"]
    S["agent_h"] = {"X-Agent-Id": S["agent_id"], "X-Agent-Key": S["agent_key"]}
    pend = await client.get(f"{API}/integrations/tally/outbox/pending", headers=S["agent_h"])
    assert pend.status_code == 200, body(pend)
    assert not [j for j in pend.json() if j["entity_id"] in pids], pend.json()
    assert qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id = ANY(%s::uuid[])", (pids,)) == 0
    print(f"\n[08] jobs for unverified payments: 0; agent pending returned {len(pend.json())} job(s), none ours")


# ---------------------------------------------------------------------------
# 9  Verify -> exactly one job; double verify 409; reject after verify 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_09_verify_enqueues_exactly_one_job(client):
    ah = await _admin_headers(client)
    pid = S["cash_id"]
    r = await client.post(f"{API}/payments/{pid}/verify", headers=ah)
    assert r.status_code == 200 and r.json()["status"] == "VERIFIED", body(r)
    jobs = qall("SELECT id::text AS id, status AS s, idempotency_key AS k, entity_type AS t FROM tally_writeback_queue WHERE entity_id=%s", (pid,))
    print(f"\n[09] after verify jobs: {jobs}")
    assert len(jobs) == 1 and jobs[0]["k"] == f"fieldtrack_payment:{pid}" and jobs[0]["t"] == "PAYMENT"

    r2 = await client.post(f"{API}/payments/{pid}/verify", headers=ah)
    print(f"[09] second verify -> {body(r2)}")
    assert r2.status_code == 409 and "PAYMENT_ALREADY_REVIEWED" in r2.text
    assert qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id=%s", (pid,)) == 1

    r3 = await client.post(f"{API}/payments/{pid}/reject", headers=ah, json={"rejection_reason": "too late"})
    print(f"[09] reject after verify -> {body(r3)}")
    assert r3.status_code == 409
    assert q1("SELECT status::text AS s FROM payments WHERE id=%s", (pid,))["s"] == "VERIFIED"

    # Agent now sees exactly the verified payment's job, never the unverified cheque.
    pend = await client.get(f"{API}/integrations/tally/outbox/pending", headers=S["agent_h"])
    assert pend.status_code == 200, body(pend)
    mine = [j for j in pend.json() if j["entity_id"] in (S["cash_id"], S["cheque_id"])]
    assert [j["entity_id"] for j in mine] == [S["cash_id"]], pend.json()

    # Reject the cheque (pending): allowed, and still no job.
    rr = await client.post(f"{API}/payments/{S['cheque_id']}/reject", headers=ah, json={"rejection_reason": "synthetic reject"})
    assert rr.status_code == 200 and rr.json()["status"] == "REJECTED", body(rr)
    assert qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id=%s", (S["cheque_id"],)) == 0
    rv = await client.post(f"{API}/payments/{S['cheque_id']}/verify", headers=ah)
    assert rv.status_code == 409, body(rv)
    assert qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id=%s", (S["cheque_id"],)) == 0


# ---------------------------------------------------------------------------
# 10  Authorization boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_employee_scope_and_admin_endpoints_forbidden(client):
    ah = await _admin_headers(client)
    # employee A raises a requirement on the outlet (owned by A)
    rq = await client.post(
        f"{API}/customers/{S['customer_id']}/requirements",
        headers=S["emp_a_h"],
        json={"visit_id": S["visit_id"], "requirement_type": "Stock Replenishment", "product_details": "10 synthetic units", "quantity": 10},
    )
    assert rq.status_code == 201, body(rq)
    S["req_id"] = rq.json()["id"]

    bh = hdr((await login_ok(client, EMP_B_EMAIL))["access_token"])
    seen: dict[str, int] = {}
    for label, path in {
        "visit": f"/visits/{S['visit_id']}",
        "visit_geo_logs": f"/visits/{S['visit_id']}/geo-logs",
        "payment": f"/payments/{S['cash_id']}",
        "requirement": f"/requirements/{S['req_id']}",
        "customer": f"/customers/{S['customer_id']}",
        "customer_requirements": f"/customers/{S['customer_id']}/requirements",
        "customer_account": f"/customers/{S['customer_id']}/account",
    }.items():
        r = await client.get(f"{API}{path}", headers=bh)
        seen[label] = r.status_code
        # Foreign records must look non-existent (404, never 403).
        assert r.status_code == 404, f"{label}: {body(r)}"
    lst = await client.get(f"{API}/visits", headers=bh)
    assert S["visit_id"] not in [v["id"] for v in lst.json()]
    today = await client.get(f"{API}/visits/me/today", headers=bh)
    assert S["visit_id"] not in [v["id"] for v in today.json()]
    prox = await client.post(
        f"{API}/payments",
        headers=bh,
        json={"visit_id": S["visit_id"], "amount": "1.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
    )
    seen["create_payment_on_foreign_visit"] = prox.status_code
    assert prox.status_code == 404, body(prox)
    ci = await client.post(f"{API}/visits/{S['visit_id']}/check-in", headers=bh, json=checkin_payload(f"x-{RUN}"))
    seen["checkin_foreign_visit"] = ci.status_code
    assert ci.status_code == 404, body(ci)
    print(f"\n[10] employee B vs A's objects: {seen}")

    ah_forbidden = {}
    for label, method, path, kw in [
        ("GET /employees", "GET", "/employees", {}),
        ("POST /brands", "POST", "/brands", {"json": {"name": f"{TEST_MARKER}E2E-Nope-{RUN}"}}),
        ("GET /integrations/tally/agents", "GET", "/integrations/tally/agents", {}),
        ("GET /integrations/tally/status", "GET", "/integrations/tally/status", {}),
        ("GET /reports/collections", "GET", "/reports/collections", {}),
        ("GET /reports/overview", "GET", "/reports/overview", {}),
        ("GET /payments/queue", "GET", "/payments/queue", {}),
        ("POST /visits", "POST", "/visits", {"json": {"customer_id": S["customer_id"], "employee_id": S["emp_a_id"], "scheduled_at": now_iso(5)}}),
        ("POST /payments/{id}/verify", "POST", f"/payments/{S['cash_id']}/verify", {}),
        ("POST /employees/register", "POST", "/employees/register", {"json": {"user": {"email": f"{TEST_MARKER}e2e_x_{RUN}@fieldtrack.test", "password": PW}, "full_name": "X"}}),
    ]:
        r = await client.request(method, f"{API}{path}", headers=S["emp_a_h"], **kw)
        ah_forbidden[label] = r.status_code
        assert r.status_code == 403, f"{label}: {body(r)}"
    assert qcount("SELECT 1 FROM brands WHERE name ILIKE %s", (f"%E2E-Nope-{RUN}%",)) == 0
    print(f"[10] employee A vs admin endpoints: {ah_forbidden}")
    # sanity: admin still sees the requirement
    ar = await client.get(f"{API}/requirements/{S['req_id']}", headers=ah)
    assert ar.status_code == 200, body(ar)


# ---------------------------------------------------------------------------
# 11  Token behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_11_token_expiry_refresh_and_reuse(client, monkeypatch):
    for label, h in {
        "no token": {},
        "garbage": hdr("not.a.jwt"),
        "expired": hdr(create_access_token(S["emp_b_user_id"], "EMPLOYEE", timedelta(seconds=-120))),
        "wrong signature": hdr(
            __import__("jose").jwt.encode({"sub": S["emp_b_user_id"], "role": "EMPLOYEE", "exp": 9999999999}, "x" * 40, algorithm="HS256")
        ),
    }.items():
        r = await client.get(f"{API}/auth/me", headers=h)
        print(f"\n[11] {label} -> {r.status_code}")
        assert r.status_code == 401, f"{label}: {body(r)}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://e2e") as c2:
        lg = await login_ok(c2, EMP_B_EMAIL)
        r1 = lg["refresh_token"]
        rf = await c2.post(f"{API}/auth/refresh", json={"refresh_token": r1})
        assert rf.status_code == 200, body(rf)
        new = rf.json()
        assert new["refresh_token"] != r1 and new["access_token"]
        me = await c2.get(f"{API}/auth/me", headers=hdr(new["access_token"]))
        assert me.status_code == 200, body(me)

        # Replay of the already-rotated token INSIDE the grace window (two tabs / a client retry
        # racing the same token): benign duplicate -> 200 with another valid rotation, the
        # session family is NOT revoked.
        replay = await c2.post(f"{API}/auth/refresh", json={"refresh_token": r1})
        print(f"[11] replayed old refresh token within grace -> {body(replay)}")
        assert replay.status_code == 200, body(replay)
        assert replay.json()["refresh_token"] not in (r1, new["refresh_token"])
        still_ok = await c2.get(f"{API}/auth/me", headers=hdr(replay.json()["access_token"]))
        assert still_ok.status_code == 200
        assert qcount(
            "SELECT 1 FROM refresh_tokens WHERE user_id=%s AND revoked = false", (S["emp_b_user_id"],)
        ) >= 2  # same family, both descendants live

        # Replay AFTER the grace window (simulated by shrinking the window to 0 s): theft ->
        # 401 and the whole family is revoked, including the freshly issued tokens.
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "refresh_reuse_grace_seconds", 0)
        late = await c2.post(f"{API}/auth/refresh", json={"refresh_token": r1})
        print(f"[11] replayed old refresh token after grace -> {body(late)}")
        assert late.status_code == 401

        after = await c2.post(f"{API}/auth/refresh", json={"refresh_token": new["refresh_token"]})
        print(f"[11] legit newest token after replay -> {after.status_code}")
        assert after.status_code == 401
        live = qcount("SELECT 1 FROM refresh_tokens WHERE user_id=%s AND revoked = false", (S["emp_b_user_id"],))
        assert live == 0, f"{live} refresh tokens still live after reuse detection"

        # logout path revokes
        lg2 = await login_ok(c2, EMP_B_EMAIL)
        assert (await c2.post(f"{API}/auth/logout", json={"refresh_token": lg2["refresh_token"]})).status_code == 204
        assert (await c2.post(f"{API}/auth/refresh", json={"refresh_token": lg2["refresh_token"]})).status_code == 401


# ---------------------------------------------------------------------------
# 12  Offline-sync replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_12_offline_replay_is_idempotent(client):
    h = hdr((await login_ok(client, EMP_A_EMAIL))["access_token"])
    vid = S["visit_id"]
    before = {
        "geo": qcount("SELECT 1 FROM geo_verification_logs WHERE visit_id=%s", (vid,)),
        "pay": qcount("SELECT 1 FROM payments WHERE visit_id=%s", (vid,)),
        "jobs": qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id = ANY(%s::uuid[])", ([S["cash_id"], S["cheque_id"]],)),
    }
    status_before = q1("SELECT status::text AS s, check_in_at, check_out_at FROM visits WHERE id=%s", (vid,))

    ci = await client.post(f"{API}/visits/{vid}/check-in", headers=h, json=checkin_payload(f"in-{RUN}"))
    print(f"\n[12] replay check-in -> {ci.status_code} status={ci.json().get('status')}")
    assert ci.status_code == 200 and ci.json()["id"] == vid

    far = await client.post(f"{API}/visits/{vid}/check-in", headers=h, json=checkin_payload(f"far-{RUN}", FAR_LAT, FAR_LNG))
    assert far.status_code == 422 and "GEO_VERIFICATION_FAILED" in far.text  # replays the original rejection

    pay = await client.post(
        f"{API}/payments",
        headers=h,
        json={
            "visit_id": vid,
            "amount": "1000.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "allocations": [{"brand": S["brand_a"], "amount": "600.00"}, {"brand": S["brand_b"], "amount": "400.00"}],
            "idempotency_key": f"pay-cash-{RUN}",
        },
    )
    print(f"[12] replay cash payment -> {pay.status_code} status={pay.json().get('status')} same_id={pay.json().get('id') == S['cash_id']}")
    assert pay.status_code in (200, 201) and pay.json()["id"] == S["cash_id"]

    out = await client.post(f"{API}/visits/{vid}/check-out", headers=h, json={**checkin_payload(f"out-{RUN}"), "notes": "e2e done"})
    print(f"[12] replay checkout -> {out.status_code} status={out.json().get('status')}")
    assert out.status_code == 200 and out.json()["status"] == "COMPLETED"

    after = {
        "geo": qcount("SELECT 1 FROM geo_verification_logs WHERE visit_id=%s", (vid,)),
        "pay": qcount("SELECT 1 FROM payments WHERE visit_id=%s", (vid,)),
        "jobs": qcount("SELECT 1 FROM tally_writeback_queue WHERE entity_id = ANY(%s::uuid[])", ([S["cash_id"], S["cheque_id"]],)),
    }
    status_after = q1("SELECT status::text AS s, check_in_at, check_out_at FROM visits WHERE id=%s", (vid,))
    print(f"[12] counts before={before} after={after}")
    assert before == after and status_before == status_after


# ---------------------------------------------------------------------------
# 13  Account deletion (DELETE /auth/me)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_13_account_deletion_retains_business_records(client):
    ah = await _admin_headers(client)
    emp_id, user_id = await _register_employee(client, ah, EMP_C_EMAIL, "E2E Throwaway C", f"E2EC{RUN}")
    S["emp_c_id"], S["emp_c_user_id"] = emp_id, user_id
    v = await client.post(
        f"{API}/visits", headers=ah, json={"customer_id": S["customer_id"], "employee_id": emp_id, "scheduled_at": now_iso(30)}
    )
    assert v.status_code == 201, body(v)
    cvid = v.json()["id"]
    lg = await login_ok(client, EMP_C_EMAIL)
    ch = hdr(lg["access_token"])
    assert (await client.post(f"{API}/visits/{cvid}/check-in", headers=ch, json=checkin_payload(f"c-in-{RUN}"))).status_code == 200
    pr = await client.post(
        f"{API}/payments",
        headers=ch,
        json={"visit_id": cvid, "amount": "250.00", "payment_method": "CASH", "payment_date": date.today().isoformat(), "idempotency_key": f"c-pay-{RUN}"},
    )
    assert pr.status_code == 201, body(pr)
    cpid = pr.json()["id"]

    d = await client.request("DELETE", f"{API}/auth/me", headers=ch, json={"password": PW, "reason": "e2e throwaway"})
    print(f"\n[13] DELETE /auth/me -> {body(d)}")
    assert d.status_code == 200 and d.json()["status"] == "DELETED"

    relog = await login(client, EMP_C_EMAIL)
    print(f"[13] login after deletion -> {body(relog)}")
    assert relog.status_code in (401, 403)
    old = await client.get(f"{API}/auth/me", headers=ch)
    print(f"[13] old access token after deletion -> {old.status_code}")
    assert old.status_code in (401, 403)
    rf = await client.post(f"{API}/auth/refresh", json={"refresh_token": lg["refresh_token"]})
    assert rf.status_code in (401, 403), body(rf)

    u = q1("SELECT is_active, email FROM users WHERE id=%s", (user_id,))
    assert u["is_active"] is False and EMP_C_EMAIL not in u["email"]
    assert q1("SELECT full_name FROM employees WHERE id=%s", (emp_id,))["full_name"] == "Deleted User"
    assert qcount("SELECT 1 FROM visits WHERE id=%s", (cvid,)) == 1
    assert qcount("SELECT 1 FROM payments WHERE id=%s", (cpid,)) == 1
    assert qcount("SELECT 1 FROM geo_verification_logs WHERE visit_id=%s", (cvid,)) == 1
    gv = await client.get(f"{API}/visits/{cvid}", headers=ah)
    gp = await client.get(f"{API}/payments/{cpid}", headers=ah)
    assert gv.status_code == 200 and gp.status_code == 200, (body(gv), body(gp))
    print("[13] user deactivated/anonymised; visit, geo log and payment retained and still visible to admin")
