from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SecurityAuditLog(Base):
    """
    Append-only record of security-sensitive administrative actions (admin password
    reset, role change, super-admin bootstrap, privileged account changes).

    NEVER store credentials here: no passwords, hashes, tokens or OTPs. `details` carries only
    non-secret facts (previous/new role, number of sessions revoked, expiry minutes, reason code).
    Actor/target ids are SET NULL on user deletion so the trail itself is never lost.
    """

    __tablename__ = "security_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # e.g. ADMIN_PASSWORD_RESET, ROLE_CHANGE, SUPER_ADMIN_BOOTSTRAP, ACCOUNT_DEACTIVATED
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # SUCCESS | DENIED | FAILED
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
