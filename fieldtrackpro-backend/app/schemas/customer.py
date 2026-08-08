"""
Customer request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class LocationIn(BaseModel):
    """GeoJSON-like lat/lng input."""

    latitude: float
    longitude: float

    @model_validator(mode="after")
    def validate_coords(self) -> "LocationIn":
        if not (-90 <= self.latitude <= 90):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180 <= self.longitude <= 180):
            raise ValueError("longitude must be between -180 and 180")
        return self

    def to_wkt(self) -> str:
        return f"POINT({self.longitude} {self.latitude})"


class LocationOut(BaseModel):
    latitude: float
    longitude: float


class CustomerCreate(BaseModel):
    name: str
    contact_number: str
    address: str
    location: LocationIn
    geofence_radius_m: int = 75
    territory_id: uuid.UUID | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    contact_number: str | None = None
    address: str | None = None
    location: LocationIn | None = None
    geofence_radius_m: int | None = None
    territory_id: uuid.UUID | None = None


class CustomerRead(BaseModel):
    id: uuid.UUID
    name: str
    contact_number: str
    address: str
    geofence_radius_m: int
    territory_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
