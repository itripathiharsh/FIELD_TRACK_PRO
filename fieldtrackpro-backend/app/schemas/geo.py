"""
Geo verification schemas: standalone validation requests, responses, and audit logs.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.models.geo_verification_log import GeoVerificationType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.geo_verification_log import (
        GeoVerificationLog as GeoVerificationLogModel,
    )


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
    """
    Immutable audit log entry.

    FT-031: `verification_type` distinguishes a check-in attempt from a
    check-out attempt. The device coordinates are exposed so an administrator
    reviewing a flagged visit can see where the attempt was actually made -
    which is the entire point of the Flagged Visit Review screen.
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
            # A log row with an undecodable position is still a real audit
            # record; report it without coordinates rather than failing the
            # whole request.
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
