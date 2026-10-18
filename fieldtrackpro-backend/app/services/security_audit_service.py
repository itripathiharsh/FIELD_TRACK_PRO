"""
Security audit trail for administrative actions (password reset, role changes, bootstrap).

Rows never contain credentials: callers pass only non-secret facts. `record` adds the row to the
caller's session so it commits atomically with the change it describes; `record_denied` writes
a standalone row for refused attempts (the business transaction was rolled back).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_request_id
from app.models.security_audit import SecurityAuditLog

logger = logging.getLogger("fieldtrackpro")

#: Keys that must never be persisted even if a caller passes them by mistake.
_FORBIDDEN_DETAIL_KEYS = {
    "password", "temporary_password", "temp_password", "new_password", "old_password",
    "current_password", "token", "access_token", "refresh_token", "otp", "hash", "password_hash",
}


def _clean_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    return {k: v for k, v in details.items() if k.lower() not in _FORBIDDEN_DETAIL_KEYS}


def build_entry(
    event_type: str,
    outcome: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    previous_role: str | None = None,
    new_role: str | None = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
    client_ip: str | None = None,
) -> SecurityAuditLog:
    return SecurityAuditLog(
        event_type=event_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        previous_role=previous_role,
        new_role=new_role,
        reason_code=reason_code,
        details=_clean_details(details),
        request_id=get_current_request_id() or None,
        client_ip=client_ip,
    )


def record(session: AsyncSession, event_type: str, outcome: str = "SUCCESS", **kwargs: Any) -> SecurityAuditLog:
    """Add an audit row to `session` (committed with the caller's transaction)."""
    entry = build_entry(event_type, outcome, **kwargs)
    session.add(entry)
    logger.info(
        "event=security_audit type=%s outcome=%s actor=%s target=%s reason=%s",
        event_type, outcome, kwargs.get("actor_user_id"), kwargs.get("target_user_id"), kwargs.get("reason_code"),
    )
    return entry


async def record_denied(session: AsyncSession, event_type: str, reason_code: str, **kwargs: Any) -> None:
    """
    Persist a refused/failed attempt in its own commit. Call AFTER rolling back the business
    transaction (and before raising) so the audit row survives the rollback.
    """
    outcome = kwargs.pop("outcome", "DENIED")
    record(session, event_type, outcome, reason_code=reason_code, **kwargs)
    await session.commit()


async def list_events(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    event_type: str | None = None,
    target_user_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[SecurityAuditLog]:
    stmt = select(SecurityAuditLog).order_by(SecurityAuditLog.created_at.desc())
    if event_type:
        stmt = stmt.where(SecurityAuditLog.event_type == event_type)
    if target_user_id:
        stmt = stmt.where(SecurityAuditLog.target_user_id == target_user_id)
    if actor_user_id:
        stmt = stmt.where(SecurityAuditLog.actor_user_id == actor_user_id)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())
