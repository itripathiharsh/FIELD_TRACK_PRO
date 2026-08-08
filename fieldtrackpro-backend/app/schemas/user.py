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


class CurrentUserRead(BaseModel):
    """
    Identity payload for `GET /auth/me`.

    FT-011: the client needs a display name and the caller's territory to render
    the shell correctly. `full_name` and `territory_id` come from the linked
    employee profile; administrators have no employee row, so `full_name` falls
    back to the account identity rather than being omitted (an absent field
    previously forced the UI to invent one).
    """

    id: uuid.UUID
    email: str | None
    mobile_number: str | None
    full_name: str
    role: Role
    is_active: bool
    territory_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None


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
