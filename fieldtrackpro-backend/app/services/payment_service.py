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
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
from app.models.payment import Payment, PaymentStatus
from app.models.payment_proof import PaymentProof
from app.models.user import Role, User
from app.repositories.payment_repo import PaymentProofRepository, PaymentRepository
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services.file_validation_service import FileValidationService
from app.services.invoice_service import get_invoice
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit_for_user

logger = logging.getLogger("fieldtrackpro")


def to_payment_read(payment: Payment) -> PaymentRead:
    return PaymentRead(
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
            for p in payment.proofs
        ],
    )


async def create_payment(data: PaymentCreate, current_user: User, session: AsyncSession) -> Payment:
    """
    Create a collection. `visit_id` is the single source of truth for which
    outlet/employee this payment belongs to - the client never supplies
    customer_id/employee_id, so a collection can never be attached to the
    wrong (similarly-named) outlet by mistake.

    P0-2: a double-tap or a retried request after a dropped response must not
    create two collection rows. When the caller supplies `idempotency_key`,
    a prior payment for the same (visit, key) is returned as-is instead of
    inserting again. The pre-check alone is only correct for sequential
    retries; the DB's own `uq_payments_visit_idempotency` constraint is what
    actually makes this safe under concurrent duplicate requests - a race
    that slips past the pre-check hits that constraint, and the resulting
    IntegrityError is caught below and resolved to the winning row rather
    than surfacing as a raw 500.
    """
    visit = await get_visit_for_user(data.visit_id, current_user, session)

    if data.invoice_id is not None:
        invoice = await get_invoice(data.invoice_id, session)
        if invoice.customer_id != visit.customer_id:
            raise BaseAPIException(
                status_code=422,
                detail="That invoice does not belong to this visit's outlet",
                error_code="INVOICE_OUTLET_MISMATCH",
            )

    repo = PaymentRepository(session)

    if data.idempotency_key:
        existing = await repo.find_by_visit_and_idempotency_key(visit.id, data.idempotency_key)
        if existing is not None:
            return existing

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
        created_by=current_user.id,
        idempotency_key=data.idempotency_key,
    )
    await repo.add(payment)
    try:
        await repo.commit()
    except IntegrityError:
        await session.rollback()
        if data.idempotency_key:
            existing = await repo.find_by_visit_and_idempotency_key(visit.id, data.idempotency_key)
            if existing is not None:
                return existing
        raise
    # Re-fetch through the eager-loaded query rather than returning the
    # just-added ORM object directly: `proofs` would otherwise be an unloaded
    # relationship, and accessing it later (to build the response) risks a
    # MissingGreenlet lazy-load under the async driver.
    return await repo.get_by_id(payment.id)


async def _assert_payment_visible(payment: Payment, current_user: User, session: AsyncSession) -> Payment:
    """
    ADMIN sees any payment. EMPLOYEE may only see their own collections - not
    other reps' (an employee cannot browse a colleague's collections/proofs).
    """
    if current_user.role == Role.ADMIN:
        return payment
    from app.services.employee_service import get_employee_by_user_id

    employee = await get_employee_by_user_id(current_user.id, session)
    if payment.employee_id != employee.id:
        raise BaseAPIException(
            status_code=403,
            detail="You are not the collector of this payment",
            error_code="PAYMENT_NOT_OWNED",
        )
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
    session: AsyncSession, status: PaymentStatus | None = None, skip: int = 0, limit: int = 50
) -> Sequence[Payment]:
    """Admin/accountant review queue. Route gates this AdminOnly."""
    repo = PaymentRepository(session)
    return await repo.list_queue(status=status, skip=skip, limit=limit)


async def to_payment_read_for_queue(payment: Payment, session: AsyncSession) -> PaymentRead:
    """
    Same as to_payment_read, but also fills the display-only outlet/employee/
    territory fields the accountant queue table needs (Outlet, Employee
    columns) - a plain to_payment_read() intentionally leaves these null to
    avoid extra joins on paths that don't render them.
    """
    from app.models.customer import Customer
    from app.models.territory import Territory

    read = to_payment_read(payment)

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


