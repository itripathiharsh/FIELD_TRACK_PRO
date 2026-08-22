from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.field_exception import ExceptionType, ExceptionStatus


class FieldExceptionCreate(BaseModel):
    visit_id: Optional[uuid.UUID] = None
    customer_id: uuid.UUID
    exception_type: ExceptionType
    description: str = Field(min_length=3, max_length=2000)


class FieldExceptionReview(BaseModel):
    status: ExceptionStatus = Field(description="Must be APPROVED or REJECTED")
    admin_notes: Optional[str] = Field(default=None, max_length=2000)


class FieldExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    visit_id: Optional[uuid.UUID] = None
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    dms_code: Optional[str] = None
    exception_type: ExceptionType
    description: str
    status: ExceptionStatus
    admin_notes: Optional[str] = None
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
