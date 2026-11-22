"""Release 3.1 - Distribution-only business scope.

Group rules decide a debtor ledger's scope (a MANUAL ledger decision wins); a ledger of a group without a rule is
PENDING. Out-of-scope ledgers: the outlet stops being a FieldTrack debtor and the ledger's rows are retired
(OUT_OF_SCOPE / SCOPE_PENDING) - never deleted; allocations and the voucher index are untouched, and a decision
back to DISTRIBUTION restores the rows exactly. With no rule at all, nothing changes (pre-3.1 behaviour).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from app.database import AsyncSessionLocal
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA
from app.models.tally_debtor_ledger import TallyDebtorLedger
from app.models.tally_ledger import TallyLedgerAdjustment
from app.models.tally_scope_group import TallyScopeGroup
from app.models.tally_voucher_index import TallyVoucherIndex
from app.services import business_scope as bs
from app.services import tally_reconciliation
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _cust, _post, _snapshot, _vch, env  # noqa: F401  (fixture reuse)

D = "2026-03-12"   # a date no other test writes vouchers on


def _ledger(e, n, group, **kw):
    return {"guid": f"SC-{e['tag']}-{n}", "name": f"Scope Ledger {e['tag']} {n}", "is_debtor": True,
            "parent": group, "opening_balance": "0", "closing_balance": kw.pop("closing", "0"), **kw}


def _sale(e, key, ledger, amount="1000", bill=None):
    return {**_vch(e, key, "Oppo", "Sales", [{"ledger_name": ledger, "amount": f"-{amount}", "bill_allocations": [
        {"name": bill or f"{key}-{e['tag']}", "bill_type": "New Ref", "amount": f"-{amount}"}]}],
        number=f"SGRG/{e['tag']}/{key}", d=D), "alter_id": 30}


def _receipt(e, key, ledger, bill, amount="400"):
    return {**_vch(e, key, "BANK RECEIPT", "Receipt", [{"ledger_name": ledger, "amount": amount, "bill_allocations": [
        {"name": bill, "bill_type": "Agst Ref", "amount": amount}]}],
        counter=[{"ledger_name": "HDFC", "ledger_class": "BANK", "amount": f"-{amount}"}], d=D), "alter_id": 31}


@pytest_asyncio.fixture
async def rules(env):
    t = env["tag"]
    groups = {f"DIST GROUP {t}": "DISTRIBUTION", f"OTHER DEBTOR {t}": "EXCLUDED"}
    async with AsyncSessionLocal() as s:
        for g, sc in groups.items():
            s.add(TallyScopeGroup(group_name=g, scope=sc))
        await s.commit()
    yield groups
    async with AsyncSessionLocal() as s:
        await s.execute(delete(TallyScopeGroup))
        await s.execute(text("UPDATE tally_debtor_ledgers SET business_scope = NULL, scope_source = NULL, "
                             "scope_reason = NULL WHERE tally_guid LIKE :p"), {"p": f"SC-{t}-%"})
        await s.commit()


async def _led(guid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == guid))).scalar_one()


async def _rows(guid_prefix):
    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.tally_voucher_guid.like(guid_prefix)))).scalars().all()
        pay = (await s.execute(select(Payment).where(Payment.tally_voucher_guid.like(guid_prefix)))).scalars().all()
        adj = (await s.execute(select(TallyLedgerAdjustment).where(
            TallyLedgerAdjustment.tally_voucher_guid.like(guid_prefix)))).scalars().all()
        return inv, pay, adj


@requires_db
@pytest.mark.asyncio
async def test_without_rules_nothing_changes(env):
    t = env["tag"]
    await _snapshot(env, [_ledger(env, 1, "Some Group")])
    led = await _led(f"SC-{t}-1")
    assert led.business_scope is None and led.in_scope
    assert (await _cust(f"SC-{t}-1")).tally_is_debtor is True


@requires_db
@pytest.mark.asyncio
async def test_group_rules_exclude_pending_and_new_outlets_sync_automatically(env, rules):
    t = env["tag"]
    dist, other = f"DIST GROUP {t}", f"OTHER DEBTOR {t}"
    res = await _snapshot(env, [_ledger(env, 1, dist, closing="-1000"), _ledger(env, 2, other, closing="-500"),
                                _ledger(env, 3, f"BRAND NEW GROUP {t}")])
    assert res["failed_count"] == 0, res
    l1, l2, l3 = [await _led(f"SC-{t}-{i}") for i in (1, 2, 3)]
    assert (l1.business_scope, l1.scope_source) == ("DISTRIBUTION", "GROUP")
    assert (l2.business_scope, l2.scope_source) == ("EXCLUDED", "GROUP")
    assert (l3.business_scope, l3.scope_source) == ("PENDING", "DEFAULT")
    assert (await _cust(f"SC-{t}-1")).tally_is_debtor is True
    assert (await _cust(f"SC-{t}-2")).tally_is_debtor is False
    assert (await _cust(f"SC-{t}-3")).tally_is_debtor is False

    a, b, c = (f"Scope Ledger {t} {i}" for i in (1, 2, 3))
    res = await _post(env, "vouchers", {"vouchers": [_sale(env, "S1", a), _sale(env, "S2", b), _sale(env, "S3", c)]})
    assert res["failed_count"] == 0, res
    inv, _, _ = await _rows(f"S%-{t}")
    by = {i.tally_voucher_guid.split("-")[0]: i for i in inv}
    assert by["S1"].source.value == "TALLY" and by["S1"].tally_retired_at is None
    assert by["S2"].source.value == "TALLY_RETIRED" and by["S2"].tally_retired_reason == "OUT_OF_SCOPE"
    assert by["S3"].source.value == "TALLY_RETIRED" and by["S3"].tally_retired_reason == "SCOPE_PENDING"
    async with AsyncSessionLocal() as s:  # every voucher stays indexed: reconcile will not re-send them
        n = (await s.execute(select(TallyVoucherIndex).where(TallyVoucherIndex.guid.in_(
            [f"S1-{t}", f"S2-{t}", f"S3-{t}"]), TallyVoucherIndex.state == "ACTIVE"))).scalars().all()
    assert len(n) == 3

    # A NEW outlet created later in an approved Distribution group is in scope at once, with its sales live.
    await _post(env, "ledgers", {"ledgers": [_ledger(env, 4, dist)]})
    l4 = await _led(f"SC-{t}-4")
    assert l4.business_scope == "DISTRIBUTION" and (await _cust(f"SC-{t}-4")).tally_is_debtor is True
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S4", f"Scope Ledger {t} 4")]})
    inv, _, _ = await _rows(f"S4-{t}")
    assert inv[0].source.value == "TALLY"

    # Hidden from outlet lists; visible again only when in scope.
    r = await env["c"].get("/api/v1/customers", params={"search": f"Scope Ledger {t}"}, headers=env["admin_h"])
    assert sorted(i["name"] for i in r.json()) == [f"Scope Ledger {t} 1", f"Scope Ledger {t} 4"]


@requires_db
@pytest.mark.asyncio
async def test_manual_decision_retires_and_restores_exactly_and_allocations_survive(env, rules):
    t = env["tag"]
    dist = f"DIST GROUP {t}"
    await _snapshot(env, [_ledger(env, 1, dist)])
    a = f"Scope Ledger {t} 1"
    bill = f"B-{t}"
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S1", a, bill=bill), _receipt(env, "R1", a, bill),
        {**_vch(env, "J1", "Journal", "Journal", [{"ledger_name": a, "amount": "-25"}], d=D), "alter_id": 32}]})
    inv, pay, adj = await _rows(f"%-{t}")
    assert len(inv) == 1 and len(pay) == 1 and len(adj) == 1
    async with AsyncSessionLocal() as s:
        allocs0 = (await s.execute(select(PIA.id, PIA.invoice_id, PIA.allocated_amount)
                                   .where(PIA.payment_id == pay[0].id))).all()
    assert allocs0, "the receipt is allocated to the invoice"
    snap0 = [(r.id, r.amount) for r in inv + pay + adj]

    async with AsyncSessionLocal() as s:
        led = (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == f"SC-{t}-1"))).scalar_one()
        r = await bs.set_manual_scope(s, led, "EXCLUDED", "inter-company")
        await s.commit()
    assert r == {**r, "invoices": 1, "payments": 1, "adjustments": 1}
    inv, pay, adj = await _rows(f"%-{t}")
    assert inv[0].tally_retired_reason == pay[0].tally_retired_reason == adj[0].retired_reason == "OUT_OF_SCOPE"
    assert (await _cust(f"SC-{t}-1")).tally_is_debtor is False
    # the ledger snapshot keeps the MANUAL decision (manual wins over the DISTRIBUTION group rule)
    await _snapshot(env, [_ledger(env, 1, dist)])
    assert (await _led(f"SC-{t}-1")).business_scope == "EXCLUDED"
    async with AsyncSessionLocal() as s:
        rep = await tally_reconciliation.build_report(s)
    assert any(x["scope"] == "EXCLUDED" for x in rep["excluded_business_scope"])

    async with AsyncSessionLocal() as s:
        led = (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == f"SC-{t}-1"))).scalar_one()
        await bs.set_manual_scope(s, led, "DISTRIBUTION", "confirmed Distribution outlet")
        await s.commit()
    inv, pay, adj = await _rows(f"%-{t}")
    assert all(x.tally_retired_at is None for x in inv + pay) and adj[0].state == "ACTIVE"
    assert [(r.id, r.amount) for r in inv + pay + adj] == snap0
    async with AsyncSessionLocal() as s:
        allocs1 = (await s.execute(select(PIA.id, PIA.invoice_id, PIA.allocated_amount)
                                   .where(PIA.payment_id == pay[0].id))).all()
    assert allocs1 == allocs0
    assert (await _cust(f"SC-{t}-1")).tally_is_debtor is True


@requires_db
@pytest.mark.asyncio
async def test_reconciliation_reports_excluded_scope_separately(env, rules):
    t = env["tag"]
    await _snapshot(env, [_ledger(env, 1, f"DIST GROUP {t}", closing="-1000"),
                          _ledger(env, 2, f"OTHER DEBTOR {t}", closing="-500")])
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S1", f"Scope Ledger {t} 1"),
                                               _sale(env, "S2", f"Scope Ledger {t} 2", amount="500")]})
    async with AsyncSessionLocal() as s:
        rep = await tally_reconciliation.build_report(s, limit=5000)
    names = {d["name"] for d in rep["differences"]}
    assert f"Scope Ledger {t} 2" not in names            # excluded ledger is not a Distribution debtor row
    exc = {x["scope"]: x for x in rep["excluded_business_scope"]}
    assert "EXCLUDED" in exc and exc["EXCLUDED"]["ledgers"] >= 1 and exc["EXCLUDED"]["invoices_retired"] >= 1
    assert isinstance(exc["EXCLUDED"]["invoices_retired"], int)
