"""
Live outlet proof (photo + GPS bundle): upload validation, kinds/status, admin review,
prospect integration, image authorization, optional auto-verify, cleanup.
"""
from __future__ import annotations

import hashlib
import io
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from geoalchemy2.shape import from_shape
from httpx import ASGITransport, AsyncClient
from PIL import Image
from shapely.geometry import Point
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.customer_location_proposal import CustomerLocationProposal, LocationProposalStatus
from app.models.customer_prospect import CustomerProspect, ProspectStatus
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.notification import Notification
from app.models.outlet_proof import OutletProof
from app.models.user import Role, User
from app.services import outlet_proof_service
from app.services.customer_service import extract_coords
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]

LAT, LON = 28.6139, 77.2090
NEAR = 0.00018  # ~20 m of latitude
FAR = 0.0020  # ~220 m of latitude


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_image(seed: int, size=(2400, 1800), fmt="JPEG", with_gps=True, orientation=None) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", size, (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    for _ in range(300):
        x, y = rnd.randint(0, size[0] - 1), rnd.randint(0, size[1] - 1)
        img.putpixel((x, y), (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    out = io.BytesIO()
    kwargs = {}
    if fmt == "JPEG" and (with_gps or orientation):
        exif = Image.Exif()
        if orientation:
            exif[0x0112] = orientation
        if with_gps:
            exif[0x010F] = "SecretPhoneMaker"
            exif[0x8825] = {1: "N", 2: (28.0, 36.0, 50.0), 3: "E", 4: (77.0, 12.0, 32.0)}
        kwargs["exif"] = exif
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


def ecode(resp):
    return resp.json()["error"]["code"]


def iso_now(delta_s: float = -5) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


def hdr(user_id, role=Role.EMPLOYEE):
    return {"Authorization": f"Bearer {create_access_token(str(user_id), role.value)}"}


async def upload(client, headers, jpeg, *, lat=LAT, lon=LON, acc=8.0, captured=None, mock=False,
                 key=None, customer_id=None, filename="p.jpg", ctype="image/jpeg"):
    data = {
        "latitude": str(lat), "longitude": str(lon), "accuracy_m": str(acc),
        "captured_at": captured or iso_now(), "is_mock_location": "true" if mock else "false",
        "idempotency_key": key or f"idem-{uuid.uuid4().hex}", "device_info": "pytest",
    }
    if customer_id is not None:
        data["customer_id"] = str(customer_id)
    return await client.post(
        "/api/v1/customers/outlet-proofs", headers=headers, data=data,
        files={"photo": (filename, jpeg, ctype)},
    )


@pytest_asyncio.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, "outlet_proof_required_for_new_outlet", True)
    monkeypatch.setattr(settings, "outlet_proof_auto_verify_min_agreeing", 0)
    tag = uuid.uuid4().hex[:8]
    ids: dict = {"tag": tag}
    async with AsyncSessionLocal() as s:
        admin = User(email=f"adm_op_{tag}@fieldtrack.test", password_hash=hash_password("x"), role=Role.ADMIN, is_active=True)
        s.add(admin)
        emps = []
        for n in ("a", "b", "c"):
            u = User(email=f"emp_op_{n}_{tag}@fieldtrack.test", password_hash=hash_password("x"), role=Role.EMPLOYEE, is_active=True)
            s.add(u)
            emps.append(u)
        await s.flush()
        employees = []
        for n, u in zip(("a", "b", "c"), emps):
            e = Employee(user_id=u.id, full_name=f"OP Rep {n} {tag}", employee_code=f"OP{n.upper()}-{tag}")
            s.add(e)
            employees.append(e)
        await s.flush()
        ids.update(admin=admin, ua=emps[0], ub=emps[1], uc=emps[2], ea=employees[0], eb=employees[1], ec=employees[2])
        await s.commit()
    ids["customers"] = []
    yield ids
    await _purge(ids)


async def _purge(ids):
    async with AsyncSessionLocal() as s:
        uids = [ids[k].id for k in ("admin", "ua", "ub", "uc")]
        cust_ids = [c for c in ids["customers"]]
        await s.execute(sa_delete(OutletProof).where(OutletProof.submitted_by.in_(uids)))
        if cust_ids:
            await s.execute(sa_delete(OutletProof).where(OutletProof.customer_id.in_(cust_ids)))
            await s.execute(sa_delete(CustomerLocationProposal).where(CustomerLocationProposal.customer_id.in_(cust_ids)))
            await s.execute(sa_delete(EmployeeCustomerAssignment).where(EmployeeCustomerAssignment.customer_id.in_(cust_ids)))
        await s.execute(sa_delete(Notification).where(Notification.user_id.in_(uids)))
        prospects = (await s.execute(select(CustomerProspect.id, CustomerProspect.resulting_customer_id).where(CustomerProspect.submitted_by.in_(uids)))).all()
        extra_c = [p[1] for p in prospects if p[1]]
        if extra_c:
            from app.models.customer_brand import CustomerBrand
            from app.models.customer_requirement import CustomerRequirement
            await s.execute(sa_delete(OutletProof).where(OutletProof.customer_id.in_(extra_c)))
            await s.execute(sa_delete(EmployeeCustomerAssignment).where(EmployeeCustomerAssignment.customer_id.in_(extra_c)))
            await s.execute(sa_delete(CustomerBrand).where(CustomerBrand.customer_id.in_(extra_c)))
            await s.execute(sa_delete(CustomerRequirement).where(CustomerRequirement.customer_id.in_(extra_c)))
        await s.execute(sa_delete(CustomerProspect).where(CustomerProspect.submitted_by.in_(uids)))
        if extra_c:
            await s.execute(sa_delete(Customer).where(Customer.id.in_(extra_c)))
        if cust_ids:
            await s.execute(sa_delete(Customer).where(Customer.id.in_(cust_ids)))
        await s.execute(sa_delete(Employee).where(Employee.user_id.in_(uids)))
        await s.execute(sa_delete(User).where(User.id.in_(uids)))
        await s.commit()


async def make_customer(env, *, located=False, status=None, assign=("ea", "eb"), name="Outlet"):
    async with AsyncSessionLocal() as s:
        c = Customer(
            name=f"{name} {env['tag']}-{uuid.uuid4().hex[:4]}",
            contact_number="9" + str(random.randint(10**8, 10**9 - 1)),
            address="x",
            location=from_shape(Point(LON, LAT), srid=4326) if located else None,
            location_status=status or ("VERIFIED" if located else "MISSING"),
            created_by=env["admin"].id,
        )
        s.add(c)
        await s.flush()
        for k in assign:
            s.add(EmployeeCustomerAssignment(employee_id=env[k].id, customer_id=c.id, created_by=env["admin"].id))
        await s.commit()
        env["customers"].append(c.id)
        return c.id


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def get_proof(pid) -> OutletProof:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(OutletProof).where(OutletProof.id == uuid.UUID(str(pid))))).scalar_one()


