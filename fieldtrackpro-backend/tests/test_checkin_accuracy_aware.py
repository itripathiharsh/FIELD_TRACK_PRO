"""
Accuracy-aware check-in (spec: fieldtrackpro-android/design-review/gps-checkin-decision-spec.md):
INSIDE / OUTSIDE / UNCERTAIN / POOR_FIX, conditional check-in, admin review queue, verification requests,
offline-queued check-ins, rate limits, concurrency, and "the outlet pin never changes".
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.database import AsyncSessionLocal
from app.models.checkin_review import CheckInReview
from app.models.user import Role
from app.models.visit import Visit
from app.services.customer_service import extract_coords
from tests.conftest import requires_db
from tests.test_outlet_proofs import (  # noqa: F401  (fixtures)
    LAT, LON, client, ecode, env, get_customer, hdr, make_customer, make_image, upload,
)

pytestmark = [requires_db, pytest.mark.asyncio]
M = 1 / 111_195.0  # degrees of latitude per metre
RV = "/api/v1/checkin-reviews"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "outlet_proof_first_location_auto_accept", True)
    yield
    async with AsyncSessionLocal() as s:
        if env["customers"]:
            await s.execute(delete(Visit).where(Visit.customer_id.in_(env["customers"])))
            await s.commit()


def now_iso(delta_s: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


def fix(metres: float, acc: float, age_s: float = 1.0, mock: bool = False, key: str | None = None) -> dict:
    body = {"latitude": LAT + metres * M, "longitude": LON, "accuracy_m": acc, "is_mock_location": mock,
            "captured_at": now_iso(-age_s)}
    if key:
        body["idempotency_key"] = key
    return body


async def new_visit(client, env, *, located=True):
    cid = await make_customer(env, located=located)
    emp = hdr(env["ua"].id)
    v = await client.post("/api/v1/visits/ad-hoc", headers=emp, json={"customer_id": str(cid), "adhoc_reason": "Cheque Bounce"})
    assert v.status_code == 201, v.text
    return cid, v.json()["id"], emp


async def checkin(client, emp, vid, body):
    return await client.post(f"/api/v1/visits/{vid}/check-in", headers=emp, json=body)


async def visit_row(vid) -> Visit:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Visit).where(Visit.id == uuid.UUID(vid)))).scalar_one()


async def reviews_for(vid) -> list[CheckInReview]:
    async with AsyncSessionLocal() as s:
        return list((await s.execute(select(CheckInReview).where(CheckInReview.visit_id == uuid.UUID(vid)))).scalars().all())


async def pin(cid):
    return extract_coords((await get_customer(cid)).location)


# ---------------------------------------------------------------- outcomes

async def test_confidently_inside_is_accepted_with_high_confidence(env, client):
    cid, vid, emp = await new_visit(client, env)
    before = await pin(cid)
    r = await checkin(client, emp, vid, fix(10, 20))
    assert r.status_code == 200, r.text
    v = await visit_row(vid)
    assert v.check_in_confidence == "HIGH" and not await reviews_for(vid)
    assert await pin(cid) == before


async def test_confidently_outside_is_rejected_with_distance(env, client):
    cid, vid, emp = await new_visit(client, env)
    r = await checkin(client, emp, vid, fix(100, 10))
    assert r.status_code == 422 and ecode(r) == "GEO_VERIFICATION_FAILED"
    assert re.search(r"Distance \(9\d\.\dm\)|Distance \(10\d\.\dm\)", r.text)


async def test_uncertain_with_point_inside_is_a_conditional_checkin_flagged_for_review(env, client):
    cid, vid, emp = await new_visit(client, env)
    before = await pin(cid)
    r = await checkin(client, emp, vid, fix(60, 70))   # 60 + 35 > 75 and 60 - 70 < 75
    assert r.status_code == 200, r.text
    v = await visit_row(vid)
    assert v.check_in_confidence == "LOW"
    revs = await reviews_for(vid)
    assert len(revs) == 1 and revs[0].kind == "CONDITIONAL" and revs[0].status == "PENDING"
    # admin sees it, approves it; coordinates untouched throughout
    admin = hdr(env["admin"].id, Role.ADMIN)
    lst = await client.get(RV, headers=admin)
    assert lst.status_code == 200 and any(x["visit_id"] == vid for x in lst.json())
    ok = await client.post(f"{RV}/{revs[0].id}/approve", headers=admin, json={"note": "seen at the shop"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"
    assert (await visit_row(vid)).check_in_confidence == "ADMIN_CONFIRMED"
    assert await pin(cid) == before


async def test_rejecting_a_conditional_checkin_flags_the_visit_and_keeps_the_pin(env, client):
    cid, vid, emp = await new_visit(client, env)
    before = await pin(cid)
    assert (await checkin(client, emp, vid, fix(60, 70))).status_code == 200
    rev = (await reviews_for(vid))[0]
    admin = hdr(env["admin"].id, Role.ADMIN)
    r = await client.post(f"{RV}/{rev.id}/reject", headers=admin, json={"reason": "not at the outlet"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert (await visit_row(vid)).status.value == "FLAGGED"
    assert await pin(cid) == before


async def test_uncertain_with_point_outside_offers_verification_and_admin_approval_checks_in(env, client):
    cid, vid, emp = await new_visit(client, env)
    before = await pin(cid)
    body = fix(100, 60)                                # 100 + 30 > 75 and 100 - 60 < 75
    r = await checkin(client, emp, vid, body)
    assert r.status_code == 422 and ecode(r) == "GEO_UNCERTAIN"
    assert r.json()["error"]["details"]["verification_available"] is True
    assert (await visit_row(vid)).status.value == "PENDING"   # nothing was silently accepted

    req = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **{k: v for k, v in body.items() if k != "idempotency_key"}})
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    assert req.json()["kind"] == "VERIFICATION_REQUEST" and req.json()["status"] == "PENDING"

    dup = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **body})
    assert dup.status_code in (409, 429)

    assert (await client.post(f"{RV}/{rid}/approve", headers=emp)).status_code in (401, 403)   # employees cannot decide
    admin = hdr(env["admin"].id, Role.ADMIN)
    ok = await client.post(f"{RV}/{rid}/approve", headers=admin)
    assert ok.status_code == 200
    v = await visit_row(vid)
    assert v.status.value == "IN_PROGRESS" and v.check_in_confidence == "ADMIN_VERIFIED"
    assert await pin(cid) == before
    again = await client.post(f"{RV}/{rid}/approve", headers=admin)
    assert again.status_code == 409


async def test_rejected_verification_leaves_the_visit_and_pin_unchanged(env, client):
    cid, vid, emp = await new_visit(client, env)
    before = await pin(cid)
    body = fix(100, 60)
    req = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **body})
    assert req.status_code == 201, req.text
    admin = hdr(env["admin"].id, Role.ADMIN)
    short = await client.post(f"{RV}/{req.json()['id']}/reject", headers=admin, json={"reason": "no"})
    assert short.status_code == 422
    r = await client.post(f"{RV}/{req.json()['id']}/reject", headers=admin, json={"reason": "employee was not at the outlet"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert (await visit_row(vid)).status.value == "PENDING"
    assert await pin(cid) == before
    # a second request right away is rate limited
    again = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(100, 60)})
    assert again.status_code == 429


async def test_verification_is_refused_when_checkin_would_be_fine_or_clearly_outside(env, client):
    cid, vid, emp = await new_visit(client, env)
    fine = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(10, 10)})
    assert fine.status_code == 409 and ecode(fine) == "CHECKIN_ALLOWED"
    outside = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(300, 10)})
    assert outside.status_code == 422


async def test_per_visit_request_limit(env, client):
    cid, vid, emp = await new_visit(client, env)
    async with AsyncSessionLocal() as s:
        for i in range(3):
            s.add(CheckInReview(
                visit_id=uuid.UUID(vid), customer_id=cid, employee_id=(await visit_row(vid)).employee_id,
                requested_by=env["ua"].id, kind="VERIFICATION_REQUEST", status="REJECTED", decision="UNCERTAIN",
                device_location=f"SRID=4326;POINT({LON} {LAT})",
                received_at=datetime.now(timezone.utc) - timedelta(hours=2 + i)))
        await s.commit()
    r = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(100, 60)})
    assert r.status_code == 429 and ecode(r) == "VERIFICATION_REQUEST_LIMIT"


# ---------------------------------------------------------------- poor fixes never decide, never flag

@pytest.mark.parametrize("acc,age,needle", [(150.0, 1, "accuracy"), (0.0, 1, "unknown")])
async def test_poor_fix_makes_no_decision(env, client, acc, age, needle):
    cid, vid, emp = await new_visit(client, env)
    r = await checkin(client, emp, vid, fix(5, acc, age_s=age))
    assert r.status_code == 422 and ecode(r) == "GEO_VERIFICATION_FAILED"
    assert needle in r.text.lower()
    assert (await visit_row(vid)).status.value == "PENDING"


async def test_stale_live_fix_cannot_be_used_for_a_verification_request(env, client):
    cid, vid, emp = await new_visit(client, env)
    r = await client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(100, 60, age_s=600)})
    assert r.status_code == 422 and "too old" in r.text.lower()


async def test_repeated_poor_or_uncertain_attempts_do_not_flag_the_visit(env, client):
    cid, vid, emp = await new_visit(client, env)
    for i in range(4):
        assert (await checkin(client, emp, vid, fix(5, 150 + i))).status_code == 422
        assert (await checkin(client, emp, vid, fix(100, 60))).status_code == 422
    assert (await visit_row(vid)).status.value == "PENDING"      # three real failures would have flagged it
    ok = await checkin(client, emp, vid, fix(5, 15))
    assert ok.status_code == 200


async def test_mock_location_is_rejected(env, client):
    cid, vid, emp = await new_visit(client, env)
    r = await checkin(client, emp, vid, fix(5, 10, mock=True))
    assert r.status_code == 422 and "mock" in r.text.lower()


async def test_indoor_coarse_fix_then_improved_fix(env, client):
    cid, vid, emp = await new_visit(client, env)
    coarse = await checkin(client, emp, vid, fix(10, 464))       # the first indoor network fix
    assert coarse.status_code == 422
    better = await checkin(client, emp, vid, fix(10, 43))        # a moment later, the real GPS fix
    assert better.status_code == 200
    assert (await visit_row(vid)).check_in_confidence == "HIGH"


# ---------------------------------------------------------------- offline queue

async def test_offline_queued_checkin_is_flagged_and_distinguishable(env, client):
    cid, vid, emp = await new_visit(client, env)
    r = await checkin(client, emp, vid, fix(10, 15, age_s=600))   # queued 10 minutes ago
    assert r.status_code == 200, r.text
    assert (await visit_row(vid)).check_in_confidence == "OFFLINE"
    revs = await reviews_for(vid)
    assert len(revs) == 1 and revs[0].kind == "OFFLINE" and revs[0].status == "PENDING"


async def test_a_day_old_fix_is_still_rejected(env, client):
    cid, vid, emp = await new_visit(client, env)
    r = await checkin(client, emp, vid, fix(10, 15, age_s=25 * 3600))
    assert r.status_code == 422 and "too old" in r.text


# ---------------------------------------------------------------- pin accuracy

async def test_pin_accuracy_is_combined_with_employee_accuracy(env, client):
    # outlet registered through the proof flow with a 30 m fix: its accuracy is stored and used
    cid = await make_customer(env)
    emp = hdr(env["ua"].id)
    reg = await upload(client, emp, make_image(940), customer_id=cid, acc=30.0)
    assert reg.status_code == 201 and reg.json()["auto_accepted"]
    v = await client.post("/api/v1/visits/ad-hoc", headers=emp, json={"customer_id": str(cid), "adhoc_reason": "Cheque Bounce"})
    vid = v.json()["id"]
    # d ~ 55 m, a = 36: alone 55 + 18 = 73 (inside); with the pin u = sqrt(36^2 + 30^2) = 46.9 -> 78.4 (uncertain)
    body = {"latitude": LAT + 55 * M, "longitude": LON, "accuracy_m": 36.0, "is_mock_location": False, "captured_at": now_iso(-1)}
    r = await checkin(client, emp, vid, body)
    assert r.status_code == 200
    assert (await visit_row(vid)).check_in_confidence == "LOW"

    cid2, vid2, emp2 = await new_visit(client, env)              # pin without a stored accuracy
    r2 = await checkin(client, emp2, vid2, body)
    assert r2.status_code == 200
    assert (await visit_row(vid2)).check_in_confidence == "HIGH"


# ---------------------------------------------------------------- no photo, idempotency, concurrency

async def test_normal_checkin_needs_no_photo(env, client):
    cid, vid, emp = await new_visit(client, env)
    body = fix(5, 12)
    assert set(body) <= {"latitude", "longitude", "accuracy_m", "is_mock_location", "captured_at", "idempotency_key"}
    assert (await checkin(client, emp, vid, body)).status_code == 200


async def test_idempotent_replay_of_an_uncertain_rejection_keeps_its_code(env, client):
    cid, vid, emp = await new_visit(client, env)
    key = f"k-{uuid.uuid4().hex}"
    a = await checkin(client, emp, vid, fix(100, 60, key=key))
    b = await checkin(client, emp, vid, fix(100, 60, key=key))
    assert ecode(a) == ecode(b) == "GEO_UNCERTAIN"


async def test_concurrent_conditional_checkins_create_one_review(env, client):
    cid, vid, emp = await new_visit(client, env)
    rs = await asyncio.gather(*[checkin(client, emp, vid, fix(60, 70, key=f"c-{i}-{uuid.uuid4().hex}")) for i in range(3)])
    assert not any(r.status_code >= 500 for r in rs), [r.text for r in rs if r.status_code >= 500]
    assert len(await reviews_for(vid)) <= 1


async def test_concurrent_verification_requests_create_one(env, client):
    cid, vid, emp = await new_visit(client, env)
    rs = await asyncio.gather(*[client.post(f"{RV}/request", headers=emp, json={"visit_id": vid, **fix(100, 60)}) for _ in range(3)])
    assert not any(r.status_code >= 500 for r in rs)
    assert sum(1 for r in rs if r.status_code == 201) == 1
    n = len([x for x in await reviews_for(vid) if x.kind == "VERIFICATION_REQUEST"])
    assert n == 1


async def test_employee_cannot_list_the_admin_queue(env, client):
    r = await client.get(RV, headers=hdr(env["ua"].id))
    assert r.status_code in (401, 403)
