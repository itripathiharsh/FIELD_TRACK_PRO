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
    CONVERT_TO_ORDER = "CONVERT_TO_ORDER"


class RequirementItemCreate(BaseModel):
    brand_id: Optional[uuid.UUID] = None
    brand_name: str = Field(..., max_length=100)
    product_model: str = Field(..., max_length=200)
    requested_quantity: int = Field(default=1, ge=1)
    expected_rate: float = Field(default=0.0, ge=0.0)
    requested_amount: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None


class RequirementItemRead(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    brand_id: Optional[uuid.UUID] = None
    brand_name: str
    product_model: str
    requested_quantity: int
    expected_rate: float
    requested_amount: float
    approved_quantity: Optional[int] = None
    approved_rate: Optional[float] = None
    approved_amount: Optional[float] = None
    tally_stock_item_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequirementItemDecisionUpdate(BaseModel):
    id: uuid.UUID
    approved_quantity: Optional[int] = Field(default=None, ge=0)
    approved_rate: Optional[float] = Field(default=None, ge=0.0)
    tally_stock_item_name: Optional[str] = None
    notes: Optional[str] = None


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
    # Multi-item list
    items: Optional[list[RequirementItemCreate]] = None


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
    approved_quantity: Optional[int] = Field(default=None, ge=0)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None
    items: Optional[list[RequirementItemDecisionUpdate]] = None


class RequirementApproveRequest(BaseModel):
    approved_quantity: Optional[int] = Field(default=None, ge=1)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None
    items: Optional[list[RequirementItemDecisionUpdate]] = None


class RequirementPartiallyApproveRequest(BaseModel):
    approved_quantity: Optional[int] = Field(default=None, ge=0)
    approved_value: Optional[float] = Field(default=None, ge=0.0)
    admin_notes: Optional[str] = None
    items: Optional[list[RequirementItemDecisionUpdate]] = None


class RequirementRejectRequest(BaseModel):
    admin_notes: Optional[str] = None


class RequirementConfirmOrderRequest(BaseModel):
    admin_notes: Optional[str] = None
    items: Optional[list[RequirementItemDecisionUpdate]] = None


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
    
    # Aggregated totals
    total_requested_value: Optional[float] = None
    total_approved_value: Optional[float] = None

    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    photo_storage_key: Optional[str] = None
    photo_media_id: Optional[uuid.UUID] = None
    photo_url: Optional[str] = None

    # Admin Decision
    # Status: NEW, PENDING, UNDER_REVIEW, APPROVED, PARTIALLY_APPROVED, REJECTED, CONVERTED_TO_ORDER
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

    # Multi-item line items
    items: list[RequirementItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OrderItemRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    brand_name: str
    product_model: str
    stock_item_name: str
    quantity: int
    unit: str = "PCS"
    rate: float
    amount: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderRead(BaseModel):
    id: uuid.UUID
    order_number: str
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    outlet_code: Optional[str] = None
    requirement_id: Optional[uuid.UUID] = None
    visit_id: Optional[uuid.UUID] = None
    employee_id: Optional[uuid.UUID] = None
    employee_name: Optional[str] = None
    total_amount: float
    status: str = "PENDING_TALLY"
    tally_guid: Optional[str] = None
    tally_master_id: Optional[str] = None
    tally_voucher_number: Optional[str] = None
    admin_notes: Optional[str] = None
    created_by: uuid.UUID
    creator_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
