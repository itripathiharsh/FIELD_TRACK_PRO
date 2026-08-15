"""
Signature router: REST endpoints for visit signatures/acknowledgements.

Security: All signature access goes through pre-signed URLs (Security Design Section 4).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.signature import SignatureCreate, SignatureRead, SignatureReplaceRequest
from app.services import signature_service

router = APIRouter(tags=["Digital Signatures"])


@router.post(
    "/visits/{visit_id}/signatures",
    response_model=SignatureRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_signature(
    visit_id: uuid.UUID,
    payload: SignatureCreate,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> SignatureRead:
    """Upload a signature/acknowledgement (customer or employee) for a visit."""
    return await signature_service.upload_signature(
        visit_id=visit_id,
        signature_type=payload.signature_type,
        signature_image_base64=payload.signature_image_base64,
        capture_method=payload.capture_method,
        current_user=current_user,
        session=session,
    )


@router.post(
    "/visits/{visit_id}/signatures/{signature_id}/replace",
    response_model=SignatureRead,
    status_code=status.HTTP_201_CREATED,
)
async def replace_signature(
    visit_id: uuid.UUID,
    signature_id: uuid.UUID,
    payload: SignatureReplaceRequest,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> SignatureRead:
    """
    Correct an incorrectly-captured signature/acknowledgement. The prior
    capture is preserved (marked superseded, blob kept) rather than
    overwritten - a new row/blob is created for the replacement.
    """
    return await signature_service.replace_signature(
        visit_id=visit_id,
        signature_id=signature_id,
        signature_image_base64=payload.signature_image_base64,
        capture_method=payload.capture_method,
        current_user=current_user,
        session=session,
    )


@router.get("/visits/{visit_id}/signatures", response_model=list[SignatureRead])
async def list_visit_signatures(
    visit_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[SignatureRead]:
    """Retrieve all signatures for a visit (current and superseded/replaced)."""
    return await signature_service.list_visit_signatures(
        visit_id=visit_id,
        current_user=current_user,
        session=session,
    )


@router.get("/signatures/{signature_id}/download")
async def get_signature_download_url(
    request: Request,
    signature_id: uuid.UUID,
    expiry_minutes: int = Query(default=15, ge=1, le=60, description="URL expiry in minutes (1-60)"),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get a pre-signed URL for signature download.

    Security Design Section 4: access only via pre-signed URLs with short expiry.
    """
    signature = await signature_service.get_signature_for_download(
        signature_id=signature_id,
        current_user=current_user,
        session=session,
    )
    # P0 fix: this call was missing `await` - generate_presigned_url is async,
    # so `url` was a coroutine object handed straight to a JSON response,
    # which FastAPI cannot serialize. Every authenticated signature download
    # request 500'd; only the auth-rejection path had test coverage, so this
    # went unnoticed.
    url = await signature_service.storage_service.generate_presigned_url(
        signature.storage_key, expiry_minutes
    )
    # Same absolute-URL requirement as /media/{id}/download: LocalStorageProvider
    # returns a relative signed path, MinIO already returns an absolute one.
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"{str(request.base_url).rstrip('/')}{url}"
    return {"download_url": url, "expires_in_minutes": expiry_minutes}