async def get_customer(cid) -> Customer:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Customer).where(Customer.id == cid))).scalar_one()


# ---------------------------------------------------------------------------
# upload: happy path + processing
# ---------------------------------------------------------------------------

async def test_upload_strips_exif_downsizes_and_uses_form_gps(env, client):
    cid = await make_customer(env)
    raw = make_image(1, size=(3000, 2000), with_gps=True)
    assert b"SecretPhoneMaker" in raw  # sanity: the fixture really embeds metadata
    r = await upload(client, hdr(env["ua"].id), raw, customer_id=cid, lat=LAT + 0.0001, lon=LON)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "INITIAL" and body["status"] == "PENDING"
    assert body["customer_id"] == str(cid)
    assert body["storage_provider"] == "LOCAL"
    assert body["image_url"]

    p = await get_proof(body["id"])
    assert p.latitude == pytest.approx(LAT + 0.0001) and p.longitude == pytest.approx(LON)
    assert p.storage_key == f"outlet-proofs/{datetime.now(timezone.utc):%Y}/{p.id}.jpg"
    from app.services.storage_service import storage_service
    stored = await storage_service.download(p.storage_key)
    assert hashlib.sha256(stored).hexdigest() == p.checksum_sha256
    assert p.size_bytes == len(stored)
    img = Image.open(io.BytesIO(stored))
    assert max(img.size) <= 1600 and img.format == "JPEG"
    assert not img.getexif() and b"SecretPhoneMaker" not in stored
    assert b"Exif" not in stored[:64]
    assert "gps" not in {k.lower() for k in img.info}

    c = await get_customer(cid)
    assert c.location_status == "PENDING_APPROVAL"
    assert c.location is None  # nothing official changes until an admin approves


async def test_exif_orientation_is_applied(env, client):
    cid = await make_customer(env)
    raw = make_image(2, size=(2000, 1000), with_gps=False, orientation=6)  # rotate 90 cw
    r = await upload(client, hdr(env["ua"].id), raw, customer_id=cid)
    assert r.status_code == 201, r.text
    from app.services.storage_service import storage_service
    p = await get_proof(r.json()["id"])
    img = Image.open(io.BytesIO(await storage_service.download(p.storage_key)))
    assert img.size[1] > img.size[0]  # portrait after transposition


