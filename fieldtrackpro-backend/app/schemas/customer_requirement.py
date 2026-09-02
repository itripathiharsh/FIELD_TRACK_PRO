from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class CustomerRequirementCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    brand: Optional[str] = Field(default=None, max_length=100)
    requirement_type: Optional[str] = Field(default=None, max_length=100, description="e.g. Bulk Order, Dealership, Stock Replenishment")
    product_details: Optional[str] = Field(default=None, description="e.g. 25 Ceiling Fans, Smart TVs")
    quantity: Optional[int] = Field(default=None, ge=1)
    expected_value: Optional[float] = Field(default=None, ge=0.0)
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None


class CustomerRequirementUpdate(BaseModel):
    brand: Optional[str] = Field(default=None, max_length=100)
    requirement_type: Optional[str] = Field(default=None, max_length=100)
    product_details: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    expected_value: Optional[float] = Field(default=None, ge=0.0)
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=50)


class CustomerRequirementRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    outlet_code: Optional[str] = None
    brand: Optional[str] = None
    requirement_type: Optional[str] = None
    product_details: Optional[str] = None
    quantity: Optional[int] = None
    expected_value: Optional[float] = None
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    status: str = "OPEN"
    created_by: uuid.UUID
    creator_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
