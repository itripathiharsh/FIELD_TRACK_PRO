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
    note: str | None = None
    uploaded_by: uuid.UUID | None = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderRead(MediaRead):
    """
    A MediaRead of media_type=ORDER, enriched with display-only visit/employee
    context - mirrors payment_service.to_payment_read_for_queue's pattern of
    leaving these null on the base read and filling them only for the
    cross-visit outlet history view that actually renders them.
    """

    visit_scheduled_at: datetime | None = None
    employee_name: str | None = None
