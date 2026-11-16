"""
Payment ("Collection") Service.

Follows the same Router -> Service -> Repository -> Storage Service pattern
as media_service.py, reusing the identical ownership check
(visit_service.get_visit_for_user) so a collection can never be created
against a visit the caller doesn't own, and reusing storage_service directly
for proof upload/download rather than a new media abstraction.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
from app.models.payment import Payment, PaymentBrandAllocation, PaymentStatus, PaymentSource
from app.models.payment_proof import PaymentProof
from app.models.invoice import Invoice, InvoiceSource
from app.models.user import Role, User
from app.models.visit import VisitStatus
from app.repositories.payment_repo import PaymentProofRepository, PaymentRepository
from app.schemas.payment import PaymentAllocationUpdate, PaymentCreate, PaymentRead, PaymentVerifyRequest
from app.services.file_validation_service import FileValidationService
from app.services.invoice_service import get_invoice
from app.services.period_service import assert_period_open_for_date
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit_for_user

logger = logging.getLogger("fieldtrackpro")


_MONEY_TOLERANCE = Decimal("0.005")


async def _lock_payment(payment_id: uuid.UUID, session: AsyncSession) -> Payment | None:
    """SELECT ... FOR UPDATE on the payment so concurrent verify/reject serialise."""
    result = await session.execute(
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _lock_invoice(invoice_id: uuid.UUID, session: AsyncSession) -> Invoice:
    result = await session.execute(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise BaseAPIException(status_code=404, detail="Invoice not found", error_code="INVOICE_NOT_FOUND")
    return invoice


async def _pending_amount_for_invoice(
    invoice_id: uuid.UUID, session: AsyncSession, exclude_payment_id: uuid.UUID | None = None
) -> Decimal:
    stmt = select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
        Payment.invoice_id == invoice_id,
        Payment.status == PaymentStatus.PENDING_VERIFICATION,
    )
    if exclude_payment_id is not None:
        stmt = stmt.where(Payment.id != exclude_payment_id)
    return (await session.execute(stmt)).scalar() or Decimal("0.00")


async def invoice_outstanding_under_lock(
    invoice_id: uuid.UUID,
    session: AsyncSession,
    exclude_payment_id: uuid.UUID | None = None,
    include_pending: bool = True,
) -> tuple[Invoice, Decimal]:
    """
    Lock the invoice row and return (invoice, outstanding). Outstanding is
    invoice.amount minus money settled in Tally, minus VERIFIED-but-awaiting-Tally
    money (committed, not yet reflected in the displayed balance), minus (optionally) other collections
    still awaiting verification, so two field reps cannot both collect the
    last rupee of the same invoice.
    """
    from app.services.invoice_service import _verified_paid_amount

    from app.services import payment_tally

    invoice = await _lock_invoice(invoice_id, session)
    paid = await _verified_paid_amount(invoice_id, session)
    # Verified money not yet confirmed in Tally does not reduce the displayed
    # outstanding, but it IS committed: it must still block over-collection.
    awaiting = (await payment_tally.awaiting_by_invoice(session, [invoice_id], exclude_payment_id))[invoice_id]
    pending = (
        await _pending_amount_for_invoice(invoice_id, session, exclude_payment_id) if include_pending else Decimal("0.00")
    )
    return invoice, invoice.amount - paid - awaiting - pending


def to_payment_read(payment: Payment, job=None, is_admin: bool = False) -> PaymentRead:
    """
    `job` is the payment's Tally write-back job (see payment_tally.load_jobs);
    callers that hold a session should prefer `build_payment_reads`, which
    fetches it. `is_admin` unlocks tally_error / tally_stuck / bank fields.
    """
    from app.services import payment_tally

    return PaymentRead(
        **payment_tally.tally_fields(payment, job, is_admin),
        bank_reference=payment.bank_reference if is_admin else None,
        bank_verified_on=payment.bank_verified_on if is_admin else None,
        verified_note=payment.verified_note if is_admin else None,
        id=payment.id,
        visit_id=payment.visit_id,
        customer_id=payment.customer_id,
        employee_id=payment.employee_id,
        invoice_id=payment.invoice_id,
        amount=payment.amount,
        payment_method=payment.payment_method,
        payment_date=payment.payment_date,
        cheque_number=payment.cheque_number,
        cheque_bank_name=payment.cheque_bank_name,
        utr_reference=payment.utr_reference,
        notes=payment.notes,
        status=payment.status,
        source=payment.source,
        source_reference=payment.source_reference,
        tally_voucher_type=payment.tally_voucher_type,
        tally_transaction_type=payment.tally_transaction_type,
        narration=payment.narration,
        rejection_reason=payment.rejection_reason,
        reviewed_by=payment.reviewed_by,
        reviewed_at=payment.reviewed_at,
        created_by=payment.created_by,
        created_at=payment.created_at,
        proofs=[
            {
                "id": p.id,
                "payment_id": p.payment_id,
                "storage_key": p.storage_key,
                "file_size_bytes": p.file_size_bytes,
                "original_filename": p.original_filename,
                "uploaded_by": p.uploaded_by,
                "uploaded_at": p.uploaded_at,
            }
            for p in (payment.proofs or [])
        ],
        allocations=[
            {
                "id": a.id,
                "payment_id": a.payment_id,
                "brand": a.brand,
                "allocated_amount": a.allocated_amount,
                "created_at": a.created_at,
            }
            for a in (payment.allocations or [])
        ],
    )


async def build_payment_reads(
    payments: Sequence[Payment], session: AsyncSession, is_admin: bool
) -> list[PaymentRead]:
    """Single helper that turns payments into PaymentRead with Tally status
    (one batched job lookup). Admin sees tally_error/tally_stuck; employees do not.
    `is_admin` is passed in (captured before any service call) because a rollback
    inside the service expires the request's User object."""
    from app.services import payment_tally

    jobs = await payment_tally.load_jobs(session, [p.id for p in payments])
    return [to_payment_read(p, jobs.get(p.id), is_admin) for p in payments]


