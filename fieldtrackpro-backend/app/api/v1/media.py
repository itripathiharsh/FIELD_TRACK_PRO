"""
Media router: REST endpoints for visit attachments, file upload, download, and deletion.

Security: All file access goes through pre-signed URLs (Security Design Section 4).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.media import MediaRead
from app.services import media_service

router = APIRouter(tags=["Media Management"])


@router.post(
    "/visits/{visit_id}/media",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    visit_id: uuid.UUID,
    file: UploadFile = File(...),
    is_document: bool = Query(default=False, description="True for document uploads (PDF/DOC), False for images"),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> MediaRead:
    """Upload a photo or document attachment for a visit."""
    file_bytes = await file.read()
    filename = file.filename or "uploaded_attachment"
    return await media_service.upload_visit_media(
        visit_id=visit_id,
        original_filename=filename,
        file_bytes=file_bytes,
        current_user=current_user,
        session=session,
        is_document=is_document,
    )


@router.get("/visits/{visit_id}/media", response_model=list[MediaRead])
async def list_visit_media(
    visit_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[MediaRead]:
    """Retrieve metadata for all media attachments belonging to a visit."""
    return await media_service.list_visit_media(
        visit_id=visit_id,
        current_user=current_user,
        session=session,
    )


@router.get("/media/{media_id}", response_model=MediaRead)
async def get_media_metadata(
    media_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> MediaRead:
    """Get metadata for a single media item."""
    return await media_service.get_media_metadata(
        media_id=media_id,
        current_user=current_user,
        session=session,
    )


@router.get("/media/{media_id}/download")
async def get_media_download_url(
    media_id: uuid.UUID,
    expiry_minutes: int = Query(default=15, ge=1, le=60, description="URL expiry in minutes (1-60)"),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get a pre-signed URL for media download.

    Security Design Section 4: access only via pre-signed URLs with short expiry.
    The URL expires after the specified number of minutes (default 15).
    """
    url = await media_service.get_media_download_url(
        media_id=media_id,
        current_user=current_user,
        session=session,
        expiry_minutes=expiry_minutes,
    )
    return {"download_url": url, "expires_in_minutes": expiry_minutes}


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a media attachment from storage and metadata repository."""
    await media_service.delete_media(
        media_id=media_id,
        current_user=current_user,
        session=session,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
