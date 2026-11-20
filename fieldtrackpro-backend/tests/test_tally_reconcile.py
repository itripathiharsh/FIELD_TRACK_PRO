"""Release 3.0 - reconciliation: the voucher index and POST /integrations/tally/sync/reconcile.

Every voucher the agent sends is indexed (GUID, latest AlterID, date, state) in the same savepoint as its rows -
including vouchers that leave no invoice / payment / adjustment row (cancelled, purchase-type). Reconcile compares
Tally's headers for a window with the index: missing / stale / extra. It writes nothing.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.invoice import Invoice
from app.models.sync_agent import SyncAgent
from app.models.tally_voucher_index import TallyVoucherIndex
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, _setup_debtors, _vch, env  # noqa: F401  (fixture reuse)

D = "2026-03-11"   # a date no other test writes vouchers on


def _sale(e, key, ledger, amount="1000", alter=10, d=D, **kw):
    return {**_vch(e, key, "Sales", "Sales", [{"ledger_name": ledger, "amount": f"-{amount}",
                                                 "bill_allocations": [{"name": f"{key}-{e['tag']}", "bill_type": "New Ref",
                                                                       "amount": f"-{amount}"}]}], d=d), "alter_id": alter, **kw}


async def _index(guid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyVoucherIndex).where(TallyVoucherIndex.guid == guid))).scalar_one_or_none()


async def _reconcile(e, entries, a=D, b=D, status=200, company=None):
    body = {"batch_id": str(uuid.uuid4()), "window_from": a, "window_to": b,
            "entries": [{"guid": g, "alter_id": al} for g, al in entries]}
    if company:
        body["company_guid"] = company
    r = await e["c"].post("/api/v1/integrations/tally/sync/reconcile", json=body, headers=e["agent_h"])
    assert r.status_code == status, r.text
    return r.json()


@requires_db
@pytest.mark.asyncio
async def test_every_processed_voucher_is_indexed_including_rowless_ones(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    res = await _post(env, "vouchers", {"vouchers": [
        _sale(env, "S1", a, alter=21),
        {**_vch(env, "CXL", "Sales", "Sales", [{"ledger_name": a, "amount": "-50"}], d=D), "alter_id": 22, "is_cancelled": True},
        {**_vch(env, "PUR", "Purchase", "Purchase", [], d=D), "alter_id": 23},   # no customer line: no row at all
    ]})
    assert res["failed_count"] == 0, res
    for key, alter in (("S1", 21), ("CXL", 22), ("PUR", 23)):
        ix = await _index(f"{key}-{t}")
        assert ix is not None and ix.alter_id == alter and ix.state == "ACTIVE" and str(ix.voucher_date) == D, key
    r = await _reconcile(env, [(f"S1-{t}", 21), (f"CXL-{t}", 22), (f"PUR-{t}", 23)])
    mine = {f"S1-{t}", f"CXL-{t}", f"PUR-{t}"}
    assert not (set(r["missing"]) | set(r["stale"])) & mine, "nothing to repair"
    assert not set(r["extra"]) & mine


@requires_db
@pytest.mark.asyncio
async def test_missing_stale_and_extra(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "K1", a, alter=31), _sale(env, "K2", a, alter=32),
                                               _sale(env, "K3", a, alter=33)]})
    # Tally now: K1 unchanged, K2 edited (AlterID 40), K3 deleted, NEW never sent.
    r = await _reconcile(env, [(f"K1-{t}", 31), (f"K2-{t}", 40), (f"NEW-{t}", 41)])
    assert f"NEW-{t}" in r["missing"] and f"K2-{t}" in r["stale"] and f"K3-{t}" in r["extra"]
    assert f"K1-{t}" not in r["missing"] + r["stale"] + r["extra"]
    assert r["listed"] == 3
    # reconcile writes nothing
    assert (await _index(f"K3-{t}")).state == "ACTIVE" and await _index(f"NEW-{t}") is None


@requires_db
@pytest.mark.asyncio
async def test_resend_fixes_stale_and_an_older_copy_never_lowers_the_index(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "E1", a, "1000", alter=50)]})
    await _post(env, "vouchers", {"vouchers": [_sale(env, "E1", a, "1200", alter=55)]})
    ix = await _index(f"E1-{t}")
    assert ix.alter_id == 55
    await _post(env, "vouchers", {"vouchers": [_sale(env, "E1", a, "1000", alter=50)]})   # a retried, older batch
    assert (await _index(f"E1-{t}")).alter_id == 55, "the older copy is skipped (STALE_VERSION) and never lowers it"
    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.source_reference == f"E1-{t}"))).scalar_one()
    assert str(inv.amount) == "1200.00"
    r = await _reconcile(env, [(f"E1-{t}", 55)])
    assert f"E1-{t}" not in r["stale"]


@requires_db
@pytest.mark.asyncio
async def test_failed_voucher_is_not_indexed_and_stays_missing(env):
    t = env["tag"]
    res = await _post(env, "vouchers", {"vouchers": [_sale(env, "BAD", f"Unknown ledger {t}", alter=60)]})
    assert res["failed_count"] == 1
    assert await _index(f"BAD-{t}") is None, "rows were not written, so the index does not claim the voucher"
    r = await _reconcile(env, [(f"BAD-{t}", 60)])
    assert f"BAD-{t}" in r["missing"], "reconciliation keeps asking for it until it loads"


@requires_db
@pytest.mark.asyncio
async def test_accepted_manifest_marks_the_index_deleted_and_a_restored_voucher_is_missing_again(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    d = "2026-03-12"
    await _post(env, "vouchers", {"vouchers": [_sale(env, "M1", a, alter=70, d=d), _sale(env, "M2", a, alter=71, d=d)]})
    # Tally still lists M1 and every voucher other tests / earlier runs left on this date in the shared database;
    # only M2 is gone (a manifest must be complete, or the 50% floor refuses it).
    async with AsyncSessionLocal() as s:
        others = [g for (g,) in (await s.execute(select(TallyVoucherIndex.guid).where(
            TallyVoucherIndex.voucher_date == date.fromisoformat(d), TallyVoucherIndex.state == "ACTIVE",
            TallyVoucherIndex.guid != f"M2-{t}"))).all()]
    await _post(env, "manifest", {"snapshot_id": f"MAN-{t}", "window_from": d, "window_to": d, "is_final_chunk": True,
                                  "guids": sorted(set(others) | {f"M1-{t}"})})
    assert (await _index(f"M2-{t}")).state == "DELETED" and (await _index(f"M1-{t}")).state == "ACTIVE"
    r = await _reconcile(env, [(f"M1-{t}", 70), (f"M2-{t}", 71)], d, d)
    assert f"M2-{t}" in r["missing"], "a voucher restored in Tally (re-listed) is fetched again"
    await _post(env, "vouchers", {"vouchers": [_sale(env, "M2", a, alter=71, d=d)]})
    assert (await _index(f"M2-{t}")).state == "ACTIVE"


@requires_db
@pytest.mark.asyncio
async def test_re_dated_voucher_moves_its_index_date(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "RD", a, alter=80, d="2026-03-13")]})
    await _post(env, "vouchers", {"vouchers": [_sale(env, "RD", a, alter=81, d="2026-03-14")]})
    ix = await _index(f"RD-{t}")
    assert str(ix.voucher_date) == "2026-03-14" and ix.alter_id == 81
    r = await _reconcile(env, [], "2026-03-13", "2026-03-13")
    assert f"RD-{t}" not in r["extra"], "no longer dated in the old window"


@requires_db
@pytest.mark.asyncio
async def test_reconcile_refuses_another_company(env):
    async with AsyncSessionLocal() as s:
        ag = (await s.execute(select(SyncAgent).where(SyncAgent.id == uuid.UUID(env["agent_h"]["X-Agent-Id"])))).scalar_one()
        ag.tally_company_guid = "COMPANY-A"
        await s.commit()
    await _reconcile(env, [], company="COMPANY-B", status=409)
    await _reconcile(env, [], company="COMPANY-A")


@requires_db
@pytest.mark.asyncio
async def test_reconcile_requires_agent_authentication(env):
    r = await env["c"].post("/api/v1/integrations/tally/sync/reconcile",
                            json={"batch_id": "x", "window_from": D, "window_to": D, "entries": []})
    assert r.status_code in (401, 403)


async def _links(receipt_key):
    from app.models.payment import Payment
    from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Invoice.source_reference, PIA.allocated_amount).join(PIA, PIA.invoice_id == Invoice.id)
                                .join(Payment, Payment.id == PIA.payment_id).where(Payment.source_reference == receipt_key))).all()
    return {k: str(a) for k, a in rows}


def _receipt(e, key, ledger, bill, amount="1000", alter=10, d=D):
    return {**_vch(e, key, "Receipt", "Receipt", [{"ledger_name": ledger, "amount": amount,
                                                    "bill_allocations": [{"name": bill, "bill_type": "Agst Ref",
                                                                          "amount": amount}]}], d=d), "alter_id": alter}


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["cancelled", "deleted"])
async def test_receipt_is_relinked_when_its_invoice_is_cancelled_or_deleted(env, how):
    """Bill numbers restart each FY: two invoices of one ledger raise the same bill name. A receipt settles the later
    one; when that invoice is cancelled / deleted in Tally, the receipt settles the bill Tally still holds - the
    earlier invoice - instead of pointing at a retired row (found by the 3.0 lifecycle harness on SGRG data)."""
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    bill = f"BILL-{t}"
    old = {**_vch(env, "OLD", "Sales", "Sales", [{"ledger_name": a, "amount": "-5000", "bill_allocations": [
        {"name": bill, "bill_type": "New Ref", "amount": "-5000"}]}], d="2026-02-14"), "alter_id": 90}
    new = {**_vch(env, "NEW", "Sales", "Sales", [{"ledger_name": a, "amount": "-3000", "bill_allocations": [
        {"name": bill, "bill_type": "New Ref", "amount": "-3000"}]}], d="2026-03-10"), "alter_id": 91}
    await _post(env, "vouchers", {"vouchers": [old, new, _receipt(env, "R", a, bill, "1000", alter=92, d="2026-03-11")]})
    assert await _links(f"R-{t}") == {f"NEW-{t}": "1000.00"}
    if how == "cancelled":
        await _post(env, "vouchers", {"vouchers": [{**new, "alter_id": 93, "is_cancelled": True}]})
    else:
        async with AsyncSessionLocal() as s:
            others = [g for (g,) in (await s.execute(select(TallyVoucherIndex.guid).where(
                TallyVoucherIndex.voucher_date == date(2026, 3, 10), TallyVoucherIndex.state == "ACTIVE",
                TallyVoucherIndex.guid != f"NEW-{t}"))).all()]
        await _post(env, "manifest", {"snapshot_id": f"DEL-{t}", "window_from": "2026-03-10", "window_to": "2026-03-10",
                                      "is_final_chunk": True, "guids": others or [f"OTHER-{t}"]})
    assert await _links(f"R-{t}") == {f"OLD-{t}": "1000.00"}, "relinked to the bill Tally still holds"
