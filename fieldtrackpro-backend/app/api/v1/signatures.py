"""
Signature router: REST endpoints for visit digital signatures.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.signature import SignatureCreate, SignatureRead
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
    """Upload a digital signature (customer or employee) for a visit."""
    return await signature_service.upload_signature(
        visit_id=visit_id,
        signature_type=payload.signature_type,
        signature_image_base64=payload.signature_image_base64,
        current_user=current_user,
        session=session,
    )


@router.get("/visits/{visit_id}/signatures", response_model=list[SignatureRead])
async def list_visit_signatures(
    visit_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[SignatureRead]:
    """Retrieve all signatures for a visit."""
    return await signature_service.list_visit_signatures(
        visit_id=visit_id,
        current_user=current_user,
        session=session,
    )


@router.get("/signatures/{signature_id}/download")
async def download_signature(
    signature_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Download a signature image."""
    image_bytes, content_type = await signature_service.download_signature_bytes(
        signature_id=signature_id,
        current_user=current_user,
        session=session,
    )
    return Response(
        content=image_bytes,
        media_type=content_type,
    )
