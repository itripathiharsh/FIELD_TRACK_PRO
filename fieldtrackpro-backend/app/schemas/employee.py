"""
Employee request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserSummary


class EmployeeCreate(BaseModel):
    """Create an employee profile linked to an existing user."""

    user_id: uuid.UUID
    full_name: str
    territory_id: uuid.UUID | None = None
    employee_code: str | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    territory_id: uuid.UUID | None = None
    employee_code: str | None = None


class EmployeeRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    territory_id: uuid.UUID | None
    employee_code: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EmployeeReadWithUser(EmployeeRead):
    user: UserSummary
