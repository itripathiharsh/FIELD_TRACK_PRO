"""
Notification request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationCreate(BaseModel):
    """Create a notification."""
    user_id: uuid.UUID
    type: str
    message: str
    visit_id: uuid.UUID | None = None


class NotificationRead(BaseModel):
    """Notification response."""
    id: uuid.UUID
    user_id: uuid.UUID
    visit_id: uuid.UUID | None
    type: str
    message: str
    is_read: bool
    sent_at: datetime

    model_config = {"from_attributes": True}
