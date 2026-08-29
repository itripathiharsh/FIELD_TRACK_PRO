"""
Employee request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserCreate, UserSummary


def _validate_full_name(v: str | None) -> str | None:
    if v is not None:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Full name must be at least 2 characters and cannot be whitespace only")
        return stripped
    return v


def _normalize_employee_code(v: str | None) -> str | None:
    if v is not None:
        stripped = v.strip().upper()
        return stripped if stripped else None
    return None


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

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        res = _validate_full_name(v)
        if not res:
            raise ValueError("Full name is required")
        return res

    @field_validator("employee_code")
    @classmethod
    def normalize_code(cls, v: str | None) -> str | None:
        return _normalize_employee_code(v)


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

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        res = _validate_full_name(v)
        if not res:
            raise ValueError("Full name is required")
        return res

    @field_validator("employee_code")
    @classmethod
    def normalize_code(cls, v: str | None) -> str | None:
        return _normalize_employee_code(v)


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

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        return _validate_full_name(v)

    @field_validator("employee_code")
    @classmethod
    def normalize_code(cls, v: str | None) -> str | None:
        return _normalize_employee_code(v)


class EmployeeRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    territory_id: uuid.UUID | None
    effective_territory_id: uuid.UUID | None = None
    effective_territory_name: str | None = None
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
