"""
Media management schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.visit_media import MediaType


class MediaRead(BaseModel):
    """
    Visit media metadata.

    FT-036: exposes the content hash and the original filename so a client can
    display a real name and an auditor can confirm the stored bytes are the
    bytes that were uploaded.
    """

    id: uuid.UUID
    visit_id: uuid.UUID
    media_type: MediaType
    storage_key: str
    file_size_bytes: int
    checksum_sha256: str | None = None
    original_filename: str | None = None
    uploaded_by: uuid.UUID | None = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
