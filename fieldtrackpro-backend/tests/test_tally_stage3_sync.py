"""
Stage 3 backend mapping: ledger GUID identity, Tally-authoritative master fields,
voucher-GUID invoice identity, real due dates / bill names, and validated
replacement of guessed receipt allocations by Tally's bill-wise allocations.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA
from app.models.tally_audit import TallyAuditLog
from app.models.user import Role, User
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]
D = Decimal


@pytest_asyncio.fixture
async def env():
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as s:
        admin = User(email=f"admin_s3_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"), role=Role.ADMIN, is_active=True)
        s.add(admin)
        await s.commit()
        admin_id = admin.id
    admin_h = {"Authorization": f"Bearer {create_access_token(subject=str(admin_id), role=Role.ADMIN.value)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        reg = await c.post("/api/v1/integrations/tally/agents", json={"name": f"S3{tag}", "organization_id": "o"}, headers=admin_h)
        assert reg.status_code == 201, reg.text
        agent_h = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
        yield {"c": c, "tag": tag, "agent_h": agent_h, "admin_id": admin_id}


async def _post(e, kind, items):
    r = await e["c"].post(f"/api/v1/integrations/tally/sync/{kind}",
                          json={"batch_id": str(uuid.uuid4()), kind: items}, headers=e["agent_h"])
    assert r.status_code == 200, r.text
    return r.json()


async def _customer_by_guid(guid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Customer).where(Customer.tally_guid == guid))).scalar_one_or_none()


async def test_ledger_guid_survives_rename_and_stores_mobile_email_balance(env):
    guid = f"G-LED-{env['tag']}"
    name = f"S3 Store {env['tag']}"
    await _post(env, "customers", [{"source_reference": guid, "name": name, "address": "Kidwai Nagar",
                                    "mobile": "9876543210", "email": "s3@example.com", "closing_balance": -4800.00}])
    c = await _customer_by_guid(guid)
    assert c is not None and c.name == name
    assert c.mobile_number == "9876543210" and c.email == "s3@example.com"
    assert c.contact_number == "9876543210", "no phone in Tally: mobile is the contact number"
    assert c.tally_closing_balance == D("-4800.00") and c.tally_closing_balance_at is not None

    renamed = f"{name} (Renamed)"
    res = await _post(env, "customers", [{"source_reference": guid, "name": renamed, "address": "",
                                          "closing_balance": -100.00}])
    assert res["created_count"] == 0 and res["updated_count"] == 1
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Customer).where(Customer.tally_guid == guid))).scalars().all()
    assert len(rows) == 1, "a renamed ledger is the same outlet"
    assert rows[0].name == renamed
    assert rows[0].address == "Kidwai Nagar", "an empty Tally field does not wipe the stored value"
    assert rows[0].tally_closing_balance == D("-100.00")


async def test_existing_outlet_adopts_guid_tally_values_win_and_reminder_clears(env):
    name = f"S3 Legacy {env['tag']}"
    async with AsyncSessionLocal() as s:
        s.add(Customer(name=name, address="Old address", contact_person="Old", created_by=env["admin_id"],
                       needs_tally_entry=True))
        await s.commit()
    guid = f"G-LEG-{env['tag']}"
    await _post(env, "customers", [{"source_reference": guid, "name": name, "address": "New address from Tally",
                                    "contact_person": "Ravi", "gst_number": "09ABCDE1234F1Z5"}])
    c = await _customer_by_guid(guid)
    assert c is not None and c.address == "New address from Tally" and c.contact_person == "Ravi"
    assert c.gst_number == "09ABCDE1234F1Z5" and c.needs_tally_entry is False
    # The agent's name-based fallback reference is not an identity.
    await _post(env, "customers", [{"source_reference": f"TALLY_LEDGER_{name}", "name": name}])
    assert (await _customer_by_guid(f"TALLY_LEDGER_{name}")) is None


async def _make_customer(env, suffix="A"):
    guid = f"G-C{suffix}-{env['tag']}"
    name = f"S3 Party {suffix} {env['tag']}"
    await _post(env, "customers", [{"source_reference": guid, "name": name}])
    return name, (await _customer_by_guid(guid)).id


async def test_voucher_guid_identity_reused_number_and_party_change(env):
    name_a, cid_a = await _make_customer(env, "A")
    name_b, cid_b = await _make_customer(env, "B")
    num = f"SGRG/S3/{env['tag']}"
    base = {"invoice_number": num, "customer_name": name_a, "amount": 1000.00, "invoice_date": "2026-05-01"}
    await _post(env, "invoices", [{**base, "source_reference": f"GI-1-{env['tag']}", "due_date": "2026-05-31",
                                   "bill_name": f"BILL-{env['tag']}"}])
    # Same number for the same outlet in the next financial year (numbering restarted),
    # different voucher GUID: a second invoice; the first is never overwritten.
    res = await _post(env, "invoices", [
        {**base, "source_reference": f"GI-2-{env['tag']}", "invoice_date": "2027-04-03", "amount": 50.00}])
    assert res["created_count"] == 1 and res["failed_count"] == 0, res
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Invoice).where(Invoice.invoice_number == num))).scalars().all()
    assert sorted(r.financial_year for r in rows) == ["2026-27", "2027-28"]
    first = next(r for r in rows if r.source_reference == f"GI-1-{env['tag']}")
    assert first.amount == D("1000.00"), "not overwritten by the other voucher"
    assert first.due_date == date(2026, 5, 31) and first.tally_bill_name == f"BILL-{env['tag']}"
    # A voucher GUID can never become a second invoice.
    res = await _post(env, "invoices", [{**base, "source_reference": f"GI-2-{env['tag']}", "invoice_date": "2027-04-03",
                                         "amount": 60.00}])
    assert res["created_count"] == 0 and res["updated_count"] == 1

    # Party changed in Tally and the credit period removed: the invoice follows the party,
    # and the due date becomes unknown rather than keeping the old value.
    res = await _post(env, "invoices", [{**base, "customer_name": name_b, "source_reference": f"GI-1-{env['tag']}"}])
    assert res["created_count"] == 0 and res["updated_count"] == 1
    async with AsyncSessionLocal() as s:
        moved = (await s.execute(select(Invoice).where(Invoice.source_reference == f"GI-1-{env['tag']}"))).scalar_one()
    assert moved.customer_id == cid_b and moved.due_date is None


async def _payment_allocs(guid):
    async with AsyncSessionLocal() as s:
        p = (await s.execute(select(Payment).where(Payment.source_reference == guid))).scalar_one()
        rows = (await s.execute(select(PIA).where(PIA.payment_id == p.id))).scalars().all()
        return p, sorted(((r.bill_type, r.allocated_amount, r.invoice_id) for r in rows), key=str)


async def test_tally_bill_allocations_replace_guessed_fifo_links(env):
    name, cid = await _make_customer(env, "P")
    bill = f"KNP-{env['tag']}"
    await _post(env, "invoices", [
        {"source_reference": f"GI-OLD-{env['tag']}", "invoice_number": f"S3/OLD/{env['tag']}", "customer_name": name,
         "amount": 3000.00, "invoice_date": "2026-04-05"},
        {"source_reference": f"GI-KNP-{env['tag']}", "invoice_number": f"S3/KNP/{env['tag']}", "bill_name": bill,
         "customer_name": name, "amount": 10000.00, "invoice_date": "2026-05-01"},
    ])
    async with AsyncSessionLocal() as s:
        inv_old = (await s.execute(select(Invoice.id).where(Invoice.source_reference == f"GI-OLD-{env['tag']}"))).scalar_one()
        inv_knp = (await s.execute(select(Invoice.id).where(Invoice.source_reference == f"GI-KNP-{env['tag']}"))).scalar_one()

    rguid = f"GR-{env['tag']}"
    receipt = {"source_reference": rguid, "receipt_number": "R-1", "customer_name": name,
               "payment_date": "2026-05-10", "amount": 8000.00, "payment_method": "ONLINE"}
    async with AsyncSessionLocal() as s:
        p0 = Payment(customer_id=cid, amount=D("8000.00"), payment_method="ONLINE", payment_date=date(2026, 5, 10),
                     status="VERIFIED", source="TALLY", source_reference=rguid, created_by=env["admin_id"])
        s.add(p0)
        await s.flush()
        # A guessed FIFO link left by the old sync, still in the data.
        s.add(PIA(payment_id=p0.id, invoice_id=inv_old, bill_name="x", bill_type="FIFO_ON_ACCOUNT",
                  allocated_amount=D("3000.00")))
        await s.commit()
    p, rows = await _payment_allocs(rguid)
    assert {r[0] for r in rows} == {"FIFO_ON_ACCOUNT"}

    res = await _post(env, "payments", [{**receipt, "bill_allocations": [
        {"bill_name": bill, "bill_type": "Agst Ref", "amount": 5000.00},
        {"bill_name": "OLD-2025-77", "bill_type": "Agst Ref", "amount": 2000.00},
        {"bill_name": "On Account", "bill_type": "On Account", "amount": 1000.00},
    ]}])
    assert res["updated_count"] == 1 and not res["errors"]
    p2, rows = await _payment_allocs(rguid)
    assert p2.id == p.id and p2.amount == D("8000.00"), "the payment record and amount are preserved"
    assert rows == [("Agst Ref", D("5000.00"), inv_knp)], "only Tally's real link remains; FIFO guess removed"
    assert p2.invoice_id == inv_knp
    async with AsyncSessionLocal() as s:
        log = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "SYNC_PAYMENTS")
                               .order_by(TallyAuditLog.timestamp.desc()).limit(1))).scalar_one()
    assert log.details["bill_allocations_replaced_count"] == 1
    assert log.details["unresolved_bill_count"] == 1 and log.details["unresolved_bill_amount"] == "2000.00"
    assert inv_old not in [r[2] for r in rows], "the FIFO guess on the older invoice is gone"


async def test_receipt_without_bill_allocation_stays_unallocated_and_is_reported(env):
    name, cid = await _make_customer(env, "U")
    await _post(env, "invoices", [{"source_reference": f"GI-U-{env['tag']}", "invoice_number": f"S3/U/{env['tag']}",
                                   "customer_name": name, "amount": 10000.00, "invoice_date": "2026-05-01",
                                   "brand": "USHA"}])
    rguid = f"GRU-{env['tag']}"
    res = await _post(env, "payments", [{"source_reference": rguid, "customer_name": name, "payment_date": "2026-05-10",
                                         "amount": 4000.00, "payment_method": "CASH",
                                         "brand_allocations": [{"brand": "USHA", "allocated_amount": 4000.00}]}])
    assert res["created_count"] == 1
    p, rows = await _payment_allocs(rguid)
    assert rows == [] and p.invoice_id is None, "no guessed oldest-first link"
    async with AsyncSessionLocal() as s:
        log = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "SYNC_PAYMENTS")
                               .order_by(TallyAuditLog.timestamp.desc()).limit(1))).scalar_one()
        admin = (await s.execute(select(User).where(User.id == env["admin_id"]))).scalar_one()
        from app.services import account_service
        acct = await account_service.get_account_summary(customer_id=cid, current_user=admin, session=s)
    assert log.details["receipts_without_bill_allocation_count"] == 1
    assert log.details["receipts_without_bill_allocation_amount"] == "4000.00"
    # The invoice itself is not marked paid, but the outlet balance nets the on-account money (as Tally's ledger does).
    assert acct.total_outstanding == D("6000.00")


async def test_over_allocated_bill_data_is_rejected_and_links_kept(env):
    name, _ = await _make_customer(env, "Q")
    await _post(env, "invoices", [{"source_reference": f"GI-Q-{env['tag']}", "invoice_number": f"S3/Q/{env['tag']}",
                                   "customer_name": name, "amount": 900.00, "invoice_date": "2026-05-01"}])
    rguid = f"GRQ-{env['tag']}"
    receipt = {"source_reference": rguid, "customer_name": name, "payment_date": "2026-05-10",
               "amount": 500.00, "payment_method": "CASH"}
    await _post(env, "payments", [receipt])
    _, before = await _payment_allocs(rguid)
    res = await _post(env, "payments", [{**receipt, "bill_allocations": [
        {"bill_name": f"S3/Q/{env['tag']}", "bill_type": "Agst Ref", "amount": 700.00}]}])
    assert res["errors"] and "exceed" in res["errors"][0]["error"]
    _, after = await _payment_allocs(rguid)
    assert after == before
