"""
Media router: REST endpoints for visit attachments, file upload, download, and deletion.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
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
async def download_media(
    media_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Download binary content of a media attachment."""
    file_bytes, content_type, filename = await media_service.download_media_bytes(
        media_id=media_id,
        current_user=current_user,
        session=session,
    )
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
