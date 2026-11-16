"""
Tally lifecycle of a payment - the ONE place that decides whether a collection
has reached Tally.

Business rule (owner-approved): Tally is the final truth.

    employee records (PENDING_VERIFICATION)
      -> admin verifies against the bank (VERIFIED)
      -> the receipt reaches Tally, either
           * the sync agent writes it (write-back job CONFIRMED), or
           * the accountant keys it by hand, the agent imports it as a TALLY
             payment, and an admin links the collection to it
      -> ONLY NOW may outstanding balances drop.

Money is counted exactly once. A linked MANUAL collection and its TALLY receipt
are the same money: the TALLY row carries it in every total and the linked
MANUAL row keeps only the operational record (who collected it, which visit).

Money roles of a VERIFIED payment (the SQL clauses below and the Python helpers
agree on these):
  posted    source TALLY, or MANUAL with a CONFIRMED write-back job (not linked)
  awaiting  MANUAL, no CONFIRMED job, not linked
  (none)    MANUAL linked to a TALLY receipt; any other source (EXCEL_IMPORT is
            legacy data and never counts as Tally money)
  collected = posted + awaiting

Derived `tally_status` (display, per payment):
  NOT_APPLICABLE  not VERIFIED (pending / rejected), or a non-TALLY non-MANUAL source
  AWAITING_TALLY  verified MANUAL, job PENDING/PROCESSING/SENT or no job, not linked
  POSTED          source TALLY, job CONFIRMED, or linked to a TALLY receipt
  FAILED          job FAILED (terminal; admin may retry)

Collections *totals* (dashboard/reports) count `collected` - the cash has been
received - and expose the posted / awaiting split separately.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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


def _not_linked():
    return Payment.tally_receipt_payment_id.is_(None)


def posted_clause():
    """SQL predicate (money): VERIFIED and its receipt is in Tally, counted once -
    a MANUAL collection linked to a TALLY receipt is excluded (the receipt counts)."""
    return and_(
        Payment.status == PaymentStatus.VERIFIED,
        or_(
            Payment.source == PaymentSource.TALLY,
            and_(Payment.source == PaymentSource.MANUAL, _not_linked(), confirmed_job_exists()),
        ),
    )


def awaiting_clause():
    """SQL predicate (money): VERIFIED MANUAL collection not yet in Tally - no
    CONFIRMED write-back job and not linked to an imported Tally receipt."""
    return and_(
        Payment.status == PaymentStatus.VERIFIED,
        Payment.source == PaymentSource.MANUAL,
        _not_linked(),
        ~confirmed_job_exists(),
    )


def linked_clause():
    """SQL predicate: VERIFIED MANUAL collection confirmed via a linked Tally receipt."""
    return and_(
        Payment.status == PaymentStatus.VERIFIED,
        Payment.source == PaymentSource.MANUAL,
        Payment.tally_receipt_payment_id.is_not(None),
    )


def collected_clause(employee_id: uuid.UUID | None = None):
    """SQL predicate (money): cash received, each rupee once = posted + awaiting.

    Scoped to one employee it is that employee's verified field collections,
    linked ones included: an imported Tally receipt carries no employee, so the
    linked collection is the only record crediting that money to the employee
    (and the receipt itself never matches an employee filter, so nothing doubles)."""
    if employee_id is not None:
        return and_(
            Payment.status == PaymentStatus.VERIFIED,
            Payment.source == PaymentSource.MANUAL,
            Payment.employee_id == employee_id,
        )
    return or_(posted_clause(), awaiting_clause())


def posted_clause_for(employee_id: uuid.UUID | None = None):
    """The `posted` part of collected_clause(employee_id): posted + awaiting == collected."""
    if employee_id is not None:
        return or_(posted_clause(), linked_clause())
    return posted_clause()


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
    manual_open = and_(
        Payment.status == PaymentStatus.VERIFIED,
        Payment.source == PaymentSource.MANUAL,
        _not_linked(),
        ~confirmed_job_exists(),
    )
    if ts == TallyStatus.NOT_APPLICABLE:
        return or_(
            Payment.status != PaymentStatus.VERIFIED,
            Payment.source.not_in([PaymentSource.TALLY, PaymentSource.MANUAL]),
        )
    if ts == TallyStatus.POSTED:
        return or_(posted_clause(), linked_clause())
    if ts == TallyStatus.FAILED:
        return and_(manual_open, failed)
    return and_(manual_open, ~failed)  # AWAITING_TALLY


def stuck_clause(now: datetime | None = None):
    """FAILED, or AWAITING_TALLY for >= TALLY_STUCK_MINUTES since verification.

    With write-back disabled no agent will ever post the receipt, so an awaiting
    collection is waiting for the accountant + an admin link, not stuck."""
    if not settings.tally_writeback_enabled:
        return tally_status_clause(TallyStatus.FAILED)
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


def is_linked(payment: Payment) -> bool:
    return payment.source == PaymentSource.MANUAL and payment.tally_receipt_payment_id is not None


def is_posted(payment: Payment, job: TallyWritebackQueue | None) -> bool:
    """Money role, mirrors posted_clause(): False for a linked collection (its
    TALLY receipt carries the money)."""
    if payment.status != PaymentStatus.VERIFIED:
        return False
    if payment.source == PaymentSource.TALLY:
        return True
    if payment.source != PaymentSource.MANUAL or is_linked(payment):
        return False
    return _job_status_value(job) == WritebackStatus.CONFIRMED.value


def is_awaiting(payment: Payment, job: TallyWritebackQueue | None) -> bool:
    """Money role, mirrors awaiting_clause()."""
    return (
        payment.status == PaymentStatus.VERIFIED
        and payment.source == PaymentSource.MANUAL
        and not is_linked(payment)
        and _job_status_value(job) != WritebackStatus.CONFIRMED.value
    )


def derive_tally_status(payment: Payment, job: TallyWritebackQueue | None) -> TallyStatus:
    if payment.status != PaymentStatus.VERIFIED:
        return TallyStatus.NOT_APPLICABLE
    if payment.source == PaymentSource.TALLY:
        return TallyStatus.POSTED
    if payment.source != PaymentSource.MANUAL:
        return TallyStatus.NOT_APPLICABLE
    if is_linked(payment):
        return TallyStatus.POSTED
    js = _job_status_value(job)
    if js == WritebackStatus.CONFIRMED.value:
        return TallyStatus.POSTED
    if js == WritebackStatus.FAILED.value:
        return TallyStatus.FAILED
    return TallyStatus.AWAITING_TALLY


def is_stuck(payment: Payment, status: TallyStatus, now: datetime | None = None) -> bool:
    """FAILED always needs an admin; AWAITING_TALLY becomes stuck after 30 minutes
    (measured from verification time) - only while write-back is enabled."""
    if status == TallyStatus.FAILED:
        return True
    if status != TallyStatus.AWAITING_TALLY or not settings.tally_writeback_enabled:
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
    if is_linked(payment):
        posted_at = payment.tally_linked_at
    elif job is not None and _job_status_value(job) == WritebackStatus.CONFIRMED.value:
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
        "tally_receipt_payment_id": payment.tally_receipt_payment_id,
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
    await _apply_tally_open_bills(session, ids, out)
    return out


async def _apply_tally_open_bills(session: AsyncSession, ids: list[uuid.UUID], out: dict[uuid.UUID, Decimal]) -> None:
    """Tally-balance mode: for a Tally invoice of a Tally debtor, what is still open is
    Tally's own pending amount for its bill in the latest Bills Receivable snapshot
    (0 when the bill is no longer open), so settled = amount - pending. Invoices
    keyed in after that snapshot, or without a bill name, keep the allocation figure."""
    from app.models.customer import Customer
    from app.models.invoice import Invoice, InvoiceSource
    from app.models.tally_ledger import TallyOpenBill, TallySnapshotRun

    run = (await session.execute(
        select(TallySnapshotRun).where(TallySnapshotRun.kind == "BILLS", TallySnapshotRun.status == "COMPLETE")
        .order_by(TallySnapshotRun.as_of_date.desc(), TallySnapshotRun.completed_at.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return
    rows = (await session.execute(
        select(Invoice.id, Invoice.customer_id, Invoice.tally_bill_name, Invoice.amount)
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(
            Invoice.id.in_(ids), Invoice.source == InvoiceSource.TALLY, Invoice.tally_bill_name.is_not(None),
            Invoice.created_at <= run.started_at, Customer.tally_is_debtor.is_(True),
        )
    )).all()
    if not rows:
        return
    pending: dict[tuple[uuid.UUID, str], Decimal] = {}
    for cid, name, amt in (await session.execute(
        select(TallyOpenBill.customer_id, TallyOpenBill.bill_name, func.sum(TallyOpenBill.pending_amount))
        .where(TallyOpenBill.as_of_date == run.as_of_date,
               TallyOpenBill.customer_id.in_({r.customer_id for r in rows}))
        .group_by(TallyOpenBill.customer_id, TallyOpenBill.bill_name)
    )).all():
        pending[(cid, name)] = amt or Decimal("0.00")
    for inv_id, cid, name, amount in rows:
        still_open = max(min(pending.get((cid, name), Decimal("0.00")), amount), Decimal("0.00"))
        out[inv_id] = amount - still_open


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
