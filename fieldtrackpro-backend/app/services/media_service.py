"""
Media Service: orchestrates business rules, ownership validation,
server-side security inspection, object storage calls, and database persistence.
Follows: Router → Service → Repository → Storage Service → Storage Provider
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("fieldtrackpro")

from app.exceptions.custom import BaseAPIException
from app.models.user import User
from app.models.visit_media import MediaType, VisitMedia
from app.repositories.media_repo import MediaRepository
from app.services.file_validation_service import FileValidationService
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit_for_user


async def _assert_visit_access(visit_id: uuid.UUID, current_user: User, session: AsyncSession):
    """
    Verify the caller may act on the target visit.

    Delegates to the single ownership rule in visit_service (FT-002) rather than
    re-implementing it here, so media and visit endpoints can never drift apart.
    """
    return await get_visit_for_user(visit_id, current_user, session)


async def upload_visit_media(
    visit_id: uuid.UUID,
    original_filename: str,
    file_bytes: bytes,
    current_user: User,
    session: AsyncSession,
) -> VisitMedia:
    """
    Validate, store the binary object, and persist the metadata record.

    Order matters: ownership, then content validation, then duplicate
    detection, and only then any write. Nothing reaches storage until the
    upload is known to be acceptable.
    """
    await _assert_visit_access(visit_id, current_user, session)

    # 1. Inspect & validate file safety (magic bytes, size, sanitised name).
    detected_mime, media_type, sanitized_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=file_bytes,
        original_filename=original_filename,
    )

    # 2. FT-036: reject byte-identical content already attached to this visit.
    #    Checked before writing so a rejected duplicate leaves nothing behind.
    repo = MediaRepository(session)
    duplicate = await repo.find_by_checksum_for_visit(visit_id, checksum)
    if duplicate is not None:
        raise BaseAPIException(
            status_code=409,
            detail=(
                "This exact file is already attached to this visit "
                f"(uploaded {duplicate.uploaded_at:%Y-%m-%d %H:%M} UTC)."
            ),
            error_code="MEDIA_DUPLICATE_CONTENT",
        )

    # 3. Generate identity & storage path key. The client filename is never
    #    used as a key - only as retained metadata.
    media_id = uuid.uuid4()
    storage_key = FileValidationService.generate_storage_key(
        visit_id=visit_id,
        media_id=media_id,
        sanitized_name=sanitized_name,
    )

    # 4. Store the binary via the StorageService abstraction.
    await storage_service.upload(
        file_bytes=file_bytes,
        storage_key=storage_key,
        content_type=detected_mime,
    )

    # 5. Persist metadata. If the transaction fails the blob is removed, so a
    #    stored object can never outlive its database row.
    try:
        media_record = VisitMedia(
            id=media_id,
            visit_id=visit_id,
            media_type=media_type,
            storage_key=storage_key,
            file_size_bytes=len(file_bytes),
            checksum_sha256=checksum,
            original_filename=sanitized_name,
            uploaded_by=current_user.id,
        )
        await repo.add(media_record)
        await repo.commit()
        return media_record
    except Exception:
        await session.rollback()
        try:
            await storage_service.delete(storage_key)
        except Exception:
            logger.warning(
                "Orphaned storage object after failed upload: %s", storage_key, exc_info=True
            )
        raise


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

    # FT-036: verify the bytes still match what was uploaded. A mismatch means
    # the stored object was altered or corrupted outside the application, which
    # is exactly the kind of silent evidence tampering the audit log exists to
    # prevent. Fail loudly rather than serving unverified "evidence".
    if media.checksum_sha256:
        actual = FileValidationService.compute_sha256(file_bytes)
        if actual != media.checksum_sha256:
            logger.error(
                "Checksum mismatch for media %s (key=%s): stored=%s actual=%s",
                media.id,
                media.storage_key,
                media.checksum_sha256,
                actual,
            )
            raise BaseAPIException(
                status_code=500,
                detail="Stored file failed its integrity check and was not served.",
                error_code="MEDIA_CHECKSUM_MISMATCH",
            )

    # Content type is derived from the server-detected media type, never from a
    # client-declared value or a file extension.
    content_type = "application/pdf" if media.media_type == MediaType.DOCUMENT else "image/jpeg"

    filename = media.original_filename or media.storage_key.rsplit("/", 1)[-1]
    if "_" in filename and not media.original_filename:
        filename = filename.split("_", 1)[-1]

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

    # 2. Delete object from storage provider. The row is already gone, so a
    #    failure here leaves an unreferenced blob rather than a broken record;
    #    it is logged so `find_orphaned_media` can reconcile it later.
    try:
        await storage_service.delete(storage_key)
    except Exception:
        logger.warning(
            "Media row %s deleted but storage object %s could not be removed",
            media_id,
            storage_key,
            exc_info=True,
        )


async def find_orphaned_media(session: AsyncSession) -> list[VisitMedia]:
    """
    Return media rows whose stored object is missing.

    FT-047: the seed data contained a `visit_media` row pointing at
    `uploads/visits/.../site_photo_01.jpg` with no file behind it. To the UI it
    was indistinguishable from a real attachment until a user clicked it and
    received a 404 - a genuine data-integrity defect, not an intentional
    fixture (see docs/REPAIR_DECISIONS.md RD-005).

    Read-only: callers decide what to do with the result.
    """
    repo = MediaRepository(session)
    orphans: list[VisitMedia] = []
    for media in await repo.list_all():
        if not await storage_service.exists(media.storage_key):
            orphans.append(media)
    return orphans
