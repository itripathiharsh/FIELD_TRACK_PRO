"""
Schemas for admin password reset, Super Admin role management and the security audit trail.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import Role


class AdminPasswordResetResponse(BaseModel):
    """
    Returned ONCE, only to the administrator who triggered the reset. The plaintext is never stored
    and there is no endpoint to read it again: if this response is lost the admin must reset again.
    """

    employee_id: uuid.UUID
    user_id: uuid.UUID
    temporary_password: str
    expires_at: datetime
    expires_in_minutes: int
    must_change_password: bool = True


class RoleChangeRequest(BaseModel):
    """Change an account's role. Re-authentication (the acting Super Admin's own password) is mandatory."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    current_password: str = Field(min_length=1, max_length=128)
    # Must be true for any change that grants or removes SUPER_ADMIN.
    confirm: bool = False


class SecurityAuditLogRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    event_type: str
    outcome: str
    actor_user_id: uuid.UUID | None = None
    target_user_id: uuid.UUID | None = None
    previous_role: str | None = None
    new_role: str | None = None
    reason_code: str | None = None
    details: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)
