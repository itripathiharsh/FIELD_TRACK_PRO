"""
Integration: object-level access scoping (A1 hardening).

Covers customers scoping + ad-hoc search redaction, location proposals,
requirements IDOR / edit rules, media cross-attachment, admin-only brands,
organization redaction, orders scoping and self-service account deletion.
All data is synthetic and tagged with TEST_MARKER.
"""
from __future__ import annotations

import asyncio
import random
import uuid

import pytest
import pytest_asyncio

from app.core.security import hash_password
from tests.integration.conftest import (
    TEST_MARKER,
    TEST_PASSWORD,
    VALID_JPEG,
    auth_headers,
    create_visit,
    db_cursor,
    iso_in,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def _make_customer(client, admin_headers, created_customers, label, phone=None):
    name = f"{TEST_MARKER}{label}{uuid.uuid4().hex[:6]}"
    phone = phone or f"+9198{random.randint(10_000_000, 99_999_999)}"
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": name,
            "contact_number": phone,
            "contact_person": "Synthetic Person",
            "gst_number": "29ABCDE1234F1Z5",
            "address": f"{label} Synthetic Road",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    created_customers.append(resp.json()["id"])
    return resp.json()


@pytest_asyncio.fixture
async def world(client, admin_headers, seeded_world, created_customers, created_visits):
    """cust_a: visited by employee A; cust_b: unrelated to A; B has its own visit on cust_a."""
    cust_a = await _make_customer(client, admin_headers, created_customers, "ScopeA")
    cust_b = await _make_customer(client, admin_headers, created_customers, "ScopeB")
    visit_a = await create_visit(
        client, admin_headers, cust_a["id"], seeded_world["employee_id"], created_visits, iso_in(3)
    )
    visit_b = await create_visit(
        client, admin_headers, cust_a["id"], seeded_world["other_employee_id"], created_visits, iso_in(6)
    )
    return {"cust_a": cust_a, "cust_b": cust_b, "visit_a": visit_a, "visit_b": visit_b}


# ---------------------------------------------------------------- customers

async def test_employee_list_contains_only_scoped_customers(client, employee_headers, world):
    resp = await client.get("/api/v1/customers?limit=500", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    ids = {c["id"] for c in resp.json()}
    assert world["cust_a"]["id"] in ids
    assert world["cust_b"]["id"] not in ids


async def test_employee_get_unassigned_customer_forbidden(client, employee_headers, world):
    ok = await client.get(f"/api/v1/customers/{world['cust_a']['id']}", headers=employee_headers)
    assert ok.status_code == 200
    bad = await client.get(f"/api/v1/customers/{world['cust_b']['id']}", headers=employee_headers)
    assert bad.status_code == 404


async def test_employee_account_invoices_orders_scoped(client, employee_headers, world):
    for suffix in ("account", "invoices", "orders"):
        r = await client.get(f"/api/v1/customers/{world['cust_b']['id']}/{suffix}", headers=employee_headers)
        assert r.status_code == 404, suffix


async def test_map_locations_scoped_for_employee(client, employee_headers, admin_headers, world):
    emp = await client.get("/api/v1/customers/map-locations", headers=employee_headers)
    assert emp.status_code == 200
    emp_ids = {c["id"] for c in emp.json()}
    assert world["cust_a"]["id"] in emp_ids and world["cust_b"]["id"] not in emp_ids
    adm = await client.get("/api/v1/customers/map-locations", headers=admin_headers)
    assert world["cust_b"]["id"] in {c["id"] for c in adm.json()}


async def test_adhoc_search_is_redacted_and_not_contact_searchable(client, employee_headers, world):
    cust_b = world["cust_b"]
    token = cust_b["name"][len(TEST_MARKER):]
    resp = await client.get(f"/api/v1/customers?search={token}", headers=employee_headers)
    assert resp.status_code == 200
    hit = next(c for c in resp.json() if c["id"] == cust_b["id"])
    assert hit["contact_number"] == ""
    assert hit["contact_person"] is None
    assert hit["gst_number"] is None
    assert hit["brands"] == []
    assert hit["location"] is not None  # coordinates stay: needed to pick the outlet
    a_token = world["cust_a"]["name"][len(TEST_MARKER):]
    resp_a = await client.get(f"/api/v1/customers?search={a_token}", headers=employee_headers)
    hit_a = next(c for c in resp_a.json() if c["id"] == world["cust_a"]["id"])
    assert hit_a["contact_number"] == world["cust_a"]["contact_number"]
    by_phone = await client.get(
        f"/api/v1/customers?search={cust_b['contact_number'].replace('+', '')}", headers=employee_headers
    )
    assert cust_b["id"] not in {c["id"] for c in by_phone.json()}


async def test_adhoc_search_requires_min_length_for_directory(client, employee_headers, world):
    resp = await client.get("/api/v1/customers?search=Sc", headers=employee_headers)
    assert resp.status_code == 200
    assert world["cust_b"]["id"] not in {c["id"] for c in resp.json()}


async def test_unlinked_employee_gets_empty_directory(client, world):
    email = f"{TEST_MARKER}unlinked@fieldtrack.test"
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
            (str(uuid.uuid4()), email, hash_password(TEST_PASSWORD)),
        )
    try:
        headers = await auth_headers(client, email, TEST_PASSWORD)
        resp = await client.get("/api/v1/customers", headers=headers)
        assert resp.status_code == 200 and resp.json() == []
        assert resp.headers["X-Total-Count"] == "0"
        assert (await client.get("/api/v1/customers?search=Scope", headers=headers)).json() == []
        assert (await client.get("/api/v1/customers/map-locations", headers=headers)).json() == []
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))


