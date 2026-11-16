"""
Tally v2 sync (agent 2.0): ledgers, every debtor voucher, Bills Receivable,
GUID manifest, Tally-balance account position and the reconciliation report.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA
from app.models.tally_ledger import TallyLedgerAdjustment, TallyOpenBill
from app.models.user import Role, User
from app.schemas.tally_sync_v2 import VoucherItem
from app.services import account_position, tally_v2_sync as v2
from tests.conftest import requires_db

D = Decimal


# ---------------------------------------------------------------------------
# Pure classification (no database)
# ---------------------------------------------------------------------------

def _v(**kw) -> VoucherItem:
    base = {"guid": "G1", "date": "2026-11-13", "voucher_type": "Sales", "voucher_parent": "Sales",
            "voucher_number": "SGRG/26-27/1", "debtor_lines": [], "counter_lines": []}
    base.update(kw)
    return VoucherItem.model_validate(base)


def test_sales_debit_is_invoice_receipt_credit_is_payment_rest_is_adjustment():
    assert v2.plan_voucher(_v(debtor_lines=[{"ledger_name": "A", "amount": "-1000"}]))[0].kind == v2.KIND_INVOICE
    rc = v2.plan_voucher(_v(voucher_type="BANK RECEIPT", voucher_parent="Receipt",
                            debtor_lines=[{"ledger_name": "A", "amount": "500"}]))[0]
    assert rc.kind == v2.KIND_PAYMENT and rc.receivable == D("-500.00")
    cn = v2.plan_voucher(_v(voucher_type="Credit Note", voucher_parent="Credit Note",
                            debtor_lines=[{"ledger_name": "A", "amount": "200"}]))[0]
    assert cn.kind == v2.KIND_ADJUSTMENT and cn.receivable == D("-200.00")
    bp = v2.plan_voucher(_v(voucher_type="BANK PAYMENT", voucher_parent="Payment",
                            debtor_lines=[{"ledger_name": "A", "amount": "-300"}]))[0]
    assert bp.kind == v2.KIND_ADJUSTMENT and bp.receivable == D("300.00")
    dr_in_receipt = v2.plan_voucher(_v(voucher_parent="Receipt", debtor_lines=[{"ledger_name": "A", "amount": "-50"}]))[0]
    assert dr_in_receipt.kind == v2.KIND_ADJUSTMENT


def test_multi_debtor_voucher_keys_lines_by_ledger_and_nets_same_ledger():
    plans = v2.plan_voucher(_v(guid="J1", voucher_type="Journal", voucher_parent="Journal", debtor_lines=[
        {"ledger_name": "A", "amount": "-100"}, {"ledger_name": "B", "amount": "100"},
        {"ledger_name": "A", "amount": "40"},
    ]))
    assert [(p.key, p.receivable) for p in plans] == [("J1::A", D("60.00")), ("J1::B", D("-100.00"))]
    zero = v2.plan_voucher(_v(guid="J2", voucher_parent="Journal", debtor_lines=[
        {"ledger_name": "A", "amount": "-10"}, {"ledger_name": "A", "amount": "10"}]))
    assert zero == []


def test_exclusions_cancelled_optional_non_accounting():
    assert v2.exclusion_reason(_v(is_cancelled=True)) == v2.R_CANCELLED
    assert v2.exclusion_reason(_v(voucher_type="Performa Invoice", is_optional=True)) == v2.R_OPTIONAL
    assert v2.exclusion_reason(_v(voucher_type="Sales Order", voucher_parent="Sales Order")) == v2.R_NON_ACCOUNTING
    assert v2.exclusion_reason(_v(voucher_type="Delivery Note", voucher_parent="Delivery Note")) == v2.R_NON_ACCOUNTING
    assert v2.exclusion_reason(_v()) is None


def test_payment_mode_only_as_tally_states_it():
    def bank(**alloc):
        return [{"ledger_name": "UCO", "ledger_class": "BANK", "amount": "-5", "bank_allocations": [alloc]}]
    # Real 13-Nov patterns: Tally's own unique reference is never taken as a UTR.
    d = v2.payment_details(_v(counter_lines=bank(transaction_type="Inter Bank Transfer",
                                                 unique_reference="5Z38Rdxumgu1hGvS")))
    assert d["method"] == PaymentMethod.ONLINE and d["utr_reference"] is None
    d = v2.payment_details(_v(counter_lines=bank(transaction_type="Cheque/DD", instrument_number="001249",
                                                 unique_reference="5Z2Tu28Imgu1hGvS")))
    assert d["method"] == PaymentMethod.CHEQUE and d["cheque_number"] == "001249" and d["utr_reference"] is None
    # Bank-statement import: default type "Cheque", no instrument (an RTGS in the narration).
    d = v2.payment_details(_v(counter_lines=bank(transaction_type="Cheque")))
    assert d["method"] == PaymentMethod.UNSPECIFIED and d["transaction_type"] == "Cheque"
    assert v2.payment_details(_v(counter_lines=bank(transaction_type="Cash")))["method"] == PaymentMethod.CASH
    assert v2.payment_details(_v(counter_lines=[{"ledger_name": "Cash", "ledger_class": "CASH", "amount": "-5"}]))["method"] == PaymentMethod.CASH
    assert v2.payment_details(_v(counter_lines=[{"ledger_name": "UCO", "ledger_class": "BANK", "amount": "-5"}]))["method"] == PaymentMethod.UNSPECIFIED


def test_tally_brand_position_bills_residue_and_credit_netting():
    from app.services.aging_service import AgingStatus as S
    t = account_position.TallyBrandInputs(
        bills=[account_position.InvoiceLine(D("100"), D("100"), 40, S.OVERDUE),
               account_position.InvoiceLine(D("50"), D("50"), 3, S.NORMAL),
               account_position.InvoiceLine(D("-30"), D("-30"), 1, S.NORMAL)],
        residue=D("-20"), invoiced=D("150"), adjustments=D("-10"), posted_payments=D("70"),
    )
    p = account_position.compute_tally_brand_position(t)
    assert p.outstanding == D("100") and p.ageing.overdue == D("50") and p.ageing.normal == D("50")
    assert p.opening_balance == D("100") - D("150") + D("10") + D("70")
    assert p.reconciles and p.balance_source == "TALLY"


# ---------------------------------------------------------------------------
# Through the API, against the database
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def env():
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as s:
        admin = User(email=f"admin_v2_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"),
                     role=Role.ADMIN, is_active=True)
        s.add(admin)
        await s.commit()
        admin_id = admin.id
    admin_h = {"Authorization": f"Bearer {create_access_token(subject=str(admin_id), role=Role.ADMIN.value)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        reg = await c.post("/api/v1/integrations/tally/agents", json={"name": f"V2{tag}", "organization_id": "o"},
                           headers=admin_h)
        assert reg.status_code == 201, reg.text
        agent_h = {"X-Agent-Id": reg.json()["agent"]["id"], "X-Agent-Key": reg.json()["api_key"]}
        yield {"c": c, "tag": tag, "agent_h": agent_h, "admin_h": admin_h}


async def _post(e, kind, body):
    body = {"batch_id": str(uuid.uuid4()), **body}
    r = await e["c"].post(f"/api/v1/integrations/tally/sync/{kind}", json=body, headers=e["agent_h"])
    assert r.status_code == 200, r.text
    return r.json()


def _led(e, n, **kw):
    return {"guid": f"LG-{e['tag']}-{n}", "name": f"V2 Ledger {e['tag']} {n}", "is_debtor": True,
            "parent": "Sundry Debtors", **kw}


async def _cust(guid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Customer).where(Customer.tally_guid == guid))).scalar_one_or_none()


async def _snapshot(e, ledgers, period=date(2026, 4, 1)):
    sid = f"L-{uuid.uuid4().hex}"
    return await _post(e, "ledgers", {"snapshot_id": sid, "is_final_chunk": True, "period_start": str(period),
                                      "as_of": datetime.now(timezone.utc).isoformat(), "ledgers": ledgers})


pytestmark_db = [requires_db, pytest.mark.asyncio]


@requires_db
@pytest.mark.asyncio
async def test_ledger_snapshot_debtors_aliases_balances_and_non_debtor_flag(env):
    t = env["tag"]
    async with AsyncSessionLocal() as s:  # an old-sync "customer" that is really a bank ledger
        uid = (await s.execute(select(User.id).where(User.email == f"admin_v2_{t}@fieldtrack.test"))).scalar_one()
        s.add(Customer(name=f"UCO BANK OD {t}", address="", contact_number="", created_by=uid))
        await s.commit()
    res = await _snapshot(env, [
        _led(env, 1, aliases=[f"UPDD9{t[:5]}"], outlet_code=f"UPDD9{t[:5]}", is_bill_wise=True,
             opening_balance="-1000.00", closing_balance="-1500.00"),
        {"guid": f"BANK-{t}", "name": f"UCO BANK OD {t}", "is_debtor": False, "parent": "Bank OD A/c"},
    ])
    assert res["failed_count"] == 0, res
    c = await _cust(f"LG-{t}-1")
    assert c.tally_is_debtor is True and c.tally_aliases == [f"UPDD9{t[:5]}"] and c.outlet_code == f"UPDD9{t[:5]}"
    assert c.tally_opening_balance == D("-1000.00") and c.tally_opening_balance_as_of == date(2026, 4, 1)
    assert c.tally_closing_balance == D("-1500.00") and c.tally_is_bill_wise is True
    bank = await _cust(f"BANK-{t}")
    assert bank is not None and bank.tally_is_debtor is False and bank.tally_parent_group == "Bank OD A/c"

    # Incremental (no snapshot): master details only, balances untouched.
    await _post(env, "ledgers", {"ledgers": [_led(env, 1, closing_balance="-1.00", email="x@example.com")]})
    c = await _cust(f"LG-{t}-1")
    assert c.tally_closing_balance == D("-1500.00") and c.email == "x@example.com"

    # Outlet lists hide the bank ledger.
    r = await env["c"].get("/api/v1/customers", params={"search": f"BANK OD {t}"}, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    assert [i["name"] for i in r.json()] == []
    r = await env["c"].get("/api/v1/customers", params={"search": f"V2 Ledger {t} 1"}, headers=env["admin_h"])
    assert [i["name"] for i in r.json()] == [f"V2 Ledger {t} 1"]


async def _setup_debtors(env, n=2):
    await _snapshot(env, [_led(env, i, opening_balance="0", closing_balance="0") for i in range(1, n + 1)])
    return [f"V2 Ledger {env['tag']} {i}" for i in range(1, n + 1)]


def _vch(env, guid, vtype, parent, lines, number="N1", d="2026-11-13", counter=None, **kw):
    return {"guid": f"{guid}-{env['tag']}", "alter_id": 10, "date": d, "voucher_type": vtype, "voucher_parent": parent,
            "voucher_number": number, "debtor_lines": lines, "counter_lines": counter or [], **kw}


@requires_db
@pytest.mark.asyncio
async def test_vouchers_classified_bills_linked_and_changes_retire(env):
    t = env["tag"]
    a, b = await _setup_debtors(env)
    ga = f"LG-{t}-1"
    res = await _post(env, "vouchers", {"vouchers": [
        _vch(env, "INV", "Oppo", "Sales", [{"ledger_name": a, "ledger_guid": ga, "amount": "-11800", "brand": "Oppo",
              "bill_allocations": [{"name": f"SGRG/{t}/1", "bill_type": "New Ref", "amount": "-11800"}]}],
             number=f"SGRG/{t}/1", narration="sale"),
        _vch(env, "RCT", "BANK RECEIPT", "Receipt",
             [{"ledger_name": a, "amount": "10000",
               "bill_allocations": [{"name": f"SGRG/{t}/1", "bill_type": "Agst Ref", "amount": "8000"},
                                    {"name": "", "bill_type": "On Account", "amount": "2000"}]}],
             counter=[{"ledger_name": "HDFC", "ledger_class": "BANK", "amount": "-10000",
                       "bank_allocations": [{"transaction_type": "Inter Bank Transfer", "instrument_number": "UTR9",
                                             "unique_reference": "5Z38Rdxumgu1hGvS"}]}],
             narration="BULK POSTING-UPI"),
        _vch(env, "CN", "Credit Note", "Credit Note", [{"ledger_name": a, "amount": "500"}]),
        _vch(env, "JV", "Journal", "Journal", [{"ledger_name": a, "amount": "-100"}, {"ledger_name": b, "amount": "100"}]),
        _vch(env, "PRO", "Performa Invoice", "Sales", [{"ledger_name": a, "amount": "-908200"}], is_optional=True),
        _vch(env, "SO", "Sales Order", "Sales Order", [{"ledger_name": a, "amount": "-65747.40"}]),
    ]})
    assert res["failed_count"] == 0, res
    assert res["details"]["by_kind"] == {"INVOICE": 1, "PAYMENT": 1, "ADJUSTMENT": 3}
    assert res["details"]["excluded"] == {"OPTIONAL": 1, "NON_ACCOUNTING_TYPE": 1}

    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.source_reference == f"INV-{t}"))).scalar_one()
        assert inv.amount == D("11800.00") and inv.tally_bill_name == f"SGRG/{t}/1" and inv.due_date is None
        pay = (await s.execute(select(Payment).where(Payment.source_reference == f"RCT-{t}"))).scalar_one()
        assert pay.amount == D("10000.00") and pay.payment_method == PaymentMethod.ONLINE
        assert pay.utr_reference == "UTR9" and pay.narration == "BULK POSTING-UPI" and pay.status == PaymentStatus.VERIFIED
        links = (await s.execute(select(PIA).where(PIA.payment_id == pay.id))).scalars().all()
        assert [(l.invoice_id, l.allocated_amount) for l in links] == [(inv.id, D("8000.00"))]
        adj = {r.source_reference: r.amount for r in (await s.execute(
            select(TallyLedgerAdjustment).where(TallyLedgerAdjustment.tally_voucher_guid.in_([f"CN-{t}", f"JV-{t}"]))
        )).scalars()}
        assert adj == {f"CN-{t}": D("-500.00"), f"JV-{t}::{a}": D("100.00"), f"JV-{t}::{b}": D("-100.00")}
        assert (await s.execute(select(Invoice).where(Invoice.source_reference == f"PRO-{t}"))).first() is None

    # The receipt is changed in Tally into a bank payment between bank ledgers (no debtor line):
    # its FieldTrack copy is retired, not deleted. The credit note is cancelled.
    res = await _post(env, "vouchers", {"vouchers": [
        _vch(env, "RCT", "BANK PAYMENT", "Payment", [],
             counter=[{"ledger_name": "UCO BANK OD", "ledger_class": "BANK", "amount": "10000"}]),
        _vch(env, "CN", "Credit Note", "Credit Note", [], is_cancelled=True),
    ]})
    assert res["retired_count"] == 2, res
    async with AsyncSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.source_reference == f"RCT-{t}"))).scalar_one()
        assert pay.source == PaymentSource.TALLY_RETIRED and pay.tally_retired_reason == v2.R_LINE_REMOVED
        cn = (await s.execute(select(TallyLedgerAdjustment).where(TallyLedgerAdjustment.source_reference == f"CN-{t}"))).scalar_one()
        assert cn.state == "RETIRED" and cn.retired_reason == v2.R_CANCELLED

    # ... and changed back: reactivated (same row).
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, "RCT", "BANK RECEIPT", "Receipt", [{"ledger_name": a, "amount": "10000"}],
             counter=[{"ledger_name": "HDFC", "ledger_class": "BANK", "amount": "-10000"}])]})
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Payment).where(Payment.source_reference == f"RCT-{t}"))).scalars().all()
        assert len(rows) == 1 and rows[0].source == PaymentSource.TALLY and rows[0].tally_retired_at is None
        assert rows[0].payment_method == PaymentMethod.UNSPECIFIED


@requires_db
@pytest.mark.asyncio
async def test_an_older_copy_never_overwrites_a_newer_voucher(env):
    (a,) = await _setup_debtors(env, 1)
    new = _vch(env, "S", "Sales", "Sales", [{"ledger_name": a, "amount": "-200"}], number="S1")
    new["alter_id"] = 50
    old = dict(new, alter_id=40, debtor_lines=[{"ledger_name": a, "amount": "-100"}])
    await _post(env, "vouchers", {"vouchers": [new]})
    res = await _post(env, "vouchers", {"vouchers": [old]})
    assert res["details"]["excluded"] == {"STALE_VERSION": 1}
    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.source_reference == f"S-{env['tag']}"))).scalar_one()
    assert inv.amount == D("200.00") and inv.tally_alter_id == 50


@requires_db
@pytest.mark.asyncio
async def test_unknown_ledger_fails_the_voucher_without_creating_a_customer(env):
    res = await _post(env, "vouchers", {"vouchers": [
        _vch(env, "X", "Sales", "Sales", [{"ledger_name": f"Nobody {env['tag']}", "amount": "-10"}])]})
    assert res["failed_count"] == 1 and "not a known customer" in res["errors"][0]["error"]
    async with AsyncSessionLocal() as s:
        assert (await s.execute(select(Customer).where(Customer.name == f"Nobody {env['tag']}"))).first() is None


@requires_db
@pytest.mark.asyncio
async def test_bills_snapshot_due_dates_position_and_reconciliation(env):
    t = env["tag"]
    led = _led(env, 1, opening_balance="-2000.00", closing_balance="-5300.00", brand="Oppo")
    await _snapshot(env, [led])
    name, guid = led["name"], led["guid"]
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, "I1", "Oppo", "Sales", [{"ledger_name": name, "amount": "-5000", "brand": "Oppo",
              "bill_allocations": [{"name": f"B1-{t}", "bill_type": "New Ref", "amount": "-5000"}]}], number=f"B1-{t}"),
        _vch(env, "R1", "Receipt", "Receipt", [{"ledger_name": name, "amount": "1500",
              "bill_allocations": [{"name": f"OLD-{t}", "bill_type": "Agst Ref", "amount": "1500"}]}],
             counter=[{"ledger_name": "Cash", "ledger_class": "CASH", "amount": "-1500"}]),
        _vch(env, "C1", "Credit Note", "Credit Note", [{"ledger_name": name, "amount": "200"}]),
    ]})
    # Ledger closing must equal opening + movements: 2000 + 5000 - 1500 - 200 = 5300.
    await _snapshot(env, [led])
    sid = f"B-{uuid.uuid4().hex}"
    res = await _post(env, "bills", {"snapshot_id": sid, "as_of_date": "2026-11-16", "is_final_chunk": True, "bills": [
        {"ledger_name": name, "bill_name": f"B1-{t}", "bill_date": "2026-11-13", "due_date": "2026-11-20",
         "pending_amount": "-4800", "overdue_days": 0},
        {"ledger_name": name, "bill_name": f"OLD-{t}", "bill_date": "2026-01-10", "due_date": "2026-01-10",
         "pending_amount": "-500", "overdue_days": 310},
        {"ledger_name": f"Some creditor {t}", "bill_name": "X", "pending_amount": "-1"},
    ]})
    assert res["created_count"] == 2 and res["details"]["invoice_due_dates_set"] == 1
    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.source_reference == f"I1-{t}"))).scalar_one()
        assert inv.due_date == date(2026, 11, 20)
        pay = (await s.execute(select(Payment).where(Payment.source_reference == f"R1-{t}"))).scalar_one()
        assert pay.payment_method == PaymentMethod.CASH
        cust = await _cust(guid)
        pos = (await account_position.load_outlet_positions(s, [cust.id], today=date(2026, 11, 16)))[cust.id]
        o = pos.outlet
        assert o.balance_source == "TALLY"
        assert o.outstanding == D("5300.00"), o
        assert o.tally_difference == D("0.00") and o.reconciles
        assert o.adjustments == D("-200.00") and o.invoiced == D("5000.00") and o.paid_in_tally == D("1500.00")
        assert o.ageing.overdue == D("500.00") and o.ageing.normal == D("4800.00")
        from app.services import payment_tally
        paid = await payment_tally.posted_paid_by_invoice(s, [inv.id])
        assert paid[inv.id] == D("200.00"), "Tally says 4,800 of 5,000 is still open"

    r = await env["c"].get("/api/v1/integrations/tally/reconciliation", headers=env["admin_h"])
    assert r.status_code == 200, r.text
    assert all(d["name"] != name for d in r.json()["differences"])


@requires_db
@pytest.mark.asyncio
async def test_manifest_retires_deleted_vouchers_in_window_only(env):
    t = env["tag"]
    # A window no other test uses (a manifest retires everything in its window it does not list).
    day = date(2040 + int(t[:4], 16) % 50, 1 + int(t[4:6], 16) % 12, 15)
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, "K1", "Sales", "Sales", [{"ledger_name": a, "amount": "-10"}], number="K1", d=str(day)),
        _vch(env, "K2", "Sales", "Sales", [{"ledger_name": a, "amount": "-20"}], number="K2", d=str(day)),
        _vch(env, "K3", "Sales", "Sales", [{"ledger_name": a, "amount": "-30"}], number="K3",
             d=str(day.replace(day=1))),
    ]})
    res = await _post(env, "manifest", {"snapshot_id": f"M-{uuid.uuid4().hex}", "window_from": str(day),
                                        "window_to": str(day), "is_final_chunk": True, "guids": [f"K1-{t}"]})
    assert res["details"]["retired"] == {"invoices": 1, "payments": 0, "adjustments": 0}, res
    async with AsyncSessionLocal() as s:
        src = {r.source_reference: r.source for r in (await s.execute(
            select(Invoice).where(Invoice.source_reference.in_([f"K1-{t}", f"K2-{t}", f"K3-{t}"])))).scalars()}
    assert src == {f"K1-{t}": InvoiceSource.TALLY, f"K2-{t}": InvoiceSource.TALLY_RETIRED,
                   f"K3-{t}": InvoiceSource.TALLY}, "K3 is outside the window"

    # A manifest covering under half of what FieldTrack holds is refused, retiring nothing.
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, f"K{i}", "Sales", "Sales", [{"ledger_name": a, "amount": "-1"}], number=f"K{i}", d=str(day))
        for i in range(4, 8)]})
    res = await _post(env, "manifest", {"snapshot_id": f"M-{uuid.uuid4().hex}", "window_from": str(day),
                                        "window_to": str(day), "is_final_chunk": True, "guids": [f"K1-{t}"]})
    assert "not applied" in res["details"].get("error", ""), res


@requires_db
@pytest.mark.asyncio
async def test_field_collection_cannot_use_unspecified_mode():
    from pydantic import ValidationError
    from app.schemas.payment import PaymentCreate
    with pytest.raises(ValidationError):
        PaymentCreate(visit_id=uuid.uuid4(), amount=D("10"), payment_method=PaymentMethod.UNSPECIFIED,
                      payment_date=date(2026, 11, 16))
