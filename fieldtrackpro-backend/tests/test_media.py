"""
Phase 5 — Media Management & Storage Test Suite.

Covers:
- Server-side magic byte inspection (JPEG, PNG, PDF)
- Empty file & oversized file validation guards
- Filename sanitization & path traversal prevention
- Storage Provider CRUD operations (LocalStorageProvider)
- API Router authorization & endpoint checks
"""
from __future__ import annotations

import tempfile
import uuid

import pytest
from httpx import AsyncClient

from app.exceptions.custom import BaseAPIException
from app.services.file_validation_service import FileValidationService
from app.services.storage.local_provider import LocalStorageProvider
from tests.conftest import admin_headers, employee_headers, requires_db


# Sample valid headers
JPEG_HEADER = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00"
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
PDF_HEADER = b"%PDF-1.4\n%...\n"


# ---------------------------------------------------------------------------
# File Validation & Security Tests
# ---------------------------------------------------------------------------

def test_file_validation_valid_jpeg():
    """Valid JPEG header passes inspection and returns image/jpeg MIME type."""
    mime, m_type, clean_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=JPEG_HEADER,
        original_filename="../../my_photo.jpg",
    )
    assert mime == "image/jpeg"
    assert m_type.value == "PHOTO"
    assert clean_name == "my_photo.jpg"
    assert len(checksum) == 64  # SHA-256 hex string


def test_file_validation_valid_png():
    """Valid PNG header passes inspection."""
    mime, m_type, clean_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=PNG_HEADER,
        original_filename="invoice_receipt.png",
    )
    assert mime == "image/png"
    assert m_type.value == "PHOTO"


def test_file_validation_valid_pdf():
    """Valid PDF header passes inspection and returns DOCUMENT MediaType."""
    mime, m_type, clean_name, checksum = FileValidationService.validate_and_inspect(
        file_bytes=PDF_HEADER,
        original_filename="contract.pdf",
    )
    assert mime == "application/pdf"
    assert m_type.value == "DOCUMENT"


def test_file_validation_empty_file():
    """Empty 0-byte payload raises 400 INVALID_FILE_EMPTY."""
    with pytest.raises(BaseAPIException) as exc_info:
        FileValidationService.validate_and_inspect(
            file_bytes=b"",
            original_filename="empty.jpg",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "INVALID_FILE_EMPTY"


def test_file_validation_unsupported_magic_bytes():
    """Unknown file header (e.g. text/exe) raises 415 UNSUPPORTED_MEDIA_TYPE."""
    with pytest.raises(BaseAPIException) as exc_info:
        FileValidationService.validate_and_inspect(
            file_bytes=b"MZ\x90\x00\x03\x00\x00\x00",  # EXE header
            original_filename="malicious.exe",
        )
    assert exc_info.value.status_code == 415
    assert exc_info.value.error_code == "UNSUPPORTED_MEDIA_TYPE"


def test_file_validation_oversized_file():
    """Payload exceeding 10MB limit raises 413 FILE_TOO_LARGE."""
    oversized_data = JPEG_HEADER + b"\x00" * (10 * 1024 * 1024 + 1)
    with pytest.raises(BaseAPIException) as exc_info:
        FileValidationService.validate_and_inspect(
            file_bytes=oversized_data,
            original_filename="giant_image.jpg",
        )
    assert exc_info.value.status_code == 413
    assert exc_info.value.error_code == "FILE_TOO_LARGE"


class _FakeUploadStream:
    """Minimal async-read stream standing in for UploadFile in these unit tests."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk, self._pos = self._data[self._pos :], len(self._data)
        else:
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_read_upload_within_limit_rejects_oversized_stream_without_full_buffer():
    """
    The whole point of streaming the read is to never materialize a too-large
    upload in memory - verify it rejects (413) using a stream far bigger than
    the cap, read in small chunks so the running-total check is actually exercised.
    """
    cap = 1024
    oversized = b"x" * (cap * 50)
    stream = _FakeUploadStream(oversized)
    with pytest.raises(BaseAPIException) as exc_info:
        await FileValidationService.read_upload_within_limit(stream, max_bytes=cap, chunk_size=64)
    assert exc_info.value.status_code == 413
    assert exc_info.value.error_code == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_read_upload_within_limit_allows_payload_at_or_under_cap():
    cap = 1024
    exact = b"y" * cap
    under = b"z" * (cap - 1)
    assert await FileValidationService.read_upload_within_limit(_FakeUploadStream(exact), cap, chunk_size=64) == exact
    assert await FileValidationService.read_upload_within_limit(_FakeUploadStream(under), cap, chunk_size=64) == under


# ---------------------------------------------------------------------------
# Storage Provider Unit Tests (LocalStorageProvider)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_storage_crud_lifecycle():
    """Verify LocalStorageProvider upload, exists, download, and delete sequence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        provider = LocalStorageProvider(base_dir=tmp_dir)
        key = "visits/test-uuid/media_1.jpg"
        data = JPEG_HEADER

        # Upload
        saved_key = await provider.upload(data, key, "image/jpeg")
        assert saved_key == key

        # Exists
        assert await provider.exists(key) is True

        # Download
        content = await provider.download(key)
        assert content == data

        # Delete
        deleted = await provider.delete(key)
        assert deleted is True
        assert await provider.exists(key) is False


@pytest.mark.asyncio
async def test_local_storage_path_traversal_prevention():
    """Path traversal attempt in storage key raises 400 PATH_TRAVERSAL_DETECTED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        provider = LocalStorageProvider(base_dir=tmp_dir)
        with pytest.raises(BaseAPIException) as exc_info:
            await provider.download("../../../etc/passwd")
        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "PATH_TRAVERSAL_DETECTED"


# ---------------------------------------------------------------------------
# API Router Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_media_endpoints_unauthorized(client: AsyncClient):
    """Anonymous calls to media management endpoints return 401/403."""
    v_id = uuid.uuid4()
    m_id = uuid.uuid4()

    r1 = await client.get(f"/api/v1/visits/{v_id}/media")
    assert r1.status_code in (401, 403)

    r2 = await client.get(f"/api/v1/media/{m_id}")
    assert r2.status_code in (401, 403)

    r3 = await client.get(f"/api/v1/media/{m_id}/download")
    assert r3.status_code in (401, 403)

    r4 = await client.delete(f"/api/v1/media/{m_id}")
    assert r4.status_code in (401, 403)


@requires_db
@pytest.mark.asyncio
async def test_get_nonexistent_media_returns_404(client: AsyncClient):
    """Authenticated request for non-existent media returns 404."""
    m_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/media/{m_id}", headers=admin_headers())
    assert resp.status_code == 404
