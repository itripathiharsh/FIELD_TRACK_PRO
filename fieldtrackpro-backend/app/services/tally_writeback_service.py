from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment, PaymentSource
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.schemas.tally_writeback import TallyWritebackAckRequest, TallyWritebackFailRequest

logger = logging.getLogger("fieldtrackpro")

BACKOFF_SECONDS = [30, 60, 120, 300, 600]


async def enqueue_payment_writeback(
    session: AsyncSession,
    payment: Payment,
    customer: Optional[Customer] = None,
    invoice: Optional[Invoice] = None,
) -> Optional[TallyWritebackQueue]:
    """
    Enqueues a Tally receipt write-back job in the same DB transaction as the payment.
    Only enqueues MANUAL field collections (never re-enqueues TALLY or EXCEL_IMPORT records).
    Idempotent by fieldtrack_payment:{payment_id}.
    """
    if payment.source != PaymentSource.MANUAL:
        logger.debug(
            "Skipping Tally writeback for non-manual payment id=%s source=%s",
            payment.id,
            payment.source.value,
        )
        return None

    idempotency_key = f"fieldtrack_payment:{payment.id}"

    # Check if job already enqueued
    stmt = select(TallyWritebackQueue).where(
        TallyWritebackQueue.idempotency_key == idempotency_key
    )
    existing_job = (await session.execute(stmt)).scalar_one_or_none()
    if existing_job is not None:
        return existing_job

    # Resolve customer if not passed
    if customer is None:
        c_stmt = select(Customer).where(Customer.id == payment.customer_id)
        customer = (await session.execute(c_stmt)).scalar_one_or_none()

    customer_name = customer.name if customer else "Unknown Customer"
    outlet_code = customer.outlet_code if customer else None

    # Resolve invoice if not passed
    invoice_number = None
    if invoice is None and payment.invoice_id is not None:
        i_stmt = select(Invoice).where(Invoice.id == payment.invoice_id)
        invoice = (await session.execute(i_stmt)).scalar_one_or_none()

    if invoice is not None:
        invoice_number = invoice.invoice_number

    # Build allocations list
    allocations = []
    from app.models.payment import PaymentBrandAllocation
    alloc_stmt = select(PaymentBrandAllocation).where(
        PaymentBrandAllocation.payment_id == payment.id
    )
    alloc_rows = (await session.execute(alloc_stmt)).scalars().all()
    for a in alloc_rows:
        allocations.append({
            "brand": a.brand,
            "amount": float(a.allocated_amount),
        })

    # Resolve employee if not passed or available on payment
    employee_name = None
    if payment.employee_id is not None:
        from app.models.employee import Employee
        e_stmt = select(Employee).where(Employee.id == payment.employee_id)
        emp_obj = (await session.execute(e_stmt)).scalar_one_or_none()
        if emp_obj:
            employee_name = emp_obj.full_name

    # Prepare payload
    payload = {
        "payment_id": str(payment.id),
        "customer_id": str(payment.customer_id),
        "customer_name": customer_name,
        "employee_id": str(payment.employee_id) if payment.employee_id else None,
        "employee_name": employee_name,
        "outlet_code": outlet_code,
        "amount": float(payment.amount),
        "payment_method": (
            payment.payment_method.value
            if hasattr(payment.payment_method, "value")
            else str(payment.payment_method)
        ),
        "payment_date": payment.payment_date.isoformat(),
        "cheque_number": payment.cheque_number,
        "cheque_bank_name": payment.cheque_bank_name,
        "utr_reference": payment.utr_reference,
        "notes": payment.notes or "",
        "invoice_id": str(payment.invoice_id) if payment.invoice_id else None,
        "invoice_number": invoice_number,
        "allocations": allocations,
    }

    job = TallyWritebackQueue(
        idempotency_key=idempotency_key,
        entity_type="PAYMENT",
        entity_id=payment.id,
        operation="CREATE_RECEIPT",
        payload=payload,
        status=WritebackStatus.PENDING,
        retry_count=0,
    )
    session.add(job)
    logger.info(
        "Enqueued Tally writeback job for payment_id=%s idempotency_key=%s amount=%s",
        payment.id,
        idempotency_key,
        payment.amount,
    )
    return job


