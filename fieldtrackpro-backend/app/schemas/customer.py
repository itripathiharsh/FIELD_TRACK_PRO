"""
Customer request/response schemas.
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.customer_requirement import CustomerRequirementCreate, CustomerRequirementRead
from app.validation import PHONE_PATTERN, PHONE_MAX_LENGTH

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.customer import Customer as CustomerModel


class LocationIn(BaseModel):
    """GeoJSON-like lat/lng input. (0,0) is valid coordinates."""

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
    contact_number: str = Field(
        min_length=1,
        max_length=PHONE_MAX_LENGTH,
        pattern=PHONE_PATTERN,
    )
    contact_person: str | None = Field(default=None, max_length=150)
    gst_number: str | None = Field(default=None, max_length=20)
    address: str = Field(default="")
    location: LocationIn | None = None
    auto_geocode: bool = Field(default=False)
    geofence_radius_m: int = Field(default=75, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    outlet_code: str | None = Field(default=None, max_length=50)
    location_status: str | None = Field(default="MISSING")
    brands: list[str] = Field(default_factory=list)

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str | None) -> str:
        if v is not None:
            stripped = v.strip()
            if v != "" and not stripped:
                raise ValueError("Address cannot be empty or whitespace only")
            return stripped
        return ""

    @field_validator("outlet_code")
    @classmethod
    def normalize_outlet_code(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return None

    @field_validator("gst_number")
    @classmethod
    def normalize_gst_number(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return None

    @model_validator(mode="after")
    def validate_location_presence(self) -> "CustomerCreate":
        if self.location is None and not self.auto_geocode and not self.outlet_code:
            raise ValueError("location is required unless auto_geocode is true or outlet_code is provided")
        return self


class CustomerProspectCreate(BaseModel):
    """Payload submitted by field employee to onboard a new customer/outlet with brands & requirement."""
    name: str = Field(min_length=1, max_length=150)
    contact_number: str = Field(
        min_length=1,
        max_length=PHONE_MAX_LENGTH,
        pattern=PHONE_PATTERN,
    )
    contact_person: str | None = Field(default=None, max_length=150)
    gst_number: str | None = Field(default=None, max_length=20)
    address: str = Field(default="")
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    outlet_code: str | None = Field(default=None, max_length=50)
    brands: list[str] = Field(default_factory=list)
    requirement: Optional["CustomerRequirementCreate"] = None
    location: LocationIn | None = None
    gps_accuracy_meters: float | None = None
    notes: str | None = Field(default=None, max_length=1000)
    force: bool = Field(default=False, description="Set to true to bypass duplicate warnings if confirmed")
    # Live outlet proof (POST /customers/outlet-proofs with no customer_id). When attached, the
    # proposed location/accuracy are taken FROM THE PROOF and client-supplied location is ignored.
    outlet_proof_id: uuid.UUID | None = None

    @field_validator("gst_number")
    @classmethod
    def normalize_gst(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_number: str | None = Field(
        default=None,
        max_length=PHONE_MAX_LENGTH,
        pattern=PHONE_PATTERN,
    )
    contact_person: str | None = Field(default=None, max_length=150)
    gst_number: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None)
    location: LocationIn | None = None
    auto_geocode: bool = Field(default=False)
    geofence_radius_m: int | None = Field(default=None, gt=0, le=100_000)
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    outlet_code: str | None = Field(default=None, max_length=50)
    location_status: str | None = Field(default=None)
    brands: list[str] | None = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Address cannot be empty or whitespace only")
            return stripped
        return v

    @field_validator("outlet_code")
    @classmethod
    def normalize_outlet_code(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return None

    @field_validator("gst_number")
    @classmethod
    def normalize_gst(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return None


class CustomerMapLocation(BaseModel):
    """Lightweight map pin projection."""
    id: uuid.UUID
    name: str
    outlet_code: str | None = None
    address: str | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    latitude: float
    longitude: float
    geofence_radius_m: int = 75
    location_status: str = "VERIFIED"
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None



class LedgerRead(BaseModel):
    """One Tally ledger linked to a physical outlet (balances in receivable sign: + = owed)."""

    id: uuid.UUID
    tally_guid: str
    name: str
    parent_group: str | None = None
    tally_outlet_code: str | None = None
    brand: str | None = None
    brand_source: str = "NONE"  # TALLY | OVERRIDE | NONE
    is_primary: bool = False
    is_debtor: bool | None = None
    mapping_status: str = "AUTO_1TO1"
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    closing_balance_at: datetime | None = None
    gst_number: str | None = None
    mobile: str | None = None
    pincode: str | None = None

    @classmethod
    def from_model(cls, l) -> "LedgerRead":
        return cls(
            id=l.id, tally_guid=l.tally_guid, name=l.name, parent_group=l.parent_group,
            tally_outlet_code=l.tally_outlet_code, brand=l.effective_brand, brand_source=l.brand_source,
            is_primary=bool(l.is_primary), is_debtor=l.is_debtor, mapping_status=l.mapping_status,
            opening_balance=None if l.opening_balance is None else -l.opening_balance,
            closing_balance=None if l.closing_balance is None else -l.closing_balance,
            closing_balance_at=l.closing_balance_at, gst_number=l.gst_number, mobile=l.mobile, pincode=l.pincode,
        )


class CustomerRead(BaseModel):
    """
    Customer projection returned by the API.
    """

    id: uuid.UUID
    name: str
    contact_number: str
    contact_person: str | None = None
    gst_number: str | None = None
    address: str
    location: LocationOut | None = None
    geofence_radius_m: int
    location_status: str = "MISSING"
    territory_id: uuid.UUID | None
    area_id: uuid.UUID | None = None
    area_name: str | None = None
    territory_name: str | None = None
    outlet_code: str | None = None
    dms_code: str | None = None
    assigned_fos_names: list[str] = []
    brands: list[str] = []
    created_by: uuid.UUID
    created_at: datetime
    needs_tally_entry: bool = False
    # Release 2.1.0 (additive): the outlet is a physical shop; its Tally ledgers.
    ledger_count: int = 0
    tally_codes: list[str] = []
    merged_into_customer_id: uuid.UUID | None = None
    ledgers: list[LedgerRead] = []
    # --- live outlet proof (additive; filled by outlet_proof_service.enrich_customer_reads) ---
    primary_outlet_image_available: bool = False
    primary_outlet_proof_id: uuid.UUID | None = None  # stream via GET /customers/outlet-proofs/{id}/image
    outlet_proof_count: int = 0
    outlet_location_confirmations: int = 0

    @classmethod
    def from_model(cls, customer: "CustomerModel") -> "CustomerRead":
        """Build the response, decoding the stored PostGIS point."""
        from app.services.customer_service import extract_coords

        location_out: LocationOut | None = None
        if customer.location is not None:
            latitude, longitude = extract_coords(customer.location)
            # WEB-CUST-017: (0,0) is valid geographic coordinates; only NULL is missing
            location_out = LocationOut(latitude=latitude, longitude=longitude)

        cust_dict = getattr(customer, "__dict__", {})
        area_obj = cust_dict.get("area")
        area_name = area_obj.name if area_obj is not None else None

        terr_obj = cust_dict.get("territory")
        territory_name = terr_obj.name if terr_obj is not None else None
        
        fos_names = []
        assignments = cust_dict.get("employee_assignments")
        if assignments:
            for assignment in assignments:
                assign_dict = getattr(assignment, "__dict__", {})
                emp = assign_dict.get("employee")
                if emp and getattr(emp, "full_name", None):
                    fos_names.append(emp.full_name)

        brand_names = []
        brand_objs = cust_dict.get("brands")
        if brand_objs:
            for b in brand_objs:
                if getattr(b, "is_active", True) and getattr(b, "brand", None):
                    brand_names.append(b.brand)

        return cls(
            id=customer.id,
            name=customer.name,
            contact_number=customer.contact_number or "",
            contact_person=customer.contact_person,
            gst_number=getattr(customer, "gst_number", None),
            address=customer.address or "",
            location=location_out,
            geofence_radius_m=customer.geofence_radius_m or 75,
            location_status=getattr(customer, "location_status", "MISSING") or "MISSING",
            territory_id=customer.territory_id,
            area_id=customer.area_id,
            area_name=area_name,
            territory_name=territory_name,
            outlet_code=customer.outlet_code,
            dms_code=customer.outlet_code,
            assigned_fos_names=fos_names,
            brands=brand_names,
            created_by=customer.created_by,
            created_at=customer.created_at,
            needs_tally_entry=getattr(customer, "needs_tally_entry", False) or False,
            merged_into_customer_id=getattr(customer, "merged_into_customer_id", None),
        )


CustomerProspectCreate.model_rebuild()
