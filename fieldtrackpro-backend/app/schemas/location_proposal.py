from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.customer_location_proposal import LocationProposalStatus


class LocationProposalCreate(BaseModel):
    proposed_latitude: float = Field(..., ge=-90.0, le=90.0, description="Proposed latitude coordinate")
    proposed_longitude: float = Field(..., ge=-180.0, le=180.0, description="Proposed longitude coordinate")
    gps_accuracy_meters: Optional[float] = Field(default=None, ge=0.0, description="Reported GPS fix accuracy in meters")
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional employee notes / explanation")

    @model_validator(mode="after")
    def validate_coordinates(self) -> "LocationProposalCreate":
        if not (-90 <= self.proposed_latitude <= 90):
            raise ValueError("proposed_latitude must be between -90 and 90")
        if not (-180 <= self.proposed_longitude <= 180):
            raise ValueError("proposed_longitude must be between -180 and 180")
        return self


class LocationProposalReview(BaseModel):
    rejection_reason: Optional[str] = Field(default=None, max_length=255, description="Reason for rejection (required if rejecting)")


class LocationProposalRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    customer_outlet_code: Optional[str] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    proposed_latitude: float
    proposed_longitude: float
    gps_accuracy_meters: Optional[float] = None
    distance_meters: Optional[float] = None
    submitted_by: uuid.UUID
    submitter_name: Optional[str] = None
    submitted_by_employee_id: Optional[uuid.UUID] = None
    submitted_at: datetime
    status: LocationProposalStatus
    reviewed_by: Optional[uuid.UUID] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