async def test_png_accepted(env, client):
    cid = await make_customer(env)
    r = await upload(client, hdr(env["ua"].id), make_image(3, size=(800, 600), fmt="PNG"), customer_id=cid,
                     filename="p.png", ctype="image/png")
    assert r.status_code == 201, r.text
    assert r.json()["content_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# upload: rejections
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs,status,code",
    [
        ({"mock": True}, 422, "OUTLET_PROOF_MOCK_LOCATION"),
        ({"acc": 31.0}, 422, "OUTLET_PROOF_ACCURACY_TOO_LOW"),
        ({"captured": "STALE"}, 422, "OUTLET_PROOF_STALE_CAPTURE"),
        ({"captured": "FUTURE"}, 422, "OUTLET_PROOF_FUTURE_CAPTURE"),
        ({"lat": 51.5, "lon": -0.12}, 422, "OUTLET_PROOF_OUTSIDE_INDIA"),
        ({"captured": "2026-01-01T10:00:00"}, 422, "OUTLET_PROOF_CAPTURED_AT_INVALID"),
    ],
)
async def test_capture_rejections(env, client, kwargs, status, code):
    cid = await make_customer(env)
    kwargs = dict(kwargs)
    if kwargs.get("captured") == "STALE":
        kwargs["captured"] = iso_now(-200)
    if kwargs.get("captured") == "FUTURE":
        kwargs["captured"] = iso_now(+120)
    r = await upload(client, hdr(env["ua"].id), make_image(10), customer_id=cid, **kwargs)
    assert r.status_code == status, r.text
    assert ecode(r) == code


async def test_accuracy_exactly_at_limit_and_missing(env, client):
    cid = await make_customer(env)
    ok = await upload(client, hdr(env["ua"].id), make_image(11), customer_id=cid, acc=30.0)
    assert ok.status_code == 201, ok.text
    cid2 = await make_customer(env)
    r = await client.post(
        "/api/v1/customers/outlet-proofs", headers=hdr(env["ua"].id),
        data={"latitude": str(LAT), "longitude": str(LON), "captured_at": iso_now(), "is_mock_location": "false",
              "idempotency_key": "idem-noacc-0001", "customer_id": str(cid2)},
        files={"photo": ("p.jpg", make_image(12), "image/jpeg")},
    )
    assert r.status_code == 422 and ecode(r) == "OUTLET_PROOF_ACCURACY_REQUIRED"


async def test_bad_magic_bytes_and_oversize(env, client):
    cid = await make_customer(env)
    r = await upload(client, hdr(env["ua"].id), b"%PDF-1.4 definitely not an image" * 20, customer_id=cid,
                     filename="x.jpg", ctype="image/jpeg")
    assert r.status_code == 415, r.text
    big = b"\xff\xd8\xff\xe0" + b"\x00" * (10 * 1024 * 1024 + 10)
    r2 = await upload(client, hdr(env["ua"].id), big, customer_id=cid)
    assert r2.status_code == 413 and ecode(r2) == "FILE_TOO_LARGE"
    # a file that has JPEG magic but is not decodable
    r3 = await upload(client, hdr(env["ua"].id), b"\xff\xd8\xff\xe0" + b"\x00" * 200, customer_id=cid)
    assert r3.status_code in (415, 422), r3.text


async def test_duplicate_image_across_outlets_409(env, client):
    c1 = await make_customer(env)
    c2 = await make_customer(env)
    raw = make_image(20)
    assert (await upload(client, hdr(env["ua"].id), raw, customer_id=c1)).status_code == 201
    r = await upload(client, hdr(env["ub"].id), raw, customer_id=c2)
    assert r.status_code == 409 and ecode(r) == "OUTLET_PROOF_DUPLICATE_IMAGE"
    # also blocked as a new (unattached) outlet photo
    r2 = await upload(client, hdr(env["ub"].id), raw)
    assert r2.status_code == 409 and ecode(r2) == "OUTLET_PROOF_DUPLICATE_IMAGE"


async def test_idempotent_replay_returns_same_proof_even_when_stale(env, client):
    cid = await make_customer(env)
    raw = make_image(30)
    r1 = await upload(client, hdr(env["ua"].id), raw, customer_id=cid, key="idem-same-key-1")
    r2 = await upload(client, hdr(env["ua"].id), raw, customer_id=cid, key="idem-same-key-1", captured=iso_now(-900))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    async with AsyncSessionLocal() as s:
        n = len((await s.execute(select(OutletProof.id).where(OutletProof.customer_id == cid))).all())
    assert n == 1


