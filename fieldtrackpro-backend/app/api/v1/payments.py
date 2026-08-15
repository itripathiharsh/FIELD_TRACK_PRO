"""
Payments router — /api/v1/payments (the "Collection" workflow)

Route order matters: `/payments/queue` must be declared before
`/payments/{payment_id}` (Starlette matches routes in declaration order, and
"queue" would otherwise be captured as a {payment_id} path parameter).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.payment import PaymentStatus
from app.models.user import Role
from app.schemas.payment import PaymentCreate, PaymentProofRead, PaymentRead, PaymentReviewAction
from app.services import payment_service
from app.services.payment_service import to_payment_read as _to_read

router = APIRouter(prefix="/payments", tags=["payments"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("/queue", response_model=list[PaymentRead], dependencies=[AdminOnly])
async def get_review_queue(
    session: DbSession,
    status: PaymentStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """Admin/accountant review queue - see design note in the P1 report re: no dedicated ACCOUNTANT role."""
    payments = await payment_service.list_review_queue(session, status=status, skip=skip, limit=limit)
    return [await payment_service.to_payment_read_for_queue(p, session) for p in payments]


@router.post("", response_model=PaymentRead, status_code=201, dependencies=[AnyAuth])
async def create_payment(data: PaymentCreate, current_user: CurrentUser, session: DbSession):
    """Employee: record a field collection. visit_id determines the outlet/employee - see payment_service."""
    payment = await payment_service.create_payment(data, current_user, session)
    return _to_read(payment)


@router.get("/{payment_id}", response_model=PaymentRead, dependencies=[AnyAuth])
async def get_payment(payment_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    payment = await payment_service.get_payment_for_user(payment_id, current_user, session)
    return await payment_service.to_payment_read_for_queue(payment, session)


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
    file_bytes = await file.read()
    filename = file.filename or "payment_proof"
    return await payment_service.upload_payment_proof(
        payment_id=payment_id,
        original_filename=filename,
        file_bytes=file_bytes,
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
async def verify_payment(payment_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    payment = await payment_service.verify_payment(payment_id, current_user, session)
    return _to_read(payment)


@router.post("/{payment_id}/reject", response_model=PaymentRead, dependencies=[AdminOnly])
async def reject_payment(
    payment_id: uuid.UUID, data: PaymentReviewAction, current_user: CurrentUser, session: DbSession
):
    payment = await payment_service.reject_payment(
        payment_id, data.rejection_reason, current_user, session
    )
    return _to_read(payment)