async def create_payment(data: PaymentCreate, current_user: User, session: AsyncSession) -> Payment:
    """
    Create a collection with brand allocations. `visit_id` is the single source of truth for which
    outlet/employee this payment belongs to - the client never supplies
    customer_id/employee_id, so a collection can never be attached to the
    wrong (similarly-named) outlet by mistake.

    P0-2: a double-tap or a retried request after a dropped response must not
    create two collection rows. When the caller supplies `idempotency_key`,
    a prior payment for the same (visit, key) is returned as-is instead of
    inserting again.
    """
    visit = await get_visit_for_user(data.visit_id, current_user, session)
    repo = PaymentRepository(session)

    # Idempotent replay first: a retry of an already-recorded collection must
    # keep succeeding even if the visit has since changed state.
    if data.idempotency_key:
        existing = await repo.find_by_visit_and_idempotency_key(visit.id, data.idempotency_key)
        if existing is not None:
            return existing

    # A collection cannot be recorded against a visit that never happened.
    # (There is no CANCELLED visit status in this system; MISSED is the
    # equivalent. COMPLETED stays allowed: the Android app records the
    # collection from the outlet account screen after check-out and offline
    # submissions are replayed after the visit is closed.)
    if visit.status == VisitStatus.MISSED:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot record a collection against a missed visit",
            error_code="VISIT_NOT_COLLECTABLE",
        )

    # Enforce financial lock: reject payments into a finalized period
    await assert_period_open_for_date(data.payment_date, session)

    if data.invoice_id is not None:
        invoice = await get_invoice(data.invoice_id, session)
        if invoice.customer_id != visit.customer_id:
            raise BaseAPIException(
                status_code=422,
                detail="That invoice does not belong to this visit's outlet",
                error_code="INVOICE_OUTLET_MISMATCH",
            )
        if invoice.source != InvoiceSource.TALLY:
            raise BaseAPIException(
                status_code=422,
                detail="That invoice is not a Tally invoice; record the collection without an invoice as an advance.",
                error_code="INVOICE_NOT_IN_TALLY",
            )
        # Lock the invoice and cap the amount at what is still outstanding.
        # A payment with NO invoice is an on-account/advance collection, which
        # the system already models (AccountSummary.advance_amount), so it is
        # intentionally not capped by customer outstanding.
        _, outstanding = await invoice_outstanding_under_lock(data.invoice_id, session)
        if data.amount - outstanding > _MONEY_TOLERANCE:
            raise BaseAPIException(
                status_code=422,
                detail=(
                    f"Amount {data.amount:,.2f} exceeds the invoice's outstanding balance "
                    f"({max(outstanding, Decimal('0')):,.2f}). Record the excess without an invoice as an advance."
                ),
                error_code="PAYMENT_EXCEEDS_INVOICE_OUTSTANDING",
            )

    payment = Payment(
        visit_id=visit.id,
        customer_id=visit.customer_id,
        employee_id=visit.employee_id,
        invoice_id=data.invoice_id,
        amount=data.amount,
        payment_method=data.payment_method,
        payment_date=data.payment_date,
        cheque_number=data.cheque_number,
        cheque_bank_name=data.cheque_bank_name,
        utr_reference=data.utr_reference,
        notes=data.notes,
        status=PaymentStatus.PENDING_VERIFICATION,
        source=PaymentSource.MANUAL,
        created_by=current_user.id,
        idempotency_key=data.idempotency_key,
    )

    if data.allocations:
        from app.services import brand_service
        for alloc in data.allocations:
            brand_obj = await brand_service.validate_brand_for_transaction(session, alloc.brand.strip())
            payment.allocations.append(
                PaymentBrandAllocation(
                    brand=brand_obj.name,
                    brand_id=brand_obj.id,
                    allocated_amount=alloc.amount,
                )
            )

    # Capture before a possible rollback: expired ORM attributes cannot lazy-load
    # on an async session (MissingGreenlet).
    visit_id = visit.id
    payment_id = payment.id

    try:
        await repo.add(payment)
        await session.flush()
        # NOTE: no Tally write-back is enqueued here. A collection is only
        # untrusted field data until an admin verifies it (verify_payment).
        await repo.commit()
    except IntegrityError:
        await session.rollback()
        if data.idempotency_key:
            existing = await repo.find_by_visit_and_idempotency_key(visit_id, data.idempotency_key)
            if existing is not None:
                return existing
        raise

    req_id = get_current_request_id()
    method_str = payment.payment_method.value if hasattr(payment.payment_method, "value") else str(payment.payment_method)
    alloc_summary = ",".join([f"{a.brand}:{a.amount}" for a in (data.allocations or [])])
    logger.info(
        "event=payment_submit result=success request_id=%s payment_id=%s customer_id=%s employee_id=%s amount=%s payment_method=%s allocations=%s",
        req_id,
        payment.id,
        payment.customer_id,
        payment.employee_id,
        payment.amount,
        method_str,
        alloc_summary or "none",
    )

    return await repo.get_by_id(payment.id)


