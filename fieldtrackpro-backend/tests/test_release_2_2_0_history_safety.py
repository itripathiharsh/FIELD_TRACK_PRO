"""
Release 2.2.0 - historical financial years cannot disturb the live system.

  B1  historical Tally invoices / receipts create no reporting period (no PENDING_CLOSE for past years)
  B4  live screens (collections overview, account summary, BI without a window) exclude history;
      an explicit window still reaches it
  B6  a bill name used by two invoices of one customer (numbers restart each FY) is matched on its date
      for the due date and for "still open"
  capabilities endpoint: history_safe for the 2.2.0 agent's interlock
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceSource
from app.models.monthly_reporting_period import MonthlyReportingPeriod
from app.models.payment import Payment, PaymentSource
from app.models.tally_ledger import TallyOpenBill, TallySnapshotRun
from app.services import payment_tally, reporting_floor as RF
from app.services.period_service import ensure_monthly_periods_synced
from app.services.tally_sync_service import _get_system_user_id
from app.services.tally_v2_sync import _finish_bills_snapshot
from tests.conftest import requires_db

HIST = date(2025, 6, 10)    # FY 2025-26: history
LIVE = date(2026, 6, 10)    # FY 2026-27: live


# ------------------------------------------------------------------ unit: the floor itself

def test_floor_is_the_live_fy_start_and_explicit_windows_are_honoured():
    assert RF.reporting_floor() == date(2026, 4, 1)
    assert RF.effective_start(None) == date(2026, 4, 1)
    assert RF.effective_start(date(2025, 4, 1)) == date(2025, 4, 1)


def test_is_live_classifies_tally_history_and_never_field_collections():
    class R:
        def __init__(self, **kw):
            self.__dict__.update(kw)
    assert not RF.is_live_invoice(R(source=InvoiceSource.TALLY, invoice_date=HIST))
    assert not RF.is_live_invoice(R(source=InvoiceSource.TALLY_RETIRED, invoice_date=HIST))
    assert RF.is_live_invoice(R(source=InvoiceSource.TALLY, invoice_date=LIVE))
    assert RF.is_live_invoice(R(source=InvoiceSource.MANUAL, invoice_date=HIST))
    assert not RF.is_live_payment(R(source=PaymentSource.TALLY, payment_date=HIST))
    assert RF.is_live_payment(R(source=PaymentSource.MANUAL, payment_date=HIST)), "field collections are live"


# ------------------------------------------------------------------ DB fixtures

async def _customer(session) -> Customer:
    c = (await session.execute(select(Customer).where(Customer.tally_is_debtor.is_(True)).limit(1))).scalar_one_or_none()
    if c is None:
        c = (await session.execute(select(Customer).limit(1))).scalar_one()
    return c


async def _invoice(session, customer_id, d: date, amount: str, bill: str) -> Invoice:
    inv = Invoice(customer_id=customer_id, invoice_number=f"T22-{uuid.uuid4().hex[:8]}", invoice_date=d,
                  amount=Decimal(amount), source=InvoiceSource.TALLY, source_reference=f"T22-GUID-{uuid.uuid4()}",
                  tally_bill_name=bill, created_by=await _get_system_user_id(session))
    session.add(inv)
    await session.flush()
    return inv


# ------------------------------------------------------------------ B1

@requires_db
@pytest.mark.asyncio
async def test_B1_historical_tally_invoice_creates_no_reporting_period():
    year, month = 2025, 6
    async with AsyncSessionLocal() as session:
        await session.execute(delete(MonthlyReportingPeriod).where(MonthlyReportingPeriod.period_year == year,
                                                                   MonthlyReportingPeriod.period_month == month))
        await session.commit()
        cust = await _customer(session)
        inv = await _invoice(session, cust.id, HIST, "1000.00", f"B1-{uuid.uuid4().hex[:6]}")
        await session.commit()
        try:
            periods = await ensure_monthly_periods_synced(session)
            assert not [p for p in periods if (p.period_year, p.period_month) == (year, month)]
            assert (await session.execute(select(MonthlyReportingPeriod).where(
                MonthlyReportingPeriod.period_year == year, MonthlyReportingPeriod.period_month == month))).first() is None
        finally:
            await session.execute(delete(Invoice).where(Invoice.id == inv.id))
            await session.commit()


# ------------------------------------------------------------------ B4

@requires_db
@pytest.mark.asyncio
async def test_B4_live_clause_excludes_history_in_sql():
    async with AsyncSessionLocal() as session:
        cust = await _customer(session)
        h = await _invoice(session, cust.id, HIST, "100.00", f"B4H-{uuid.uuid4().hex[:6]}")
        l = await _invoice(session, cust.id, LIVE, "200.00", f"B4L-{uuid.uuid4().hex[:6]}")
        await session.commit()
        try:
            ids = {r for (r,) in (await session.execute(
                select(Invoice.id).where(Invoice.id.in_([h.id, l.id]), RF.live_invoice_clause(Invoice)))).all()}
            assert ids == {l.id}
        finally:
            await session.execute(delete(Invoice).where(Invoice.id.in_([h.id, l.id])))
            await session.commit()


# ------------------------------------------------------------------ B6

@requires_db
@pytest.mark.asyncio
async def test_B6_repeated_bill_name_matches_on_date_for_due_date_and_open_amount():
    bill = f"SGRG/KNP/{uuid.uuid4().hex[:5]}"
    sid = f"BILLS-T22-{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as session:
        cust = await _customer(session)
        old = await _invoice(session, cust.id, HIST, "100.00", bill)   # FY 2025-26 invoice, same bill name
        new = await _invoice(session, cust.id, LIVE, "200.00", bill)   # FY 2026-27 invoice
        await session.commit()
        run = TallySnapshotRun(id=sid, kind="BILLS", as_of_date=date(2099, 1, 1), status="RECEIVING")
        session.add(run)
        session.add(TallyOpenBill(customer_id=cust.id, as_of_date=date(2099, 1, 1), snapshot_id=sid, bill_name=bill,
                                  bill_date=LIVE, due_date=date(2026, 7, 10), pending_amount=Decimal("150.00")))
        await session.flush()
        try:
            await _finish_bills_snapshot(session, run)
            await session.commit()
            await session.refresh(old)
            await session.refresh(new)
            assert new.due_date == date(2026, 7, 10)
            assert old.due_date != date(2026, 7, 10), "the FY 2025-26 invoice with the same bill name is not touched"
            settled = await payment_tally.posted_paid_by_invoice(session, [old.id, new.id])
            if cust.tally_is_debtor:
                assert settled[new.id] == Decimal("50.00"), "200 - 150 still open"
                assert settled[old.id] == Decimal("100.00"), "no open bill on its date: settled"
        finally:
            await session.execute(delete(TallyOpenBill).where(TallyOpenBill.snapshot_id == sid))
            await session.execute(delete(TallySnapshotRun).where(TallySnapshotRun.id == sid))
            await session.execute(delete(Invoice).where(Invoice.id.in_([old.id, new.id])))
            await session.commit()


# ------------------------------------------------------------------ capabilities

def test_capabilities_route_is_registered_and_declares_history_safe():
    from app.api.v1 import tally_integration as T
    routes = {r.path: r for r in T.router.routes}
    assert any(p.endswith("/capabilities") for p in routes)
    import inspect
    src = inspect.getsource(T.agent_capabilities)
    assert '"history_safe": True' in src
