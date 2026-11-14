"""Admin alerts for failed / stuck Tally posts (service layer, no scheduler)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.models.user import Role, User
from app.schemas.tally_writeback import TallyWritebackFailRequest
from app.services import tally_writeback_service as svc
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio, pytest.mark.usefixtures("tally_writeback_on")]


async def _world(reviewed_minutes_ago: int = 5):
    tag = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as s:
        admin = User(email=f"adm_al_{tag}@fieldtrack.test", password_hash="h", role=Role.ADMIN, is_active=True)
        off = User(email=f"adm_off_{tag}@fieldtrack.test", password_hash="h", role=Role.ADMIN, is_active=False)
        emp_user = User(email=f"emp_al_{tag}@fieldtrack.test", password_hash="h", role=Role.EMPLOYEE, is_active=True)
        s.add_all([admin, off, emp_user])
        await s.flush()
        emp = Employee(user_id=emp_user.id, full_name=f"Alert Rep {tag}", employee_code=f"REP-AL{tag.upper()}")
        cust = Customer(name=f"Alert Store {tag}", outlet_code=f"UPAL{tag.upper()}", address="x", created_by=admin.id)
        s.add_all([emp, cust])
        await s.flush()
        pay = Payment(
            customer_id=cust.id, employee_id=emp.id, amount=Decimal("1234.50"),
            payment_method=PaymentMethod.CASH, payment_date=date.today(),
            status=PaymentStatus.VERIFIED, source=PaymentSource.MANUAL, created_by=admin.id,
            reviewed_at=datetime.now(timezone.utc) - timedelta(minutes=reviewed_minutes_ago),
        )
        s.add(pay)
        await s.flush()
        job = await svc.enqueue_payment_writeback(s, pay)
        await s.commit()
        return {
            "admin_id": admin.id, "off_id": off.id, "payment_id": pay.id,
            "job_id": job.id, "outlet": cust.name,
        }


async def _notes(user_id, title, payment_id=None):
    async with AsyncSessionLocal() as s:
        rows = list(
            (await s.execute(select(Notification).where(Notification.user_id == user_id, Notification.title == title)))
            .scalars()
            .all()
        )
    if payment_id is not None:
        rows = [n for n in rows if n.payment_id == payment_id]
    return rows


async def _fail(job_id, retryable, msg="Ledger not found"):
    async with AsyncSessionLocal() as s:
        await svc.fail_writeback_job(s, job_id, TallyWritebackFailRequest(error_message=msg, is_retryable=retryable))


async def _set_job(job_id, **fields):
    async with AsyncSessionLocal() as s:
        job = (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id))).scalar_one()
        for k, v in fields.items():
            setattr(job, k, v)
        await s.commit()


async def _job(job_id):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id))).scalar_one()


async def test_permanent_failure_notifies_active_admins_once():
    w = await _world()
    await _fail(w["job_id"], retryable=False)
    notes = await _notes(w["admin_id"], "Tally post failed", w["payment_id"])
    assert len(notes) == 1
    m = notes[0].message
    assert "1,234.50" in m and w["outlet"] in m and "Ledger not found" in m
    assert "₹1,234.50" in m and "Rs " not in m
    # The reference is the structured payment_id column, no longer message text.
    assert notes[0].payment_id == w["payment_id"]
    assert "Ref:" not in m and str(w["payment_id"]) not in m
    assert await _notes(w["off_id"], "Tally post failed", w["payment_id"]) == []
    # A late duplicate failure report on the already-FAILED job must not re-alert.
    await _fail(w["job_id"], retryable=False)
    assert len(await _notes(w["admin_id"], "Tally post failed", w["payment_id"])) == 1


async def test_retryable_failure_does_not_notify_until_retries_exhausted():
    w = await _world()
    await _set_job(w["job_id"], retry_count=1)
    await _fail(w["job_id"], retryable=True)
    assert (await _job(w["job_id"])).status == WritebackStatus.PENDING
    assert await _notes(w["admin_id"], "Tally post failed", w["payment_id"]) == []
    await _set_job(w["job_id"], retry_count=5)
    await _fail(w["job_id"], retryable=True)
    assert (await _job(w["job_id"])).status == WritebackStatus.FAILED
    assert len(await _notes(w["admin_id"], "Tally post failed", w["payment_id"])) == 1


async def test_notification_failure_never_breaks_tally_flow(monkeypatch):
    w = await _world()

    async def boom(*a, **k):
        raise RuntimeError("notif down")

    monkeypatch.setattr(svc, "_notify_admins", boom)
    await _fail(w["job_id"], retryable=False)
    assert (await _job(w["job_id"])).status == WritebackStatus.FAILED


async def test_stuck_alert_once_per_payment_and_skips_fresh_and_confirmed():
    stuck = await _world(reviewed_minutes_ago=45)
    fresh = await _world(reviewed_minutes_ago=5)
    confirmed = await _world(reviewed_minutes_ago=45)
    await _set_job(confirmed["job_id"], status=WritebackStatus.CONFIRMED)

    async with AsyncSessionLocal() as s:
        await svc.notify_stuck_tally_posts(s)
    assert len(await _notes(stuck["admin_id"], "Tally post stuck", stuck["payment_id"])) == 1
    assert await _notes(fresh["admin_id"], "Tally post stuck", fresh["payment_id"]) == []
    assert await _notes(confirmed["admin_id"], "Tally post stuck", confirmed["payment_id"]) == []

    # Second sweep is deduped.
    async with AsyncSessionLocal() as s:
        await svc.notify_stuck_tally_posts(s)
    assert len(await _notes(stuck["admin_id"], "Tally post stuck", stuck["payment_id"])) == 1
    note = (await _notes(stuck["admin_id"], "Tally post stuck", stuck["payment_id"]))[0]
    assert note.payment_id == stuck["payment_id"]
    assert "Ref:" not in note.message and str(stuck["payment_id"]) not in note.message


async def test_stuck_dedupe_uses_payment_id_not_message_text():
    w = await _world(reviewed_minutes_ago=45)
    # Same title, but pointing at ANOTHER payment (and mentioning this one in text) must not dedupe.
    other = await _world(reviewed_minutes_ago=5)
    async with AsyncSessionLocal() as s:
        s.add(Notification(
            user_id=w["admin_id"], type="REMINDER", title="Tally post stuck",
            message=f"Ref: {w['payment_id']}", payment_id=other["payment_id"],
        ))
        await s.commit()
    async with AsyncSessionLocal() as s:
        await svc.notify_stuck_tally_posts(s)
    assert len(await _notes(w["admin_id"], "Tally post stuck", w["payment_id"])) == 1
    # An alert older than the 24h window no longer dedupes.
    async with AsyncSessionLocal() as s:
        await s.execute(
            Notification.__table__.update()
            .where(Notification.payment_id == w["payment_id"])
            .values(sent_at=datetime.now(timezone.utc) - timedelta(hours=25))
        )
        await s.commit()
    async with AsyncSessionLocal() as s:
        await svc.notify_stuck_tally_posts(s)
    assert len(await _notes(w["admin_id"], "Tally post stuck", w["payment_id"])) == 2


async def test_notification_list_endpoint_returns_payment_id(client):
    from app.core.security import create_access_token

    w = await _world()
    await _fail(w["job_id"], retryable=False)
    token = create_access_token(str(w["admin_id"]), Role.ADMIN.value)
    resp = await client.get("/api/v1/notifications/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    rows = [n for n in resp.json() if n["title"] == "Tally post failed"]
    assert len(rows) == 1 and rows[0]["payment_id"] == str(w["payment_id"])


async def test_scheduler_disabled_by_config(monkeypatch):
    from app.config import settings
    from app.jobs import scheduler as sch

    monkeypatch.setattr(settings, "enable_scheduler", False)
    assert sch.start_scheduler() is None