async def update_payment_allocations(
    payment_id: uuid.UUID,
    data: PaymentAllocationUpdate,
    current_user: User,
    session: AsyncSession,
) -> Payment:
    """
    Admin pre-verification allocation adjustment.
    Allows Admins to correct the brand breakdown (e.g. from bank statement) before final verification.
    """
    req_id = get_current_request_id()
    if not current_user.is_admin:
        logger.warning("event=payment_reallocate result=rejected reason=ADMIN_REQUIRED request_id=%s user_id=%s", req_id, current_user.id)
        raise BaseAPIException(
            status_code=403,
            detail="Only administrators can adjust payment brand allocations",
            error_code="ADMIN_REQUIRED",
        )

    repo = PaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        logger.warning("event=payment_reallocate result=rejected reason=PAYMENT_NOT_FOUND request_id=%s payment_id=%s", req_id, payment_id)
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")

    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        logger.warning(
            "event=payment_reallocate result=rejected reason=PAYMENT_NOT_PENDING request_id=%s payment_id=%s status=%s",
            req_id,
            payment.id,
            payment.status.value,
        )
        raise BaseAPIException(
            status_code=409,
            detail=f"Cannot adjust allocations for a payment that is already {payment.status.value}",
            error_code="PAYMENT_NOT_PENDING",
        )

    total_allocated = sum((a.amount for a in data.allocations), Decimal("0"))
    if abs(total_allocated - payment.amount) > Decimal("0.001"):
        logger.warning(
            "event=payment_reallocate result=rejected reason=ALLOCATION_TOTAL_MISMATCH request_id=%s payment_id=%s total_allocated=%s payment_amount=%s",
            req_id,
            payment.id,
            total_allocated,
            payment.amount,
        )
        raise BaseAPIException(
            status_code=422,
            detail=f"Sum of brand allocations (₹{total_allocated:,.2f}) must equal payment total (₹{payment.amount:,.2f})",
            error_code="ALLOCATION_TOTAL_MISMATCH",
        )

    # Log previous allocations for auditability
    old_breakdown = ", ".join([f"{a.brand}: ₹{a.allocated_amount}" for a in (payment.allocations or [])])
    new_breakdown = ", ".join([f"{a.brand}: ₹{a.amount}" for a in data.allocations])
    audit_note = f"[Allocation adjusted by Admin {current_user.id} at {datetime.now(timezone.utc).isoformat()}: (Old: {old_breakdown}) -> (New: {new_breakdown})]"
    payment.notes = f"{payment.notes}\n{audit_note}" if payment.notes else audit_note

    # Clear existing allocations and flush deletes before inserting new ones
    payment.allocations.clear()
    await session.flush()

    from app.services import brand_service
    for alloc in data.allocations:
        brand_obj = await brand_service.validate_brand_for_transaction(session, alloc.brand.strip())
        payment.allocations.append(
            PaymentBrandAllocation(
                payment_id=payment.id,
                brand=brand_obj.name,
                brand_id=brand_obj.id,
                allocated_amount=alloc.amount,
            )
        )

    session.add(payment)
    await session.commit()
    logger.info(
        "event=payment_reallocate result=success request_id=%s payment_id=%s updated_by=%s allocations=%s",
        req_id,
        payment.id,
        current_user.id,
        new_breakdown,
    )
    return await repo.get_by_id(payment.id)


