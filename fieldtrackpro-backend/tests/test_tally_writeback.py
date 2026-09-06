import uuid
from decimal import Decimal
from datetime import date
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.schemas.payment import PaymentCreate
from app.services.payment_service import create_payment
from app.services.tally_writeback_service import enqueue_payment_writeback
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def writeback_test_env():
    async with AsyncSessionLocal() as session:
        tag = uuid.uuid4().hex[:6]
        admin = User(
            email=f"admin_wb_{tag}@fieldtrack.test",
            password_hash=hash_password("Admin123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin)

        emp_user = User(
            email=f"emp_wb_{tag}@fieldtrack.test",
            password_hash=hash_password("Emp123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(emp_user)
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name=f"Writeback Rep {tag}",
            employee_code=f"REP-{tag.upper()}",
        )
        session.add(employee)
        await session.flush()

        customer = Customer(
            name=f"Aaditya Telecom {tag}",
            outlet_code=f"UPDD{tag.upper()}",
            address="Civil Lines, Kanpur",
            contact_number="9839000000",
            created_by=admin.id,
        )
        session.add(customer)
        await session.flush()

        from datetime import datetime, timezone
        visit = Visit(
            employee_id=employee.id,
            customer_id=customer.id,
            scheduled_at=datetime.now(timezone.utc),
            status=VisitStatus.COMPLETED,
            created_by=admin.id,
        )
        session.add(visit)
        await session.flush()

        await session.commit()
        return {
            "admin": admin,
            "employee_user": emp_user,
            "employee": employee,
            "customer": customer,
            "visit": visit,
        }


@pytest.mark.asyncio
@requires_db
async def test_payment_creation_enqueues_writeback(writeback_test_env):
    """TEST A & TEST C: Creating a field payment transactionally creates exactly ONE writeback job."""
    env = writeback_test_env
    visit = env["visit"]
    emp_user = env["employee_user"]

    async with AsyncSessionLocal() as session:
        data = PaymentCreate(
            visit_id=visit.id,
            amount=Decimal("1500.00"),
            payment_method=PaymentMethod.CASH,
            payment_date=date.today(),
            notes="Field collection test",
            idempotency_key=f"visit_{visit.id}_{uuid.uuid4().hex[:6]}",
        )
        payment = await create_payment(data, emp_user, session)
        assert payment.id is not None

        # Verify exactly one writeback job enqueued
        wb_stmt = select(TallyWritebackQueue).where(
            TallyWritebackQueue.entity_id == payment.id
        )
        jobs = (await session.execute(wb_stmt)).scalars().all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == WritebackStatus.PENDING
        assert job.idempotency_key == f"fieldtrack_payment:{payment.id}"
        assert job.payload["amount"] == 1500.0
        assert job.payload["customer_name"] == env["customer"].name
        assert job.payload["payment_method"] == "CASH"

        # Calling enqueue again with same payment returns existing job (idempotent)
        job2 = await enqueue_payment_writeback(session, payment, customer=env["customer"])
        assert job2.id == job.id


@pytest.mark.asyncio
@requires_db
async def test_tally_payment_never_enqueues_writeback(writeback_test_env):
    """TEST G: Payments originating from Tally are never enqueued for writeback (avoids loop)."""
    env = writeback_test_env
    async with AsyncSessionLocal() as session:
        tally_pmt = Payment(
            customer_id=env["customer"].id,
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.CASH,
            payment_date=date.today(),
            status=PaymentStatus.VERIFIED,
            source=PaymentSource.TALLY,
            source_reference=f"TALLY_VCH_{uuid.uuid4().hex[:6]}",
            created_by=env["admin"].id,
        )
        session.add(tally_pmt)
        await session.flush()

        res = await enqueue_payment_writeback(session, tally_pmt, customer=env["customer"])
        assert res is None

        # Confirm nothing in queue
        wb_stmt = select(TallyWritebackQueue).where(
            TallyWritebackQueue.entity_id == tally_pmt.id
        )
        assert (await session.execute(wb_stmt)).scalar_one_or_none() is None


@pytest.mark.asyncio
@requires_db
async def test_outbox_claim_ack_and_reconciliation_flow(writeback_test_env):
    """
    TEST B, D, E, F: End-to-end outbox lifecycle:
    1. Agent claims pending job
    2. Agent ACKs job with Tally GUID
    3. Payment source_reference is linked
    4. Upstream Tally -> Backend sync reconciles payment instead of duplicating
    """
    env = writeback_test_env
    admin = env["admin"]
    admin_token = create_access_token(subject=str(admin.id), role=Role.ADMIN.value)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register Agent
        reg_res = await client.post(
            "/api/v1/integrations/tally/agents",
            json={
                "name": f"WB Agent {uuid.uuid4().hex[:4]}",
                "organization_id": "test_org",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reg_res.status_code == 201
        agent_data = reg_res.json()
        agent_headers = {
            "X-Agent-Id": agent_data["agent"]["id"],
            "X-Agent-Key": agent_data["api_key"],
        }

        # Create a field payment
        async with AsyncSessionLocal() as session:
            data = PaymentCreate(
                visit_id=env["visit"].id,
                amount=Decimal("2500.00"),
                payment_method=PaymentMethod.ONLINE,
                payment_date=date.today(),
                utr_reference=f"UTR{uuid.uuid4().hex[:8].upper()}",
                notes="Writeback test payment",
                idempotency_key=f"visit_{env['visit'].id}_{uuid.uuid4().hex[:6]}",
            )
            payment = await create_payment(data, env["employee_user"], session)
            payment_id = payment.id

        # 1. Claim pending job
        claim_res = await client.get(
            "/api/v1/integrations/tally/outbox/pending?limit=10",
            headers=agent_headers,
        )
        assert claim_res.status_code == 200
        claimed_jobs = claim_res.json()
        matching = [j for j in claimed_jobs if j["entity_id"] == str(payment_id)]
        assert len(matching) == 1
        job_id = matching[0]["id"]
        assert matching[0]["status"] == "PROCESSING"

        # Polling immediately again returns no duplicate claim (lease locked)
        claim_again = await client.get(
            "/api/v1/integrations/tally/outbox/pending?limit=10",
            headers=agent_headers,
        )
        assert not any(j["id"] == job_id for j in claim_again.json())

        # 2. Acknowledge job with Tally GUID
        tally_guid = f"19a03e17-e1ab-44f2-8e7f-1bff56f20ebe-{uuid.uuid4().hex[:8]}"
        tally_vch_num = "9901"
        ack_res = await client.post(
            f"/api/v1/integrations/tally/outbox/{job_id}/ack",
            json={
                "tally_guid": tally_guid,
                "tally_master_id": "54321",
                "tally_voucher_number": tally_vch_num,
            },
            headers=agent_headers,
        )
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "CONFIRMED"

        # Verify payment now has source_reference set
        async with AsyncSessionLocal() as session:
            p_check = (
                await session.execute(select(Payment).where(Payment.id == payment_id))
            ).scalar_one()
            assert p_check.source_reference == tally_guid

        # Repeat ACK is idempotent
        ack_repeat = await client.post(
            f"/api/v1/integrations/tally/outbox/{job_id}/ack",
            json={
                "tally_guid": tally_guid,
                "tally_master_id": "54321",
                "tally_voucher_number": tally_vch_num,
            },
            headers=agent_headers,
        )
        assert ack_repeat.status_code == 200
        assert ack_repeat.json()["status"] == "CONFIRMED"

        # 3. Simulate Tally -> Backend sync with this receipt (LOOP PREVENTION)
        sync_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "payments": [
                {
                    "source_reference": tally_guid,
                    "receipt_number": tally_vch_num,
                    "customer_name": env["customer"].name,
                    "payment_date": date.today().isoformat(),
                    "amount": 2500.00,
                    "payment_method": "ONLINE",
                    "notes": f"FT:{payment_id} | Online sync",
                }
            ],
        }
        sync_res = await client.post(
            "/api/v1/integrations/tally/sync/payments",
            json=sync_batch,
            headers=agent_headers,
        )
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["created_count"] == 0
        assert sync_data["updated_count"] == 1

        # Verify no duplicate payment was created
        async with AsyncSessionLocal() as session:
            all_pmts = (
                await session.execute(
                    select(Payment).where(Payment.customer_id == env["customer"].id)
                )
            ).scalars().all()
            assert len(all_pmts) == 1
            assert all_pmts[0].id == payment_id
            assert all_pmts[0].source_reference == tally_guid


@pytest.mark.asyncio
@requires_db
async def test_outbox_failure_and_retry_backoff(writeback_test_env):
    """TEST H: Failure recording with backoff and terminal failure."""
    env = writeback_test_env
    admin = env["admin"]
    admin_token = create_access_token(subject=str(admin.id), role=Role.ADMIN.value)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register Agent
        reg_res = await client.post(
            "/api/v1/integrations/tally/agents",
            json={"name": f"Agent {uuid.uuid4().hex[:4]}", "organization_id": "test_org"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        agent_headers = {
            "X-Agent-Id": reg_res.json()["agent"]["id"],
            "X-Agent-Key": reg_res.json()["api_key"],
        }

        # Create payment
        async with AsyncSessionLocal() as session:
            data = PaymentCreate(
                visit_id=env["visit"].id,
                amount=Decimal("3000.00"),
                payment_method=PaymentMethod.CASH,
                payment_date=date.today(),
                idempotency_key=f"fail_test_{uuid.uuid4().hex[:6]}",
            )
            pmt = await create_payment(data, env["employee_user"], session)
            pmt_id = pmt.id

        # Claim
        claim_res = await client.get("/api/v1/integrations/tally/outbox/pending", headers=agent_headers)
        job = next(j for j in claim_res.json() if j["entity_id"] == str(pmt_id))
        job_id = job["id"]

        # 1. Retryable failure -> PENDING with next_retry_at scheduled
        fail_res = await client.post(
            f"/api/v1/integrations/tally/outbox/{job_id}/fail",
            json={"error_message": "Tally connection timed out", "is_retryable": True},
            headers=agent_headers,
        )
        assert fail_res.status_code == 200
        assert fail_res.json()["status"] == "PENDING"

        # 2. Non-retryable failure (e.g. invalid ledger) -> FAILED
        fail_term = await client.post(
            f"/api/v1/integrations/tally/outbox/{job_id}/fail",
            json={"error_message": "Ledger 'XYZ' does not exist", "is_retryable": False},
            headers=agent_headers,
        )
        assert fail_term.status_code == 200
        assert fail_term.json()["status"] == "FAILED"
