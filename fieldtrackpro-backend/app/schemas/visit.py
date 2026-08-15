"""
Visit request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.form_template import FormStatus
from app.models.visit import VisitStatus
from app.schemas.customer import LocationIn


class VisitCreate(BaseModel):
    customer_id: uuid.UUID
    employee_id: uuid.UUID
    scheduled_at: datetime
    # The form the employee must fill during this visit. Optional - not
    # every visit requires one. Must reference a PUBLISHED template
    # (enforced in visit_service) - a draft isn't ready for employees to
    # see, and an archived one is no longer meant for new work.
    required_form_id: uuid.UUID | None = None


class BulkVisitCreate(BaseModel):
    """Bulk create visits for multiple customers."""
    customer_ids: list[uuid.UUID]
    employee_id: uuid.UUID
    scheduled_at: datetime
    required_form_id: uuid.UUID | None = None


class VisitRequiredFormUpdate(BaseModel):
    """Admin: assign/change/clear the form required for an existing visit."""
    required_form_id: uuid.UUID | None = None


class CheckInRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    # P0-4: required, not optional. A real GPS fix always reports an accuracy;
    # making this mandatory closes the loophole where an omitted value let a
    # request skip GeoVerificationService's accuracy-threshold check entirely
    # rather than being evaluated by it. This does not by itself prove the
    # coordinates came from a sensor rather than a keyboard - the server
    # cannot verify that without a device-attestation mechanism, which is a
    # separate, larger decision (see the audit) - but it does close a real,
    # unconditional bypass of an existing check.
    accuracy_m: float = Field(..., ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Flag indicating if location source is fake/mock provider")
    # Required, not optional, for the same reason accuracy_m is required: an
    # omitted timestamp must not silently skip GeoVerificationService's
    # freshness check. This is when the DEVICE captured the fix, not when the
    # request reached the server - the two can differ by hours if the device
    # was offline and queued the attempt (see OfflineQueueManager).
    captured_at: datetime = Field(..., description="When the device captured this GPS fix")
    idempotency_key: str | None = None


class CheckOutRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    accuracy_m: float = Field(..., ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Flag indicating if location source is fake/mock provider")
    captured_at: datetime = Field(..., description="When the device captured this GPS fix")


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
    required_form_id: uuid.UUID | None = None
    # Denormalized so a visit list/detail view never needs a second round
    # trip just to show which form is required and whether it's still usable.
    required_form_name: str | None = None
    required_form_status: FormStatus | None = None

    model_config = {"from_attributes": True}


class VisitStatusUpdate(BaseModel):
    """Admin-only forced status override."""

    status: VisitStatus
    reason: str | None = None