async def _assert_payment_visible(payment: Payment, current_user: User, session: AsyncSession) -> Payment:
    """
    ADMIN sees any payment. EMPLOYEE may only see their own collections - not
    other reps' (an employee cannot browse a colleague's collections/proofs).
    """
    if current_user.is_admin:
        return payment
    from app.services.employee_service import get_employee_by_user_id

    employee = await get_employee_by_user_id(current_user.id, session)
    if payment.employee_id != employee.id:
        # 404, not 403: do not reveal that another employee's payment exists.
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    return payment


async def get_payment_for_user(payment_id: uuid.UUID, current_user: User, session: AsyncSession) -> Payment:
    repo = PaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    return await _assert_payment_visible(payment, current_user, session)


async def list_payments_for_customer(
    customer_id: uuid.UUID, current_user: User, session: AsyncSession
) -> Sequence[Payment]:
    from app.services.account_service import assert_employee_can_view_account

    await assert_employee_can_view_account(customer_id, current_user, session)
    repo = PaymentRepository(session)
    return await repo.list_by_customer(customer_id)


async def list_review_queue(
    session: AsyncSession,
    status: PaymentStatus | None = None,
    skip: int = 0,
    limit: int = 50,
    tally_status=None,
    stuck: bool | None = None,
) -> Sequence[Payment]:
    """Admin/accountant review queue. Route gates this AdminOnly."""
    repo = PaymentRepository(session)
    return await repo.list_queue(status=status, skip=skip, limit=limit, tally_status=tally_status, stuck=stuck)


