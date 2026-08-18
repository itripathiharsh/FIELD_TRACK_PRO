"""
File Validation Service: server-side magic byte analysis, MIME verification,
file size constraints, checksum generation, and path sanitization.

Uses python-magic (libmagic) for content-based type detection rather than
trusting client-declared MIME type or file extension.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid

import magic

from app.exceptions.custom import BaseAPIException
from app.models.visit_media import MediaType

logger = logging.getLogger("fieldtrackpro")


class FileValidationService:
    """Server-side file inspector and security validator."""

    MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit for images
    MAX_DOCUMENT_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB limit for documents

    ALLOWED_IMAGE_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_DOCUMENT_TYPES: set[str] = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """Strip directory paths and unsafe characters from raw filename."""
        base_name = os.path.basename(filename)
        cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base_name)
        return cleaned or "unnamed_file"

    @classmethod
    def compute_sha256(cls, file_bytes: bytes) -> str:
        """Generate SHA-256 checksum hex string for content integrity."""
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def detect_mime_type(cls, file_bytes: bytes) -> str:
        """
        Detect MIME type from actual file content using python-magic.

        This reads the magic bytes of the file, not the client-declared
        Content-Type header or the file extension.
        """
        try:
            return magic.from_buffer(file_bytes[:8192], mime=True)
        except Exception as e:
            logger.warning("python-magic detection failed: %s", e)
            return "application/octet-stream"

    @classmethod
    def validate_image(cls, file_bytes: bytes, original_filename: str) -> tuple[str, MediaType, str, str]:
        """
        Validate an image file and return (detected_mime, media_type, sanitized_filename, checksum).

        Raises BaseAPIException if file is empty, oversized, or has invalid content.
        """
        if len(file_bytes) == 0:
            raise BaseAPIException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes)",
                error_code="INVALID_FILE_EMPTY",
            )
        if len(file_bytes) > cls.MAX_IMAGE_SIZE_BYTES:
            raise BaseAPIException(
                status_code=413,
                detail=f"Image size ({len(file_bytes)} bytes) exceeds maximum limit ({cls.MAX_IMAGE_SIZE_BYTES} bytes)",
                error_code="FILE_TOO_LARGE",
            )

        detected_mime = cls.detect_mime_type(file_bytes)
        if detected_mime not in cls.ALLOWED_IMAGE_TYPES:
            raise BaseAPIException(
                status_code=415,
                detail=f"Unsupported image type (detected: {detected_mime}). Only JPEG, PNG, and WEBP are allowed.",
                error_code="UNSUPPORTED_MEDIA_TYPE",
            )

        sanitized_name = cls.sanitize_filename(original_filename)
        checksum = cls.compute_sha256(file_bytes)
        return detected_mime, MediaType.PHOTO, sanitized_name, checksum

    @classmethod
    def validate_document(cls, file_bytes: bytes, original_filename: str) -> tuple[str, MediaType, str, str]:
        """
        Validate a document file and return (detected_mime, media_type, sanitized_filename, checksum).

        Raises BaseAPIException if file is empty, oversized, or has invalid content.
        """
        if len(file_bytes) == 0:
            raise BaseAPIException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes)",
                error_code="INVALID_FILE_EMPTY",
            )
        if len(file_bytes) > cls.MAX_DOCUMENT_SIZE_BYTES:
            raise BaseAPIException(
                status_code=413,
                detail=f"Document size ({len(file_bytes)} bytes) exceeds maximum limit ({cls.MAX_DOCUMENT_SIZE_BYTES} bytes)",
                error_code="FILE_TOO_LARGE",
            )

        detected_mime = cls.detect_mime_type(file_bytes)
        if detected_mime not in cls.ALLOWED_DOCUMENT_TYPES:
            raise BaseAPIException(
                status_code=415,
                detail=f"Unsupported document type (detected: {detected_mime}). Only PDF, DOC, and DOCX are allowed.",
                error_code="UNSUPPORTED_MEDIA_TYPE",
            )

        sanitized_name = cls.sanitize_filename(original_filename)
        checksum = cls.compute_sha256(file_bytes)
        return detected_mime, MediaType.DOCUMENT, sanitized_name, checksum

    @classmethod
    def validate_and_inspect(
        cls,
        file_bytes: bytes,
        original_filename: str,
        expected_type: MediaType | None = None,
    ) -> tuple[str, MediaType, str, str]:
        """
        Validate file safety and return (detected_mime, media_type, sanitized_filename, checksum).

        Uses python-magic for content-based type detection. If expected_type is
        provided, validates against that specific type's rules. Otherwise,
        auto-detects the type based on content.

        Raises BaseAPIException if file is empty, corrupted, oversized, or has unknown magic bytes.
        """
        # Check empty file first (before type detection)
        if len(file_bytes) == 0:
            raise BaseAPIException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes)",
                error_code="INVALID_FILE_EMPTY",
            )

        if expected_type == MediaType.DOCUMENT:
            return cls.validate_document(file_bytes, original_filename)

        if expected_type == MediaType.ORDER:
            detected_mime = cls.detect_mime_type(file_bytes)
            if detected_mime in cls.ALLOWED_IMAGE_TYPES:
                _, _, sanitized_name, checksum = cls.validate_image(file_bytes, original_filename)
                return detected_mime, MediaType.ORDER, sanitized_name, checksum
            # Text-only structured order note
            sanitized_name = cls.sanitize_filename(original_filename)
            checksum = cls.compute_sha256(file_bytes)
            return "text/plain", MediaType.ORDER, sanitized_name, checksum

        # Auto-detect: try image first, then document
        detected_mime = cls.detect_mime_type(file_bytes)
        if detected_mime in cls.ALLOWED_IMAGE_TYPES:
            return cls.validate_image(file_bytes, original_filename)
        elif detected_mime in cls.ALLOWED_DOCUMENT_TYPES:
            return cls.validate_document(file_bytes, original_filename)
        else:
            # Cannot determine type - reject
            raise BaseAPIException(
                status_code=415,
                detail=f"Unsupported file type (detected: {detected_mime}). Only images (JPEG, PNG, WEBP) and documents (PDF, DOC, DOCX) are allowed.",
                error_code="UNSUPPORTED_MEDIA_TYPE",
            )

    @classmethod
    def generate_storage_key(cls, visit_id: uuid.UUID, media_id: uuid.UUID, sanitized_name: str) -> str:
        """Construct secure object key path: visits/{visit_id}/{media_id}_{sanitized_name}."""
        return f"visits/{visit_id}/{media_id}_{sanitized_name}"


file_validation_service = FileValidationService()
