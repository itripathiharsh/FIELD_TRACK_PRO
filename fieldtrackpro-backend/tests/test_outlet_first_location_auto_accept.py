"""First valid outlet location is auto-accepted; later ones need an admin; check-in stays GPS-only."""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.outlet_proof import OutletProof
from app.models.user import Role
from app.models.visit import Visit
from app.services.customer_service import extract_coords
from tests.conftest import requires_db
from tests.test_outlet_proofs import (  # noqa: F401  (fixtures)
    FAR, LAT, LON, client, ecode, env, get_customer, get_proof, hdr, make_customer, make_image, upload,
)

pytestmark = [requires_db, pytest.mark.asyncio]
BASE = "/api/v1/customers/outlet-proofs"


@pytest_asyncio.fixture(autouse=True)
async def _auto_on(env, monkeypatch):
    monkeypatch.setattr(settings, "outlet_proof_first_location_auto_accept", True)
    yield
    async with AsyncSessionLocal() as s:  # visits reference the outlets; remove them before env teardown
        if env["customers"]:
            await s.execute(delete(Visit).where(Visit.customer_id.in_(env["customers"])))
            await s.commit()


async def _visit_count(cid) -> int:
    async with AsyncSessionLocal() as s:
        return len((await s.execute(select(Visit.id).where(Visit.customer_id == cid))).scalars().all())


async def test_first_registration_auto_accepted_without_visit(env, client):
    cid = await make_customer(env)
    r = await upload(client, hdr(env["ua"].id), make_image(901), customer_id=cid)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["kind"] == "INITIAL" and b["status"] == "APPROVED" and b["is_primary"] and b["auto_accepted"]
    c = await get_customer(cid)
    assert c.location_status == "VERIFIED"
    assert extract_coords(c.location)[0] == pytest.approx(LAT, abs=1e-6)
    assert await _visit_count(cid) == 0  # registration never checks anyone in


async def test_later_suggestion_stays_pending_and_keeps_coords(env, client):
    cid = await make_customer(env)
    await upload(client, hdr(env["ua"].id), make_image(902), customer_id=cid)
    r = await upload(client, hdr(env["ub"].id), make_image(903), customer_id=cid, lat=LAT + FAR)
    b = r.json()
    assert b["kind"] == "CHANGE_REQUEST" and b["status"] == "PENDING" and not b["auto_accepted"]
    assert extract_coords((await get_customer(cid)).location)[0] == pytest.approx(LAT, abs=1e-6)


async def test_admin_approval_updates_and_rejection_preserves(env, client):
    admin = hdr(env["admin"].id, Role.ADMIN)
    cid = await make_customer(env)
    await upload(client, hdr(env["ua"].id), make_image(904), customer_id=cid)
    rej = (await upload(client, hdr(env["ub"].id), make_image(905), customer_id=cid, lat=LAT + FAR)).json()
    r = await client.post(f"{BASE}/{rej['id']}/reject", headers=admin, json={"reason": "wrong building"})
    assert r.status_code == 200 and (await get_proof(rej["id"])).status == "REJECTED"
    assert extract_coords((await get_customer(cid)).location)[0] == pytest.approx(LAT, abs=1e-6)
    ok = (await upload(client, hdr(env["ua"].id), make_image(906), customer_id=cid, lat=LAT + FAR)).json()
    assert (await client.post(f"{BASE}/{ok['id']}/approve", headers=admin)).status_code == 200
    assert extract_coords((await get_customer(cid)).location)[0] == pytest.approx(LAT + FAR, abs=1e-6)


async def test_employee_cannot_approve_or_reject(env, client):
    cid = await make_customer(env)
    await upload(client, hdr(env["ua"].id), make_image(907), customer_id=cid)
    p = (await upload(client, hdr(env["ub"].id), make_image(908), customer_id=cid, lat=LAT + FAR)).json()
    emp = hdr(env["ua"].id)
    assert (await client.post(f"{BASE}/{p['id']}/approve", headers=emp)).status_code in (401, 403)
    assert (await client.post(f"{BASE}/{p['id']}/reject", headers=emp, json={"reason": "no reason"})).status_code in (401, 403)
    assert (await get_proof(p["id"])).status == "PENDING"


async def test_invalid_first_suggestion_is_not_accepted(env, client):
    cid = await make_customer(env)
    r = await upload(client, hdr(env["ua"].id), make_image(909), customer_id=cid, acc=80.0)
    assert r.status_code == 422
    m = await upload(client, hdr(env["ua"].id), make_image(910), customer_id=cid, mock=True)
    assert m.status_code == 422
    assert (await get_customer(cid)).location is None


async def test_concurrent_first_registrations_single_winner(env, client):
    cid = await make_customer(env, assign=("ea", "eb"))
    users = ["ua", "ub", "ua", "ub"]
    rs = await asyncio.gather(*[
        upload(client, hdr(env[u].id), make_image(920 + i), customer_id=cid, lat=LAT + i * 0.0001)
        for i, u in enumerate(users)
    ])
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(OutletProof).where(OutletProof.customer_id == cid))).scalars().all()
    assert sum(1 for p in rows if p.auto_accepted) == 1
    assert sum(1 for p in rows if p.is_primary) == 1
    assert not any(r.status_code >= 500 for r in rs)


async def test_checkin_is_gps_only_inside_and_outside(env, client):
    from datetime import datetime, timezone
    cid = await make_customer(env, located=True)
    emp = hdr(env["ua"].id)
    v = await client.post("/api/v1/visits/ad-hoc", headers=emp, json={"customer_id": str(cid), "adhoc_reason": "Cheque Bounce"})
    assert v.status_code == 201, v.text
    vid = v.json()["id"]

    def body(lat):
        return {"latitude": lat, "longitude": LON, "accuracy_m": 10.0, "is_mock_location": False,
                "captured_at": datetime.now(timezone.utc).isoformat()}  # no photo field at all
    far = await client.post(f"/api/v1/visits/{vid}/check-in", headers=emp, json=body(LAT + FAR))
    assert far.status_code == 422 and ecode(far) == "GEO_VERIFICATION_FAILED"
    ok = await client.post(f"/api/v1/visits/{vid}/check-in", headers=emp, json=body(LAT + 0.0001))
    assert ok.status_code == 200, ok.text


async def test_checkin_on_outlet_without_gps_is_rejected(env, client):
    from datetime import datetime, timezone
    cid = await make_customer(env)
    emp = hdr(env["ua"].id)
    v = await client.post("/api/v1/visits/ad-hoc", headers=emp, json={"customer_id": str(cid), "adhoc_reason": "Cheque Bounce"})
    assert v.status_code == 201, v.text
    r = await client.post(f"/api/v1/visits/{v.json()['id']}/check-in", headers=emp, json={
        "latitude": LAT, "longitude": LON, "accuracy_m": 10.0, "is_mock_location": False,
        "captured_at": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 422 and ecode(r) == "OUTLET_LOCATION_NOT_CONFIGURED"