async def test_out_of_scope_employee_gets_404(env, client):
    cid = await make_customer(env, assign=("eb",))
    r = await upload(client, hdr(env["ua"].id), make_image(40), customer_id=cid)
    assert r.status_code == 404 and ecode(r) == "CUSTOMER_NOT_FOUND"


# ---------------------------------------------------------------------------
# kinds / status
# ---------------------------------------------------------------------------

async def test_confirmation_within_radius_and_change_request_beyond(env, client):
    cid = await make_customer(env, located=True)
    r1 = await upload(client, hdr(env["ua"].id), make_image(50), customer_id=cid, lat=LAT + NEAR)
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["kind"] == "CONFIRMATION" and b1["status"] == "CONFIRMED"
    assert 5 < b1["distance_from_verified_m"] <= 50

    r2 = await upload(client, hdr(env["ub"].id), make_image(51), customer_id=cid, lat=LAT + FAR)
    b2 = r2.json()
    assert b2["kind"] == "CHANGE_REQUEST" and b2["status"] == "PENDING"
    assert b2["distance_from_verified_m"] > 150
    c = await get_customer(cid)
    assert c.location_status == "VERIFIED"  # a dispute never touches the official pin
    lat, lon = extract_coords(c.location)
    assert lat == pytest.approx(LAT, abs=1e-6)

    # one pending per employee, one counted confirmation per employee
    dup = await upload(client, hdr(env["ub"].id), make_image(52), customer_id=cid, lat=LAT + FAR)
    assert dup.status_code == 409 and ecode(dup) == "OUTLET_PROOF_ALREADY_PENDING"
    again = await upload(client, hdr(env["ua"].id), make_image(53), customer_id=cid, lat=LAT + NEAR)
    assert again.status_code == 409 and ecode(again) == "OUTLET_PROOF_ALREADY_CONFIRMED"


async def test_unverified_existing_location_is_initial(env, client):
    cid = await make_customer(env, located=True, status="NEEDS_REVIEW")
    r = await upload(client, hdr(env["ua"].id), make_image(55), customer_id=cid, lat=LAT + NEAR)
    assert r.json()["kind"] == "INITIAL" and r.json()["status"] == "PENDING"


async def test_multiple_employees_pending_visible_to_admin(env, client):
    cid = await make_customer(env)
    ra = await upload(client, hdr(env["ua"].id), make_image(60), customer_id=cid)
    rb = await upload(client, hdr(env["ub"].id), make_image(61), customer_id=cid, lat=LAT + NEAR)
    assert ra.status_code == rb.status_code == 201
    r = await client.get(f"/api/v1/customers/outlet-proofs?status=PENDING&customer_id={cid}", headers=hdr(env["admin"].id, Role.ADMIN))
    assert r.status_code == 200 and r.headers["X-Total-Count"] == "2"
    items = r.json()
    assert {i["submitted_by"] for i in items} == {str(env["ua"].id), str(env["ub"].id)}
    for i in items:
        assert i["customer_name"] and i["image_url"] and i["submitted_by_name"] and i["accuracy_m"] == 8.0
        assert i["nearby_pending_proofs"] == 1
    # filters
    assert (await client.get("/api/v1/customers/outlet-proofs?kind=CHANGE_REQUEST&customer_id=" + str(cid),
                             headers=hdr(env["admin"].id, Role.ADMIN))).json() == []
    # employees cannot use the admin queue
    assert (await client.get("/api/v1/customers/outlet-proofs", headers=hdr(env["ua"].id))).status_code == 403
    # per-customer listing: admin sees all, employee only own
    adm = await client.get(f"/api/v1/customers/{cid}/outlet-proofs", headers=hdr(env["admin"].id, Role.ADMIN))
    emp = await client.get(f"/api/v1/customers/{cid}/outlet-proofs", headers=hdr(env["ua"].id))
    assert len(adm.json()) == 2 and [i["submitted_by"] for i in emp.json()] == [str(env["ua"].id)]


# ---------------------------------------------------------------------------
# admin approve / reject
# ---------------------------------------------------------------------------

