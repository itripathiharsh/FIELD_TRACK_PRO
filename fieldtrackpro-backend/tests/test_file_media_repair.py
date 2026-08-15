"""
Tests for File & Media repair phase:
- Image compression
- Pre-signed URL generation
- Document size limits (20MB)
- python-magic validation
"""
from __future__ import annotations

import hashlib
import io
import os
import tempfile
import uuid

import pytest
from PIL import Image

from app.exceptions.custom import BaseAPIException
from app.services.file_validation_service import FileValidationService
from app.services.media_service import _compress_image
from app.services.storage.local_provider import LocalStorageProvider, verify_local_media_signature


# Test data
JPEG_HEADER = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00" + b"\x00" * 256
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01" + b"\x00" * 256
PDF_HEADER = b"%PDF-1.4\n" + b"\x00" * 128


class TestImageCompression:
    """Tests for mandatory image compression (Phase 5 Section 2)."""

    def test_compress_large_image_reduces_dimensions(self):
        """Images larger than 1920px should be resized."""
        # Create a 3000x2000 test image
        img = Image.new("RGB", (3000, 2000), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        original_bytes = buf.getvalue()

        compressed = _compress_image(original_bytes, max_dimension=1920, quality=80)

        # Verify compressed image dimensions
        compressed_img = Image.open(io.BytesIO(compressed))
        assert max(compressed_img.size) == 1920
        assert compressed_img.size[0] == 1920
        assert compressed_img.size[1] == 1280  # Aspect ratio preserved

    def test_compress_preserves_aspect_ratio(self):
        """Aspect ratio must be preserved during compression."""
        img = Image.new("RGB", (4000, 2000), color="blue")  # 2:1 ratio
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        original_bytes = buf.getvalue()

        compressed = _compress_image(original_bytes, max_dimension=1920, quality=80)
        compressed_img = Image.open(io.BytesIO(compressed))

        # Aspect ratio should be approximately 2:1
        ratio = compressed_img.size[0] / compressed_img.size[1]
        assert 1.9 < ratio < 2.1

    def test_compress_outputs_jpeg(self):
        """Compressed output should be JPEG format."""
        img = Image.new("RGB", (2000, 2000), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")  # Start with PNG
        original_bytes = buf.getvalue()

        compressed = _compress_image(original_bytes, max_dimension=1920, quality=80)
        compressed_img = Image.open(io.BytesIO(compressed))
        assert compressed_img.format == "JPEG"

    def test_small_image_unchanged(self):
        """Images smaller than max_dimension should not be resized."""
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        original_bytes = buf.getvalue()

        compressed = _compress_image(original_bytes, max_dimension=1920, quality=80)
        compressed_img = Image.open(io.BytesIO(compressed))
        assert compressed_img.size == (100, 100)

    def test_compress_rgba_image(self):
        """RGBA images should be converted to RGB for JPEG output."""
        img = Image.new("RGBA", (2000, 2000), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        original_bytes = buf.getvalue()

        compressed = _compress_image(original_bytes, max_dimension=1920, quality=80)
        compressed_img = Image.open(io.BytesIO(compressed))
        assert compressed_img.mode == "RGB"

    def test_compress_invalid_image_returns_original(self):
        """If PIL cannot process the image, original bytes should be returned."""
        result = _compress_image(JPEG_HEADER, max_dimension=1920, quality=80)
        assert result == JPEG_HEADER


class TestDocumentValidation:
    """Tests for document-specific validation (20MB limit)."""

    def test_valid_pdf_accepted(self):
        """Valid PDF should be accepted as DOCUMENT type."""
        mime, m_type, name, checksum = FileValidationService.validate_and_inspect(
            file_bytes=PDF_HEADER,
            original_filename="contract.pdf",
        )
        assert mime == "application/pdf"
        assert m_type.value == "DOCUMENT"

    def test_document_size_limit_20mb(self):
        """Documents up to 20MB should be accepted."""
        large_doc = PDF_HEADER + b"\x00" * (20 * 1024 * 1024 - len(PDF_HEADER))
        mime, m_type, name, checksum = FileValidationService.validate_and_inspect(
            file_bytes=large_doc,
            original_filename="large_contract.pdf",
        )
        assert m_type.value == "DOCUMENT"

    def test_document_over_20mb_rejected(self):
        """Documents over 20MB should be rejected."""
        oversized_doc = PDF_HEADER + b"\x00" * (20 * 1024 * 1024 + 1)
        with pytest.raises(BaseAPIException) as exc_info:
            FileValidationService.validate_and_inspect(
                file_bytes=oversized_doc,
                original_filename="huge_contract.pdf",
            )
        assert exc_info.value.status_code == 413

    def test_image_over_10mb_rejected(self):
        """Images over 10MB should be rejected."""
        oversized_image = JPEG_HEADER + b"\x00" * (10 * 1024 * 1024 + 1)
        with pytest.raises(BaseAPIException) as exc_info:
            FileValidationService.validate_and_inspect(
                file_bytes=oversized_image,
                original_filename="huge_photo.jpg",
            )
        assert exc_info.value.status_code == 413


class TestPresignedUrlGeneration:
    """Tests for pre-signed URL generation."""

    @pytest.mark.asyncio
    async def test_local_storage_presigned_url(self):
        """
        P0 fix: local storage previously returned a bare file://<server-disk-
        path>, unusable by any remote client and carrying no signature or
        expiry. It must now return a signed, time-boxed URL pointing at the
        local-file-serving endpoint, with a signature that verifies.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider = LocalStorageProvider(base_dir=tmp_dir)
            key = "visits/test/media_1.jpg"
            await provider.upload(JPEG_HEADER, key, "image/jpeg")

            url = await provider.generate_presigned_url(key, expiry_minutes=15)
            assert not url.startswith("file://")
            assert url.startswith("/api/v1/media/local-file?")
            assert f"key={key}" in url

            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(url).query)
            expires_at = int(query["expires"][0])
            sig = query["sig"][0]
            assert verify_local_media_signature(key, expires_at, sig)
            assert not verify_local_media_signature(key, expires_at, "tampered")
            assert not verify_local_media_signature(key, expires_at - 20 * 60, sig)

    @pytest.mark.asyncio
    async def test_presigned_url_for_missing_object_raises_error(self):
        """Requesting URL for non-existent object should raise error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider = LocalStorageProvider(base_dir=tmp_dir)

            with pytest.raises(BaseAPIException) as exc_info:
                await provider.generate_presigned_url("nonexistent/key.jpg")
            assert exc_info.value.status_code == 404


class TestPythonMagicValidation:
    """Tests for python-magic based file validation."""

    def test_detect_jpeg_content(self):
        """python-magic should detect JPEG content."""
        detected = FileValidationService.detect_mime_type(JPEG_HEADER)
        assert detected == "image/jpeg"

    def test_detect_png_content(self):
        """python-magic should detect PNG content."""
        detected = FileValidationService.detect_mime_type(PNG_HEADER)
        assert detected == "image/png"

    def test_detect_pdf_content(self):
        """python-magic should detect PDF content."""
        detected = FileValidationService.detect_mime_type(PDF_HEADER)
        assert detected == "application/pdf"

    def test_reject_executable_content(self):
        """Executable content should be rejected."""
        exe_content = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
        with pytest.raises(BaseAPIException) as exc_info:
            FileValidationService.validate_and_inspect(
                file_bytes=exe_content,
                original_filename="malicious.exe",
            )
        assert exc_info.value.status_code == 415

    def test_reject_empty_file(self):
        """Empty files should be rejected with 400."""
        with pytest.raises(BaseAPIException) as exc_info:
            FileValidationService.validate_and_inspect(
                file_bytes=b"",
                original_filename="empty.jpg",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "INVALID_FILE_EMPTY"
