"""Regression tests: Tally receipt -> invoice links (staging import of the client's data, 19-Nov-2026).

R1  A receipt that settles some bills and re-opens others (positive and negative bill allocations, netting to the
    receipt) is linked with Tally's signs. Before the fix every amount was taken as absolute: the client's
    receipt 2128 (Rs 1,00,000 = +2,00,000 on three bills - 1,00,000 on three others) failed with
    "bill allocations 200000.00 exceed receipt 100000.00; left unlinked" and was quarantined (77 receipts).
R2  A receipt that reaches FieldTrack BEFORE the invoice raising its bill (a historical year loaded after the live
    year: 3,194 allocations, Rs 10.26 crore) is linked as soon as the invoice arrives.
R3  The remaining 78 cases, each class separately:
    a) New Ref / Advance allocation under the invoice's bill name (one Tally bill = ledger + name), advance
       received before the invoice;
    b) the same bill named twice in one receipt;
    c) a negative allocation alone on a bill (re-opens it);
    d) a bill name used by two invoices (numbers restart): the latest invoice on or before the receipt.
Plus: re-sending the same vouchers creates no duplicate row or link.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, _setup_debtors, _vch, env  # noqa: F401  (fixture reuse)


def _sale(e, key, ledger, number, amount, d, ref_type="New Ref"):
    return _vch(e, key, "Oppo", "Sales", [{"ledger_name": ledger, "amount": f"-{amount}",
                "bill_allocations": [{"name": number, "bill_type": ref_type, "amount": f"-{amount}"}]}],
                number=number, d=d)


def _receipt(e, key, ledger, amount, allocs, d):
    return _vch(e, key, "BANK RECEIPT", "Receipt",
                [{"ledger_name": ledger, "amount": str(amount),
                  "bill_allocations": [{"name": n, "bill_type": bt, "amount": str(a)} for n, bt, a in allocs]}],
                counter=[{"ledger_name": "UCO BANK OD", "ledger_class": "BANK", "amount": f"-{amount}"}], d=d)


async def _links(e, key):
    async with AsyncSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.source_reference == f"{key}-{e['tag']}"))).scalar_one()
        rows = (await s.execute(
            select(Invoice.tally_bill_name, PIA.allocated_amount).join(Invoice, Invoice.id == PIA.invoice_id)
            .where(PIA.payment_id == pay.id))).all()
        return {n: a for n, a in rows}


@requires_db
@pytest.mark.asyncio
async def test_r1_positive_and_negative_allocations_link_with_tally_signs(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    bills = {f"{t}/2127": "35716", f"{t}/723": "30000", f"{t}/920": "34284",
             f"{t}/329": "11961.60", f"{t}/348": "63807", f"{t}/526": "124231.40"}
    await _post(env, "vouchers", {"vouchers": [_sale(env, f"S{i}", a, n, "200000", "2026-05-01")
                                               for i, n in enumerate(bills)]})
    res = await _post(env, "vouchers", {"vouchers": [_receipt(env, "R2128", a, "100000", [
        (f"{t}/2127", "Agst Ref", "-35716"), (f"{t}/723", "Agst Ref", "-30000"), (f"{t}/920", "Agst Ref", "-34284"),
        (f"{t}/329", "Agst Ref", "11961.60"), (f"{t}/348", "Agst Ref", "63807"), (f"{t}/526", "Agst Ref", "124231.40"),
    ], "2026-06-05")]})
    assert res["failed_count"] == 0 and not res.get("errors"), res
    links = await _links(env, "R2128")
    assert links == {f"{t}/2127": D("-35716.00"), f"{t}/723": D("-30000.00"), f"{t}/920": D("-34284.00"),
                     f"{t}/329": D("11961.60"), f"{t}/348": D("63807.00"), f"{t}/526": D("124231.40")}
    assert sum(links.values()) == D("100000.00")


@requires_db
@pytest.mark.asyncio
async def test_r1_allocations_really_exceeding_the_receipt_still_refused(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S", a, f"{t}/1", "50000", "2026-05-01")]})
    res = await _post(env, "vouchers", {"vouchers": [_receipt(env, "R", a, "10000", [(f"{t}/1", "Agst Ref", "20000")],
                                                              "2026-05-02")]})
    assert "exceed receipt" in str(res), res
    assert await _links(env, "R") == {}


@requires_db
@pytest.mark.asyncio
async def test_r2_receipt_before_its_invoice_is_linked_when_the_invoice_arrives(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    # Live year first: an FY 2026-27 receipt paying an FY 2025-26 bill that FieldTrack does not hold yet.
    await _post(env, "vouchers", {"vouchers": [_receipt(env, "R", a, "25000", [
        (f"SGRG/25-26/{t}", "Agst Ref", "15000"), (f"SGRG/26-27/{t}", "Agst Ref", "10000")], "2026-04-01")]})
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S27", a, f"SGRG/26-27/{t}", "10000", "2026-04-01")]})
    assert await _links(env, "R") == {f"SGRG/26-27/{t}": D("10000.00")}
    # The historical year arrives afterwards: the waiting allocation links by itself.
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S26", a, f"SGRG/25-26/{t}", "40000", "2026-03-10")]})
    assert await _links(env, "R") == {f"SGRG/26-27/{t}": D("10000.00"), f"SGRG/25-26/{t}": D("15000.00")}


@requires_db
@pytest.mark.asyncio
async def test_r3a_advance_and_new_ref_under_the_invoice_bill_name_settle_it(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [
        _receipt(env, "ADV", a, "45000", [(f"{t}/1797", "Advance", "45000")], "2025-09-30"),     # before the invoice
        _receipt(env, "NEW", a, "1000", [(f"{t}/289", "New Ref", "1000")], "2026-05-22"),        # same day
    ]})
    await _post(env, "vouchers", {"vouchers": [_sale(env, "I1797", a, f"{t}/1797", "46290", "2025-10-04"),
                                               _sale(env, "I289", a, f"{t}/289", "1000", "2026-05-22")]})
    assert await _links(env, "ADV") == {f"{t}/1797": D("45000.00")}
    assert await _links(env, "NEW") == {f"{t}/289": D("1000.00")}


@requires_db
@pytest.mark.asyncio
async def test_r3b_same_bill_twice_in_one_receipt_is_netted_into_one_link(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S1", a, f"{t}/382", "62854", "2026-06-05"),
                                               _sale(env, "S2", a, f"{t}/559", "13380", "2026-06-26")]})
    # The client's receipt (13-Nov-2026): bill 559 named twice, offset by a negative on-account line;
    # Tally's allocations net to the receipt 31,234 (the old code saw 44,614 > 31,234 and linked nothing).
    res = await _post(env, "vouchers", {"vouchers": [_receipt(env, "R", a, "31234", [
        (f"{t}/382", "Agst Ref", "17854"), (f"{t}/559", "Agst Ref", "13380"), (f"{t}/559", "Agst Ref", "13380"),
        ("", "On Account", "-13380")], "2026-11-13")]})
    assert res["failed_count"] == 0 and not res.get("errors"), res
    assert await _links(env, "R") == {f"{t}/382": D("17854.00"), f"{t}/559": D("26760.00")}


@requires_db
@pytest.mark.asyncio
async def test_r3c_negative_allocation_alone_reopens_the_bill(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "S1", a, f"{t}/2571", "10948", "2026-06-19"),
                                               _sale(env, "S2", a, f"{t}/538", "19576", "2026-06-24")]})
    await _post(env, "vouchers", {"vouchers": [_receipt(env, "R", a, "5899", [
        (f"{t}/2571", "Agst Ref", "-552"), (f"{t}/538", "Agst Ref", "6451")], "2026-06-27")]})
    assert await _links(env, "R") == {f"{t}/2571": D("-552.00"), f"{t}/538": D("6451.00")}


@requires_db
@pytest.mark.asyncio
async def test_r3d_reused_bill_name_links_the_invoice_on_or_before_the_receipt(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    await _post(env, "vouchers", {"vouchers": [_sale(env, "FEB", a, f"UNO/66/{t}", "112378", "2026-02-11"),
                                               _sale(env, "APR", a, f"UNO/66/{t}", "129792", "2026-04-08")]})
    await _post(env, "vouchers", {"vouchers": [
        _receipt(env, "RMAR", a, "50000", [(f"UNO/66/{t}", "Agst Ref", "50000")], "2026-03-01"),
        _receipt(env, "RMAY", a, "60000", [(f"UNO/66/{t}", "Agst Ref", "60000")], "2026-05-01")]})
    async with AsyncSessionLocal() as s:
        def inv_of(key):
            return select(Invoice.id).where(Invoice.source_reference == f"{key}-{t}").scalar_subquery()
        for rkey, ikey in (("RMAR", "FEB"), ("RMAY", "APR")):
            got = (await s.execute(select(PIA.invoice_id).join(Payment, Payment.id == PIA.payment_id)
                                   .where(Payment.source_reference == f"{rkey}-{t}"))).scalars().all()
            assert got == [(await s.execute(select(inv_of(ikey)))).scalar_one()], rkey


@requires_db
@pytest.mark.asyncio
async def test_resend_creates_no_duplicate_rows_or_links(env):
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    batch = [_sale(env, "S", a, f"{t}/9", "30000", "2026-07-01"),
             _receipt(env, "R", a, "30000", [(f"{t}/9", "Agst Ref", "40000"), (f"{t}/8", "Agst Ref", "-10000")],
                      "2026-07-02")]
    for _ in range(3):
        res = await _post(env, "vouchers", {"vouchers": batch})
        assert res["failed_count"] == 0, res
    async with AsyncSessionLocal() as s:
        n_pay = (await s.execute(select(func.count()).select_from(Payment)
                                 .where(Payment.source_reference == f"R-{t}"))).scalar_one()
        n_inv = (await s.execute(select(func.count()).select_from(Invoice)
                                 .where(Invoice.source_reference == f"S-{t}"))).scalar_one()
        n_link = (await s.execute(select(func.count()).select_from(PIA).join(Payment, Payment.id == PIA.payment_id)
                                  .where(Payment.source_reference == f"R-{t}"))).scalar_one()
    assert (n_pay, n_inv, n_link) == (1, 1, 1)
    assert await _links(env, "R") == {f"{t}/9": D("40000.00")}   # the -10000 bill is not in FieldTrack


@requires_db
@pytest.mark.asyncio
async def test_r4_one_bill_raised_by_two_invoices_on_one_date_shows_tally_pending_once():
    """The client's bill SGRG/25-26/2645 (SGRG Automobiles): invoices 2693 (Rs 28,500) and 2708 (Rs 2,899), both
    19-Dec-2025, each raise Rs 2,899 on the same bill; Tally's pending is Rs 5,798. Before the fix every invoice
    of the bill got the whole pending (5,798 + 2,899 = 8,697 open)."""
    from datetime import date
    from sqlalchemy import delete
    from app.models.tally_ledger import TallyOpenBill, TallySnapshotRun
    from app.services import payment_tally
    from app.services.tally_v2_sync import _finish_bills_snapshot
    from tests.test_release_2_2_0_history_safety import _customer, _invoice

    bill, d = f"SGRG/25-26/{__import__('uuid').uuid4().hex[:6]}", date(2025, 12, 19)
    sid = f"BILLS-R4-{__import__('uuid').uuid4().hex}"
    async with AsyncSessionLocal() as s:
        cust = await _customer(s)
        if not cust.tally_is_debtor:
            pytest.skip("needs a Tally debtor customer in the test database")
        big = await _invoice(s, cust.id, d, "28500.00", bill)
        small = await _invoice(s, cust.id, d, "2899.00", bill)
        other = await _invoice(s, cust.id, date(2026, 5, 1), "1000.00", bill)   # same name, other date (B6 repeat)
        await s.commit()
        run = TallySnapshotRun(id=sid, kind="BILLS", as_of_date=date(2099, 1, 2), status="RECEIVING")
        s.add(run)
        s.add(TallyOpenBill(customer_id=cust.id, as_of_date=date(2099, 1, 2), snapshot_id=sid, bill_name=bill,
                            bill_date=d, due_date=d, pending_amount=D("5798.00")))
        await s.flush()
        try:
            await _finish_bills_snapshot(s, run)
            await s.commit()
            paid = await payment_tally.posted_paid_by_invoice(s, [big.id, small.id, other.id])
            open_ = {k: inv.amount - paid[inv.id] for k, inv in (("big", big), ("small", small), ("other", other))}
            assert open_["big"] + open_["small"] == D("5798.00"), open_
            assert open_["other"] == D("0.00"), open_
            # Asking for one invoice alone gives the same share as asking for all of them.
            alone = await payment_tally.posted_paid_by_invoice(s, [small.id])
            assert small.amount - alone[small.id] == open_["small"]
        finally:
            await s.execute(delete(TallyOpenBill).where(TallyOpenBill.snapshot_id == sid))
            await s.execute(delete(TallySnapshotRun).where(TallySnapshotRun.id == sid))
            await s.execute(delete(Invoice).where(Invoice.id.in_([big.id, small.id, other.id])))
            await s.commit()


@requires_db
@pytest.mark.asyncio
async def test_r5_link_choice_is_deterministic_for_invoices_of_one_bill_and_date(env):
    """The client's bill SGRG/UNO/911 (D K Mobile Safipur): two invoices of 15-Jun-2026 raise the same bill. A repeat
    upload moved the receipt's link from one to the other (tie on the creation time of a batch). The choice now
    depends on Tally data only (date, then voucher key) and never changes on re-send."""
    t = env["tag"]
    (a,) = await _setup_debtors(env, 1)
    s1 = _sale(env, "S1", a, f"UNO/911/{t}", "60950", "2026-06-15")
    s2 = _sale(env, "S2", a, f"UNO/911/{t}", "45712", "2026-06-15")
    rec = _receipt(env, "R", a, "97607.47", [(f"UNO/911/{t}", "Agst Ref", "97607.47")], "2026-08-14")
    seen = set()
    # S2 reaches FieldTrack first, S1 later (load order opposite to the voucher keys), then re-sends in any order.
    for i, batch in enumerate(([s2], [s1, rec], [rec], [s1, s2], [s2, s1, rec])):
        await _post(env, "vouchers", {"vouchers": batch})
        if i == 0:
            continue                         # the receipt is not in FieldTrack yet
        async with AsyncSessionLocal() as s:
            got = (await s.execute(select(Invoice.source_reference).join(PIA, PIA.invoice_id == Invoice.id)
                                   .join(Payment, Payment.id == PIA.payment_id)
                                   .where(Payment.source_reference == f"R-{t}"))).scalars().all()
        seen.add(tuple(got))
    assert seen == {(f"S2-{t}",)}, seen      # latest key of the two same-day invoices, every time
