"""
User request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.user import Role


# ---------------------------------------------------------------------------
# Read schemas
# ---------------------------------------------------------------------------

class UserRead(BaseModel):
    id: uuid.UUID
    email: str | None
    mobile_number: str | None
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """Lightweight user projection used in nested responses."""

    id: uuid.UUID
    email: str | None
    mobile_number: str | None
    role: Role

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Create / update schemas (admin-only)
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str | None = None
    mobile_number: str | None = None
    password: str
    role: Role = Role.EMPLOYEE

    @property
    def has_identity(self) -> bool:
        return bool(self.email or self.mobile_number)


class UserUpdatePassword(BaseModel):
    old_password: str
    new_password: str
