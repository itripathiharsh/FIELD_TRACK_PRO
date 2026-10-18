"""
Tally lifecycle of a payment - the ONE place that decides whether a collection
has reached Tally.

Business rule (owner-approved): Tally is the final truth.

    employee records (PENDING_VERIFICATION)
      -> admin verifies against the bank (VERIFIED)
      -> sync agent writes the receipt to Tally (write-back job CONFIRMED)
      -> ONLY NOW may outstanding balances drop.

A payment "counts toward outstanding" (is *posted*) iff it is VERIFIED and
either
  * its source is not MANUAL (TALLY / EXCEL_IMPORT rows already live in Tally), or
  * its Tally write-back job is CONFIRMED.

Derived `tally_status`:
  NOT_APPLICABLE  payment is not VERIFIED (pending / rejected)
  AWAITING_TALLY  verified, job PENDING/PROCESSING/SENT (or no job yet)
  POSTED          job CONFIRMED (or non-MANUAL source)
  FAILED          job FAILED (terminal; admin may retry)

Collections *totals* (dashboard/reports) keep counting at VERIFIED - the cash
has been received - and expose the posted / awaiting split separately.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentSource, PaymentStatus
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus

TALLY_STUCK_MINUTES = 30


class TallyStatus(str, enum.Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AWAITING_TALLY = "AWAITING_TALLY"
    POSTED = "POSTED"
    FAILED = "FAILED"


def _job_status_value(job: TallyWritebackQueue | None) -> str | None:
    if job is None:
        return None
    s = job.status
    return s.value if hasattr(s, "value") else str(s)


# ---------------------------------------------------------------------------
# SQL expressions (usable inside any select)
# ---------------------------------------------------------------------------

def confirmed_job_exists():
    """Correlated EXISTS: a CONFIRMED write-back job for Payment.id."""
    return exists().where(
        and_(
            TallyWritebackQueue.entity_type == "PAYMENT",
            TallyWritebackQueue.entity_id == Payment.id,
            TallyWritebackQueue.status == WritebackStatus.CONFIRMED.value,
        )
    )


def posted_clause():
    """SQL predicate: payment is VERIFIED and its receipt is in Tally."""
    return and_(
        Payment.status == PaymentStatus.VERIFIED,
        or_(Payment.source != PaymentSource.MANUAL, confirmed_job_exists()),
    )


def awaiting_clause():
    """SQL predicate: payment is VERIFIED, MANUAL and NOT yet confirmed in Tally
    (job pending/processing/sent/failed/missing)."""
    return and_(
        Payment.status == PaymentStatus.VERIFIED,
        Payment.source == PaymentSource.MANUAL,
        ~confirmed_job_exists(),
    )


def _job_status_exists(status: WritebackStatus):
    return exists().where(
        and_(
            TallyWritebackQueue.entity_type == "PAYMENT",
            TallyWritebackQueue.entity_id == Payment.id,
            TallyWritebackQueue.status == status.value,
        )
    )


def tally_status_clause(ts: "TallyStatus"):
    """SQL predicate equivalent of derive_tally_status() == ts (queue filters)."""
    failed = _job_status_exists(WritebackStatus.FAILED)
    manual_verified = and_(Payment.status == PaymentStatus.VERIFIED, Payment.source == PaymentSource.MANUAL)
    if ts == TallyStatus.NOT_APPLICABLE:
        return Payment.status != PaymentStatus.VERIFIED
    if ts == TallyStatus.POSTED:
        return posted_clause()
    if ts == TallyStatus.FAILED:
        return and_(manual_verified, ~confirmed_job_exists(), failed)
    return and_(manual_verified, ~confirmed_job_exists(), ~failed)  # AWAITING_TALLY


def stuck_clause(now: datetime | None = None):
    """FAILED, or AWAITING_TALLY for >= TALLY_STUCK_MINUTES since verification."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=TALLY_STUCK_MINUTES)
    awaiting_old = and_(
        tally_status_clause(TallyStatus.AWAITING_TALLY),
        func.coalesce(Payment.reviewed_at, Payment.created_at) <= cutoff,
    )
    return or_(tally_status_clause(TallyStatus.FAILED), awaiting_old)


# ---------------------------------------------------------------------------
# Python helpers
# ---------------------------------------------------------------------------

async def load_jobs(
    session: AsyncSession, payment_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, TallyWritebackQueue]:
    """payment_id -> write-back job (one job per payment: idempotency key)."""
    ids = list({pid for pid in payment_ids})
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(TallyWritebackQueue)
            .where(TallyWritebackQueue.entity_type == "PAYMENT", TallyWritebackQueue.entity_id.in_(ids))
            .order_by(TallyWritebackQueue.created_at.asc())
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    # If (abnormally) several exist, a CONFIRMED one wins, then the newest.
    out: dict[uuid.UUID, TallyWritebackQueue] = {}
    for j in rows:
        cur = out.get(j.entity_id)
        if cur is None or _job_status_value(cur) != WritebackStatus.CONFIRMED.value:
            out[j.entity_id] = j
    return out


