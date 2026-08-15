"""
P2-3 — Signature image validation coverage.

The P2-3 investigation confirmed `signature_service._decode_signature_image`
is a deliberately separate, narrower validator than
`FileValidationService` (1MB cap vs 10/20MB, PNG/JPEG-only vs a broader
image/document whitelist, hand-rolled magic-byte matching vs libmagic) and
must not be merged with it. It had no dedicated regression tests at all -
this file closes that gap without changing any production behavior.
"""
from __future__ import annotations

import base64

import pytest

from app.exceptions.custom import BaseAPIException
from app.services.signature_service import (
    MAX_SIGNATURE_SIZE_BYTES,
    _decode_signature_image,
)

PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
JPEG_HEADER = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_valid_png_signature_is_accepted():
    image_bytes, content_type = _decode_signature_image(_b64(PNG_HEADER))
    assert image_bytes == PNG_HEADER
    assert content_type == "image/png"


def test_valid_jpeg_signature_is_accepted():
    image_bytes, content_type = _decode_signature_image(_b64(JPEG_HEADER))
    assert image_bytes == JPEG_HEADER
    assert content_type == "image/jpeg"


def test_data_uri_prefix_is_stripped_before_decoding():
    data_uri = f"data:image/png;base64,{_b64(PNG_HEADER)}"
    image_bytes, content_type = _decode_signature_image(data_uri)
    assert image_bytes == PNG_HEADER
    assert content_type == "image/png"


def test_invalid_base64_is_rejected():
    with pytest.raises(BaseAPIException) as exc_info:
        _decode_signature_image("not-valid-base64!!!")
    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "INVALID_SIGNATURE_DATA"


def test_empty_decoded_image_is_rejected():
    with pytest.raises(BaseAPIException) as exc_info:
        _decode_signature_image(_b64(b""))
    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "INVALID_SIGNATURE_EMPTY"


def test_image_exactly_at_the_size_limit_is_accepted():
    # PNG header padded with trailing bytes up to exactly MAX_SIGNATURE_SIZE_BYTES.
    padded = PNG_HEADER + (b"\x00" * (MAX_SIGNATURE_SIZE_BYTES - len(PNG_HEADER)))
    image_bytes, content_type = _decode_signature_image(_b64(padded))
    assert len(image_bytes) == MAX_SIGNATURE_SIZE_BYTES
    assert content_type == "image/png"


def test_image_one_byte_over_the_size_limit_is_rejected():
    oversized = PNG_HEADER + (b"\x00" * (MAX_SIGNATURE_SIZE_BYTES - len(PNG_HEADER) + 1))
    with pytest.raises(BaseAPIException) as exc_info:
        _decode_signature_image(_b64(oversized))
    assert exc_info.value.status_code == 413
    assert exc_info.value.error_code == "SIGNATURE_TOO_LARGE"


def test_unsupported_image_type_is_rejected():
    gif_header = b"GIF89a\x00\x00\x00\x00"
    with pytest.raises(BaseAPIException) as exc_info:
        _decode_signature_image(_b64(gif_header))
    assert exc_info.value.status_code == 415
    assert exc_info.value.error_code == "UNSUPPORTED_SIGNATURE_TYPE"


def test_non_image_bytes_are_rejected():
    with pytest.raises(BaseAPIException) as exc_info:
        _decode_signature_image(_b64(b"just some random bytes, not an image"))
    assert exc_info.value.status_code == 415
    assert exc_info.value.error_code == "UNSUPPORTED_SIGNATURE_TYPE"