async def test_approve_initial_sets_location_primary_and_confirms_nearby(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    a = (await upload(client, hdr(env["ua"].id), make_image(70), customer_id=cid)).json()
    b = (await upload(client, hdr(env["ub"].id), make_image(71), customer_id=cid, lat=LAT + NEAR)).json()
    c_far = (await upload(client, hdr(env["uc"].id), make_image(72), customer_id=cid, lat=LAT + FAR))
    # C is not assigned -> 404; use admin-created far proof instead
    assert c_far.status_code == 404
    far = (await upload(client, admin, make_image(73), customer_id=cid, lat=LAT + FAR)).json()

    r = await client.post(f"/api/v1/customers/outlet-proofs/{a['id']}/approve", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED" and r.json()["is_primary"] is True

    cust = await get_customer(cid)
    assert cust.location_status == "VERIFIED"
    assert extract_coords(cust.location)[0] == pytest.approx(LAT, abs=1e-6)
    pb, pf = await get_proof(b["id"]), await get_proof(far["id"])
    assert pb.status == "CONFIRMED" and pb.kind == "CONFIRMATION"
    assert pf.status == "PENDING" and pf.kind == "CHANGE_REQUEST" and pf.distance_from_verified_m > 150

    again = await client.post(f"/api/v1/customers/outlet-proofs/{a['id']}/approve", headers=admin)
    assert again.status_code == 409 and ecode(again) == "OUTLET_PROOF_NOT_PENDING"

    # notifications went to the submitters (REMINDER type, no new enum values)
    async with AsyncSessionLocal() as s:
        titles = (await s.execute(select(Notification.title).where(Notification.user_id == env["ua"].id))).scalars().all()
        assert "Outlet location approved" in titles
        titles_b = (await s.execute(select(Notification.title).where(Notification.user_id == env["ub"].id))).scalars().all()
        assert "Outlet location confirmed" in titles_b

    # customer summary fields
    g = await client.get(f"/api/v1/customers/{cid}", headers=admin)
    j = g.json()
    assert j["primary_outlet_image_available"] is True and j["primary_outlet_proof_id"] == a["id"]
    assert j["outlet_location_confirmations"] == 1 and j["outlet_proof_count"] >= 3

    # change request approved later: supersedes previous primary and its stale confirmation
    r2 = await client.post(f"/api/v1/customers/outlet-proofs/{far['id']}/approve", headers=admin)
    assert r2.status_code == 200
    assert (await get_proof(a["id"])).status == "SUPERSEDED" and (await get_proof(a["id"])).is_primary is False
    assert (await get_proof(b["id"])).status == "SUPERSEDED"
    cust2 = await get_customer(cid)
    assert extract_coords(cust2.location)[0] == pytest.approx(LAT + FAR, abs=1e-6)


async def test_reject_requires_reason_and_restores_status(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    p = (await upload(client, hdr(env["ua"].id), make_image(80), customer_id=cid)).json()
    assert (await get_customer(cid)).location_status == "PENDING_APPROVAL"
    bad = await client.post(f"/api/v1/customers/outlet-proofs/{p['id']}/reject", headers=admin, json={"reason": "x"})
    assert bad.status_code == 422
    ok = await client.post(f"/api/v1/customers/outlet-proofs/{p['id']}/reject", headers=admin, json={"reason": "photo shows wrong shop"})
    assert ok.status_code == 200 and ok.json()["status"] == "REJECTED"
    assert (await get_customer(cid)).location_status == "MISSING"
    async with AsyncSessionLocal() as s:
        titles = (await s.execute(select(Notification.title).where(Notification.user_id == env["ua"].id))).scalars().all()
    assert "Outlet photo rejected" in titles
    # rejecting the SAME employee's proof frees them to submit again
    again = await upload(client, hdr(env["ua"].id), make_image(81), customer_id=cid)
    assert again.status_code == 201


async def test_reject_keeps_pending_when_other_initial_remains(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    p1 = (await upload(client, hdr(env["ua"].id), make_image(82), customer_id=cid)).json()
    await upload(client, hdr(env["ub"].id), make_image(83), customer_id=cid)
    await client.post(f"/api/v1/customers/outlet-proofs/{p1['id']}/reject", headers=admin, json={"reason": "blurry photo"})
    assert (await get_customer(cid)).location_status == "PENDING_APPROVAL"


async def test_reject_change_request_keeps_verified(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env, located=True)
    p = (await upload(client, hdr(env["ua"].id), make_image(84), customer_id=cid, lat=LAT + FAR)).json()
    assert p["kind"] == "CHANGE_REQUEST"
    await client.post(f"/api/v1/customers/outlet-proofs/{p['id']}/reject", headers=admin, json={"reason": "not this outlet"})
    assert (await get_customer(cid)).location_status == "VERIFIED"


async def test_approval_closes_agreeing_legacy_location_proposal(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    old = await client.post(f"/api/v1/customers/{cid}/location-proposals", headers=hdr(env["ub"].id),
                            json={"proposed_latitude": LAT + NEAR, "proposed_longitude": LON})
    assert old.status_code == 201, old.text
    p = (await upload(client, hdr(env["ua"].id), make_image(85), customer_id=cid)).json()
    await client.post(f"/api/v1/customers/outlet-proofs/{p['id']}/approve", headers=admin)
    async with AsyncSessionLocal() as s:
        lp = (await s.execute(select(CustomerLocationProposal).where(CustomerLocationProposal.customer_id == cid))).scalar_one()
    assert lp.status == LocationProposalStatus.APPROVED


# ---------------------------------------------------------------------------
# image endpoint authorization
# ---------------------------------------------------------------------------

async def test_image_endpoint_authorization(env, client):
    cid = await make_customer(env)
    p = (await upload(client, hdr(env["ua"].id), make_image(90), customer_id=cid)).json()
    url = f"/api/v1/customers/outlet-proofs/{p['id']}/image"
    adm = await client.get(url, headers=hdr(env["admin"].id, Role.ADMIN))
    own = await client.get(url, headers=hdr(env["ua"].id))
    other = await client.get(url, headers=hdr(env["ub"].id))
    anon = await client.get(url)
    assert adm.status_code == 200 and adm.headers["content-type"] == "image/jpeg" and adm.content[:2] == b"\xff\xd8"
    assert own.status_code == 200 and own.content == adm.content
    assert other.status_code == 404
    assert anon.status_code in (401, 403)
    # the signed URL itself also works (LOCAL provider), and is a relative path - never absolute in DB
    signed = await client.get(p["image_url"])
    assert signed.status_code == 200 and signed.content == adm.content
    assert not (await get_proof(p["id"])).storage_key.startswith(("http", "/"))


async def test_customer_primary_image_endpoint(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    assert (await client.get(f"/api/v1/customers/{cid}/outlet-image", headers=hdr(env["ua"].id))).status_code == 404
    p = (await upload(client, hdr(env["ua"].id), make_image(91), customer_id=cid)).json()
    await client.post(f"/api/v1/customers/outlet-proofs/{p['id']}/approve", headers=admin)
    r = await client.get(f"/api/v1/customers/{cid}/outlet-image", headers=hdr(env["ub"].id))
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    lst = await client.get("/api/v1/customers?limit=5000", headers=admin)
    row = next(c for c in lst.json() if c["id"] == str(cid))
    assert row["primary_outlet_image_available"] is True


# ---------------------------------------------------------------------------
# prospect integration
# ---------------------------------------------------------------------------

def prospect_body(env, **extra):
    n = random.randint(10**8, 10**9 - 1)
    body = {"name": f"OP Prospect {env['tag']}-{n}", "contact_number": f"9{n}", "address": "Shop 1",
            "brands": ["Havells"], "location": {"latitude": 19.0, "longitude": 72.8}, "gps_accuracy_meters": 99.0}
    body.update(extra)
    return body


async def test_prospect_requires_proof_when_flag_on(env, client):
    r = await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id), json=prospect_body(env))
    assert r.status_code == 422 and ecode(r) == "OUTLET_PROOF_REQUIRED"


async def test_prospect_with_proof_uses_proof_gps_then_approve_links_customer(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    up = await upload(client, hdr(env["ua"].id), make_image(100), lat=LAT, lon=LON, acc=7.0)
    assert up.status_code == 201, up.text
    ub = up.json()
    assert ub["status"] == "UNATTACHED" and ub["customer_id"] is None and ub["prospect_id"] is None

    # another employee can not use it
    steal = await client.post("/api/v1/customers/prospect", headers=hdr(env["ub"].id),
                              json=prospect_body(env, outlet_proof_id=ub["id"]))
    assert steal.status_code == 404

    r = await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id),
                          json=prospect_body(env, outlet_proof_id=ub["id"]))
    assert r.status_code == 201, r.text
    pid = r.json()["prospect_id"]
    async with AsyncSessionLocal() as s:
        pr = (await s.execute(select(CustomerProspect).where(CustomerProspect.id == uuid.UUID(pid)))).scalar_one()
        assert pr.proposed_latitude == pytest.approx(LAT) and pr.proposed_longitude == pytest.approx(LON)
        assert pr.gps_accuracy_meters == 7.0  # client-supplied 19.0/72.8 / 99 m ignored
    proof = await get_proof(ub["id"])
    assert proof.prospect_id == uuid.UUID(pid) and proof.status == "PENDING" and proof.kind == "INITIAL"

    # the prospect read model exposes its linked live proof (admin list + detail)
    lst = await client.get("/api/v1/customers/prospects", headers=admin)
    assert lst.status_code == 200, lst.text
    row = next(x for x in lst.json() if x["id"] == pid)
    assert row["outlet_proof_id"] == ub["id"] and row["outlet_proof_accuracy_m"] == 7.0 and row["outlet_proof_captured_at"]
    det = await client.get(f"/api/v1/customers/prospects/{pid}", headers=admin)
    assert det.status_code == 200 and det.json()["outlet_proof_id"] == ub["id"]

    # reuse of an already-attached proof is refused
    reuse = await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id),
                              json=prospect_body(env, outlet_proof_id=ub["id"]))
    assert reuse.status_code == 409

    # via the proof endpoint, a prospect proof must go through the prospect
    blocked = await client.post(f"/api/v1/customers/outlet-proofs/{ub['id']}/approve", headers=admin)
    assert blocked.status_code == 409 and ecode(blocked) == "OUTLET_PROOF_PROSPECT_PENDING"

    ap = await client.post(f"/api/v1/customers/prospects/{pid}/approve", headers=admin)
    assert ap.status_code == 200, ap.text
    cust = ap.json()
    assert cust["location_status"] == "VERIFIED"
    assert cust["primary_outlet_image_available"] is True and cust["primary_outlet_proof_id"] == ub["id"]
    assert cust["location"]["latitude"] == pytest.approx(LAT)
    proof = await get_proof(ub["id"])
    assert proof.customer_id == uuid.UUID(cust["id"]) and proof.status == "APPROVED" and proof.is_primary
    assert proof.reviewed_by == env["admin"].id
    env["customers"].append(uuid.UUID(cust["id"]))


async def test_prospect_reject_marks_proof_rejected(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    ub = (await upload(client, hdr(env["ua"].id), make_image(101))).json()
    pid = (await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id),
                             json=prospect_body(env, outlet_proof_id=ub["id"]))).json()["prospect_id"]
    r = await client.post(f"/api/v1/customers/prospects/{pid}/reject", headers=admin, json={"reason": "duplicate shop"})
    assert r.status_code == 200
    p = await get_proof(ub["id"])
    assert p.status == "REJECTED" and p.rejection_reason == "duplicate shop"
    # object retained for audit
    from app.services.storage_service import storage_service
    assert await storage_service.exists(p.storage_key)


