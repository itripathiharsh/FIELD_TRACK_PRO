"""
Signature Service: orchestrates business rules, ownership validation,
image decoding, storage calls, and database persistence.

Covers two optional customer-acknowledgement capture methods (see
SignatureCaptureMethod) plus the pre-existing employee signature - all three
share the same upload/validate/store pipeline, distinguished only by the
capture_method tag recorded on the row.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.user import User
from app.models.visit_signature import VisitSignature, SignatureType, SignatureCaptureMethod
from app.repositories.signature_repo import SignatureRepository
from app.services.file_validation_service import FileValidationService
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit_for_user

logger = logging.getLogger("fieldtrackpro")

SIGNATURE_STORAGE_PREFIX = "signatures"

# Maximum signature/acknowledgement image size, measured on the DECODED
# bytes (not the base64 text, which runs ~33% larger on the wire - see
# _decode_signature_image). Deliberately unchanged: a photo of a signed
# document is expected to go through the same client-side downsampling
# pipeline already used for other visit photo evidence before it reaches
# this limit, rather than this limit being raised to accommodate raw
# full-resolution camera photos.
MAX_SIGNATURE_SIZE_BYTES = 1024 * 1024

# Valid PNG/JPEG magic bytes for signature/acknowledgement images.
VALID_SIGNATURE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xFF\xD8\xFF": "image/jpeg",
}

CONTENT_TYPE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
}

# Explicit allow-list for signature_type. Pydantic's enum typing on
# SignatureCreate.signature_type already rejects any other value before this
# service ever runs; this is kept as a deliberate second gate, not the only
# one, matching this codebase's general "never trust client" convention.
VALID_SIGNED_BY = {"EMPLOYEE", "CUSTOMER"}


async def _assert_visit_access(visit_id: uuid.UUID, current_user: User, session: AsyncSession):
    """Verify the caller may act on the target visit."""
    return await get_visit_for_user(visit_id, current_user, session)


def _decode_signature_image(base64_data: str) -> tuple[bytes, str]:
    """
    Decode and validate a base64-encoded signature/acknowledgement image.

    Returns (image_bytes, content_type).
    Raises BaseAPIException if the data is invalid.
    """
    try:
        # Strip data URI prefix if present
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        image_bytes = base64.b64decode(base64_data, validate=True)
    except Exception:
        raise BaseAPIException(
            status_code=400,
            detail="Invalid signature image data. Expected base64-encoded PNG or JPEG.",
            error_code="INVALID_SIGNATURE_DATA",
        )

    if len(image_bytes) == 0:
        raise BaseAPIException(
            status_code=400,
            detail="Signature image is empty.",
            error_code="INVALID_SIGNATURE_EMPTY",
        )

    if len(image_bytes) > MAX_SIGNATURE_SIZE_BYTES:
        raise BaseAPIException(
            status_code=413,
            detail=f"Signature image exceeds maximum size ({MAX_SIGNATURE_SIZE_BYTES} decoded bytes).",
            error_code="SIGNATURE_TOO_LARGE",
        )

    # Validate magic bytes
    content_type = None
    for magic, mime in VALID_SIGNATURE_MAGIC.items():
        if image_bytes.startswith(magic):
            content_type = mime
            break

    if content_type is None:
        raise BaseAPIException(
            status_code=415,
            detail="Signature must be a PNG or JPEG image.",
            error_code="UNSUPPORTED_SIGNATURE_TYPE",
        )

    return image_bytes, content_type


def _build_storage_key(visit_id: uuid.UUID, signature_id: uuid.UUID, content_type: str) -> str:
    extension = CONTENT_TYPE_EXTENSIONS.get(content_type, "bin")
    return f"{SIGNATURE_STORAGE_PREFIX}/{visit_id}/{signature_id}.{extension}"


async def upload_signature(
    visit_id: uuid.UUID,
    signature_type: SignatureType,
    signature_image_base64: str,
    current_user: User,
    session: AsyncSession,
    capture_method: SignatureCaptureMethod = SignatureCaptureMethod.SIGNATURE,
) -> VisitSignature:
    """
    Validate, store the signature/acknowledgement image, and persist the
    metadata record.

    `created_by` records which authenticated account (always an employee or
    admin login - customers have none) actually submitted this row. That is
    an honest audit trail of who captured the evidence; it does not and
    cannot prove whose hand actually held the pen for a SIGNATURE capture,
    or who is depicted signing in a PHOTO_UPLOAD - this service does not
    claim otherwise, and neither should any caller of it.
    """
    await _assert_visit_access(visit_id, current_user, session)

    # 0. Explicitly validate signature type (server-side, never trust client)
    if signature_type.value not in VALID_SIGNED_BY:
        raise BaseAPIException(
            status_code=400,
            detail=f"signature_type must be one of: {', '.join(sorted(VALID_SIGNED_BY))}",
            error_code="INVALID_SIGNATURE_TYPE",
        )

    # 1. Decode and validate the signature image
    image_bytes, content_type = _decode_signature_image(signature_image_base64)
    checksum = FileValidationService.compute_sha256(image_bytes)

    # 2. Check for an existing CURRENT signature of this type (one active
    # per type per visit - a superseded/replaced one does not block a fresh
    # upload of the same type, since replace_signature is what creates those).
    repo = SignatureRepository(session)
    existing = await repo.find_current_by_visit_and_type(visit_id, signature_type.value)
    if existing is not None:
        raise BaseAPIException(
            status_code=409,
            detail=f"A {signature_type.value.lower()} signature already exists for this visit.",
            error_code="SIGNATURE_ALREADY_EXISTS",
        )

    signature_record = await _store_and_persist(
        visit_id=visit_id,
        signature_type=signature_type,
        capture_method=capture_method,
        image_bytes=image_bytes,
        content_type=content_type,
        checksum=checksum,
        created_by=current_user.id,
        session=session,
    )
    return signature_record


async def replace_signature(
    visit_id: uuid.UUID,
    signature_id: uuid.UUID,
    signature_image_base64: str,
    current_user: User,
    session: AsyncSession,
    capture_method: SignatureCaptureMethod = SignatureCaptureMethod.SIGNATURE,
) -> VisitSignature:
    """
    Correct an incorrectly-captured signature/acknowledgement.

    The prior row is marked superseded (its storage blob is kept, not
    deleted) rather than overwritten, and a brand-new row/blob is created for
    the replacement - so a corrected capture never destroys the previous
    evidence, it only stops being "current".
    """
    await _assert_visit_access(visit_id, current_user, session)

    repo = SignatureRepository(session)
    existing = await repo.get_by_id(signature_id)
    if existing is None or existing.visit_id != visit_id:
        raise BaseAPIException(
            status_code=404, detail="Signature not found", error_code="SIGNATURE_NOT_FOUND",
        )
    if existing.superseded_at is not None:
        raise BaseAPIException(
            status_code=400,
            detail="This signature has already been replaced; only the current signature of a given type can be replaced.",
            error_code="SIGNATURE_ALREADY_SUPERSEDED",
        )

    image_bytes, content_type = _decode_signature_image(signature_image_base64)
    checksum = FileValidationService.compute_sha256(image_bytes)

    new_record = await _store_and_persist(
        visit_id=visit_id,
        signature_type=existing.signature_type,
        capture_method=capture_method,
        image_bytes=image_bytes,
        content_type=content_type,
        checksum=checksum,
        created_by=current_user.id,
        session=session,
        superseding=existing,
    )
    return new_record


async def _store_and_persist(
    *,
    visit_id: uuid.UUID,
    signature_type: SignatureType,
    capture_method: SignatureCaptureMethod,
    image_bytes: bytes,
    content_type: str,
    checksum: str,
    created_by: uuid.UUID,
    session: AsyncSession,
    superseding: VisitSignature | None = None,
) -> VisitSignature:
    """Shared store-blob + persist-row logic for both a fresh upload and a replacement."""
    repo = SignatureRepository(session)
    signature_id = uuid.uuid4()
    storage_key = _build_storage_key(visit_id, signature_id, content_type)

    await storage_service.upload(
        file_bytes=image_bytes,
        storage_key=storage_key,
        content_type=content_type,
    )

    try:
        # Supersede the predecessor BEFORE inserting the new row: repo.add()
        # flushes immediately (to get the PK), and the partial unique index
        # only allows one non-superseded row per (visit_id, signature_type)
        # at any moment the DB is queried - inserting the new current row
        # while the old one still reads superseded_at IS NULL would violate
        # that constraint, even within the same still-uncommitted transaction.
        if superseding is not None:
            superseding.superseded_at = datetime.now(tz=timezone.utc)
            session.add(superseding)
            await session.flush()

        signature_record = VisitSignature(
            id=signature_id,
            visit_id=visit_id,
            signature_type=signature_type,
            capture_method=capture_method,
            storage_key=storage_key,
            content_type=content_type,
            file_size_bytes=len(image_bytes),
            checksum_sha256=checksum,
            created_by=created_by,
        )
        await repo.add(signature_record)
        await repo.commit()
        return signature_record
    except Exception:
        await session.rollback()
        try:
            await storage_service.delete(storage_key)
        except Exception:
            logger.warning(
                "Orphaned signature storage object after failed upload: %s",
                storage_key,
                exc_info=True,
            )
        raise


async def list_visit_signatures(
    visit_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> list[VisitSignature]:
    """Retrieve all signatures for a visit, current and superseded (full audit trail)."""
    await _assert_visit_access(visit_id, current_user, session)
    repo = SignatureRepository(session)
    return list(await repo.list_by_visit(visit_id))


async def get_signature_for_download(
    signature_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> VisitSignature:
    """
    Retrieve a signature record for download, with authorization check.
    Returns the signature record (storage key used for pre-signed URL generation).
    """
    repo = SignatureRepository(session)
    signature = await repo.get_by_id(signature_id)
    if signature is None:
        raise BaseAPIException(
            status_code=404,
            detail="Signature not found",
            error_code="SIGNATURE_NOT_FOUND",
        )
    await _assert_visit_access(signature.visit_id, current_user, session)
    return signature


async def download_signature_bytes(
    signature_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> tuple[bytes, str]:
    """
    Download raw signature image bytes (for backward compatibility).
    Returns (image_bytes, content_type) - the actual stored content type,
    falling back to image/png only for legacy rows predating that column.
    """
    signature = await get_signature_for_download(signature_id, current_user, session)
    image_bytes = await storage_service.download(signature.storage_key)
    content_type = signature.content_type or "image/png"
    return image_bytes, content_type
