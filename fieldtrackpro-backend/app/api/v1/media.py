"""
Media router: REST endpoints for visit attachments, file upload, download, and deletion.

Security: All file access goes through pre-signed URLs (Security Design Section 4).
"""
from __future__ import annotations

import mimetypes
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.schemas.media import MediaRead
from app.services import media_service
from app.services.storage.local_provider import verify_local_media_signature
from app.services.storage_service import storage_service

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
    is_order: bool = Query(default=False, description="True for a photographed order (diary/order note)"),
    note: str | None = Query(default=None, description="Optional short note/summary, e.g. for an order capture"),
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> MediaRead:
    """Upload a photo, document, or order-capture attachment for a visit."""
    file_bytes = await file.read()
    filename = file.filename or "uploaded_attachment"
    return await media_service.upload_visit_media(
        visit_id=visit_id,
        original_filename=filename,
        file_bytes=file_bytes,
        current_user=current_user,
        session=session,
        is_document=is_document,
        is_order=is_order,
        note=note,
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


@router.get("/media/local-file")
async def download_local_media_file(key: str, expires: int, sig: str):
    """
    Serves local-disk media bytes for a signed URL produced by
    LocalStorageProvider.generate_presigned_url.

    Deliberately has no auth dependency: the signature itself is the
    credential, matching how a real object-store presigned URL works (the
    caller shouldn't need a separate Authorization header to use it).

    Must be declared before the /media/{media_id} routes below - Starlette
    matches routes in declaration order, and "local-file" structurally
    matches the {media_id} path parameter too (that ordering bug is what
    caused this endpoint to 401 against the *other* route on first attempt).
    """
    if not verify_local_media_signature(key, expires, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired download link")

    try:
        file_bytes = await storage_service.download(key)
    except BaseAPIException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=file_bytes, media_type=content_type)


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
    request: Request,
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
    # The local storage provider returns a relative signed path (see
    # LocalStorageProvider.generate_presigned_url); MinIO already returns a
    # full absolute URL. Callers (web and Android) fetch this value directly,
    # so it must always be absolute.
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"{str(request.base_url).rstrip('/')}{url}"
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
