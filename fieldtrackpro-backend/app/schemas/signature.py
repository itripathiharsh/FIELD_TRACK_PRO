"""
Signature request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.visit_signature import SignatureCaptureMethod, SignatureType


class SignatureCreate(BaseModel):
    """Upload a signature/acknowledgement for a visit."""
    signature_type: SignatureType
    signature_image_base64: str
    capture_method: SignatureCaptureMethod = SignatureCaptureMethod.SIGNATURE


class SignatureReplaceRequest(BaseModel):
    """Replace an existing (not yet superseded) signature/acknowledgement with a corrected capture."""
    signature_image_base64: str
    capture_method: SignatureCaptureMethod = SignatureCaptureMethod.SIGNATURE


class SignatureRead(BaseModel):
    """Signature metadata."""
    id: uuid.UUID
    visit_id: uuid.UUID
    signature_type: SignatureType
    capture_method: SignatureCaptureMethod
    storage_key: str
    content_type: str | None = None
    file_size_bytes: int | None = None
    created_by: uuid.UUID | None = None
    signed_at: datetime
    superseded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
