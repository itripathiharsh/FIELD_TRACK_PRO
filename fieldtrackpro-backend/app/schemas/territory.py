"""
Territory request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TerritoryCreate(BaseModel):
    name: str


class TerritoryUpdate(BaseModel):
    name: str | None = None


class TerritoryRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}
