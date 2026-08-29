"""
Geographic request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field

from app.models.geo_verification_log import GeoVerificationType

if TYPE_CHECKING:
    from app.models.geo_verification_log import (
        GeoVerificationLog as GeoVerificationLogModel,
    )


class LocationVerifyRequest(BaseModel):
    customer_id: uuid.UUID
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Device latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Device longitude")
    accuracy_m: float = Field(..., ge=0.0, description="GPS horizontal accuracy in meters")
    is_mock_location: bool = Field(default=False, description="Mock provider flag")


class LocationVerifyResponse(BaseModel):
    is_valid: bool
    distance_m: float
    geofence_radius_m: float
    is_mock: bool
    accuracy_m: float | None = None
    failure_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GeoVerificationLogRead(BaseModel):
    """
    Immutable audit log entry.
    """

    id: uuid.UUID
    visit_id: uuid.UUID
    verification_type: GeoVerificationType
    attempted_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    distance_from_customer_m: float
    is_valid: bool
    failure_reason: str | None = None
    idempotency_key: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, log: "GeoVerificationLogModel") -> "GeoVerificationLogRead":
        """Build the response, decoding the stored PostGIS point."""
        from app.services.customer_service import extract_coords

        try:
            latitude, longitude = extract_coords(log.device_location)
        except ValueError:
            latitude, longitude = None, None

        return cls(
            id=log.id,
            visit_id=log.visit_id,
            verification_type=log.verification_type,
            attempted_at=log.attempted_at,
            latitude=latitude,
            longitude=longitude,
            distance_from_customer_m=float(log.distance_from_customer_m),
            is_valid=log.is_valid,
            failure_reason=log.failure_reason,
            idempotency_key=log.idempotency_key,
        )


class GeoLogWithContextRead(GeoVerificationLogRead):
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    employee_id: uuid.UUID | None = None
    employee_name: str | None = None
