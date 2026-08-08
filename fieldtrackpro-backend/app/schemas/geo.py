"""
Geo verification schemas: standalone validation requests, responses, and audit logs.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationVerifyRequest(BaseModel):
    """Client payload to test coordinate proximity against a customer geofence."""

    customer_id: uuid.UUID
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    accuracy_m: float | None = Field(default=None, ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Flag indicating if location source is fake/mock provider")

    model_config = ConfigDict(from_attributes=True)


class LocationVerifyResponse(BaseModel):
    """Server decision payload for location verification."""

    is_valid: bool
    distance_m: float
    geofence_radius_m: float
    is_mock: bool
    accuracy_m: float | None = None
    failure_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GeoVerificationLogRead(BaseModel):
    """Immutable audit log entry schema."""

    id: uuid.UUID
    visit_id: uuid.UUID
    attempted_at: datetime
    distance_from_customer_m: float
    is_valid: bool
    failure_reason: str | None = None
    idempotency_key: str | None = None

    model_config = ConfigDict(from_attributes=True)
