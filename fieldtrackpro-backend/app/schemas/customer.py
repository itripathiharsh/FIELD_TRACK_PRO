"""
Customer request/response schemas.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator, model_validator

from app.validation import PHONE_PATTERN, PHONE_MAX_LENGTH

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
    # Phone validation: only digits, +, -, spaces, parentheses allowed.
    contact_number: str = Field(
        min_length=1,
        max_length=PHONE_MAX_LENGTH,
        pattern=PHONE_PATTERN,
    )
    contact_person: str | None = Field(default=None, max_length=150)
    address: str = Field(min_length=1)
    location: LocationIn | None = None
    auto_geocode: bool = Field(default=False)
    geofence_radius_m: int = Field(default=75, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None
    # Zone -> Area -> Outlet. If set, the service derives/validates
    # territory_id FROM the area rather than trusting a separately-supplied
    # value, so an outlet's Zone and Area can never disagree (see
    # customer_service.py) - Area is the source of truth once assigned.
    area_id: uuid.UUID | None = None
    # External-system cross-reference (Tally ledger code, Excel/MIS import
    # key) - never the outlet name, to avoid similar-name mismatches.
    outlet_code: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_location_or_geocode(self) -> "CustomerCreate":
        """Ensure either location is provided or auto_geocode is enabled with an address."""
        if self.location is None and not self.auto_geocode:
            raise ValueError(
                "Either 'location' must be provided or 'auto_geocode' must be True "
                "to derive coordinates from the address"
            )
        return self


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=PHONE_MAX_LENGTH,
        pattern=PHONE_PATTERN,
    )
    contact_person: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, min_length=1)
    location: LocationIn | None = None
    auto_geocode: bool = Field(default=False)
    geofence_radius_m: int | None = Field(default=None, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    outlet_code: str | None = Field(default=None, max_length=50)


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
    area_id: uuid.UUID | None = None
    # Denormalized for display (same convention as PaymentRead.territory_name
    # etc.) - avoids a second round trip just to show an outlet's Area name.
    area_name: str | None = None
    outlet_code: str | None = None
    created_by: uuid.UUID
    created_at: datetime

    @classmethod
    def from_model(cls, customer: "CustomerModel") -> "CustomerRead":
        """Build the response, decoding the stored PostGIS point."""
        from app.services.customer_service import extract_coords

        latitude, longitude = extract_coords(customer.location)
        # Safe: Customer.area is lazy="joined", always eagerly loaded.
        area_name = customer.area.name if customer.area is not None else None
        return cls(
            id=customer.id,
            name=customer.name,
            contact_number=customer.contact_number,
            contact_person=customer.contact_person,
            address=customer.address,
            location=LocationOut(latitude=latitude, longitude=longitude),
            geofence_radius_m=customer.geofence_radius_m,
            territory_id=customer.territory_id,
            area_id=customer.area_id,
            area_name=area_name,
            outlet_code=customer.outlet_code,
            created_by=customer.created_by,
            created_at=customer.created_at,
        )