# ------------------------------------------------------- location proposals

async def test_location_proposals_scoped_to_submitter(
    client, admin_headers, employee_headers, other_employee_headers, world
):
    cust_a = world["cust_a"]["id"]
    created = await client.post(
        f"/api/v1/customers/{cust_a}/location-proposals",
        json={"proposed_latitude": 12.98, "proposed_longitude": 77.6, "gps_accuracy_meters": 5},
        headers=employee_headers,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    other_list = await client.get("/api/v1/location-proposals?status=ALL", headers=other_employee_headers)
    assert pid not in {p["id"] for p in other_list.json()}
    other_cust = await client.get(f"/api/v1/customers/{cust_a}/location-proposals", headers=other_employee_headers)
    assert other_cust.status_code == 200 and pid not in {p["id"] for p in other_cust.json()}

    own = await client.get("/api/v1/location-proposals?status=ALL", headers=employee_headers)
    assert pid in {p["id"] for p in own.json()}
    adm = await client.get("/api/v1/location-proposals?status=ALL", headers=admin_headers)
    assert pid in {p["id"] for p in adm.json()}

    cust_b = world["cust_b"]["id"]
    assert (
        await client.post(
            f"/api/v1/customers/{cust_b}/location-proposals",
            json={"proposed_latitude": 12.98, "proposed_longitude": 77.6},
            headers=employee_headers,
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/customers/{cust_b}/location-proposals", headers=employee_headers)
    ).status_code == 404


# ------------------------------------------------------------- requirements

async def _create_req(client, headers, customer_id, **extra):
    payload = {"product_details": "Synthetic fans", "quantity": 2, "expected_value": 1000.0, **extra}
    return await client.post(f"/api/v1/customers/{customer_id}/requirements", json=payload, headers=headers)


async def test_requirement_idor_read_paths(client, employee_headers, other_employee_headers, admin_headers, world):
    cust_a = world["cust_a"]["id"]
    r = await _create_req(client, employee_headers, cust_a, visit_id=world["visit_a"])
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    assert (await client.get(f"/api/v1/requirements/{rid}", headers=other_employee_headers)).status_code == 404
    listed = await client.get("/api/v1/requirements", headers=other_employee_headers)
    assert rid not in {x["id"] for x in listed.json()}
    peek = await client.get(
        "/api/v1/requirements", params={"employee_id": str(uuid.uuid4())}, headers=other_employee_headers
    )
    assert rid not in {x["id"] for x in peek.json()}
    # B has scope on cust_a (own visit) but only ever sees requirements B created.
    per_customer = await client.get(f"/api/v1/customers/{cust_a}/requirements", headers=other_employee_headers)
    assert per_customer.status_code == 200 and rid not in {x["id"] for x in per_customer.json()}
    own = await client.get(f"/api/v1/customers/{cust_a}/requirements", headers=employee_headers)
    assert rid in {x["id"] for x in own.json()}
    no_scope = await client.get(
        f"/api/v1/customers/{world['cust_b']['id']}/requirements", headers=employee_headers
    )
    assert no_scope.status_code == 404
    adm = await client.get(f"/api/v1/customers/{cust_a}/requirements", headers=admin_headers)
    assert rid in {x["id"] for x in adm.json()}
    vis = await client.get(f"/api/v1/visits/{world['visit_a']}/requirements", headers=employee_headers)
    assert rid in {x["id"] for x in vis.json()}


async def test_requirement_patch_rules(client, employee_headers, other_employee_headers, admin_headers, world):
    cust_a = world["cust_a"]["id"]
    rid = (await _create_req(client, employee_headers, cust_a)).json()["id"]

    other = await client.patch(f"/api/v1/requirements/{rid}", json={"notes": "hax"}, headers=other_employee_headers)
    assert other.status_code == 404
    ok = await client.patch(f"/api/v1/requirements/{rid}", json={"notes": "mine"}, headers=employee_headers)
    assert ok.status_code == 200 and ok.json()["notes"] == "mine"
    forbidden = await client.patch(
        f"/api/v1/requirements/{rid}", json={"status": "APPROVED"}, headers=employee_headers
    )
    assert forbidden.status_code == 403
    assert (await client.get(f"/api/v1/requirements/{rid}", headers=admin_headers)).json()["status"] != "APPROVED"
    dec = await client.post(
        f"/api/v1/requirements/{rid}/decision", json={"action": "APPROVE"}, headers=admin_headers
    )
    assert dec.status_code == 200
    locked = await client.patch(f"/api/v1/requirements/{rid}", json={"notes": "late"}, headers=employee_headers)
    assert locked.status_code == 409
    adm = await client.patch(
        f"/api/v1/requirements/{rid}", json={"status": "PENDING", "notes": "admin"}, headers=admin_headers
    )
    assert adm.status_code == 200 and adm.json()["status"] == "PENDING"


async def test_requirement_photo_upload_owner_only(client, employee_headers, other_employee_headers, world):
    rid = (await _create_req(client, employee_headers, world["cust_a"]["id"])).json()["id"]
    r = await client.post(
        f"/api/v1/requirements/{rid}/photo",
        files={"file": ("p.jpg", VALID_JPEG, "image/jpeg")},
        headers=other_employee_headers,
    )
    assert r.status_code == 404


async def test_requirement_create_visit_ownership(client, employee_headers, world):
    cust_a = world["cust_a"]["id"]
    r1 = await _create_req(client, employee_headers, cust_a, visit_id=world["visit_b"])
    assert r1.status_code == 404
    r2 = await client.post(
        "/api/v1/requirements",
        json={"visit_id": world["visit_b"], "product_details": "x", "quantity": 1},
        headers=employee_headers,
    )
    assert r2.status_code == 404
    r3 = await client.post(
        "/api/v1/requirements",
        json={"visit_id": world["visit_a"], "product_details": "x", "quantity": 1},
        headers=employee_headers,
    )
    assert r3.status_code == 201 and r3.json()["customer_id"] == cust_a
    r4 = await _create_req(client, employee_headers, world["cust_b"]["id"], visit_id=world["visit_a"])
    assert r4.status_code == 422


async def test_requirement_without_visit_needs_outlet_scope(client, employee_headers, world):
    r = await _create_req(client, employee_headers, world["cust_b"]["id"])
    assert r.status_code == 404


async def test_requirement_photo_media_cannot_be_cross_attached(
    client, employee_headers, other_employee_headers, world, created_media
):
    cust_a = world["cust_a"]["id"]
    up_b = await client.post(
        f"/api/v1/visits/{world['visit_b']}/media",
        files={"file": ("b.jpg", VALID_JPEG, "image/jpeg")},
        headers=other_employee_headers,
    )
    assert up_b.status_code == 201, up_b.text
    media_b = up_b.json()["id"]
    created_media.append(media_b)

    bad = await _create_req(client, employee_headers, cust_a, visit_id=world["visit_a"], photo_media_id=media_b)
    assert bad.status_code == 404
    bad2 = await _create_req(client, employee_headers, cust_a, photo_media_id=media_b)
    assert bad2.status_code == 404
    missing = await _create_req(
        client, employee_headers, cust_a, visit_id=world["visit_a"], photo_media_id=str(uuid.uuid4())
    )
    assert missing.status_code == 404

    up_a = await client.post(
        f"/api/v1/visits/{world['visit_a']}/media",
        files={"file": ("a.jpg", VALID_JPEG + b"\x01", "image/jpeg")},
        headers=employee_headers,
    )
    assert up_a.status_code == 201, up_a.text
    media_a = up_a.json()["id"]
    created_media.append(media_a)
    good = await _create_req(client, employee_headers, cust_a, visit_id=world["visit_a"], photo_media_id=media_a)
    assert good.status_code == 201, good.text
    assert good.json()["photo_media_id"] == media_a


# -------------------------------------------------------------------- media

async def test_employee_cannot_fetch_other_employees_media(
    client, employee_headers, other_employee_headers, world, created_media
):
    up = await client.post(
        f"/api/v1/visits/{world['visit_b']}/media",
        files={"file": ("b.jpg", VALID_JPEG + b"\x02", "image/jpeg")},
        headers=other_employee_headers,
    )
    assert up.status_code == 201, up.text
    mid = up.json()["id"]
    created_media.append(mid)
    assert (await client.get(f"/api/v1/media/{mid}", headers=employee_headers)).status_code == 404
    assert (await client.get(f"/api/v1/media/{mid}/download", headers=employee_headers)).status_code == 404
    assert (await client.get(f"/api/v1/visits/{world['visit_b']}/media", headers=employee_headers)).status_code == 404
    assert (await client.delete(f"/api/v1/media/{mid}", headers=employee_headers)).status_code == 404
    assert (await client.get(f"/api/v1/media/{mid}/download", headers=other_employee_headers)).status_code == 200
    sigs = await client.get(f"/api/v1/visits/{world['visit_b']}/signatures", headers=employee_headers)
    assert sigs.status_code == 404


# ------------------------------------------------- brands / org / orders

async def test_brands_write_is_admin_only(client, admin_headers, employee_headers):
    name = f"{TEST_MARKER}Brand{uuid.uuid4().hex[:5]}"
    assert (await client.post("/api/v1/brands", json={"name": name}, headers=employee_headers)).status_code == 403
    assert (await client.get("/api/v1/brands", headers=employee_headers)).status_code == 200
    created = await client.post("/api/v1/brands", json={"name": name}, headers=admin_headers)
    assert created.status_code == 201, created.text
    bid = created.json()["id"]
    try:
        emp = await client.patch(f"/api/v1/brands/{bid}", json={"is_active": False}, headers=employee_headers)
        assert emp.status_code == 403
        adm = await client.patch(f"/api/v1/brands/{bid}", json={"is_active": False}, headers=admin_headers)
        assert adm.status_code == 200
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM brands WHERE id = %s", (bid,))


async def test_organization_redacted_for_employee(client, admin_headers, employee_headers):
    emp = (await client.get("/api/v1/organization", headers=employee_headers)).json()
    assert "organization_name" in emp
    for key in ("gstin", "contact_email", "contact_phone", "total_employees", "total_customers"):
        assert key not in emp
    adm = (await client.get("/api/v1/organization", headers=admin_headers)).json()
    for key in ("gstin", "contact_email", "contact_phone"):
        assert key in adm


async def test_orders_listing_scoped_to_employee(
    client, employee_headers, other_employee_headers, admin_headers, world
):
    oid = str(uuid.uuid4())
    with db_cursor(privileged=True) as cur:
        cur.execute("SELECT id FROM employees WHERE employee_code = %s", (f"{TEST_MARKER}EMP1",))
        emp_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM users WHERE email = %s", (f"{TEST_MARKER}admin@fieldtrack.test",))
        admin_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO orders (id,order_number,customer_id,employee_id,total_amount,status,created_by,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,100,'PENDING_TALLY',%s,now(),now())",
            (oid, f"{TEST_MARKER}SO-{uuid.uuid4().hex[:6]}", world["cust_a"]["id"], emp_id, admin_id),
        )
    try:
        mine = await client.get("/api/v1/orders", headers=employee_headers)
        assert oid in {o["id"] for o in mine.json()}
        theirs = await client.get("/api/v1/orders", headers=other_employee_headers)
        assert oid not in {o["id"] for o in theirs.json()}
        assert (await client.get(f"/api/v1/orders/{oid}", headers=other_employee_headers)).status_code == 404
        assert (await client.get(f"/api/v1/orders/{oid}", headers=employee_headers)).status_code == 200
        assert (await client.get(f"/api/v1/orders/{oid}", headers=admin_headers)).status_code == 200
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM orders WHERE id = %s", (oid,))


# --------------------------------------------------------- account deletion

async def _make_user(role, with_employee):
    uid, eid = str(uuid.uuid4()), str(uuid.uuid4())
    email = f"{TEST_MARKER}del{uuid.uuid4().hex[:6]}@fieldtrack.test"
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,mobile_number,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,true,now(),now())",
            (uid, email, f"+9177{random.randint(10_000_000, 99_999_999)}", hash_password(TEST_PASSWORD), role),
        )
        if with_employee:
            cur.execute(
                "INSERT INTO employees (id,user_id,full_name,employee_code,address,aadhaar_no,pan_no,father_name,created_at) "
                "VALUES (%s,%s,'Delete Me',%s,'1 Private Lane','111122223333','ABCDE1234F','Father Name',now())",
                (eid, uid, f"{TEST_MARKER}DEL{uuid.uuid4().hex[:5]}"),
            )
    return uid, eid, email


