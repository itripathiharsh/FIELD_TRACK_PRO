"""
Payments router — /api/v1/payments (the "Collection" workflow)

Route order matters: `/payments/queue` must be declared before
`/payments/{payment_id}` (Starlette matches routes in declaration order, and
"queue" would otherwise be captured as a {payment_id} path parameter).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uploads import read_upload_limited
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.payment import PaymentStatus
from app.models.user import Role
from app.schemas.payment import (
    PaymentAllocationUpdate,
    PaymentCreate,
    PaymentProofRead,
    PaymentRead,
    PaymentReviewAction,
    PaymentVerifyRequest,
    TallyReceiptCandidate,
    TallyReceiptLinkRequest,
    TallyReceiptUnlinkRequest,
)
from app.services import payment_reconciliation_service, payment_service
from app.services.file_validation_service import FileValidationService
from app.services.payment_tally import TallyStatus

router = APIRouter(prefix="/payments", tags=["payments"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("/queue", response_model=list[PaymentRead], dependencies=[AdminOnly])
async def get_review_queue(
    session: DbSession,
    status: PaymentStatus | None = Query(default=None),
    tally_status: TallyStatus | None = Query(
        default=None, description="Filter by derived Tally lifecycle: NOT_APPLICABLE|AWAITING_TALLY|POSTED|FAILED"
    ),
    stuck: bool | None = Query(
        default=None,
        description="true = only FAILED write-backs or AWAITING_TALLY for 30+ minutes after verification",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """Admin/accountant review queue - see design note in the P1 report re: no dedicated ACCOUNTANT role."""
    payments = await payment_service.list_review_queue(
        session, status=status, skip=skip, limit=limit, tally_status=tally_status, stuck=stuck
    )
    return [await payment_service.to_payment_read_for_queue(p, session, is_admin=True) for p in payments]


@router.post("", response_model=PaymentRead, status_code=201, dependencies=[AnyAuth])
async def create_payment(data: PaymentCreate, current_user: CurrentUser, session: DbSession):
    """Employee: record a field collection. visit_id determines the outlet/employee - see payment_service."""
    is_admin = current_user.has_global_scope  # captured first: a rollback in the service expires current_user
    payment = await payment_service.create_payment(data, current_user, session)
    return (await payment_service.build_payment_reads([payment], session, is_admin))[0]


@router.get("/{payment_id}", response_model=PaymentRead, dependencies=[AnyAuth])
async def get_payment(payment_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    is_admin = current_user.has_global_scope
    payment = await payment_service.get_payment_for_user(payment_id, current_user, session)
    return await payment_service.to_payment_read_for_queue(payment, session, is_admin=is_admin)


@router.post(
    "/{payment_id}/proof",
    response_model=PaymentProofRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AnyAuth],
)
async def upload_payment_proof(
    payment_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Upload a cheque photo or online-payment screenshot for a collection."""
    file_bytes = await read_upload_limited(
        file, FileValidationService.MAX_IMAGE_SIZE_BYTES
    )
    filename = file.filename or "payment_proof"
    mime_type = file.content_type or "image/jpeg"
    return await payment_service.upload_payment_proof(
        payment_id=payment_id,
        file_bytes=file_bytes,
        original_filename=filename,
        mime_type=mime_type,
        current_user=current_user,
        session=session,
    )


@router.get("/proofs/{proof_id}/download", dependencies=[AnyAuth])
async def get_proof_download_url(
    request: Request,
    proof_id: uuid.UUID,
    expiry_minutes: int = Query(default=15, ge=1, le=60),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Pre-signed download URL for a payment proof. Same absolute-URL handling
    as /media/{id}/download and /signatures/{id}/download.
    """
    url = await payment_service.get_proof_download_url(proof_id, current_user, session, expiry_minutes)
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"{str(request.base_url).rstrip('/')}{url}"
    return {"download_url": url, "expires_in_minutes": expiry_minutes}


@router.post("/{payment_id}/verify", response_model=PaymentRead, dependencies=[AdminOnly])
async def verify_payment(
    payment_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    data: Annotated[PaymentVerifyRequest | None, Body()] = None,
):
    """Verify against the bank. The body (bank_reference / bank_verified_on / verified_note) is optional."""
    payment = await payment_service.verify_payment(payment_id, current_user, session, bank=data)
    return (await payment_service.build_payment_reads([payment], session, True))[0]


@router.post("/{payment_id}/tally-retry", response_model=PaymentRead, dependencies=[AdminOnly])
async def tally_retry_payment(payment_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Admin: re-queue a FAILED Tally write-back of this payment (409 unless tally_status is FAILED)."""
    payment = await payment_service.tally_retry_payment(payment_id, current_user, session)
    return (await payment_service.build_payment_reads([payment], session, True))[0]


@router.get(
    "/{payment_id}/tally-receipt-candidates",
    response_model=list[TallyReceiptCandidate],
    dependencies=[AdminOnly],
)
async def get_tally_receipt_candidates(
    payment_id: uuid.UUID,
    session: DbSession,
    window_days: int = Query(default=payment_reconciliation_service.DEFAULT_WINDOW_DAYS, ge=0,
                             le=payment_reconciliation_service.MAX_WINDOW_DAYS),
):
    """Admin: imported Tally receipts this field collection could be linked to. Suggestions only."""
    return await payment_reconciliation_service.suggest_tally_receipts(session, payment_id, window_days)


@router.post("/{payment_id}/link-tally-receipt", response_model=PaymentRead, dependencies=[AdminOnly])
async def link_tally_receipt(
    payment_id: uuid.UUID, data: TallyReceiptLinkRequest, current_user: CurrentUser, session: DbSession
):
    """Admin: confirm this verified field collection is the same money as an imported Tally receipt."""
    actor_id = current_user.id
    payment = await payment_reconciliation_service.link_tally_receipt(
        session, payment_id, data.tally_receipt_payment_id, actor_id
    )
    return (await payment_service.build_payment_reads([payment], session, True))[0]


@router.post("/{payment_id}/unlink-tally-receipt", response_model=PaymentRead, dependencies=[AdminOnly])
async def unlink_tally_receipt(
    payment_id: uuid.UUID, data: TallyReceiptUnlinkRequest, current_user: CurrentUser, session: DbSession
):
    """Admin: undo a wrong link (reason required); the collection returns to AWAITING_TALLY."""
    actor_id = current_user.id
    payment = await payment_reconciliation_service.unlink_tally_receipt(session, payment_id, data.reason, actor_id)
    return (await payment_service.build_payment_reads([payment], session, True))[0]


@router.post("/{payment_id}/reject", response_model=PaymentRead, dependencies=[AdminOnly])
async def reject_payment(
    payment_id: uuid.UUID, data: PaymentReviewAction, current_user: CurrentUser, session: DbSession
):
    payment = await payment_service.reject_payment(
        payment_id, data.rejection_reason, current_user, session
    )
    return (await payment_service.build_payment_reads([payment], session, True))[0]


@router.patch("/{payment_id}/allocations", response_model=PaymentRead, dependencies=[AdminOnly])
async def update_payment_allocations(
    payment_id: uuid.UUID,
    data: PaymentAllocationUpdate,
    current_user: CurrentUser,
    session: DbSession,
):
    """Admin: adjust brand allocations before final verification/rejection."""
    payment = await payment_service.update_payment_allocations(payment_id, data, current_user, session)
    return (await payment_service.build_payment_reads([payment], session, True))[0]