async def to_payment_read_for_queue(payment: Payment, session: AsyncSession, is_admin: bool = False) -> PaymentRead:
    """
    Same as to_payment_read, but also fills the display-only outlet/employee/
    territory fields the accountant queue table needs (Outlet, Employee
    columns) - a plain to_payment_read() intentionally leaves these null to
    avoid extra joins on paths that don't render them.
    """
    from app.models.customer import Customer
    from app.models.territory import Territory

    from app.services import payment_tally

    job = (await payment_tally.load_jobs(session, [payment.id])).get(payment.id)
    read = to_payment_read(payment, job, is_admin)

    customer_row = await session.execute(
        select(Customer.name, Customer.outlet_code).where(Customer.id == payment.customer_id)
    )
    customer_name, outlet_code = customer_row.one_or_none() or (None, None)

    employee_row = await session.execute(
        select(Employee.full_name, Territory.name)
        .outerjoin(Territory, Territory.id == Employee.territory_id)
        .where(Employee.id == payment.employee_id)
    )
    employee_name, territory_name = employee_row.one_or_none() or (None, None)

    read.customer_name = customer_name
    read.outlet_code = outlet_code
    read.employee_name = employee_name
    read.territory_name = territory_name
    return read


async def verify_payment(
    payment_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
    bank: PaymentVerifyRequest | None = None,
) -> Payment:
    """
    Admin verification (optionally recording the bank reference / date / note).
    Verifying only marks the cash as received: outstanding balances do NOT drop
    until the receipt is in Tally (see payment_tally.py). The payment row is locked (FOR UPDATE) so concurrent
    verify/reject calls serialise and the loser gets 409. When Tally write-back
    is enabled the job is enqueued here - and only here - inside the same
    transaction, keyed by the unique idempotency key `fieldtrack_payment:{id}`,
    so a retry or a double click cannot create a second job. When it is
    disabled no job is created: the accountant keys the receipt into Tally and
    an admin links the imported receipt (payment_reconciliation_service).
    """
    from app.services import tally_audit_service
    from app.services.tally_writeback_service import enqueue_payment_writeback

    req_id = get_current_request_id()
    repo = PaymentRepository(session)
    payment = await _lock_payment(payment_id, session)
    if payment is None:
        logger.warning("event=payment_verify result=rejected reason=PAYMENT_NOT_FOUND request_id=%s payment_id=%s", req_id, payment_id)
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        logger.warning(
            "event=payment_verify result=rejected reason=PAYMENT_ALREADY_REVIEWED request_id=%s payment_id=%s status=%s",
            req_id,
            payment.id,
            payment.status.value,
        )
        current_status = payment.status.value
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail=f"Payment is already {current_status}, cannot verify again",
            error_code="PAYMENT_ALREADY_REVIEWED",
        )

    if payment.invoice_id is not None:
        invoice, outstanding = await invoice_outstanding_under_lock(
            payment.invoice_id, session, exclude_payment_id=payment.id, include_pending=False
        )
        if payment.amount - outstanding > _MONEY_TOLERANCE:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail=(
                    "Verifying this payment would exceed the invoice's outstanding balance "
                    f"({max(outstanding, Decimal('0')):,.2f}). Reject it or re-record the excess as an advance."
                ),
                error_code="PAYMENT_EXCEEDS_INVOICE_OUTSTANDING",
            )

    before_status = payment.status.value
    payment.status = PaymentStatus.VERIFIED
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.now(tz=timezone.utc)
    if bank is not None:
        payment.bank_reference = bank.bank_reference
        payment.bank_verified_on = bank.bank_verified_on
        payment.verified_note = bank.verified_note
    session.add(payment)

    from app.models.customer import Customer

    job = None
    if settings.tally_writeback_enabled:
        cust_obj = (await session.execute(select(Customer).where(Customer.id == payment.customer_id))).scalar_one_or_none()
        inv_obj = await get_invoice(payment.invoice_id, session) if payment.invoice_id else None
        job = await enqueue_payment_writeback(session, payment, customer=cust_obj, invoice=inv_obj)
    await session.flush()

    await tally_audit_service.record_review_audit(
        session,
        operation="PAYMENT_VERIFY",
        actor_user_id=current_user.id,
        payment_id=payment.id,
        before_status=before_status,
        after_status=payment.status.value,
        writeback_job_id=job.id if job is not None else None,
        details={
            "writeback_enqueued": job is not None,
            "bank_reference": payment.bank_reference,
            "bank_verified_on": payment.bank_verified_on.isoformat() if payment.bank_verified_on else None,
        },
    )

    await session.commit()
    logger.info(
        "event=payment_verify result=approved request_id=%s payment_id=%s customer_id=%s amount=%s verified_by=%s",
        req_id,
        payment.id,
        payment.customer_id,
        payment.amount,
        current_user.id,
    )
    return await repo.get_by_id(payment.id)


