from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RequirementDecisionAction(str, enum.Enum):
    APPROVE = "APPROVE"
    PARTIALLY_APPROVE = "PARTIALLY_APPROVE"
    REJECT = "REJECT"


class CustomerRequirementCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    visit_id: Optional[uuid.UUID] = None
    brand: Optional[str] = Field(default=None, max_length=100)
    requirement_type: Optional[str] = Field(
        default=None,
        max_length=100,
        description="e.g. Bulk Order, Dealership, Stock Replenishment",
    )
    product_details: Optional[str] = Field(default=None, description="e.g. 25 Ceiling Fans, Smart TVs")
    quantity: Optional[int] = Field(default=None, ge=1)
    expected_value: Optional[float] = Field(default=None, ge=0.0)
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    photo_media_id: Optional[uuid.UUID] = None


class CustomerRequirementUpdate(BaseModel):
    brand: Optional[str] = Field(default=None, max_length=100)
    requirement_type: Optional[str] = Field(default=None, max_length=100)
    product_details: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    expected_value: Optional[float] = Field(default=None, ge=0.0)
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=50)


class RequirementDecisionRequest(BaseModel):
    action: RequirementDecisionAction
    approved_quantity: Optional[int] = Field(default=None, ge=1)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None


class RequirementApproveRequest(BaseModel):
    approved_quantity: Optional[int] = Field(default=None, ge=1)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None


class RequirementPartiallyApproveRequest(BaseModel):
    approved_quantity: Optional[int] = Field(default=None, ge=1)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None


class RequirementRejectRequest(BaseModel):
    admin_notes: Optional[str] = None


class CustomerRequirementRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    outlet_code: Optional[str] = None
    visit_id: Optional[uuid.UUID] = None
    visit_date: Optional[date] = None
    brand: Optional[str] = None
    requirement_type: Optional[str] = None
    product_details: Optional[str] = None
    quantity: Optional[int] = None
    expected_value: Optional[float] = None
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    photo_storage_key: Optional[str] = None
    photo_media_id: Optional[uuid.UUID] = None
    photo_url: Optional[str] = None

    # Admin Decision
    status: str = "PENDING"
    approved_quantity: Optional[int] = None
    approved_value: Optional[float] = None
    admin_notes: Optional[str] = None
    decided_by: Optional[uuid.UUID] = None
    decider_name: Optional[str] = None
    decided_at: Optional[datetime] = None

    created_by: uuid.UUID
    creator_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
