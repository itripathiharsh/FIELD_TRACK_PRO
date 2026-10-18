from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.customer_prospect import ProspectStatus
from app.schemas.customer import CustomerRead, LocationOut
from app.validation import PHONE_MAX_LENGTH, PHONE_PATTERN


class ProspectRequirementPayload(BaseModel):
    """The optional initial requirement/order captured alongside a new outlet - held as-is
    until the prospect is approved, then turned into a real CustomerRequirement."""

    brand: str | None = Field(default=None, max_length=100)
    requirement_type: str | None = Field(default=None, max_length=100)
    product_details: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    expected_value: float | None = Field(default=None, ge=0.0)
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class CustomerProspectUpdate(BaseModel):
    """Admin edits before approving - every field optional, only what's sent is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_number: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH, pattern=PHONE_PATTERN)
    contact_person: str | None = Field(default=None, max_length=150)
    gst_number: str | None = Field(default=None, max_length=20)
    address: str | None = None
    outlet_code: str | None = Field(default=None, max_length=50)
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    brands: list[str] | None = None
    requirement: ProspectRequirementPayload | None = None
    proposed_latitude: float | None = None
    proposed_longitude: float | None = None

    @field_validator("gst_number", "outlet_code")
    @classmethod
    def normalize_upper(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip().upper()
            return stripped if stripped else None
        return v


class CustomerProspectRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class CustomerProspectSubmitResponse(BaseModel):
    """
    Response for POST /customers/prospect. An ADMIN caller still gets the outlet created
    immediately (status=CREATED, customer populated). An EMPLOYEE caller's submission is
    held for review instead (status=PENDING_APPROVAL, prospect_id populated, customer is
    null) - it will not appear anywhere as a live outlet until an admin approves it.
    """

    status: Literal["CREATED", "PENDING_APPROVAL"]
    message: str
    customer: CustomerRead | None = None
    prospect_id: uuid.UUID | None = None


class CustomerProspectRead(BaseModel):
    id: uuid.UUID
    status: ProspectStatus
    name: str
    contact_number: str
    contact_person: str | None = None
    gst_number: str | None = None
    address: str
    outlet_code: str | None = None
    territory_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    territory_name: str | None = None
    area_name: str | None = None
    brands: list[str] = []
    requirement: ProspectRequirementPayload | None = None
    location: LocationOut | None = None
    gps_accuracy_meters: float | None = None
    location_notes: str | None = None
    submitted_by: uuid.UUID
    submitted_by_name: str | None = None
    submitted_at: datetime
    reviewed_by: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    resulting_customer_id: uuid.UUID | None = None
    # Linked live outlet proof (photo + GPS captured together). Filled by the router
    # via attach_outlet_proofs(); None when no proof is attached (legacy prospects).
    outlet_proof_id: uuid.UUID | None = None
    outlet_proof_accuracy_m: float | None = None
    outlet_proof_captured_at: datetime | None = None

    @classmethod
    def from_model(cls, prospect) -> "CustomerProspectRead":
        d = getattr(prospect, "__dict__", {})
        territory = d.get("territory")
        area = d.get("area")
        submitter_employee = d.get("submitter_employee")
        submitter = d.get("submitter_user")
        submitter_name = getattr(submitter_employee, "full_name", None) or getattr(submitter, "email", None)
        reviewer = d.get("reviewer_user")
        location = None
        if prospect.proposed_latitude is not None and prospect.proposed_longitude is not None:
            location = LocationOut(latitude=prospect.proposed_latitude, longitude=prospect.proposed_longitude)
        requirement = None
        if prospect.requirement_payload:
            requirement = ProspectRequirementPayload(**prospect.requirement_payload)
        return cls(
            id=prospect.id,
            status=prospect.status,
            name=prospect.name,
            contact_number=prospect.contact_number or "",
            contact_person=prospect.contact_person,
            gst_number=prospect.gst_number,
            address=prospect.address or "",
            outlet_code=prospect.outlet_code,
            territory_id=prospect.territory_id,
            area_id=prospect.area_id,
            territory_name=getattr(territory, "name", None),
            area_name=getattr(area, "name", None),
            brands=list(prospect.brand_names or []),
            requirement=requirement,
            location=location,
            gps_accuracy_meters=prospect.gps_accuracy_meters,
            location_notes=prospect.location_notes,
            submitted_by=prospect.submitted_by,
            submitted_by_name=submitter_name,
            submitted_at=prospect.submitted_at,
            reviewed_by=prospect.reviewed_by,
            reviewed_by_name=getattr(reviewer, "email", None),
            reviewed_at=prospect.reviewed_at,
            rejection_reason=prospect.rejection_reason,
            resulting_customer_id=prospect.resulting_customer_id,
        )
