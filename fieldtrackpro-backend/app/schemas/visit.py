"""
Visit request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.visit import VisitStatus
from app.schemas.customer import LocationIn


class VisitCreate(BaseModel):
    customer_id: uuid.UUID
    employee_id: uuid.UUID
    scheduled_at: datetime


class CheckInRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    accuracy_m: float | None = Field(default=None, ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Flag indicating if location source is fake/mock provider")
    idempotency_key: str | None = None


class CheckOutRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    accuracy_m: float | None = Field(default=None, ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Flag indicating if location source is fake/mock provider")


class VisitRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    employee_id: uuid.UUID
    scheduled_at: datetime
    status: VisitStatus
    check_in_at: datetime | None
    check_out_at: datetime | None
    synced: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VisitStatusUpdate(BaseModel):
    """Admin-only forced status override."""

    status: VisitStatus
    reason: str | None = None
