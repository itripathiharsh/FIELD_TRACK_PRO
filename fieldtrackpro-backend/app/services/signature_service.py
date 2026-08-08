"""
Signature Service: orchestrates business rules, ownership validation,
image decoding, storage calls, and database persistence.
"""
from __future__ import annotations

import base64
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.user import User
from app.models.visit_signature import VisitSignature, SignatureType
from app.repositories.signature_repo import SignatureRepository
from app.services.storage_service import storage_service
from app.services.visit_service import get_visit_for_user

logger = logging.getLogger("fieldtrackpro")

SIGNATURE_STORAGE_PREFIX = "signatures"

# Maximum signature image size: 1MB (base64 encoded)
MAX_SIGNATURE_SIZE_BYTES = 1024 * 1024

# Valid PNG/JPEG magic bytes for signature images
VALID_SIGNATURE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xFF\xD8\xFF": "image/jpeg",
}


async def _assert_visit_access(visit_id: uuid.UUID, current_user: User, session: AsyncSession):
    """Verify the caller may act on the target visit."""
    return await get_visit_for_user(visit_id, current_user, session)


def _decode_signature_image(base64_data: str) -> tuple[bytes, str]:
    """
    Decode and validate a base64-encoded signature image.
    
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
            detail=f"Signature image exceeds maximum size ({MAX_SIGNATURE_SIZE_BYTES} bytes).",
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


async def upload_signature(
    visit_id: uuid.UUID,
    signature_type: SignatureType,
    signature_image_base64: str,
    current_user: User,
    session: AsyncSession,
) -> VisitSignature:
    """
    Validate, store the signature image, and persist the metadata record.
    """
    await _assert_visit_access(visit_id, current_user, session)

    # 1. Decode and validate the signature image
    image_bytes, content_type = _decode_signature_image(signature_image_base64)

    # 2. Check for existing signature of this type (one per type per visit)
    repo = SignatureRepository(session)
    existing = await repo.find_by_visit_and_type(visit_id, signature_type.value)
    if existing is not None:
        raise BaseAPIException(
            status_code=409,
            detail=f"A {signature_type.value.lower()} signature already exists for this visit.",
            error_code="SIGNATURE_ALREADY_EXISTS",
        )

    # 3. Generate storage key
    signature_id = uuid.uuid4()
    storage_key = f"{SIGNATURE_STORAGE_PREFIX}/{visit_id}/{signature_id}.png"

    # 4. Store the image
    await storage_service.upload(
        file_bytes=image_bytes,
        storage_key=storage_key,
        content_type=content_type,
    )

    # 5. Persist metadata
    try:
        signature_record = VisitSignature(
            id=signature_id,
            visit_id=visit_id,
            signature_type=signature_type,
            storage_key=storage_key,
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
    """Retrieve all signatures for a visit."""
    await _assert_visit_access(visit_id, current_user, session)
    repo = SignatureRepository(session)
    return list(await repo.list_by_visit(visit_id))


async def download_signature_bytes(
    signature_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> tuple[bytes, str]:
    """
    Download raw signature image bytes.
    Returns (image_bytes, content_type).
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

    image_bytes = await storage_service.download(signature.storage_key)
    content_type = "image/png"
    return image_bytes, content_type