async def reject_payment(
    payment_id: uuid.UUID, rejection_reason: str | None, current_user: User, session: AsyncSession
) -> Payment:
    """
    Admin rejection (FOR UPDATE on the payment; second concurrent action -> 409).

    Policy for money already posted to Tally: a VERIFIED payment can never be
    rejected through this endpoint (409). A payment whose write-back job is
    already SENT/CONFIRMED in Tally is also refused with PAYMENT_POSTED_TO_TALLY:
    rejecting it here would silently leave a receipt voucher in the books, so
    the receipt must be reversed/cancelled in Tally by the accountant first.
    Otherwise every PENDING/PROCESSING/retryable job is cancelled (FAILED with
    a CANCELLED marker) and can no longer be retried.
    """
    from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
    from app.services import tally_audit_service

    req_id = get_current_request_id()
    if not rejection_reason or not rejection_reason.strip():
        logger.warning("event=payment_reject result=rejected reason=REJECTION_REASON_REQUIRED request_id=%s payment_id=%s", req_id, payment_id)
        raise BaseAPIException(
            status_code=422,
            detail="A rejection reason is required",
            error_code="REJECTION_REASON_REQUIRED",
        )
    repo = PaymentRepository(session)
    payment = await _lock_payment(payment_id, session)
    if payment is None:
        logger.warning("event=payment_reject result=rejected reason=PAYMENT_NOT_FOUND request_id=%s payment_id=%s", req_id, payment_id)
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        logger.warning(
            "event=payment_reject result=rejected reason=PAYMENT_ALREADY_REVIEWED request_id=%s payment_id=%s status=%s",
            req_id,
            payment.id,
            payment.status.value,
        )
        current_status = payment.status
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail=f"Payment is already {current_status.value}, cannot reject again"
            + (
                ". If it was posted to Tally, reverse the receipt voucher in Tally instead."
                if current_status == PaymentStatus.VERIFIED
                else ""
            ),
            error_code="PAYMENT_ALREADY_REVIEWED",
        )

    jobs = (
        await session.execute(
            select(TallyWritebackQueue)
            .where(TallyWritebackQueue.entity_type == "PAYMENT", TallyWritebackQueue.entity_id == payment.id)
            .with_for_update()
        )
    ).scalars().all()
    posted = [j for j in jobs if j.status in (WritebackStatus.SENT, WritebackStatus.CONFIRMED)]
    if posted:
        await session.rollback()
        logger.warning(
            "event=payment_reject result=rejected reason=PAYMENT_POSTED_TO_TALLY request_id=%s payment_id=%s",
            req_id,
            payment_id,
        )
        raise BaseAPIException(
            status_code=409,
            detail=(
                "This payment has already been posted to Tally. Reverse or cancel the receipt "
                "voucher in Tally first; it cannot be rejected here."
            ),
            error_code="PAYMENT_POSTED_TO_TALLY",
        )

    if any(j.status == WritebackStatus.PROCESSING for j in jobs):
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail="A Tally write-back for this payment is being processed by the sync agent right now. Try again once it completes.",
            error_code="PAYMENT_WRITEBACK_IN_FLIGHT",
        )

    before_status = payment.status.value
    payment.status = PaymentStatus.REJECTED
    payment.rejection_reason = rejection_reason.strip()
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.now(tz=timezone.utc)
    session.add(payment)

    cancelled_ids: list[str] = []
    for job in jobs:
        if job.status in (WritebackStatus.PENDING, WritebackStatus.FAILED):
            job.status = WritebackStatus.FAILED
            job.next_retry_at = None
            job.last_error = f"CANCELLED: payment rejected by Admin: {rejection_reason.strip()}"
            cancelled_ids.append(str(job.id))

    await tally_audit_service.record_review_audit(
        session,
        operation="PAYMENT_REJECT",
        actor_user_id=current_user.id,
        payment_id=payment.id,
        before_status=before_status,
        after_status=payment.status.value,
        details={"cancelled_job_ids": cancelled_ids, "reason": rejection_reason.strip()[:300]},
    )

    await session.commit()
    logger.info(
        "event=payment_verify result=rejected request_id=%s payment_id=%s customer_id=%s amount=%s rejected_by=%s",
        req_id,
        payment.id,
        payment.customer_id,
        payment.amount,
        current_user.id,
    )
    return await repo.get_by_id(payment.id)