async def test_prospect_flag_off_keeps_old_behaviour(env, client, monkeypatch):
    monkeypatch.setattr(settings, "outlet_proof_required_for_new_outlet", False)
    r = await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id), json=prospect_body(env))
    assert r.status_code == 201 and r.json()["status"] == "PENDING_APPROVAL"


# ---------------------------------------------------------------------------
# auto-verify (default disabled)
# ---------------------------------------------------------------------------

async def _seed_pending(env, cid, user, employee, *, days_ago, acc=10.0, lat=LAT):
    async with AsyncSessionLocal() as s:
        cap = datetime.now(timezone.utc) - timedelta(days=days_ago)
        s.add(OutletProof(
            customer_id=cid, kind="INITIAL", status="PENDING", storage_key=f"outlet-proofs/test/{uuid.uuid4()}.jpg",
            storage_provider="LOCAL", content_type="image/jpeg", size_bytes=1, checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            latitude=lat, longitude=LON, accuracy_m=acc, captured_at=cap, submitted_by=user.id,
            submitted_by_employee_id=employee.id,
        ))
        await s.commit()


async def test_auto_verify_disabled_by_default(env, client):
    cid = await make_customer(env)
    await _seed_pending(env, cid, env["ub"], env["eb"], days_ago=1)
    r = await upload(client, hdr(env["ua"].id), make_image(110), customer_id=cid, lat=LAT + NEAR)
    assert r.json()["status"] == "PENDING"
    assert (await get_customer(cid)).location is None


