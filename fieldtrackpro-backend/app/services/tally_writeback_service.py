from __future__ import annotations

from app.models.user import ADMIN_ROLES

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment, PaymentSource, PaymentStatus
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.schemas.tally_writeback import TallyWritebackAckRequest, TallyWritebackFailRequest

logger = logging.getLogger("fieldtrackpro")

BACKOFF_SECONDS = [30, 60, 120, 300, 600]

TALLY_FAILED_TITLE = "Tally post failed"
TALLY_STUCK_TITLE = "Tally post stuck"
STUCK_DEDUPE_HOURS = 24

# A PROCESSING job whose lease keeps expiring without ever being ACKed or
# FAILed (agent crashed mid-post, stuck ack loop, ...) is reclaimed at most
# this many times before we give up silently reclaiming it and force it to
# terminal FAILED instead, so an admin is alerted. The pre-post dedupe check
# in the sync agent means even a reclaim beyond this point would self-heal
# rather than duplicate - this cap is about surfacing a stuck job promptly,
# not primarily about preventing duplicates.
MAX_LEASE_RECLAIMS = 5


def _short_error(err: Optional[str], limit: int = 120) -> str:
    text = " ".join((err or "unknown error").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


async def _active_admin_ids(session: AsyncSession) -> list[uuid.UUID]:
    from app.models.user import Role, User

    return list(
        (await session.execute(select(User.id).where(User.role.in_(ADMIN_ROLES), User.is_active.is_(True))))
        .scalars()
        .all()
    )


async def _payment_context(session: AsyncSession, payment_id: uuid.UUID) -> tuple[Optional[Payment], str, str]:
    """(payment, outlet name, employee name) - names only, no other PII."""
    from app.models.employee import Employee

    payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if payment is None:
        return None, "unknown outlet", "unknown employee"
    outlet = (
        await session.execute(select(Customer.name).where(Customer.id == payment.customer_id))
    ).scalar_one_or_none()
    emp = None
    if payment.employee_id is not None:
        emp = (
            await session.execute(select(Employee.full_name).where(Employee.id == payment.employee_id))
        ).scalar_one_or_none()
    return payment, outlet or "unknown outlet", emp or "unknown employee"


async def _notify_admins(
    session: AsyncSession, title: str, message: str, payment_id: Optional[uuid.UUID] = None
) -> int:
    """Reuses NotificationType.REMINDER (no new enum value / migration)."""
    from app.models.notification import NotificationType
    from app.services.notification_service import notification_service

    sent = 0
    for admin_id in await _active_admin_ids(session):
        await notification_service.create_notification(
            user_id=admin_id,
            notification_type=NotificationType.REMINDER,
            title=title,
            message=message,
            session=session,
            payment_id=payment_id,
        )
        sent += 1
    return sent


async def _notify_admins_writeback_failed(session: AsyncSession, job: TallyWritebackQueue) -> None:
    """Admin alert for a terminally FAILED payment write-back. Never raises."""
    job_id = job.id
    try:
        if job.entity_type != "PAYMENT":
            return
        payment, outlet, emp = await _payment_context(session, job.entity_id)
        amount = f"{payment.amount:,.2f}" if payment is not None else "?"
        msg = (
            f"Tally post failed for payment of ₹{amount} at {outlet} (by {emp}). "
            f"Error: {_short_error(job.last_error)}"
        )
        await _notify_admins(session, TALLY_FAILED_TITLE, msg, payment_id=job.entity_id)
    except Exception as exc:
        try:
            await session.rollback()
        except Exception:
            pass
        logger.warning("event=tally_failed_notify_error job_id=%s error=%s", job_id, exc)


async def notify_stuck_tally_posts(session: AsyncSession, now: Optional[datetime] = None) -> int:
    """
    Alert admins about VERIFIED MANUAL payments still not CONFIRMED in Tally
    30+ minutes after verification (jobs already FAILED were alerted at failure
    time and are skipped). Once per payment per 24h, deduped via existing
    notifications (same title + Notification.payment_id). Never raises.
    Returns the number of payments alerted.
    """
    from app.models.notification import Notification
    from app.services import payment_tally

    try:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=payment_tally.TALLY_STUCK_MINUTES)
        stmt = select(Payment.id).where(
            payment_tally.tally_status_clause(payment_tally.TallyStatus.AWAITING_TALLY),
            Payment.reviewed_at.is_not(None),
            Payment.reviewed_at <= cutoff,
        )
        payment_ids = list((await session.execute(stmt)).scalars().all())
        alerted = 0
        window_start = now - timedelta(hours=STUCK_DEDUPE_HOURS)
        for pid in payment_ids:
            already = (
                await session.execute(
                    select(Notification.id)
                    .where(
                        Notification.title == TALLY_STUCK_TITLE,
                        Notification.payment_id == pid,
                        Notification.sent_at >= window_start,
                    )
                    .limit(1)
                )
            ).first()
            if already:
                continue
            payment, outlet, emp = await _payment_context(session, pid)
            if payment is None:
                continue
            msg = (
                f"Verified payment of ₹{payment.amount:,.2f} at {outlet} (by {emp}) "
                f"has not been posted to Tally for over {payment_tally.TALLY_STUCK_MINUTES} minutes."
            )
            if await _notify_admins(session, TALLY_STUCK_TITLE, msg, payment_id=pid):
                alerted += 1
        return alerted
    except Exception as exc:
        try:
            await session.rollback()
        except Exception:
            pass
        logger.warning("event=tally_stuck_notify_error error=%s", exc)
        return 0


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
        "bank_reference": payment.bank_reference,
        "bank_verified_on": payment.bank_verified_on.isoformat() if payment.bank_verified_on else None,
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