async def upload_payment_proof(
    payment_id: uuid.UUID,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
    current_user: User,
    session: AsyncSession,
) -> PaymentProof:
    """Attach a payment proof photo/screenshot to a collection."""
    detected_mime, _, sanitized_name, checksum = FileValidationService.validate_image(file_bytes, original_filename)

    payment = await get_payment_for_user(payment_id, current_user, session)
    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        raise BaseAPIException(
            status_code=409,
            detail=f"Cannot attach proof: payment is already {payment.status.value}",
            error_code="PAYMENT_CLOSED",
        )

    proof_repo = PaymentProofRepository(session)
    existing = await proof_repo.find_by_checksum_for_payment(payment.id, checksum)
    if existing is not None:
        return existing

    proof_id = uuid.uuid4()
    storage_key = f"payments/{payment.id}/{proof_id}_{sanitized_name}"
    await storage_service.upload(
        file_bytes=file_bytes,
        storage_key=storage_key,
        content_type=detected_mime,
    )

    proof = PaymentProof(
        id=proof_id,
        payment_id=payment.id,
        storage_key=storage_key,
        file_size_bytes=len(file_bytes),
        checksum_sha256=checksum,
        original_filename=sanitized_name,
        uploaded_by=current_user.id,
    )
    await proof_repo.add(proof)
    await proof_repo.commit()
    return proof


async def get_proof_download_url(
    proof_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
    expiry_minutes: int = 15,
) -> str:
    """Pre-signed URL for viewing/downloading a payment proof."""
    proof_repo = PaymentProofRepository(session)
    proof = await proof_repo.get_by_id(proof_id)
    if proof is None:
        raise BaseAPIException(status_code=404, detail="Proof not found", error_code="PROOF_NOT_FOUND")

    await get_payment_for_user(proof.payment_id, current_user, session)
    return await storage_service.generate_presigned_url(proof.storage_key, expiry_minutes=expiry_minutes)


async def tally_retry_payment(payment_id: uuid.UUID, current_user: User, session: AsyncSession) -> Payment:
    """
    Admin: re-queue the FAILED Tally write-back of this payment (payment-centred
    wrapper over tally_writeback_service.retry_writeback_job - same row lock,
    audit record and duplicate refusal). Only allowed when tally_status is
    FAILED; the job is reset on the existing row, never duplicated.
    """
    from app.services import payment_tally
    from app.services.tally_writeback_service import retry_writeback_job

    actor_id = current_user.id  # captured before any rollback expires the user
    if not settings.tally_writeback_enabled:
        raise BaseAPIException(
            status_code=409,
            detail="Tally write-back is disabled; link the collection to its imported Tally receipt instead.",
            error_code="TALLY_WRITEBACK_DISABLED",
        )
    payment = await _lock_payment(payment_id, session)
    if payment is None:
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    job = (await payment_tally.load_jobs(session, [payment.id])).get(payment.id)
    status = payment_tally.derive_tally_status(payment, job)
    if status != payment_tally.TallyStatus.FAILED or job is None:
        current = status.value
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail=f"Tally retry is only available for FAILED write-backs (this payment is {current}).",
            error_code="PAYMENT_TALLY_NOT_FAILED",
        )
    job_id = job.id
    await session.rollback()  # release the row lock; retry_writeback_job re-locks job + payment
    await retry_writeback_job(session, job_id, actor_user_id=actor_id)
    return await PaymentRepository(session).get_by_id(payment_id)