def _cleanup_user(uid):
    with db_cursor(privileged=True) as cur:
        cur.execute(
            "DELETE FROM geo_verification_logs WHERE visit_id IN ("
            "SELECT v.id FROM visits v JOIN employees e ON e.id=v.employee_id WHERE e.user_id=%s)",
            (uid,),
        )
        cur.execute("DELETE FROM visits WHERE employee_id IN (SELECT id FROM employees WHERE user_id=%s)", (uid,))
        cur.execute("DELETE FROM employees WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))


async def test_employee_account_deletion_preserves_visits_and_anonymises(client, admin_headers, world, db):
    uid, eid, email = await _make_user("EMPLOYEE", True)
    try:
        headers = await auth_headers(client, email, TEST_PASSWORD)
        visit_id = await create_visit(client, admin_headers, world["cust_a"]["id"], eid, [], iso_in(9))
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO user_devices (id,user_id,fcm_token,device_type,is_active,created_at,updated_at) "
                "VALUES (%s,%s,%s,'ANDROID',true,now(),now())",
                (str(uuid.uuid4()), uid, f"tok-{uuid.uuid4().hex}"),
            )

        resp = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD, "reason": "leaving"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "DELETED" and resp.json()["message"]

        user = db.fetch_one("SELECT email, mobile_number, is_active FROM users WHERE id=%s", (uid,))
        assert user["is_active"] is False and user["mobile_number"] is None and user["email"] != email
        emp = db.fetch_one(
            "SELECT full_name, address, aadhaar_no, pan_no, father_name FROM employees WHERE id=%s", (eid,)
        )
        assert emp["full_name"] == "Deleted User"
        assert emp["address"] is None and emp["aadhaar_no"] is None
        assert emp["pan_no"] is None and emp["father_name"] is None
        assert db.count("refresh_tokens", "user_id=%s AND revoked=false", (uid,)) == 0
        assert db.count("user_devices", "user_id=%s", (uid,)) == 0
        assert db.count("visits", "id=%s", (visit_id,)) == 1  # retained
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
        relogin = await client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert relogin.status_code in (401, 403)
    finally:
        _cleanup_user(uid)