async def test_auto_verify_two_employees_on_distinct_dates(env, client, monkeypatch):
    monkeypatch.setattr(settings, "outlet_proof_auto_verify_min_agreeing", 2)
    cid = await make_customer(env)
    await _seed_pending(env, cid, env["ub"], env["eb"], days_ago=1, acc=5.0)
    r = await upload(client, hdr(env["ua"].id), make_image(111), customer_id=cid, lat=LAT + NEAR, acc=9.0)
    assert r.status_code == 201, r.text
    cust = await get_customer(cid)
    assert cust.location_status == "VERIFIED" and cust.location is not None
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(OutletProof).where(OutletProof.customer_id == cid))).scalars().all()
    by = {p.submitted_by: p for p in rows}
    assert by[env["ub"].id].status == "APPROVED" and by[env["ub"].id].is_primary  # most accurate
    assert by[env["ub"].id].reviewed_by is None  # system approval
    assert by[env["ua"].id].status == "CONFIRMED"


async def test_auto_verify_needs_distinct_dates_and_good_accuracy(env, client, monkeypatch):
    monkeypatch.setattr(settings, "outlet_proof_auto_verify_min_agreeing", 2)
    # same IST date -> not enough
    cid = await make_customer(env)
    await _seed_pending(env, cid, env["ub"], env["eb"], days_ago=0)
    r = await upload(client, hdr(env["ua"].id), make_image(112), customer_id=cid, lat=LAT + NEAR)
    assert r.json()["status"] == "PENDING"
    # other proof too inaccurate for auto-verify (accuracy 25 > 20)
    cid2 = await make_customer(env)
    await _seed_pending(env, cid2, env["ub"], env["eb"], days_ago=1, acc=25.0)
    r2 = await upload(client, hdr(env["ua"].id), make_image(113), customer_id=cid2, lat=LAT + NEAR)
    assert r2.json()["status"] == "PENDING"
    # agreeing proof too far away
    cid3 = await make_customer(env)
    await _seed_pending(env, cid3, env["ub"], env["eb"], days_ago=1, lat=LAT + FAR)
    r3 = await upload(client, hdr(env["ua"].id), make_image(114), customer_id=cid3)
    assert r3.json()["status"] == "PENDING"