async def _expire_stuck_processing_jobs(
    session: AsyncSession, now: datetime, max_reclaims: int = MAX_LEASE_RECLAIMS
) -> None:
    """
    Forces a PROCESSING job to terminal FAILED once its lease has expired
    `max_reclaims` times without ever being ACKed or FAILed, instead of
    reclaiming it forever. Admin is alerted and must verify Tally before
    using "retry" (same as any other FAILED job). Never raises.
    """
    try:
        stmt = (
            select(TallyWritebackQueue)
            .where(
                TallyWritebackQueue.status == WritebackStatus.PROCESSING,
                TallyWritebackQueue.next_retry_at.is_not(None),
                TallyWritebackQueue.next_retry_at <= now,
                TallyWritebackQueue.retry_count >= max_reclaims,
            )
            .with_for_update(skip_locked=True)
        )
        stuck_jobs = list((await session.execute(stmt)).scalars().all())
        if not stuck_jobs:
            return

        for job in stuck_jobs:
            job.status = WritebackStatus.FAILED
            job.next_retry_at = None
            job.last_error = (
                f"Lease expired {job.retry_count} times without confirmation from the "
                "sync agent; the post may or may not have reached Tally - verify manually "
                "in Tally before retrying."
            )
            logger.error(
                "Writeback job=%s stuck PROCESSING after %d reclaims; forced FAILED for manual review",
                job.id,
                job.retry_count,
            )
        await session.commit()

        for job in stuck_jobs:
            await _notify_admins_writeback_failed(session, job)
    except Exception as exc:
        try:
            await session.rollback()
        except Exception:
            pass
        logger.warning("event=tally_expire_stuck_jobs_error error=%s", exc)


