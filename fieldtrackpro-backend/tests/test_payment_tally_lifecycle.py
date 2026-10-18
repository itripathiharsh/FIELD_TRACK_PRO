"""
Regression: Tally is the final truth for outstanding balances.

employee records (PENDING_VERIFICATION) -> admin verifies against the bank
(VERIFIED) -> sync agent writes the receipt to Tally (write-back job CONFIRMED).
Only a CONFIRMED job lets invoice remaining / brand / customer account drop.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment
from app.models.tally_writeback import TallyWritebackQueue
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from tests.conftest import requires_db
from tests.tally_helpers import ack_payment_in_tally, fail_payment_in_tally

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def world():
    tag = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        admin = User(email=f"admin_tl_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"), role=Role.ADMIN, is_active=True)
        emp_user = User(email=f"emp_tl_{tag}@fieldtrack.test", password_hash=hash_password("Emp123!"), role=Role.EMPLOYEE, is_active=True)
        session.add_all([admin, emp_user])
        await session.flush()
        employee = Employee(user_id=emp_user.id, full_name=f"TL Rep {tag}", employee_code=f"REP-{tag.upper()}")
        session.add(employee)
        customer = Customer(name=f"Lifecycle Store {tag}", outlet_code=f"UPDL{tag.upper()}", address="x", created_by=admin.id)
        session.add(customer)
        await session.flush()
        visit = Visit(
            employee_id=employee.id, customer_id=customer.id, scheduled_at=datetime.now(timezone.utc),
            status=VisitStatus.COMPLETED, created_by=admin.id,
        )
        invoice = Invoice(
            customer_id=customer.id, invoice_number=f"INV-TL-{tag}", invoice_date=date.today(),
            amount=Decimal("10000.00"), brand="USHA", source=InvoiceSource.MANUAL, created_by=admin.id,
        )
        session.add_all([visit, invoice])
        await session.commit()
        env = {
            "admin_h": {"Authorization": f"Bearer {create_access_token(subject=str(admin.id), role=Role.ADMIN.value)}"},
            "emp_h": {"Authorization": f"Bearer {create_access_token(subject=str(emp_user.id), role=Role.EMPLOYEE.value)}"},
            "visit_id": str(visit.id),
            "customer_id": str(customer.id),
            "customer_name": customer.name,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
        }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        env["client"] = client
        yield env


async def _collect(w, amount="4000.00", invoice=True, allocations=None):
    body = {
        "visit_id": w["visit_id"], "amount": amount, "payment_method": "CASH",
        "payment_date": date.today().isoformat(),
    }
    if invoice:
        body["invoice_id"] = w["invoice_id"]
    if allocations:
        body["allocations"] = allocations
    r = await w["client"].post("/api/v1/payments", json=body, headers=w["emp_h"])
    assert r.status_code == 201, r.text
    return r.json()


async def _invoice(w):
    return (await w["client"].get(f"/api/v1/invoices/{w['invoice_id']}", headers=w["admin_h"])).json()


async def _account(w):
    return (await w["client"].get(f"/api/v1/customers/{w['customer_id']}/account", headers=w["admin_h"])).json()


def _assert_headline_matches_brands(acct):
    assert Decimal(acct["total_outstanding"]) == sum(
        (Decimal(b["total_outstanding"]) for b in acct["brand_summary"]), Decimal("0")
    )


async def _job_count(payment_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(func.count()).select_from(TallyWritebackQueue).where(TallyWritebackQueue.entity_id == uuid.UUID(payment_id))
            )
        ).scalar()


async def test_outstanding_drops_only_when_tally_confirms_and_exactly_once_after_readback(world):
    w, c = world, world["client"]
    created = await _collect(w)
    pid = created["id"]
    assert created["tally_status"] == "NOT_APPLICABLE"

    # Pending: nothing moves.
    inv = await _invoice(w)
    assert inv["remaining_amount"] == "10000.00" and inv["verified_awaiting_tally_amount"] == "0.00"

    # Verify WITHOUT a body still works -> AWAITING_TALLY, outstanding unchanged.
    v = await c.post(f"/api/v1/payments/{pid}/verify", headers=w["admin_h"])
    assert v.status_code == 200, v.text
    assert v.json()["tally_status"] == "AWAITING_TALLY"
    assert v.json()["tally_voucher_number"] is None
    inv = await _invoice(w)
    assert inv["remaining_amount"] == "10000.00"
    assert inv["verified_paid_amount"] == "0.00"
    assert inv["verified_awaiting_tally_amount"] == "4000.00"
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("10000.00")
    _assert_headline_matches_brands(acct)
    assert Decimal(acct["total_paid"]) == Decimal("0.00")
    assert Decimal(acct["verified_awaiting_tally_amount"]) == Decimal("4000.00")
    usha = {b["brand"]: b for b in acct["brand_summary"]}["USHA"]
    assert Decimal(usha["total_outstanding"]) == Decimal("10000.00")
    assert Decimal(usha["verified_awaiting_tally_amount"]) == Decimal("4000.00")

    # Agent writes the receipt and ACKs -> POSTED, outstanding drops.
    guid = await ack_payment_in_tally(pid, voucher="R-77")
    got = (await c.get(f"/api/v1/payments/{pid}", headers=w["admin_h"])).json()
    assert got["tally_status"] == "POSTED"
    assert got["tally_voucher_number"] == "R-77"
    assert got["tally_posted_at"] is not None
    inv = await _invoice(w)
    assert inv["remaining_amount"] == "6000.00" and inv["verified_paid_amount"] == "4000.00"
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("6000.00")
    assert Decimal(acct["total_paid"]) == Decimal("4000.00")
    _assert_headline_matches_brands(acct)
    assert Decimal(acct["verified_awaiting_tally_amount"]) == Decimal("0.00")

    # The sync agent reads the SAME receipt back from Tally (loop prevention via
    # source_reference == tally_guid / FT:{payment_id}). Twice, to be sure.
    reg = await c.post("/api/v1/integrations/tally/agents", json={"name": f"A{uuid.uuid4().hex[:4]}", "organization_id": "o"}, headers=w["admin_h"])
    assert reg.status_code == 201
    agent_h = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
    batch = {
        "batch_id": str(uuid.uuid4()),
        "payments": [{
            "source_reference": guid, "receipt_number": "R-77", "customer_name": w["customer_name"],
            "outlet_code": None, "payment_date": date.today().isoformat(), "amount": 4000.00,
            "payment_method": "CASH", "notes": f"FT:{pid} | Collection",
        }],
    }
    for _ in range(2):
        s = await c.post("/api/v1/integrations/tally/sync/payments", json=batch, headers=agent_h)
        assert s.status_code == 200, s.text
        assert s.json()["created_count"] == 0

    inv = await _invoice(w)
    assert inv["remaining_amount"] == "6000.00", "reduced exactly once, not twice"
    assert inv["verified_paid_amount"] == "4000.00"
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("6000.00")
    assert Decimal(acct["total_paid"]) == Decimal("4000.00")
    _assert_headline_matches_brands(acct)
    async with AsyncSessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(Payment).where(Payment.customer_id == uuid.UUID(w["customer_id"])))).scalar()
    assert n == 1


async def test_onaccount_allocated_payment_reads_back_once(world):
    """Invoice-less brand-allocated collection: ack nets outstanding; Tally read-back (FIFO on the
    invoice) must not net it a second time."""
    w, c = world, world["client"]
    p = await _collect(w, amount="3000.00", invoice=False, allocations=[{"brand": "USHA", "amount": "3000.00"}])
    await c.post(f"/api/v1/payments/{p['id']}/verify", headers=w["admin_h"])
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("10000.00")
    guid = await ack_payment_in_tally(p["id"])
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("7000.00")
    usha = {b["brand"]: b for b in acct["brand_summary"]}["USHA"]
    assert Decimal(usha["total_outstanding"]) == Decimal("7000.00")

    reg = await c.post("/api/v1/integrations/tally/agents", json={"name": f"B{uuid.uuid4().hex[:4]}", "organization_id": "o"}, headers=w["admin_h"])
    agent_h = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
    batch = {"batch_id": str(uuid.uuid4()), "payments": [{
        "source_reference": guid, "customer_name": w["customer_name"], "payment_date": date.today().isoformat(),
        "amount": 3000.00, "payment_method": "CASH", "notes": f"FT:{p['id']}",
    }]}
    assert (await c.post("/api/v1/integrations/tally/sync/payments", json=batch, headers=agent_h)).status_code == 200
    acct = await _account(w)
    assert Decimal(acct["total_outstanding"]) == Decimal("7000.00")
    assert (await _invoice(w))["remaining_amount"] == "7000.00"


async def test_failed_job_shows_failed_does_not_reduce_and_admin_can_retry(world):
    w, c = world, world["client"]
    p = await _collect(w)
    pid = p["id"]
    await c.post(f"/api/v1/payments/{pid}/verify", headers=w["admin_h"])
    # Retry is refused while not FAILED.
    assert (await c.post(f"/api/v1/payments/{pid}/tally-retry", headers=w["admin_h"])).status_code == 409

    await fail_payment_in_tally(pid, "Ledger 'Cash' not found", retryable=False)
    admin_view = (await c.get(f"/api/v1/payments/{pid}", headers=w["admin_h"])).json()
    emp_view = (await c.get(f"/api/v1/payments/{pid}", headers=w["emp_h"])).json()
    assert admin_view["tally_status"] == "FAILED" and emp_view["tally_status"] == "FAILED"
    assert "Ledger" in admin_view["tally_error"] and admin_view["tally_stuck"] is True
    assert emp_view["tally_error"] is None and emp_view["tally_stuck"] is None
    assert (await _invoice(w))["remaining_amount"] == "10000.00"
    assert Decimal((await _account(w))["total_outstanding"]) == Decimal("10000.00")

    # Stuck queue (admin) lists it; FAILED filter lists it.
    q = await c.get("/api/v1/payments/queue?stuck=true&limit=200", headers=w["admin_h"])
    assert pid in [x["id"] for x in q.json()]
    q = await c.get("/api/v1/payments/queue?tally_status=FAILED&limit=200", headers=w["admin_h"])
    assert pid in [x["id"] for x in q.json()]
    q = await c.get("/api/v1/payments/queue?tally_status=POSTED&limit=200", headers=w["admin_h"])
    assert pid not in [x["id"] for x in q.json()]

    # Employees cannot retry; admin retry resets the SAME job (no duplicate).
    assert (await c.post(f"/api/v1/payments/{pid}/tally-retry", headers=w["emp_h"])).status_code == 403
    r = await c.post(f"/api/v1/payments/{pid}/tally-retry", headers=w["admin_h"])
    assert r.status_code == 200, r.text
    assert r.json()["tally_status"] == "AWAITING_TALLY"
    assert await _job_count(pid) == 1
    assert (await c.post(f"/api/v1/payments/{pid}/tally-retry", headers=w["admin_h"])).status_code == 409

    await ack_payment_in_tally(pid)
    assert (await _invoice(w))["remaining_amount"] == "6000.00"


async def test_awaiting_older_than_30_minutes_is_stuck(world):
    w, c = world, world["client"]
    p = await _collect(w)
    pid = p["id"]
    v = await c.post(f"/api/v1/payments/{pid}/verify", headers=w["admin_h"])
    assert v.json()["tally_stuck"] is False
    q = await c.get("/api/v1/payments/queue?stuck=true&limit=200", headers=w["admin_h"])
    assert pid not in [x["id"] for x in q.json()]

    async with AsyncSessionLocal() as s:
        await s.execute(update(Payment).where(Payment.id == uuid.UUID(pid)).values(reviewed_at=datetime.now(timezone.utc) - timedelta(minutes=45)))
        await s.commit()
    got = (await c.get(f"/api/v1/payments/{pid}", headers=w["admin_h"])).json()
    assert got["tally_status"] == "AWAITING_TALLY" and got["tally_stuck"] is True
    q = await c.get("/api/v1/payments/queue?stuck=true&tally_status=AWAITING_TALLY&limit=200", headers=w["admin_h"])
    assert pid in [x["id"] for x in q.json()]


async def test_verify_with_bank_fields_and_visibility(world):
    w, c = world, world["client"]
    p = await _collect(w)
    body = {"bank_reference": "HDFC-REF-991", "bank_verified_on": date.today().isoformat(), "verified_note": "Matched statement line 12"}
    v = await c.post(f"/api/v1/payments/{p['id']}/verify", json=body, headers=w["admin_h"])
    assert v.status_code == 200, v.text
    j = v.json()
    assert j["bank_reference"] == "HDFC-REF-991" and j["bank_verified_on"] == date.today().isoformat()
    assert j["verified_note"] == "Matched statement line 12"
    # The bank record is also carried in the Tally write-back payload.
    async with AsyncSessionLocal() as s:
        job = (await s.execute(select(TallyWritebackQueue).where(TallyWritebackQueue.entity_id == uuid.UUID(p["id"])))).scalar_one()
        assert job.payload["bank_reference"] == "HDFC-REF-991"
    emp = (await c.get(f"/api/v1/payments/{p['id']}", headers=w["emp_h"])).json()
    assert emp["bank_reference"] is None and emp["verified_note"] is None and emp["bank_verified_on"] is None
    # `{}` body also fine; blank strings are normalised to null.
    p2 = await _collect(w, amount="100.00")
    v2 = await c.post(f"/api/v1/payments/{p2['id']}/verify", json={"bank_reference": "  "}, headers=w["admin_h"])
    assert v2.status_code == 200 and v2.json()["bank_reference"] is None


async def test_reject_rules_unchanged(world):
    w, c = world, world["client"]
    p1 = await _collect(w)
    # Reason is required.
    assert (await c.post(f"/api/v1/payments/{p1['id']}/reject", json={}, headers=w["admin_h"])).status_code == 422
    r = await c.post(f"/api/v1/payments/{p1['id']}/reject", json={"rejection_reason": "No bank credit"}, headers=w["admin_h"])
    assert r.status_code == 200 and r.json()["status"] == "REJECTED" and r.json()["tally_status"] == "NOT_APPLICABLE"
    # Verified payments can never be rejected (409), even once posted.
    p2 = await _collect(w, amount="500.00")
    await c.post(f"/api/v1/payments/{p2['id']}/verify", headers=w["admin_h"])
    assert (await c.post(f"/api/v1/payments/{p2['id']}/reject", json={"rejection_reason": "x"}, headers=w["admin_h"])).status_code == 409
    await ack_payment_in_tally(p2["id"])
    assert (await c.post(f"/api/v1/payments/{p2['id']}/reject", json={"rejection_reason": "x"}, headers=w["admin_h"])).status_code == 409


async def test_awaiting_money_still_blocks_over_collection(world):
    w, c = world, world["client"]
    p1 = await _collect(w, amount="9000.00")
    assert (await c.post(f"/api/v1/payments/{p1['id']}/verify", headers=w["admin_h"])).status_code == 200
    # Displayed outstanding is still 10,000 (not in Tally), but 9,000 is committed.
    body = {"visit_id": w["visit_id"], "invoice_id": w["invoice_id"], "amount": "2000.00", "payment_method": "CASH", "payment_date": date.today().isoformat()}
    r = await c.post("/api/v1/payments", json=body, headers=w["emp_h"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "PAYMENT_EXCEEDS_INVOICE_OUTSTANDING"


async def test_dashboard_collections_split(world):
    w, c = world, world["client"]

    async def kpis():
        r = await c.get("/api/v1/dashboard/summary", headers=w["admin_h"])
        assert r.status_code == 200, r.text
        k = r.json()["kpis"]
        return Decimal(str(k["total_collection"])), Decimal(str(k["total_collection_posted_in_tally"])), Decimal(str(k["total_collection_verified_awaiting_tally"]))

    base_total, base_posted, base_awaiting = await kpis()
    p = await _collect(w, amount="1234.00")
    assert await kpis() == (base_total, base_posted, base_awaiting)  # pending does not count
    await c.post(f"/api/v1/payments/{p['id']}/verify", headers=w["admin_h"])
    t, po, aw = await kpis()
    assert (t - base_total, po - base_posted, aw - base_awaiting) == (Decimal("1234.00"), Decimal("0"), Decimal("1234.00"))
    await ack_payment_in_tally(p["id"])
    t, po, aw = await kpis()
    assert (t - base_total, po - base_posted, aw - base_awaiting) == (Decimal("1234.00"), Decimal("1234.00"), Decimal("0"))