async def test_last_active_admin_cannot_delete_but_can_once_another_exists(client, seeded_world):
    # Park every other active admin so exactly one remains.
    with db_cursor(privileged=True) as cur:
        cur.execute("SELECT id FROM users WHERE role='ADMIN' AND is_active=true")
        parked = [r["id"] for r in cur.fetchall()]
        if parked:
            cur.execute("UPDATE users SET is_active=false WHERE id = ANY(%s::uuid[])", (parked,))
    uid1, _, email1 = await _make_user("ADMIN", False)
    uid2 = None
    try:
        h1 = await auth_headers(client, email1, TEST_PASSWORD)
        refused = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD}, headers=h1
        )
        assert refused.status_code == 409, refused.text
        with db_cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE id=%s", (uid1,))
            assert cur.fetchone()["is_active"] is True
        uid2, _, _ = await _make_user("ADMIN", False)
        ok = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD}, headers=h1
        )
        assert ok.status_code == 200 and ok.json()["status"] == "DELETED"
    finally:
        with db_cursor(privileged=True) as cur:
            if parked:
                cur.execute("UPDATE users SET is_active=true WHERE id = ANY(%s::uuid[])", (parked,))
        for u in (uid1, uid2):
            if u:
                _cleanup_user(u)


async def test_delete_account_requires_authentication(client):
    assert (await client.delete("/api/v1/auth/me")).status_code in (401, 403)


