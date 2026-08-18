"""
Area schemas - the geographic layer between a Zone (Territory) and an Outlet
(Customer). See app/models/area.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AreaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    territory_id: uuid.UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Area name cannot be empty")
        return s


class AreaUpdate(BaseModel):
    name: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Area name cannot be empty")
            return s
        return v


class AreaRead(BaseModel):
    id: uuid.UUID
    name: str
    territory_id: uuid.UUID
    # Denormalized for display, avoiding an extra lookup on every list/detail
    # page that shows an outlet's Zone alongside its Area - same convention
    # already used by PaymentRead.territory_name etc.
    territory_name: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
