"""
Media Service: orchestrates business rules, ownership validation,
server-side security inspection, object storage calls, and database persistence.
Follows: Router → Service → Repository → Storage Service → Storage Provider
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.user import Role, User
from app.models.visit_media import VisitMedia
from app.repositories.media_repo import MediaRepository
from app.services.employee_service import get_employee_by_user_id
from app.services.file_validation_service import FileValidationService
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit


async def _assert_visit_access(visit_id: uuid.UUID, current_user: User, session: AsyncSession):
    """Verify that current_user has access permission to target visit."""
    visit = await get_visit(visit_id, session)
    if current_user.role == Role.EMPLOYEE:
        employee = await get_employee_by_user_id(current_user.id, session)
        if visit.employee_id != employee.id:
            raise BaseAPIException(
                status_code=403,
                detail="You are not assigned to this visit",
                error_code="VISIT_NOT_ASSIGNED",
            )
    return visit


async def upload_visit_media(
    visit_id: uuid.UUID,
    original_filename: str,
    file_bytes: bytes,
    current_user: User,
    session: AsyncSession,
) -> VisitMedia:
    """Validate, store binary object, and persist metadata record."""
    await _assert_visit_access(visit_id, current_user, session)

    # 1. Inspect & validate file safety
    detected_mime, media_type, sanitized_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=file_bytes,
        original_filename=original_filename,
    )

    # 2. Generate identity & storage path key
    media_id = uuid.uuid4()
    storage_key = FileValidationService.generate_storage_key(
        visit_id=visit_id,
        media_id=media_id,
        sanitized_name=sanitized_name,
    )

    # 3. Store file binary via StorageService abstraction
    await storage_service.upload(
        file_bytes=file_bytes,
        storage_key=storage_key,
        content_type=detected_mime,
    )

    # 4. Save metadata record to DB via MediaRepository with automatic rollback cleanup
    try:
        repo = MediaRepository(session)
        media_record = VisitMedia(
            id=media_id,
            visit_id=visit_id,
            media_type=media_type,
            storage_key=storage_key,
            file_size_bytes=len(file_bytes),
        )
        await repo.add(media_record)
        await repo.commit()
        return media_record
    except Exception as err:
        # Transactional Rollback Guard: Delete uploaded blob if database transaction fails
        try:
            await storage_service.delete(storage_key)
        except Exception:
            pass
        raise err


async def list_visit_media(
    visit_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> Sequence[VisitMedia]:
    """Retrieve metadata for all media objects linked to a visit."""
    await _assert_visit_access(visit_id, current_user, session)
    repo = MediaRepository(session)
    return await repo.list_by_visit(visit_id)


async def get_media_metadata(
    media_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> VisitMedia:
    """Retrieve metadata for a single media object."""
    repo = MediaRepository(session)
    media = await repo.get_by_id(media_id)
    if media is None:
        raise BaseAPIException(
            status_code=404,
            detail="Media file not found",
            error_code="MEDIA_NOT_FOUND",
        )
    await _assert_visit_access(media.visit_id, current_user, session)
    return media


async def download_media_bytes(
    media_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> tuple[bytes, str, str]:
    """
    Download raw file bytes.
    Returns (file_bytes, content_type, original_filename).
    """
    media = await get_media_metadata(media_id, current_user, session)
    file_bytes = await storage_service.download(media.storage_key)
    
    # Infer Content-Type header from media_type or extension
    content_type = "application/pdf" if media.media_type.value == "DOCUMENT" else "image/jpeg"
    filename = media.storage_key.split("_", 1)[-1] if "_" in media.storage_key else "downloaded_file"

    return file_bytes, content_type, filename


async def delete_media(
    media_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> None:
    """Delete media object from storage service and remove DB metadata record."""
    media = await get_media_metadata(media_id, current_user, session)
    repo = MediaRepository(session)
    
    storage_key = media.storage_key

    # 1. Delete DB metadata record first
    await repo.delete(media)
    await repo.commit()

    # 2. Delete object from storage provider
    try:
        await storage_service.delete(storage_key)
    except Exception:
        # DB deletion is already committed; log storage deletion warning
        pass