# ---------------------------------------------------------------------------
# cleanup helper, logging
# ---------------------------------------------------------------------------

async def test_cleanup_expired_unattached(env, client):
    old = (await upload(client, hdr(env["ua"].id), make_image(120))).json()
    fresh = (await upload(client, hdr(env["ub"].id), make_image(121))).json()
    from app.services.storage_service import storage_service
    old_key = (await get_proof(old["id"])).storage_key
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(OutletProof).where(OutletProof.id == uuid.UUID(old["id"])))).scalar_one()
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=49)
        await s.commit()
    async with AsyncSessionLocal() as s:
        removed = await outlet_proof_service.cleanup_expired_unattached(s)
    assert removed >= 1
    async with AsyncSessionLocal() as s:
        assert (await s.execute(select(OutletProof).where(OutletProof.id == uuid.UUID(old["id"])))).scalar_one_or_none() is None
        assert (await s.execute(select(OutletProof).where(OutletProof.id == uuid.UUID(fresh["id"])))).scalar_one_or_none() is not None
    assert not await storage_service.exists(old_key)
    # an expired-but-not-yet-cleaned proof can't be used for a prospect either
    exp = (await upload(client, hdr(env["ua"].id), make_image(122))).json()
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(OutletProof).where(OutletProof.id == uuid.UUID(exp["id"])))).scalar_one()
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=50)
        await s.commit()
    r = await client.post("/api/v1/customers/prospect", headers=hdr(env["ua"].id), json=prospect_body(env, outlet_proof_id=exp["id"]))
    assert r.status_code == 409 and ecode(r) == "OUTLET_PROOF_EXPIRED"


async def test_logs_never_contain_coordinates(env, client, caplog):
    cid = await make_customer(env)
    caplog.set_level(logging.DEBUG)
    r = await upload(client, hdr(env["ua"].id), make_image(130), customer_id=cid, lat=28.123456, lon=77.654321)
    assert r.status_code == 201
    admin = hdr(env["admin"].id, Role.ADMIN)
    await client.post(f"/api/v1/customers/outlet-proofs/{r.json()['id']}/approve", headers=admin)
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "28.1234" not in text and "77.6543" not in text
    assert "outlet_proof_upload" in text and "outlet_proof_approve" in text


async def test_model_check_constraint_requires_target(env):
    from sqlalchemy.exc import IntegrityError
    async with AsyncSessionLocal() as s:
        s.add(OutletProof(
            kind="INITIAL", status="PENDING", storage_key="k", storage_provider="LOCAL", content_type="image/jpeg",
            size_bytes=1, checksum_sha256="0" * 64, latitude=LAT, longitude=LON, accuracy_m=5,
            captured_at=datetime.now(timezone.utc), submitted_by=env["ua"].id,
        ))
        with pytest.raises(IntegrityError):
            await s.commit()
