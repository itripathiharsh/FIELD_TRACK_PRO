"""
Employee request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserCreate, UserSummary


class EmployeeRegistration(BaseModel):
    """Create a user account and an employee profile together in one transaction."""

    user: UserCreate
    full_name: str
    territory_id: uuid.UUID | None = None
    employee_code: str | None = None
    working_profile: str | None = None
    cug: str | None = None
    date_of_birth: date | None = None
    address: str | None = None


class EmployeeCreate(BaseModel):
    """Create an employee profile linked to an existing user."""

    user_id: uuid.UUID
    full_name: str
    territory_id: uuid.UUID | None = None
    employee_code: str | None = None
    working_profile: str | None = None
    cug: str | None = None
    date_of_birth: date | None = None
    address: str | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    mobile_number: str | None = None
    territory_id: uuid.UUID | None = None
    employee_code: str | None = None
    working_profile: str | None = None
    cug: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    must_change_password: bool | None = None


class EmployeeRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    territory_id: uuid.UUID | None
    employee_code: str | None
    working_profile: str | None = None
    cug: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    must_change_password: bool = False
    assigned_outlets_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeReadWithUser(EmployeeRead):
    user: UserSummary


class OnboardingCredentialRow(BaseModel):
    employee_name: str
    employee_id: str
    email: str
    mobile_number: Optional[str] = None
    temporary_password: str
    application_role: str
    working_profile: Optional[str] = None
    cug: Optional[str] = None