async def claim_pending_jobs(
    session: AsyncSession, limit: int = 10, lease_minutes: int = 5
) -> List[TallyWritebackQueue]:
    """
    Safely claims pending or expired-processing writeback jobs.
    Uses FOR UPDATE SKIP LOCKED to prevent concurrent duplicate claims.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(TallyWritebackQueue)
        .where(
            or_(
                TallyWritebackQueue.status == WritebackStatus.PENDING,
                TallyWritebackQueue.status == WritebackStatus.PROCESSING,
            ),
            or_(
                TallyWritebackQueue.next_retry_at.is_(None),
                TallyWritebackQueue.next_retry_at <= now,
            ),
        )
        .order_by(TallyWritebackQueue.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    claimed_jobs = (await session.execute(stmt)).scalars().all()
    if not claimed_jobs:
        return []

    lease_expiry = now + timedelta(minutes=lease_minutes)
    for job in claimed_jobs:
        job.status = WritebackStatus.PROCESSING
        job.retry_count += 1
        job.sent_at = now
        job.next_retry_at = lease_expiry

    await session.commit()
    logger.info("Claimed %d pending Tally writeback jobs", len(claimed_jobs))
    return list(claimed_jobs)


async def ack_writeback_job(
    session: AsyncSession, job_id: uuid.UUID, data: TallyWritebackAckRequest
) -> TallyWritebackQueue:
    """
    Acknowledges successful Tally write-back, marks job CONFIRMED,
    and links Tally GUID onto the original FieldTrack payment.
    """
    stmt = select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise BaseAPIException(status_code=404, detail="Writeback job not found", error_code="JOB_NOT_FOUND")

    if job.status == WritebackStatus.CONFIRMED:
        # Idempotent repeat ACK
        return job

    now = datetime.now(timezone.utc)
    job.status = WritebackStatus.CONFIRMED
    job.confirmed_at = now
    job.tally_guid = data.tally_guid
    job.tally_master_id = data.tally_master_id
    job.tally_voucher_number = data.tally_voucher_number
    job.last_error = None
    job.next_retry_at = None

    # Link Tally identifiers to Payment or Order to guarantee loop prevention and status update
    if job.entity_type == "PAYMENT" and data.tally_guid:
        p_stmt = select(Payment).where(Payment.id == job.entity_id).with_for_update()
        payment = (await session.execute(p_stmt)).scalar_one_or_none()
        if payment:
            payment.source_reference = data.tally_guid
            logger.info(
                "Linked Tally GUID=%s to payment_id=%s from writeback job=%s",
                data.tally_guid,
                payment.id,
                job.id,
            )
    elif job.entity_type == "SALES_ORDER":
        o_stmt = select(Order).where(Order.id == job.entity_id).with_for_update()
        order = (await session.execute(o_stmt)).scalar_one_or_none()
        if order:
            order.tally_guid = data.tally_guid
            order.tally_master_id = data.tally_master_id
            order.tally_voucher_number = data.tally_voucher_number
            order.status = "TALLY_CONFIRMED"
            logger.info(
                "Linked Tally GUID=%s, VchNum=%s to order_id=%s from writeback job=%s",
                data.tally_guid,
                data.tally_voucher_number,
                order.id,
                job.id,
            )

    await session.commit()
    logger.info("Writeback job=%s marked CONFIRMED with tally_guid=%s", job.id, data.tally_guid)
    return job


async def fail_writeback_job(
    session: AsyncSession, job_id: uuid.UUID, data: TallyWritebackFailRequest, max_retries: int = 5
) -> TallyWritebackQueue:
    """
    Marks job failure. If retryable and within max_retries, sets next_retry_at with backoff.
    Otherwise marks terminal FAILED.
    """
    stmt = select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise BaseAPIException(status_code=404, detail="Writeback job not found", error_code="JOB_NOT_FOUND")

    if job.status == WritebackStatus.CONFIRMED:
        # Job was already confirmed; ignore late failure
        return job

    now = datetime.now(timezone.utc)
    job.last_error = data.error_message

    if data.is_retryable and job.retry_count < max_retries:
        backoff_idx = min(job.retry_count - 1, len(BACKOFF_SECONDS) - 1)
        delay_sec = BACKOFF_SECONDS[max(0, backoff_idx)]
        job.status = WritebackStatus.PENDING
        job.next_retry_at = now + timedelta(seconds=delay_sec)
        logger.warning(
            "Writeback job=%s failed (retryable %d/%d), retry in %ds: %s",
            job.id,
            job.retry_count,
            max_retries,
            delay_sec,
            data.error_message,
        )
    else:
        job.status = WritebackStatus.FAILED
        job.next_retry_at = None
        logger.error(
            "Writeback job=%s permanently FAILED (retryable=%s, retries=%d): %s",
            job.id,
            data.is_retryable,
            job.retry_count,
            data.error_message,
        )
        if job.entity_type == "SALES_ORDER":
            o_stmt = select(Order).where(Order.id == job.entity_id).with_for_update()
            order = (await session.execute(o_stmt)).scalar_one_or_none()
            if order:
                order.status = "TALLY_FAILED"

    await session.commit()
    return job


async def retry_writeback_job(
    session: AsyncSession, job_id: uuid.UUID
) -> TallyWritebackQueue:
    """
    Manually resets a failed or stuck write-back job to PENDING with retry_count=0
    and next_retry_at=None, allowing the Sync Agent to pick it up immediately.
    """
    stmt = select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise BaseAPIException(status_code=404, detail="Writeback job not found", error_code="JOB_NOT_FOUND")

    job.status = WritebackStatus.PENDING
    job.retry_count = 0
    job.next_retry_at = None
    job.last_error = None
    await session.commit()
    logger.info("Writeback job=%s manually reset to PENDING for re-processing", job.id)
    return job

