"""
Territory request/response schemas with geographic center and radius validation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_TERRITORY_RADIUS_KM: int = 500


class TerritoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    center_latitude: float | None = None
    center_longitude: float | None = None
    # Whole kilometers only. Pydantic's int validator already rejects a
    # fractional float (e.g. 10.5) with a clear error - it only accepts a
    # float here when it has no fractional part (e.g. 10.0 -> 10).
    radius_km: int | None = None
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Territory name cannot be empty")
        return s

    @field_validator("center_latitude")
    @classmethod
    def validate_latitude(cls, v: float | None) -> float | None:
        if v is not None:
            if not (-90.0 <= v <= 90.0):
                raise ValueError("Latitude must be between -90 and 90 degrees")
        return v

    @field_validator("center_longitude")
    @classmethod
    def validate_longitude(cls, v: float | None) -> float | None:
        if v is not None:
            if not (-180.0 <= v <= 180.0):
                raise ValueError("Longitude must be between -180 and 180 degrees")
        return v

    @field_validator("radius_km")
    @classmethod
    def validate_radius(cls, v: int | None) -> int | None:
        if v is not None:
            if v <= 0:
                raise ValueError("Radius must be greater than 0 km")
            if v > MAX_TERRITORY_RADIUS_KM:
                raise ValueError(f"Radius cannot exceed {MAX_TERRITORY_RADIUS_KM} km")
        return v

    @model_validator(mode="after")
    def validate_coordinates_completeness(self) -> TerritoryCreate:
        lat, lon, r = self.center_latitude, self.center_longitude, self.radius_km
        has_any = (lat is not None) or (lon is not None) or (r is not None)
        if has_any:
            if lat is None or lon is None or r is None:
                raise ValueError("When configuring territory location, latitude, longitude, and radius_km must all be provided")
        return self


class TerritoryUpdate(BaseModel):
    name: str | None = None
    center_latitude: float | None = None
    center_longitude: float | None = None
    radius_km: int | None = None
    status: Literal["ACTIVE", "INACTIVE"] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Territory name cannot be empty")
            return s
        return v

    @field_validator("center_latitude")
    @classmethod
    def validate_latitude(cls, v: float | None) -> float | None:
        if v is not None:
            if not (-90.0 <= v <= 90.0):
                raise ValueError("Latitude must be between -90 and 90 degrees")
        return v

    @field_validator("center_longitude")
    @classmethod
    def validate_longitude(cls, v: float | None) -> float | None:
        if v is not None:
            if not (-180.0 <= v <= 180.0):
                raise ValueError("Longitude must be between -180 and 180 degrees")
        return v

    @field_validator("radius_km")
    @classmethod
    def validate_radius(cls, v: int | None) -> int | None:
        if v is not None:
            if v <= 0:
                raise ValueError("Radius must be greater than 0 km")
            if v > MAX_TERRITORY_RADIUS_KM:
                raise ValueError(f"Radius cannot exceed {MAX_TERRITORY_RADIUS_KM} km")
        return v


class TerritoryRead(BaseModel):
    id: uuid.UUID
    name: str
    center_latitude: float | None = None
    center_longitude: float | None = None
    radius_km: int | None = None
    status: str = "ACTIVE"
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
