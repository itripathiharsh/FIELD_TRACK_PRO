"""
Security audit trail — /api/v1/security-audit-logs  (Super Admin only)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import SuperAdminOnly
from app.database import get_async_session
from app.schemas.admin_security import SecurityAuditLogRead
from app.services import security_audit_service

router = APIRouter(prefix="/security-audit-logs", tags=["security-audit"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[SecurityAuditLogRead], dependencies=[SuperAdminOnly])
async def list_security_audit_logs(
    session: DbSession,
    event_type: str | None = Query(default=None, max_length=64),
    target_user_id: uuid.UUID | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Super Admin: recent security events (password resets, role changes, privileged account changes)."""
    return await security_audit_service.list_events(
        session, limit=limit, offset=offset, event_type=event_type,
        target_user_id=target_user_id, actor_user_id=actor_user_id,
    )
