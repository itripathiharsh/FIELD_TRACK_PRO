"""
Signature request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.visit_signature import SignatureType


class SignatureCreate(BaseModel):
    """Upload a signature for a visit."""
    signature_type: SignatureType
    signature_image_base64: str


class SignatureRead(BaseModel):
    """Signature metadata."""
    id: uuid.UUID
    visit_id: uuid.UUID
    signature_type: SignatureType
    storage_key: str
    signed_at: datetime

    model_config = ConfigDict(from_attributes=True)
