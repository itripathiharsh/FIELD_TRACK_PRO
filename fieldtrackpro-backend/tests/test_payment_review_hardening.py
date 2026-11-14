"""
A2: payment review / Tally write-back hardening.

Covers: no enqueue at creation, enqueue-on-verify (atomic, idempotent), row
locking (double / concurrent verify & reject), reject semantics vs jobs already
posted to Tally, retry/claim guards, invoice outstanding cap, MISSED-visit
block, audit rows, Tally endpoint authorization and agent-key lockout.
Synthetic data only (tag a2p_*), removed after each test.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.exceptions.custom import BaseAPIException
from app.main import app
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.login_attempt import LoginAttempt
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.tally_audit import TallyAuditLog
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.schemas.payment import PaymentCreate
from app.services import payment_service, tally_writeback_service
from tests.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db, pytest.mark.usefixtures("tally_writeback_on")]


def _pc(visit_id, amount, invoice_id=None, key=None, method=PaymentMethod.CASH):
    return PaymentCreate(
        visit_id=visit_id,
        amount=Decimal(str(amount)),
        payment_method=method,
        payment_date=date.today(),
        invoice_id=invoice_id,
        idempotency_key=key or f"a2p_{uuid.uuid4().hex[:10]}",
    )


@pytest_asyncio.fixture
async def env():
    tag = uuid.uuid4().hex[:6]
    ids: dict = {}
    async with AsyncSessionLocal() as s:
        admin = User(email=f"a2p_admin_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"), role=Role.ADMIN, is_active=True)
        emp_user = User(email=f"a2p_emp_{tag}@fieldtrack.test", password_hash=hash_password("Emp12345!"), role=Role.EMPLOYEE, is_active=True)
        acct_user = User(email=f"a2p_acct_{tag}@fieldtrack.test", password_hash=hash_password("Emp12345!"), role=Role.EMPLOYEE, is_active=True)
        s.add_all([admin, emp_user, acct_user])
        await s.flush()
        employee = Employee(user_id=emp_user.id, full_name=f"A2P Rep {tag}", employee_code=f"REP-A2P{tag.upper()}")
        acct_emp = Employee(
            user_id=acct_user.id,
            full_name=f"A2P Accountant {tag}",
            employee_code=f"REP-A2Q{tag.upper()}",
            working_profile="Head Accountant & Billing In-Charge",
        )
        s.add_all([employee, acct_emp])
        await s.flush()
        customer = Customer(
            name=f"A2P Outlet {tag}",
            outlet_code=f"A2P{tag.upper()}",
            address="Test Road",
            contact_number="9000000000",
            created_by=admin.id,
        )
        s.add(customer)
        await s.flush()
        now = datetime.now(timezone.utc)
        visit = Visit(employee_id=employee.id, customer_id=customer.id, scheduled_at=now, status=VisitStatus.IN_PROGRESS, created_by=admin.id)
        missed = Visit(employee_id=employee.id, customer_id=customer.id, scheduled_at=now - timedelta(days=3), status=VisitStatus.MISSED, created_by=admin.id)
        s.add_all([visit, missed])
        await s.flush()
        invoice = Invoice(
            customer_id=customer.id,
            invoice_number=f"A2P/{tag}",
            invoice_date=date.today() - timedelta(days=5),
            amount=Decimal("1000.00"),
            source=InvoiceSource.TALLY,
            created_by=admin.id,
        )
        s.add(invoice)
        await s.commit()
        ids = dict(
            admin=admin, emp_user=emp_user, acct_user=acct_user, employee=employee, customer=customer,
            visit_id=visit.id, missed_id=missed.id, invoice_id=invoice.id,
        )
    yield ids
    async with AsyncSessionLocal() as s:
        cid = ids["customer"].id
        pids = [r[0] for r in (await s.execute(select(Payment.id).where(Payment.customer_id == cid))).all()]
        if pids:
            await s.execute(delete(TallyAuditLog).where(TallyAuditLog.details["payment_id"].as_string().in_([str(p) for p in pids])))
            await s.execute(delete(TallyWritebackQueue).where(TallyWritebackQueue.entity_id.in_(pids)))
            await s.execute(delete(Payment).where(Payment.id.in_(pids)))
        await s.execute(delete(Invoice).where(Invoice.customer_id == cid))
        await s.execute(delete(Visit).where(Visit.customer_id == cid))
        await s.execute(delete(Customer).where(Customer.id == cid))
        await s.execute(delete(Employee).where(Employee.id.in_([ids["employee"].id])))
        await s.execute(text("DELETE FROM employees WHERE user_id = :u"), {"u": ids["acct_user"].id})
        await s.execute(delete(LoginAttempt))
        await s.execute(delete(User).where(User.id.in_([ids["admin"].id, ids["emp_user"].id, ids["acct_user"].id])))
        await s.commit()


async def _jobs(payment_id):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.entity_id == payment_id))).scalars().all()


async def _legacy_job(payment_id, status):
    """A job as OLD code created it: enqueued at creation time."""
    async with AsyncSessionLocal() as s:
        job = TallyWritebackQueue(
            idempotency_key=f"fieldtrack_payment:{payment_id}",
            entity_type="PAYMENT",
            entity_id=payment_id,
            operation="CREATE_RECEIPT",
            payload={"payment_id": str(payment_id)},
            status=status,
            retry_count=0,
        )
        s.add(job)
        await s.commit()
        return job.id


async def _new_payment(env, amount=100, invoice_id=None):
    async with AsyncSessionLocal() as s:
        return await payment_service.create_payment(_pc(env["visit_id"], amount, invoice_id), env["emp_user"], s)


# ------------------------------------------------------------ enqueue / verify

async def test_create_enqueues_nothing_verify_enqueues_one_with_audit(env):
    p = await _new_payment(env)
    assert await _jobs(p.id) == []
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)
    jobs = await _jobs(p.id)
    assert len(jobs) == 1 and jobs[0].status == WritebackStatus.PENDING
    async with AsyncSessionLocal() as s:
        logs = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "PAYMENT_VERIFY", TallyAuditLog.details["payment_id"].as_string() == str(p.id)))).scalars().all()
    assert len(logs) == 1
    d = logs[0].details
    assert d["actor_user_id"] == str(env["admin"].id)
    assert d["before_status"] == "PENDING_VERIFICATION" and d["after_status"] == "VERIFIED"
    assert logs[0].writeback_job_id == jobs[0].id


async def test_double_verify_is_409_and_creates_no_second_job(env):
    p = await _new_payment(env)
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.verify_payment(p.id, env["admin"], s)
    assert ei.value.status_code == 409
    assert len(await _jobs(p.id)) == 1


async def test_concurrent_verify_exactly_one_wins(env):
    p = await _new_payment(env)

    async def attempt():
        async with AsyncSessionLocal() as s:
            try:
                await payment_service.verify_payment(p.id, env["admin"], s)
                return 200
            except BaseAPIException as e:
                return e.status_code

    results = sorted(await asyncio.gather(attempt(), attempt(), attempt()))
    assert results == [200, 409, 409]
    assert len(await _jobs(p.id)) == 1


async def test_concurrent_verify_and_reject_one_wins(env):
    p = await _new_payment(env)

    async def verify():
        async with AsyncSessionLocal() as s:
            try:
                await payment_service.verify_payment(p.id, env["admin"], s)
                return "verified"
            except BaseAPIException as e:
                return e.status_code

    async def reject():
        async with AsyncSessionLocal() as s:
            try:
                await payment_service.reject_payment(p.id, "dup", env["admin"], s)
                return "rejected"
            except BaseAPIException as e:
                return e.status_code

    a, b = await asyncio.gather(verify(), reject())
    assert (a == "verified" and b == 409) or (a == 409 and b == "rejected")
    jobs = await _jobs(p.id)
    async with AsyncSessionLocal() as s:
        final = (await s.execute(select(Payment.status).where(Payment.id == p.id))).scalar_one()
    if final == PaymentStatus.REJECTED:
        assert jobs == []
    else:
        assert len(jobs) == 1


# ------------------------------------------------------------ reject semantics

async def test_reject_cancels_legacy_pending_job_and_it_cannot_be_retried_or_claimed(env):
    p = await _new_payment(env)
    job_id = await _legacy_job(p.id, WritebackStatus.PENDING)
    async with AsyncSessionLocal() as s:
        await payment_service.reject_payment(p.id, "wrong amount", env["admin"], s)
    job = (await _jobs(p.id))[0]
    assert job.status == WritebackStatus.FAILED and job.last_error.startswith("CANCELLED")

    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await tally_writeback_service.retry_writeback_job(s, job_id)
    assert ei.value.error_code == "JOB_PAYMENT_NOT_VERIFIED"

    async with AsyncSessionLocal() as s:
        claimed = await tally_writeback_service.claim_pending_jobs(s, limit=100)
    assert job_id not in [j.id for j in claimed]

    async with AsyncSessionLocal() as s:
        log = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "PAYMENT_REJECT", TallyAuditLog.details["payment_id"].as_string() == str(p.id)))).scalar_one()
    assert log.details["before_status"] == "PENDING_VERIFICATION" and log.details["after_status"] == "REJECTED"
    assert log.details["actor_user_id"] == str(env["admin"].id)


async def test_reject_blocked_when_receipt_already_posted_to_tally(env):
    p = await _new_payment(env)
    await _legacy_job(p.id, WritebackStatus.CONFIRMED)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.reject_payment(p.id, "oops", env["admin"], s)
    assert ei.value.status_code == 409 and ei.value.error_code == "PAYMENT_POSTED_TO_TALLY"
    async with AsyncSessionLocal() as s:
        st = (await s.execute(select(Payment.status).where(Payment.id == p.id))).scalar_one()
    assert st == PaymentStatus.PENDING_VERIFICATION


async def test_reject_blocked_while_job_in_flight(env):
    p = await _new_payment(env)
    await _legacy_job(p.id, WritebackStatus.PROCESSING)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.reject_payment(p.id, "x", env["admin"], s)
    assert ei.value.error_code == "PAYMENT_WRITEBACK_IN_FLIGHT"


async def test_verified_payment_cannot_be_rejected(env):
    p = await _new_payment(env)
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.reject_payment(p.id, "late", env["admin"], s)
    assert ei.value.status_code == 409
    assert "Tally" in ei.value.detail
    assert (await _jobs(p.id))[0].status == WritebackStatus.PENDING


async def test_retry_of_confirmed_job_refused(env):
    p = await _new_payment(env)
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)
    job = (await _jobs(p.id))[0]
    async with AsyncSessionLocal() as s:
        j = (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.id == job.id))).scalar_one()
        j.status = WritebackStatus.CONFIRMED
        await s.commit()
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await tally_writeback_service.retry_writeback_job(s, job.id)
    assert ei.value.error_code == "JOB_ALREADY_POSTED"


async def test_retry_of_failed_job_for_verified_payment_audited(env):
    p = await _new_payment(env)
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)
    job = (await _jobs(p.id))[0]
    async with AsyncSessionLocal() as s:
        j = (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.id == job.id))).scalar_one()
        j.status = WritebackStatus.FAILED
        await s.commit()
    async with AsyncSessionLocal() as s:
        await tally_writeback_service.retry_writeback_job(s, job.id, actor_user_id=env["admin"].id)
    assert (await _jobs(p.id))[0].status == WritebackStatus.PENDING
    async with AsyncSessionLocal() as s:
        log = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "WRITEBACK_RETRY", TallyAuditLog.writeback_job_id == job.id))).scalar_one()
    assert log.details["actor_user_id"] == str(env["admin"].id)
    assert log.details["before_status"] == "FAILED" and log.details["after_status"] == "PENDING"


async def test_claim_never_returns_job_of_unverified_payment(env):
    p = await _new_payment(env)
    job_id = await _legacy_job(p.id, WritebackStatus.PENDING)
    async with AsyncSessionLocal() as s:
        claimed = await tally_writeback_service.claim_pending_jobs(s, limit=100)
    assert job_id not in [j.id for j in claimed]
    async with AsyncSessionLocal() as s:
        await payment_service.verify_payment(p.id, env["admin"], s)  # enqueue is idempotent: reuses the legacy job
    async with AsyncSessionLocal() as s:
        claimed = await tally_writeback_service.claim_pending_jobs(s, limit=100)
    assert job_id in [j.id for j in claimed]


# ------------------------------------------------------------ amount / visit rules

async def test_invoice_allocation_cannot_exceed_outstanding(env):
    inv = env["invoice_id"]  # 1000.00
    await _new_payment(env, 600, inv)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.create_payment(_pc(env["visit_id"], 500, inv), env["emp_user"], s)
    assert ei.value.status_code == 422 and ei.value.error_code == "PAYMENT_EXCEEDS_INVOICE_OUTSTANDING"
    await _new_payment(env, 400, inv)  # exactly the remainder is fine
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException):
            await payment_service.create_payment(_pc(env["visit_id"], 0.01, inv), env["emp_user"], s)


async def test_concurrent_creates_cannot_overcollect_invoice(env):
    inv = env["invoice_id"]

    async def attempt():
        async with AsyncSessionLocal() as s:
            try:
                await payment_service.create_payment(_pc(env["visit_id"], 700, inv), env["emp_user"], s)
                return 201
            except BaseAPIException as e:
                return e.status_code

    assert sorted(await asyncio.gather(attempt(), attempt())) == [201, 422]


async def test_on_account_payment_without_invoice_is_allowed_as_advance(env):
    p = await _new_payment(env, 999999)
    assert p.invoice_id is None


async def test_missed_visit_blocks_new_collection_but_replay_succeeds(env):
    key = f"a2p_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as s:
        first = await payment_service.create_payment(_pc(env["visit_id"], 50, key=key), env["emp_user"], s)
    async with AsyncSessionLocal() as s:
        with pytest.raises(BaseAPIException) as ei:
            await payment_service.create_payment(_pc(env["missed_id"], 50), env["emp_user"], s)
    assert ei.value.status_code == 409 and ei.value.error_code == "VISIT_NOT_COLLECTABLE"
    # same-visit idempotent replay is unaffected by later visit state
    async with AsyncSessionLocal() as s:
        v = (await s.execute(select(Visit).where(Visit.id == env["visit_id"]))).scalar_one()
        v.status = VisitStatus.MISSED
        await s.commit()
    async with AsyncSessionLocal() as s:
        again = await payment_service.create_payment(_pc(env["visit_id"], 50, key=key), env["emp_user"], s)
    assert again.id == first.id


async def test_completed_visit_still_allowed(env):
    async with AsyncSessionLocal() as s:
        v = (await s.execute(select(Visit).where(Visit.id == env["visit_id"]))).scalar_one()
        v.status = VisitStatus.COMPLETED
        await s.commit()
    assert (await _new_payment(env, 10)).id is not None


# ------------------------------------------------------------ Tally authz

def _bearer(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def test_tally_endpoints_admin_only_not_accountant_profile(env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        acct = {"Authorization": f"Bearer {create_access_token(str(env['acct_user'].id), 'EMPLOYEE')}"}
        emp = {"Authorization": f"Bearer {create_access_token(str(env['emp_user'].id), 'EMPLOYEE')}"}
        adm = _bearer(env["admin"])
        assert (await c.get("/api/v1/integrations/tally/audit-logs", headers=acct)).status_code == 403
        assert (await c.post(f"/api/v1/integrations/tally/outbox/{uuid.uuid4()}/retry", headers=acct)).status_code == 403
        assert (await c.get("/api/v1/integrations/tally/status", headers=acct)).status_code == 403
        assert (await c.get("/api/v1/integrations/tally/status", headers=emp)).status_code == 403
        assert (await c.get("/api/v1/integrations/tally/status")).status_code in (401, 403)
        assert (await c.get("/api/v1/integrations/tally/status", headers=adm)).status_code == 200
        assert (await c.get("/api/v1/integrations/tally/audit-logs", headers=adm)).status_code == 200


async def test_agent_can_read_status_and_outbox_limit_is_bounded(env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        reg = await c.post(
            "/api/v1/integrations/tally/agents",
            json={"name": f"a2p agent {uuid.uuid4().hex[:4]}", "organization_id": "a2p"},
            headers=_bearer(env["admin"]),
        )
        assert reg.status_code == 201
        ah = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
        assert (await c.get("/api/v1/integrations/tally/status", headers=ah)).status_code == 200
        assert (await c.get("/api/v1/integrations/tally/outbox/pending?limit=101", headers=ah)).status_code == 422
        assert (await c.get("/api/v1/integrations/tally/outbox/pending?limit=0", headers=ah)).status_code == 422
        assert (await c.get("/api/v1/integrations/tally/outbox/pending?limit=100", headers=ah)).status_code == 200


async def test_agent_key_bruteforce_is_locked_out(env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        reg = await c.post(
            "/api/v1/integrations/tally/agents",
            json={"name": f"a2p agent {uuid.uuid4().hex[:4]}", "organization_id": "a2p"},
            headers=_bearer(env["admin"]),
        )
        aid, good = reg.json()["agent"]["id"], reg.json()["api_key"]
        codes = [
            (await c.post("/api/v1/integrations/tally/heartbeat", json={"agent_version": "1", "tally_status": "ONLINE"},
                          headers={"X-Agent-Id": aid, "X-Agent-Key": f"wrong-{i}"})).status_code
            for i in range(12)
        ]
        assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
        # even the correct key is refused while locked out
        locked = await c.post("/api/v1/integrations/tally/heartbeat", json={"agent_version": "1", "tally_status": "ONLINE"},
                              headers={"X-Agent-Id": aid, "X-Agent-Key": good})
        assert locked.status_code == 429
