"""
Tests for automated security records cleanup service and scheduler wiring.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.jobs.scheduler import (
    MISSED_VISIT_JOB_ID,
    SECURITY_CLEANUP_JOB_ID,
    shutdown_scheduler,
    start_scheduler,
)
from app.models.login_attempt import LoginAttempt
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import Role, User
from app.services.security_cleanup_service import security_cleanup_service


@pytest_asyncio.fixture
async def session():
    async with AsyncSessionLocal() as s:
        yield s


@pytest.mark.asyncio
async def test_security_cleanup_purges_expired_and_preserves_active(session: AsyncSession):
    """Cleanup service deletes expired/revoked tokens and old login attempts while preserving active ones."""
    now = datetime.now(timezone.utc)

    # 1. Create a test user
    user = User(
        id=uuid.uuid4(),
        email=f"cleanup_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="fake_hash",
        role=Role.EMPLOYEE,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # 2. Add RefreshTokens:
    # (a) Active and future expiry -> KEEP
    active_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"active_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now + timedelta(days=5),
        revoked=False,
    )
    # (b) Expired token -> PURGE
    expired_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"expired_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now - timedelta(days=1),
        revoked=False,
    )
    # (c) Revoked recently (1 day ago) -> KEEP
    recent_revoked_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"recent_revoked_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now + timedelta(days=2),
        revoked=True,
        created_at=now - timedelta(days=1),
    )
    # (d) Revoked long ago (10 days ago) -> PURGE
    old_revoked_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"old_revoked_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now + timedelta(days=2),
        revoked=True,
        created_at=now - timedelta(days=10),
    )
    session.add_all([active_token, expired_token, recent_revoked_token, old_revoked_token])

    # 3. Add PasswordResetTokens:
    # (a) Active reset token -> KEEP
    active_reset = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"active_reset_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now + timedelta(minutes=10),
        used=False,
    )
    # (b) Expired reset token -> PURGE
    expired_reset = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"expired_reset_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now - timedelta(minutes=5),
        used=False,
    )
    # (c) Used reset token -> PURGE
    used_reset = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=f"used_reset_hash_{uuid.uuid4().hex[:8]}",
        expires_at=now + timedelta(minutes=5),
        used=True,
    )
    session.add_all([active_reset, expired_reset, used_reset])

    # 4. Add LoginAttempts:
    # (a) Recent attempt (1 hour ago) -> KEEP
    recent_attempt = LoginAttempt(
        id=uuid.uuid4(),
        identifier=f"recent_{uuid.uuid4().hex[:8]}@example.com",
        attempted_at=now - timedelta(hours=1),
    )
    # (b) Old attempt (35 days ago) -> PURGE
    old_attempt = LoginAttempt(
        id=uuid.uuid4(),
        identifier=f"old_{uuid.uuid4().hex[:8]}@example.com",
        attempted_at=now - timedelta(days=35),
    )
    session.add_all([recent_attempt, old_attempt])

    await session.commit()

    # Run cleanup
    counts = await security_cleanup_service.cleanup_expired_records(session)

    assert counts["refresh_tokens"] >= 2  # expired_token and old_revoked_token
    assert counts["password_reset_tokens"] >= 2  # expired_reset and used_reset
    assert counts["login_attempts"] >= 1  # old_attempt

    # Verify database state
    # Active refresh token still exists
    res = await session.execute(select(RefreshToken).where(RefreshToken.id == active_token.id))
    assert res.scalar_one_or_none() is not None

    # Recent revoked token still exists
    res = await session.execute(select(RefreshToken).where(RefreshToken.id == recent_revoked_token.id))
    assert res.scalar_one_or_none() is not None

    # Expired refresh token deleted
    res = await session.execute(select(RefreshToken).where(RefreshToken.id == expired_token.id))
    assert res.scalar_one_or_none() is None

    # Old revoked token deleted
    res = await session.execute(select(RefreshToken).where(RefreshToken.id == old_revoked_token.id))
    assert res.scalar_one_or_none() is None

    # Active reset token still exists
    res = await session.execute(select(PasswordResetToken).where(PasswordResetToken.id == active_reset.id))
    assert res.scalar_one_or_none() is not None

    # Expired and used reset tokens deleted
    res = await session.execute(select(PasswordResetToken).where(PasswordResetToken.id == expired_reset.id))
    assert res.scalar_one_or_none() is None
    res = await session.execute(select(PasswordResetToken).where(PasswordResetToken.id == used_reset.id))
    assert res.scalar_one_or_none() is None

    # Recent login attempt exists, old one deleted
    res = await session.execute(select(LoginAttempt).where(LoginAttempt.id == recent_attempt.id))
    assert res.scalar_one_or_none() is not None
    res = await session.execute(select(LoginAttempt).where(LoginAttempt.id == old_attempt.id))
    assert res.scalar_one_or_none() is None

    # Clean up test user
    await session.delete(user)
    await session.commit()


@pytest.mark.asyncio
async def test_scheduler_registers_security_cleanup_job():
    """Scheduler registers both missed visit sweep and security records cleanup job."""
    shutdown_scheduler()
    with patch("app.config.settings.enable_scheduler", True):
        scheduler = start_scheduler()
        assert scheduler is not None
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert MISSED_VISIT_JOB_ID in job_ids
        assert SECURITY_CLEANUP_JOB_ID in job_ids
        shutdown_scheduler()
