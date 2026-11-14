"""
Regression: Tally write-back OFF (production setting). The accountant keys each
receipt into Tally by hand, the sync agent imports it as a TALLY payment, and an
admin links the employee's field collection to it. Money is counted exactly once;
outstanding only drops for receipts that are in Tally; invoices are Tally-only.

Each test isolates itself with its own zone (territory) and, where period totals
are involved, a calendar month no other test uses - so assertions stay exact on a
shared development database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment, PaymentSource
from app.models.tally_audit import TallyAuditLog
from app.models.tally_writeback import TallyWritebackQueue
from app.models.territory import Territory
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.services.tally_writeback_service import notify_stuck_tally_posts
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]

D = Decimal
# A month no other test touches: period-level assertions use before/after deltas.
TEST_MONTH = date(2011, 7, 1)


@pytest.fixture(autouse=True)
def _writeback_off(monkeypatch):
    monkeypatch.setattr(settings, "tally_writeback_enabled", False)


async def _make_world(day: date, with_invoice: bool = True):
    tag = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as s:
        admin = User(email=f"admin_lk_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"), role=Role.ADMIN, is_active=True)
        emp_user = User(email=f"emp_lk_{tag}@fieldtrack.test", password_hash=hash_password("Emp123!"), role=Role.EMPLOYEE, is_active=True)
        s.add_all([admin, emp_user])
        await s.flush()
        zone = Territory(name=f"LinkZone {tag}")
        s.add(zone)
        await s.flush()
        employee = Employee(user_id=emp_user.id, full_name=f"LK Rep {tag}", employee_code=f"REP-LK-{tag.upper()}")
        customer = Customer(name=f"Link Store {tag}", outlet_code=f"UPLK{tag.upper()}", address="x",
                            created_by=admin.id, territory_id=zone.id)
        s.add_all([employee, customer])
        await s.flush()
        visit = Visit(employee_id=employee.id, customer_id=customer.id, scheduled_at=datetime.now(timezone.utc),
                      status=VisitStatus.COMPLETED, created_by=admin.id)
        s.add(visit)
        invoice = None
        if with_invoice:
            invoice = Invoice(customer_id=customer.id, invoice_number=f"SGRG/LK/{tag}", invoice_date=day,
                              amount=D("10000.00"), brand="USHA", source=InvoiceSource.TALLY,
                              source_reference=f"GUID-INV-{tag}", created_by=admin.id)
            s.add(invoice)
        await s.commit()
        return {
            "tag": tag,
            "day": day,
            "admin_id": admin.id,
            "admin_h": {"Authorization": f"Bearer {create_access_token(subject=str(admin.id), role=Role.ADMIN.value)}"},
            "emp_h": {"Authorization": f"Bearer {create_access_token(subject=str(emp_user.id), role=Role.EMPLOYEE.value)}"},
            "employee_id": str(employee.id),
            "visit_id": str(visit.id),
            "customer_id": str(customer.id),
            "customer_name": customer.name,
            "outlet_code": customer.outlet_code,
            "zone_id": str(zone.id),
            "invoice_id": str(invoice.id) if invoice else None,
            "invoice_number": f"SGRG/LK/{tag}",
        }


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def w(client):
    env = await _make_world(date.today())
    env["client"] = client
    reg = await client.post("/api/v1/integrations/tally/agents",
                            json={"name": f"LK{env['tag']}", "organization_id": "o"}, headers=env["admin_h"])
    assert reg.status_code == 201, reg.text
    env["agent_h"] = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
    return env


async def _collect(w, amount, invoice=True, day=None, method="CASH", utr=None):
    body = {"visit_id": w["visit_id"], "amount": amount, "payment_method": method,
            "payment_date": (day or w["day"]).isoformat()}
    if invoice:
        body["invoice_id"] = w["invoice_id"]
    if utr:
        body["utr_reference"] = utr
    r = await w["client"].post("/api/v1/payments", json=body, headers=w["emp_h"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _verify(w, pid):
    r = await w["client"].post(f"/api/v1/payments/{pid}/verify", headers=w["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


async def _import_receipt(w, amount, day=None, utr=None, customer_name=None, bill=None):
    """The accountant keyed a receipt into Tally; the agent imports it (no FT: marker).
    `bill`: the invoice number the receipt is entered against ("Agst Ref"); without it
    the receipt is on-account in Tally (nets the outlet balance, settles no invoice)."""
    guid = f"GUID-RCPT-{uuid.uuid4()}"
    item = {"source_reference": guid, "receipt_number": f"R-{guid[-6:]}",
            "customer_name": customer_name or w["customer_name"], "outlet_code": None,
            "payment_date": (day or w["day"]).isoformat(), "amount": float(amount),
            "payment_method": "ONLINE" if utr else "CASH", "notes": "Being Cash Rec.",
            # The agent resolves the receipt's brand from the same party ledger as the invoice.
            "brand_allocations": [{"brand": "USHA", "allocated_amount": float(amount)}]}
    if utr:
        item["utr_reference"] = utr
    if bill:
        item["bill_allocations"] = [{"bill_name": bill, "bill_type": "Agst Ref", "amount": float(amount)}]
    r = await w["client"].post("/api/v1/integrations/tally/sync/payments",
                               json={"batch_id": str(uuid.uuid4()), "payments": [item]}, headers=w["agent_h"])
    assert r.status_code == 200 and r.json()["created_count"] == 1, r.text
    async with AsyncSessionLocal() as s:
        return str((await s.execute(select(Payment.id).where(Payment.source_reference == guid))).scalar_one())


async def _link(w, pid, rid, headers=None):
    return await w["client"].post(f"/api/v1/payments/{pid}/link-tally-receipt",
                                  json={"tally_receipt_payment_id": rid}, headers=headers or w["admin_h"])


async def _payment(w, pid):
    return (await w["client"].get(f"/api/v1/payments/{pid}", headers=w["admin_h"])).json()


async def _account(w):
    return (await w["client"].get(f"/api/v1/customers/{w['customer_id']}/account", headers=w["admin_h"])).json()


async def _kpis(w, month: str | None = None):
    params = {"zone_id": w["zone_id"]}
    if month:
        params["month"] = month
    r = await w["client"].get("/api/v1/dashboard/summary", params=params, headers=w["admin_h"])
    assert r.status_code == 200, r.text
    k = r.json()["kpis"]
    return D(str(k["total_collection"])), D(str(k["total_collection_posted_in_tally"])), D(str(k["total_collection_verified_awaiting_tally"]))


# ---------------------------------------------------------------------------
# Lifecycle with write-back off
# ---------------------------------------------------------------------------

async def test_verify_creates_no_writeback_job_and_awaiting_is_not_stuck(w):
    c = w["client"]
    pid = await _collect(w, "4000.00")
    v = await _verify(w, pid)
    assert v["tally_status"] == "AWAITING_TALLY" and v["tally_stuck"] is False
    async with AsyncSessionLocal() as s:
        n = (await s.execute(select(func.count()).select_from(TallyWritebackQueue)
                             .where(TallyWritebackQueue.entity_id == uuid.UUID(pid)))).scalar()
        assert n == 0, "no job is created for an agent that will never process it"
        await s.execute(update(Payment).where(Payment.id == uuid.UUID(pid))
                        .values(reviewed_at=datetime.now(timezone.utc) - timedelta(hours=3)))
        await s.commit()
    got = await _payment(w, pid)
    assert got["tally_status"] == "AWAITING_TALLY" and got["tally_stuck"] is False
    q = await c.get("/api/v1/payments/queue?stuck=true&limit=200", headers=w["admin_h"])
    assert pid not in [x["id"] for x in q.json()]
    async with AsyncSessionLocal() as s:
        assert await notify_stuck_tally_posts(s) == 0
    r = await c.post(f"/api/v1/payments/{pid}/tally-retry", headers=w["admin_h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "TALLY_WRITEBACK_DISABLED"
    # Outstanding unchanged: the money is not in Tally yet.
    acct = await _account(w)
    assert D(acct["total_outstanding"]) == D("10000.00")
    assert D(acct["verified_awaiting_tally_amount"]) == D("4000.00")


async def test_manual_tally_entry_is_counted_once_after_admin_link(w):
    base = await _kpis(w)
    pid = await _collect(w, "4000.00")
    await _verify(w, pid)
    t, po, aw = await _kpis(w)
    assert (t - base[0], po - base[1], aw - base[2]) == (D("4000.00"), D("0"), D("4000.00"))

    # Accountant keys the receipt into Tally; the agent imports it as a separate TALLY payment.
    rid = await _import_receipt(w, "4000.00", bill=w["invoice_number"])
    acct = await _account(w)
    assert D(acct["total_outstanding"]) == D("6000.00"), "the Tally receipt settles the invoice (Agst Ref)"
    t, po, aw = await _kpis(w)
    # Until an admin confirms the match, both rows exist (the collection is still awaiting).
    assert (t - base[0], po - base[1], aw - base[2]) == (D("8000.00"), D("4000.00"), D("4000.00"))
    assert (await _payment(w, pid))["tally_status"] == "AWAITING_TALLY"

    r = await _link(w, pid, rid)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["tally_status"] == "POSTED"
    assert got["tally_receipt_payment_id"] == rid and got["tally_posted_at"] is not None

    t, po, aw = await _kpis(w)
    assert (t - base[0], po - base[1], aw - base[2]) == (D("4000.00"), D("4000.00"), D("0")), "counted once"
    assert t - base[0] == (po - base[1]) + (aw - base[2])
    acct = await _account(w)
    assert D(acct["total_outstanding"]) == D("6000.00"), "reduced once, by the receipt, not twice"
    assert D(acct["verified_awaiting_tally_amount"]) == D("0.00")
    inv = (await w["client"].get(f"/api/v1/invoices/{w['invoice_id']}", headers=w["admin_h"])).json()
    assert inv["remaining_amount"] == "6000.00" and inv["verified_awaiting_tally_amount"] == "0.00"
    # The employee sees their collection as posted.
    emp_view = (await w["client"].get(f"/api/v1/payments/{pid}", headers=w["emp_h"])).json()
    assert emp_view["tally_status"] == "POSTED"
    # Queue filters follow the derived status.
    q = await w["client"].get("/api/v1/payments/queue?tally_status=POSTED&limit=200", headers=w["admin_h"])
    assert pid in [x["id"] for x in q.json()]
    q = await w["client"].get("/api/v1/payments/queue?tally_status=AWAITING_TALLY&limit=200", headers=w["admin_h"])
    assert pid not in [x["id"] for x in q.json()]
    async with AsyncSessionLocal() as s:
        ops = (await s.execute(select(TallyAuditLog.operation).where(
            TallyAuditLog.details["payment_id"].as_string() == pid))).scalars().all()
    assert "PAYMENT_TALLY_LINK" in ops


async def test_unlink_restores_awaiting_and_requires_reason(w):
    base = await _kpis(w)
    pid = await _collect(w, "2500.00")
    await _verify(w, pid)
    rid = await _import_receipt(w, "2500.00")
    assert (await _link(w, pid, rid)).status_code == 200
    c = w["client"]
    r = await c.post(f"/api/v1/payments/{pid}/unlink-tally-receipt", json={"reason": "  "}, headers=w["admin_h"])
    assert r.status_code == 422
    r = await c.post(f"/api/v1/payments/{pid}/unlink-tally-receipt", json={"reason": "Wrong receipt"}, headers=w["emp_h"])
    assert r.status_code == 403
    r = await c.post(f"/api/v1/payments/{pid}/unlink-tally-receipt", json={"reason": "Wrong receipt"}, headers=w["admin_h"])
    assert r.status_code == 200, r.text
    assert r.json()["tally_status"] == "AWAITING_TALLY" and r.json()["tally_receipt_payment_id"] is None
    t, po, aw = await _kpis(w)
    assert (t - base[0], po - base[1], aw - base[2]) == (D("5000.00"), D("2500.00"), D("2500.00"))
    r = await c.post(f"/api/v1/payments/{pid}/unlink-tally-receipt", json={"reason": "again"}, headers=w["admin_h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYMENT_NOT_LINKED"
    async with AsyncSessionLocal() as s:
        ops = (await s.execute(select(TallyAuditLog.operation).where(
            TallyAuditLog.details["payment_id"].as_string() == pid))).scalars().all()
    assert "PAYMENT_TALLY_LINK" in ops and "PAYMENT_TALLY_UNLINK" in ops


async def test_link_validation(w):
    c = w["client"]
    rid = await _import_receipt(w, "1000.00")
    pending = await _collect(w, "500.00")
    r = await _link(w, pending, rid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYMENT_NOT_VERIFIED"

    pid = await _collect(w, "500.00")
    await _verify(w, pid)
    assert (await _link(w, pid, rid, headers=w["emp_h"])).status_code == 403
    r = await _link(w, pid, str(uuid.uuid4()))
    assert r.status_code == 404 and r.json()["error"]["code"] == "TALLY_RECEIPT_NOT_FOUND"
    r = await _link(w, pid, pending)  # a field collection is not a Tally receipt
    assert r.status_code == 422 and r.json()["error"]["code"] == "RECEIPT_NOT_FROM_TALLY"
    r = await _link(w, rid, rid)  # a Tally receipt is not a field collection
    assert r.status_code == 422 and r.json()["error"]["code"] == "PAYMENT_NOT_FIELD_COLLECTION"

    other = await _make_world(date.today(), with_invoice=False)
    foreign = await _import_receipt(w, "500.00", customer_name=other["customer_name"])
    r = await _link(w, pid, foreign)
    assert r.status_code == 422 and r.json()["error"]["code"] == "RECEIPT_OUTLET_MISMATCH"

    small = await _import_receipt(w, "100.00")
    r = await _link(w, pid, small)
    assert r.status_code == 422 and r.json()["error"]["code"] == "RECEIPT_AMOUNT_EXCEEDED"

    assert (await _link(w, pid, rid)).status_code == 200
    r = await _link(w, pid, rid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYMENT_ALREADY_LINKED"


async def test_several_collections_share_one_receipt_up_to_its_amount(w):
    base = await _kpis(w)
    a = await _collect(w, "3000.00", invoice=False)
    b = await _collect(w, "2000.00", invoice=False)
    extra = await _collect(w, "1000.00", invoice=False)
    for p in (a, b, extra):
        await _verify(w, p)
    rid = await _import_receipt(w, "5000.00")
    assert (await _link(w, a, rid)).status_code == 200
    assert (await _link(w, b, rid)).status_code == 200
    r = await _link(w, extra, rid)
    assert r.status_code == 422 and r.json()["error"]["code"] == "RECEIPT_AMOUNT_EXCEEDED"
    t, po, aw = await _kpis(w)
    # 5000 receipt (posted, once) + 1000 still awaiting.
    assert (t - base[0], po - base[1], aw - base[2]) == (D("6000.00"), D("5000.00"), D("1000.00"))


async def test_suggestions_are_ranked_and_never_link(w):
    pid = await _collect(w, "4000.00", invoice=False, method="ONLINE", utr="UTR998877665544")
    await _verify(w, pid)
    day = w["day"]
    by_utr = await _import_receipt(w, "4000.00", day=day + timedelta(days=3), utr="utr998877665544")
    by_amount = await _import_receipt(w, "4000.00", day=day + timedelta(days=1))
    other_amount = await _import_receipt(w, "9000.00", day=day)
    await _import_receipt(w, "4000.00", day=day + timedelta(days=10))  # outside the default window
    too_small = await _import_receipt(w, "3999.00", day=day)

    r = await w["client"].get(f"/api/v1/payments/{pid}/tally-receipt-candidates", headers=w["admin_h"])
    assert r.status_code == 200, r.text
    got = r.json()
    ids = [x["payment_id"] for x in got]
    assert ids == [by_utr, by_amount, other_amount]
    assert too_small not in ids
    assert got[0]["match_reasons"] == ["UTR", "AMOUNT"]
    assert got[1]["match_reasons"] == ["AMOUNT"] and got[2]["match_reasons"] == []
    assert D(got[2]["available_amount"]) == D("9000.00")
    assert (await _payment(w, pid))["tally_status"] == "AWAITING_TALLY", "suggesting never links"
    wide = await w["client"].get(f"/api/v1/payments/{pid}/tally-receipt-candidates?window_days=15", headers=w["admin_h"])
    assert len(wide.json()) == 4
    assert (await w["client"].get(f"/api/v1/payments/{pid}/tally-receipt-candidates", headers=w["emp_h"])).status_code == 403


async def test_employee_scoped_collections_keep_linked_money(w):
    """A Tally receipt has no employee; the linked collection is what credits the employee."""
    pid = await _collect(w, "1500.00")
    await _verify(w, pid)
    month = w["day"].strftime("%Y-%m")

    async def emp_kpis():
        r = await w["client"].get("/api/v1/dashboard/summary",
                                  params={"zone_id": w["zone_id"], "employee_id": w["employee_id"], "month": month},
                                  headers=w["admin_h"])
        assert r.status_code == 200, r.text
        k = r.json()["kpis"]
        return D(str(k["total_collection_posted_in_tally"])), D(str(k["total_collection_verified_awaiting_tally"]))

    assert await emp_kpis() == (D("0"), D("1500.00"))
    rid = await _import_receipt(w, "1500.00")
    assert (await _link(w, pid, rid)).status_code == 200
    assert await emp_kpis() == (D("1500.00"), D("0"))


# ---------------------------------------------------------------------------
# Invoices are Tally-only
# ---------------------------------------------------------------------------

async def test_non_tally_invoice_is_not_part_of_the_books(w):
    c = w["client"]
    async with AsyncSessionLocal() as s:
        legacy = Invoice(customer_id=uuid.UUID(w["customer_id"]), invoice_number=f"OLD-{w['tag']}",
                         invoice_date=w["day"], amount=D("5000.00"), brand="USHA",
                         source=InvoiceSource.MANUAL, created_by=w["admin_id"])
        s.add(legacy)
        await s.commit()
        legacy_id = str(legacy.id)
    acct = await _account(w)
    assert D(acct["total_outstanding"]) == D("10000.00"), "only the Tally invoice counts"
    listed = (await c.get(f"/api/v1/customers/{w['customer_id']}/invoices", headers=w["admin_h"])).json()
    assert [i["id"] for i in listed] == [w["invoice_id"]]
    body = {"visit_id": w["visit_id"], "invoice_id": legacy_id, "amount": "100.00",
            "payment_method": "CASH", "payment_date": w["day"].isoformat()}
    r = await c.post("/api/v1/payments", json=body, headers=w["emp_h"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVOICE_NOT_IN_TALLY"
    # Recording it as an advance (no invoice) still works: field collection is never blocked.
    body.pop("invoice_id")
    assert (await c.post("/api/v1/payments", json=body, headers=w["emp_h"])).status_code == 201


async def test_tally_sync_relabels_a_matching_legacy_invoice(w):
    number = f"MIX-{w['tag']}"
    async with AsyncSessionLocal() as s:
        s.add(Invoice(customer_id=uuid.UUID(w["customer_id"]), invoice_number=number, invoice_date=w["day"],
                      amount=D("700.00"), source=InvoiceSource.EXCEL_IMPORT, created_by=w["admin_id"]))
        await s.commit()
    batch = {"batch_id": str(uuid.uuid4()), "invoices": [{
        "source_reference": f"GUID-MIX-{w['tag']}", "invoice_number": number, "outlet_code": w["outlet_code"],
        "customer_name": w["customer_name"], "invoice_date": w["day"].isoformat(), "amount": 750.00,
    }]}
    r = await w["client"].post("/api/v1/integrations/tally/sync/invoices", json=batch, headers=w["agent_h"])
    assert r.status_code == 200 and r.json()["updated_count"] == 1, r.text
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Invoice).where(Invoice.invoice_number == number))).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == InvoiceSource.TALLY and rows[0].amount == D("750.00")
        log = (await s.execute(select(TallyAuditLog).where(TallyAuditLog.operation == "SYNC_INVOICES")
                               .order_by(TallyAuditLog.timestamp.desc()).limit(1))).scalar_one()
        assert log.details["relabelled_to_tally_count"] == 1


# ---------------------------------------------------------------------------
# Stage 1: outstanding and monthly periods
# ---------------------------------------------------------------------------

async def test_bi_dashboard_outstanding_is_invoice_minus_receipts_in_tally(client):
    """Live BI figures for a month with no snapshot: outstanding = invoice - receipts posted in Tally
    (previously the full invoice amount); a verified field collection does not reduce it."""
    day = TEST_MONTH.replace(day=10)
    env = await _make_world(day)
    env["client"] = client
    reg = await client.post("/api/v1/integrations/tally/agents", json={"name": f"B{env['tag']}", "organization_id": "o"}, headers=env["admin_h"])
    env["agent_h"] = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
    month = TEST_MONTH.strftime("%Y-%m")

    await _import_receipt(env, "4000.00", day=day + timedelta(days=5), bill=env["invoice_number"])
    pid = await _collect(env, "1000.00", invoice=False, day=day + timedelta(days=6))
    await _verify(env, pid)

    r = await client.get("/api/v1/reports/overview", params={"zone_id": env["zone_id"], "month": month}, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["data_source"] == "LIVE_INVOICES"
    assert D(o["total_sales"]) == D("10000.00")
    assert D(o["total_market_outstanding"]) == D("6000.00"), "10000 - 4000 receipt in Tally; the 1000 awaiting does not reduce it"
    assert D(o["total_overdue_gt_90"]) == D("6000.00")
    assert D(o["total_collection"]) == D("5000.00"), "4000 receipt + 1000 awaiting, each once"
    assert "receipts posted in Tally" in o["data_source_note"]
    t, po, aw = await _kpis(env, month)
    assert (t, po, aw) == (D("5000.00"), D("4000.00"), D("1000.00"))


async def test_monthly_period_outstanding_is_unavailable_not_sales(client):
    day = TEST_MONTH.replace(month=TEST_MONTH.month + 1, day=3)
    month = day.strftime("%Y-%m")

    async def period():
        env_h = admin_h
        r = await client.get("/api/v1/reports/monthly-periods", headers=env_h)
        assert r.status_code == 200, r.text
        return next((p for p in r.json() if p["period_year"] == day.year and p["period_month"] == day.month), None)

    env = await _make_world(day, with_invoice=False)
    admin_h = env["admin_h"]
    env["client"] = client
    reg = await client.post("/api/v1/integrations/tally/agents", json={"name": f"P{env['tag']}", "organization_id": "o"}, headers=admin_h)
    env["agent_h"] = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}

    before = await period()
    before_sales = D(before["total_sales"]) if before else D("0")
    before_col = D(before["total_collection"]) if before else D("0")

    inv_batch = {"batch_id": str(uuid.uuid4()), "invoices": [{
        "source_reference": f"GUID-P-{env['tag']}", "invoice_number": f"SGRG/P/{env['tag']}",
        "outlet_code": env["outlet_code"], "customer_name": env["customer_name"],
        "invoice_date": day.isoformat(), "amount": 8000.00, "brand": "USHA",
    }]}
    assert (await client.post("/api/v1/integrations/tally/sync/invoices", json=inv_batch, headers=env["agent_h"])).status_code == 200
    rid = await _import_receipt(env, "3000.00", day=day)
    pid = await _collect(env, "3000.00", invoice=False, day=day)
    await _verify(env, pid)
    assert (await _link(env, pid, rid)).status_code == 200

    p = await period()
    assert p is not None and p["snapshot_count"] == 0
    assert D(p["total_sales"]) - before_sales == D("8000.00")
    assert D(p["total_collection"]) - before_col == D("3000.00"), "linked collection + its receipt counted once"
    assert p["total_market_os"] is None and p["total_overdue_gt_90"] is None
    assert p["outstanding_available"] is False and "not available" in p["outstanding_note"]

    review = await client.get(f"/api/v1/reports/monthly-periods/{p['id']}/review", headers=admin_h)
    assert review.status_code == 200, review.text
    assert review.json()["total_outstanding"] is None and review.json()["outstanding_available"] is False