async def claim_pending_jobs(
    session: AsyncSession, limit: int = 10, lease_minutes: int = 5
) -> List[TallyWritebackQueue]:
    """
    Safely claims pending or expired-processing writeback jobs.
    Uses FOR UPDATE SKIP LOCKED to prevent concurrent duplicate claims.
    """
    now = datetime.now(timezone.utc)

    await _expire_stuck_processing_jobs(session, now)

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
            # Never hand an unverified/rejected payment's job to the agent
            # (belt and braces: jobs are only created on verification now).
            or_(
                TallyWritebackQueue.entity_type != "PAYMENT",
                exists().where(
                    and_(
                        Payment.id == TallyWritebackQueue.entity_id,
                        Payment.status == PaymentStatus.VERIFIED,
                    )
                ),
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
    session: AsyncSession, job_id: uuid.UUID, data: TallyWritebackAckRequest, agent=None
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

    from app.services import tally_audit_service

    await tally_audit_service.record_review_audit(
        session,
        operation="WRITEBACK_POSTED",
        actor_user_id=None,
        agent=agent,
        payment_id=job.entity_id if job.entity_type == "PAYMENT" else None,
        before_status="PROCESSING",
        after_status="CONFIRMED",
        writeback_job_id=job.id,
        details={"tally_voucher_number": data.tally_voucher_number},
    )
    await session.commit()
    logger.info("Writeback job=%s marked CONFIRMED", job.id)
    return job


async def fail_writeback_job(
    session: AsyncSession, job_id: uuid.UUID, data: TallyWritebackFailRequest, max_retries: int = 5, agent=None
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
    before_status = job.status.value if hasattr(job.status, "value") else str(job.status)
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

    from app.services import tally_audit_service

    await tally_audit_service.record_review_audit(
        session,
        operation="WRITEBACK_FAILED",
        actor_user_id=None,
        agent=agent,
        payment_id=job.entity_id if job.entity_type == "PAYMENT" else None,
        before_status=before_status,
        after_status=job.status.value if hasattr(job.status, "value") else str(job.status),
        writeback_job_id=job.id,
        status="FAILED",
        error_message=(data.error_message or "")[:500],
    )
    await session.commit()
    # Notify once per transition into FAILED (not per retryable attempt, and
    # not again if a late failure report hits an already-FAILED job).
    if job.status == WritebackStatus.FAILED and before_status != WritebackStatus.FAILED.value:
        await _notify_admins_writeback_failed(session, job)
        try:
            await session.refresh(job)  # a rolled-back notification must not leave `job` expired
        except Exception:
            pass
    return job


async def retry_writeback_job(
    session: AsyncSession, job_id: uuid.UUID, actor_user_id: Optional[uuid.UUID] = None
) -> TallyWritebackQueue:
    """
    Manually resets a FAILED (or stuck PENDING/PROCESSING) write-back job to
    PENDING so the Sync Agent picks it up again.

    Refused (409) when:
    * the job is CONFIRMED/SENT - re-queueing would post a duplicate receipt;
    * the job is PROCESSING with an active lease - the sync agent may genuinely
      still be mid-post; retrying now would hand the same job to the agent a
      second time while the first attempt is still in flight;
    * the job's payment is not VERIFIED (rejected / never verified) - a
      rejected payment's jobs are permanently dead.
    """
    from app.services import tally_audit_service

    stmt = select(TallyWritebackQueue).where(TallyWritebackQueue.id == job_id).with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise BaseAPIException(status_code=404, detail="Writeback job not found", error_code="JOB_NOT_FOUND")

    if job.status in (WritebackStatus.CONFIRMED, WritebackStatus.SENT):
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail="Job is already posted to Tally; retrying would create a duplicate voucher.",
            error_code="JOB_ALREADY_POSTED",
        )
    if job.status == WritebackStatus.PROCESSING:
        now = datetime.now(timezone.utc)
        lease_active = job.next_retry_at is not None and job.next_retry_at > now
        if lease_active:
            # Read before rollback() - rollback() expires the ORM instance, and
            # touching an expired attribute afterwards needs a sync lazy-load that
            # the async session can't perform outside an awaited context.
            lease_until = job.next_retry_at.isoformat()
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail=(
                    "Job is currently being processed by the Tally sync agent "
                    f"(lease active until {lease_until}); "
                    "wait for it to finish or for the lease to expire before retrying."
                ),
                error_code="JOB_IN_FLIGHT",
            )
    if job.entity_type == "PAYMENT":
        payment = (
            await session.execute(select(Payment).where(Payment.id == job.entity_id).with_for_update())
        ).scalar_one_or_none()
        if payment is None or payment.status != PaymentStatus.VERIFIED:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail="The payment for this job is not VERIFIED (rejected or unverified); it cannot be retried.",
                error_code="JOB_PAYMENT_NOT_VERIFIED",
            )

    before_status = job.status.value if hasattr(job.status, "value") else str(job.status)
    job.status = WritebackStatus.PENDING
    job.retry_count = 0
    job.next_retry_at = None
    job.last_error = None
    await tally_audit_service.record_review_audit(
        session,
        operation="WRITEBACK_RETRY",
        actor_user_id=actor_user_id,
        payment_id=job.entity_id if job.entity_type == "PAYMENT" else None,
        before_status=before_status,
        after_status="PENDING",
        writeback_job_id=job.id,
    )
    await session.commit()
    logger.info("Writeback job=%s manually reset to PENDING for re-processing", job.id)
    return job