async def confirmed_payment_ids(session: AsyncSession, payment_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    jobs = await load_jobs(session, payment_ids)
    return {pid for pid, j in jobs.items() if _job_status_value(j) == WritebackStatus.CONFIRMED.value}


def is_posted(payment: Payment, job: TallyWritebackQueue | None) -> bool:
    if payment.status != PaymentStatus.VERIFIED:
        return False
    if payment.source != PaymentSource.MANUAL:
        return True
    return _job_status_value(job) == WritebackStatus.CONFIRMED.value


def derive_tally_status(payment: Payment, job: TallyWritebackQueue | None) -> TallyStatus:
    if payment.status != PaymentStatus.VERIFIED:
        return TallyStatus.NOT_APPLICABLE
    if payment.source != PaymentSource.MANUAL:
        return TallyStatus.POSTED
    js = _job_status_value(job)
    if js == WritebackStatus.CONFIRMED.value:
        return TallyStatus.POSTED
    if js == WritebackStatus.FAILED.value:
        return TallyStatus.FAILED
    return TallyStatus.AWAITING_TALLY


def is_stuck(payment: Payment, status: TallyStatus, now: datetime | None = None) -> bool:
    """FAILED always needs an admin; AWAITING_TALLY becomes stuck after 30 minutes
    (measured from verification time)."""
    if status == TallyStatus.FAILED:
        return True
    if status != TallyStatus.AWAITING_TALLY:
        return False
    ref = payment.reviewed_at or payment.created_at
    if ref is None:
        return False
    now = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return now - ref >= timedelta(minutes=TALLY_STUCK_MINUTES)


def tally_fields(
    payment: Payment, job: TallyWritebackQueue | None, is_admin: bool, now: datetime | None = None
) -> dict:
    """The additive PaymentRead fields. `tally_error` / `tally_stuck` and the
    bank-verification record are ADMIN-only (None for employees)."""
    status = derive_tally_status(payment, job)
    voucher = None
    posted_at = None
    if job is not None and _job_status_value(job) == WritebackStatus.CONFIRMED.value:
        voucher = job.tally_voucher_number
        posted_at = job.confirmed_at
    error = None
    if is_admin and status in (TallyStatus.FAILED, TallyStatus.AWAITING_TALLY) and job is not None:
        error = job.last_error
    return {
        "tally_status": status,
        "tally_voucher_number": voucher,
        "tally_posted_at": posted_at,
        "tally_error": error,
        "tally_stuck": is_stuck(payment, status, now) if is_admin else None,
    }


# ---------------------------------------------------------------------------
# Bulk money helpers (single source for invoice-level paid / awaiting)
# ---------------------------------------------------------------------------

async def posted_paid_by_invoice(
    session: AsyncSession, invoice_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """invoice_id -> money settled against it by payments that are POSTED.

    Per payment, exactly one rule applies (so nothing is ever counted twice,
    including after the sync agent reads the same receipt back from Tally and
    creates PaymentInvoiceAllocation rows for it):
      * payment has invoice allocations -> use those amounts per invoice;
      * otherwise -> the payment's direct invoice_id gets the full amount.
    """
    from app.models.payment_invoice_allocation import PaymentInvoiceAllocation as PIA

    ids = list({i for i in invoice_ids})
    out: dict[uuid.UUID, Decimal] = {i: Decimal("0.00") for i in ids}
    if not ids:
        return out

    alloc_rows = (
        await session.execute(
            select(PIA.invoice_id, func.coalesce(func.sum(PIA.allocated_amount), Decimal("0.00")))
            .join(Payment, Payment.id == PIA.payment_id)
            .where(PIA.invoice_id.in_(ids), posted_clause())
            .group_by(PIA.invoice_id)
        )
    ).all()
    for inv_id, amt in alloc_rows:
        out[inv_id] += amt or Decimal("0.00")

    has_alloc = exists().where(PIA.payment_id == Payment.id)
    direct_rows = (
        await session.execute(
            select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
            .where(Payment.invoice_id.in_(ids), posted_clause(), ~has_alloc)
            .group_by(Payment.invoice_id)
        )
    ).all()
    for inv_id, amt in direct_rows:
        out[inv_id] += amt or Decimal("0.00")
    return out


async def awaiting_by_invoice(
    session: AsyncSession, invoice_ids: Iterable[uuid.UUID], exclude_payment_id: uuid.UUID | None = None
) -> dict[uuid.UUID, Decimal]:
    """invoice_id -> verified MANUAL money tied to it that is not yet in Tally."""
    ids = list({i for i in invoice_ids})
    out: dict[uuid.UUID, Decimal] = {i: Decimal("0.00") for i in ids}
    if not ids:
        return out
    stmt = (
        select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
        .where(Payment.invoice_id.in_(ids), awaiting_clause())
        .group_by(Payment.invoice_id)
    )
    if exclude_payment_id is not None:
        stmt = stmt.where(Payment.id != exclude_payment_id)
    for inv_id, amt in (await session.execute(stmt)).all():
        out[inv_id] += amt or Decimal("0.00")
    return out
