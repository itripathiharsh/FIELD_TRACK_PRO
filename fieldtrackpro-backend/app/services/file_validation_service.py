"""
File Validation Service: server-side magic byte analysis, MIME verification,
file size constraints, checksum generation, and path sanitization.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid

from app.exceptions.custom import BaseAPIException
from app.models.visit_media import MediaType


class FileValidationService:
    """Server-side file inspector and security validator."""

    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit

    # True magic byte headers mapped to (MIME type, MediaType enum)
    MAGIC_SIGNATURES: dict[bytes, tuple[str, MediaType]] = {
        b"\xFF\xD8\xFF": ("image/jpeg", MediaType.PHOTO),
        b"\x89PNG\r\n\x1a\n": ("image/png", MediaType.PHOTO),
        b"%PDF": ("application/pdf", MediaType.DOCUMENT),
    }

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """Strip directory paths and unsafe characters from raw filename."""
        base_name = os.path.basename(filename)
        # Remove anything except alphanumeric, dots, hyphens, and underscores
        cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base_name)
        return cleaned or "unnamed_file"

    @classmethod
    def compute_sha256(cls, file_bytes: bytes) -> str:
        """Generate SHA-256 checksum hex string for content integrity."""
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def validate_and_inspect(
        cls,
        file_bytes: bytes,
        original_filename: str,
        client_mime_type: str | None = None,
    ) -> tuple[str, MediaType, str, str]:
        """
        Validate file safety and return (detected_mime, media_type, sanitized_filename, checksum).
        
        Raises
        ------
        BaseAPIException if file is empty, corrupted, oversized, or has unknown magic bytes.
        """
        # 1. Check file size
        file_size = len(file_bytes)
        if file_size == 0:
            raise BaseAPIException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes)",
                error_code="INVALID_FILE_EMPTY",
            )
        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise BaseAPIException(
                status_code=413,
                detail=f"File size ({file_size} bytes) exceeds maximum limit ({cls.MAX_FILE_SIZE_BYTES} bytes)",
                error_code="FILE_TOO_LARGE",
            )

        # 2. Magic byte inspection
        detected_mime: str | None = None
        media_type: MediaType | None = None

        # Check exact header matches
        for sig, (mime, m_type) in cls.MAGIC_SIGNATURES.items():
            if file_bytes.startswith(sig):
                detected_mime = mime
                media_type = m_type
                break

        # WEBP special check
        if not detected_mime and file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]:
            detected_mime = "image/webp"
            media_type = MediaType.PHOTO

        if not detected_mime or not media_type:
            raise BaseAPIException(
                status_code=415,
                detail="Unsupported or corrupt file type. Only JPEG, PNG, WEBP, and PDF files are allowed.",
                error_code="UNSUPPORTED_MEDIA_TYPE",
            )

        sanitized_name = cls.sanitize_filename(original_filename)
        checksum = cls.compute_sha256(file_bytes)

        return detected_mime, media_type, sanitized_name, checksum

    @classmethod
    def generate_storage_key(cls, visit_id: uuid.UUID, media_id: uuid.UUID, sanitized_name: str) -> str:
        """Construct secure object key path: visits/{visit_id}/{media_id}_{sanitized_name}."""
        return f"visits/{visit_id}/{media_id}_{sanitized_name}"


file_validation_service = FileValidationService()
