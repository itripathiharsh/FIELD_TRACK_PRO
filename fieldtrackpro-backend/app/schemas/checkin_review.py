from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class VerificationRequestCreate(BaseModel):
    visit_id: uuid.UUID
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: float = Field(..., ge=0.0)
    is_mock_location: bool = False
    captured_at: datetime
    note: str | None = Field(default=None, max_length=500)


class CheckInReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    visit_id: uuid.UUID
    customer_id: uuid.UUID
    employee_id: uuid.UUID | None = None
    kind: str
    status: str
    decision: str | None = None
    distance_m: Decimal | None = None
    accuracy_m: Decimal | None = None
    pin_accuracy_m: Decimal | None = None
    device_captured_at: datetime | None = None
    received_at: datetime
    note: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    # filled by the router for the admin queue
    customer_name: str | None = None
    employee_name: str | None = None


class CheckInReviewApprove(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class CheckInReviewReject(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)