async def verify_payment(payment_id: uuid.UUID, current_user: User, session: AsyncSession) -> Payment:
    repo = PaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        raise BaseAPIException(
            status_code=409,
            detail=f"Payment is already {payment.status.value}, cannot verify again",
            error_code="PAYMENT_ALREADY_REVIEWED",
        )
    payment.status = PaymentStatus.VERIFIED
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.now(tz=timezone.utc)
    session.add(payment)
    await session.commit()
    # Re-fetch with `proofs` eager-loaded rather than session.refresh(), which
    # would leave the relationship expired and risk a lazy-load MissingGreenlet
    # when the route handler serializes it into PaymentRead.
    return await repo.get_by_id(payment.id)


async def reject_payment(
    payment_id: uuid.UUID, rejection_reason: str | None, current_user: User, session: AsyncSession
) -> Payment:
    if not rejection_reason or not rejection_reason.strip():
        raise BaseAPIException(
            status_code=422,
            detail="A rejection reason is required",
            error_code="REJECTION_REASON_REQUIRED",
        )
    repo = PaymentRepository(session)
    payment = await repo.get_by_id(payment_id)
    if payment is None:
        raise BaseAPIException(status_code=404, detail="Payment not found", error_code="PAYMENT_NOT_FOUND")
    if payment.status != PaymentStatus.PENDING_VERIFICATION:
        raise BaseAPIException(
            status_code=409,
            detail=f"Payment is already {payment.status.value}, cannot reject again",
            error_code="PAYMENT_ALREADY_REVIEWED",
        )
    payment.status = PaymentStatus.REJECTED
    payment.rejection_reason = rejection_reason
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.now(tz=timezone.utc)
    session.add(payment)
    await session.commit()
    return await repo.get_by_id(payment.id)


async def upload_payment_proof(
    payment_id: uuid.UUID,
    original_filename: str,
    file_bytes: bytes,
    current_user: User,
    session: AsyncSession,
) -> PaymentProof:
    """Mirrors media_service.upload_visit_media exactly, scoped to a Payment instead of a Visit."""
    payment = await get_payment_for_user(payment_id, current_user, session)

    detected_mime, _media_type, sanitized_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=file_bytes, original_filename=original_filename,
    )

    repo = PaymentProofRepository(session)
    duplicate = await repo.find_by_checksum_for_payment(payment.id, checksum)
    if duplicate is not None:
        raise BaseAPIException(
            status_code=409,
            detail="This exact file is already attached to this payment",
            error_code="PROOF_DUPLICATE_CONTENT",
        )

    proof_id = uuid.uuid4()
    storage_key = f"payments/{payment.id}/{proof_id}_{sanitized_name}"

    await storage_service.upload(file_bytes=file_bytes, storage_key=storage_key, content_type=detected_mime)

    try:
        proof = PaymentProof(
            id=proof_id,
            payment_id=payment.id,
            storage_key=storage_key,
            file_size_bytes=len(file_bytes),
            checksum_sha256=checksum,
            original_filename=sanitized_name,
            uploaded_by=current_user.id,
        )
        await repo.add(proof)
        await repo.commit()
        return proof
    except Exception:
        await session.rollback()
        try:
            await storage_service.delete(storage_key)
        except Exception:
            logger.warning("Orphaned storage object after failed proof upload: %s", storage_key, exc_info=True)
        raise


async def get_proof_download_url(
    proof_id: uuid.UUID, current_user: User, session: AsyncSession, expiry_minutes: int = 15
) -> str:
    repo = PaymentProofRepository(session)
    proof = await repo.get_by_id(proof_id)
    if proof is None:
        raise BaseAPIException(status_code=404, detail="Proof not found", error_code="PROOF_NOT_FOUND")
    await get_payment_for_user(proof.payment_id, current_user, session)
    return await storage_service.generate_presigned_url(proof.storage_key, expiry_minutes)