async def test_delete_account_wrong_password_rejected(client):
    """A destructive, irreversible action from an already-logged-in session must re-verify the password."""
    uid, _, email = await _make_user("EMPLOYEE", False)
    try:
        headers = await auth_headers(client, email, TEST_PASSWORD)
        resp = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": "definitely-wrong"}, headers=headers
        )
        assert resp.status_code == 401, resp.text
        with db_cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE id=%s", (uid,))
            assert cur.fetchone()["is_active"] is True
    finally:
        _cleanup_user(uid)


async def test_concurrent_admin_self_deletions_never_leave_zero_admins(client, seeded_world):
    """
    Two admins deleting themselves at the same moment must not both succeed -
    exactly one must win and leave at least one active admin behind, closing
    the TOCTOU race where each only saw the OTHER still active and both passed.
    """
    with db_cursor(privileged=True) as cur:
        cur.execute("SELECT id FROM users WHERE role='ADMIN' AND is_active=true")
        parked = [r["id"] for r in cur.fetchall()]
        if parked:
            cur.execute("UPDATE users SET is_active=false WHERE id = ANY(%s::uuid[])", (parked,))
    uid1, _, email1 = await _make_user("ADMIN", False)
    uid2, _, email2 = await _make_user("ADMIN", False)
    try:
        h1 = await auth_headers(client, email1, TEST_PASSWORD)
        h2 = await auth_headers(client, email2, TEST_PASSWORD)
        results = await asyncio.gather(
            client.request("DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD}, headers=h1),
            client.request("DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD}, headers=h2),
        )
        codes = sorted(r.status_code for r in results)
        assert codes == [200, 409], codes
        with db_cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM users WHERE id = ANY(%s::uuid[]) AND is_active=true", ([uid1, uid2],)
            )
            assert cur.fetchone()["n"] == 1
    finally:
        with db_cursor(privileged=True) as cur:
            if parked:
                cur.execute("UPDATE users SET is_active=true WHERE id = ANY(%s::uuid[])", (parked,))
        for u in (uid1, uid2):
            _cleanup_user(u)


async def test_account_deletion_purges_visit_media_and_signatures_keeps_rows(client, admin_headers, world):
    """
    Account deletion deletes the departing employee's own visit photos and
    signatures from storage (Play Store deletion-policy requirement) but keeps
    the rows themselves, and the GPS/visit data they're attached to, intact.
    """
    uid, eid, email = await _make_user("EMPLOYEE", True)
    try:
        headers = await auth_headers(client, email, TEST_PASSWORD)
        visit_id = await create_visit(client, admin_headers, world["cust_a"]["id"], eid, [], iso_in(9))
        media_id, sig_id = str(uuid.uuid4()), str(uuid.uuid4())
        fake_media_key = f"{TEST_MARKER}fake/visits/{visit_id}/photo_{uuid.uuid4().hex}.jpg"
        fake_sig_key = f"{TEST_MARKER}fake/visits/{visit_id}/signature_{uuid.uuid4().hex}.png"
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO visit_media (id,visit_id,media_type,storage_key,file_size_bytes,original_filename,uploaded_at) "
                "VALUES (%s,%s,'PHOTO',%s,1234,'shop_front.jpg',now())",
                (media_id, visit_id, fake_media_key),
            )
            cur.execute(
                "INSERT INTO visit_signatures (id,visit_id,signature_type,storage_key,signed_at) "
                "VALUES (%s,%s,'EMPLOYEE',%s,now())",
                (sig_id, visit_id, fake_sig_key),
            )

        resp = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD, "reason": "leaving"}, headers=headers
        )
        assert resp.status_code == 200, resp.text

        with db_cursor() as cur:
            cur.execute("SELECT 1 FROM visits WHERE id=%s", (visit_id,))
            assert cur.fetchone() is not None  # visit row retained

            cur.execute("SELECT storage_key, original_filename FROM visit_media WHERE id=%s", (media_id,))
            row = cur.fetchone()
            assert row is not None  # row retained, not deleted
            assert row["storage_key"] != fake_media_key and media_id in row["storage_key"]
            assert row["original_filename"] is None  # personally-identifying filename cleared

            cur.execute("SELECT storage_key FROM visit_signatures WHERE id=%s", (sig_id,))
            sig_row = cur.fetchone()
            assert sig_row is not None
            assert sig_row["storage_key"] != fake_sig_key and sig_id in sig_row["storage_key"]
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM visit_media WHERE id=%s", (media_id,))
            cur.execute("DELETE FROM visit_signatures WHERE id=%s", (sig_id,))
        _cleanup_user(uid)
