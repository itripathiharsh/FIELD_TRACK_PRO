"""
Media management schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.visit_media import MediaType


class MediaRead(BaseModel):
    """Schema for visit media item metadata response."""

    id: uuid.UUID
    visit_id: uuid.UUID
    media_type: MediaType
    storage_key: str
    file_size_bytes: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
