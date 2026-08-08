"""
Customer request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.customer import Customer as CustomerModel


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
    name: str = Field(min_length=1, max_length=150)
    # FT-013: bounded to the column width so an over-long value is a 422 with a
    # clear message, not a database error surfaced as 500.
    contact_number: str = Field(min_length=1, max_length=20)
    contact_person: str | None = Field(default=None, max_length=150)
    address: str = Field(min_length=1)
    location: LocationIn
    geofence_radius_m: int = Field(default=75, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_number: str | None = Field(default=None, min_length=1, max_length=20)
    contact_person: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, min_length=1)
    location: LocationIn | None = None
    geofence_radius_m: int | None = Field(default=None, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None


class CustomerRead(BaseModel):
    """
    Customer projection returned by the API.

    FT-012: `location` carries the geofence centre. It was previously omitted
    entirely, so the admin "GPS & Geofence" column was permanently blank and no
    client could show or verify where a customer actually is.
    """

    id: uuid.UUID
    name: str
    contact_number: str
    contact_person: str | None = None
    address: str
    location: LocationOut
    geofence_radius_m: int
    territory_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime

    @classmethod
    def from_model(cls, customer: "CustomerModel") -> "CustomerRead":
        """Build the response, decoding the stored PostGIS point."""
        from app.services.customer_service import extract_coords

        latitude, longitude = extract_coords(customer.location)
        return cls(
            id=customer.id,
            name=customer.name,
            contact_number=customer.contact_number,
            contact_person=customer.contact_person,
            address=customer.address,
            location=LocationOut(latitude=latitude, longitude=longitude),
            geofence_radius_m=customer.geofence_radius_m,
            territory_id=customer.territory_id,
            created_by=customer.created_by,
            created_at=customer.created_at,
        )
