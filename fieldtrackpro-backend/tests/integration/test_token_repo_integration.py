"""
Integration: TokenRepository.get_active_by_hash (P1-5).

Prior to this fix, the expiry comparison used a naive `datetime.utcnow()`
against `RefreshToken.expires_at` (DateTime(timezone=True)) - the only place
in the codebase doing so; every other timestamp comparison uses
`datetime.now(timezone.utc)`. This had zero prior direct test coverage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.security import generate_refresh_token, hash_refresh_token
from app.database import AsyncSessionLocal
from app.models.refresh_token import RefreshToken
from app.repositories.token_repo import TokenRepository
from tests.integration.conftest import login, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def _insert_token(user_id: str, expires_at: datetime, revoked: bool = False) -> str:
    raw, token_hash = generate_refresh_token()
    async with AsyncSessionLocal() as session:
        session.add(RefreshToken(
            id=uuid.uuid4(), user_id=uuid.UUID(user_id), token_hash=token_hash,
            expires_at=expires_at, revoked=revoked,
        ))
        await session.commit()
    return token_hash


async def test_valid_unexpired_token_is_returned(seeded_world):
    token_hash = await _insert_token(
        seeded_world["employee_user_id"], datetime.now(timezone.utc) + timedelta(days=1)
    )
    async with AsyncSessionLocal() as session:
        repo = TokenRepository(session)
        record = await repo.get_active_by_hash(token_hash)
    assert record is not None
    assert record.token_hash == token_hash


async def test_expired_token_is_not_returned(seeded_world):
    """The core P1-5 regression case: expires_at strictly in the past, tz-aware."""
    token_hash = await _insert_token(
        seeded_world["employee_user_id"], datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    async with AsyncSessionLocal() as session:
        repo = TokenRepository(session)
        record = await repo.get_active_by_hash(token_hash)
    assert record is None, "P1-5: an expired token must never be treated as active"


async def test_token_expiring_far_in_the_past_is_not_returned(seeded_world):
    token_hash = await _insert_token(
        seeded_world["employee_user_id"], datetime.now(timezone.utc) - timedelta(days=30)
    )
    async with AsyncSessionLocal() as session:
        repo = TokenRepository(session)
        record = await repo.get_active_by_hash(token_hash)
    assert record is None


async def test_revoked_token_is_not_returned_even_if_unexpired(seeded_world):
    token_hash = await _insert_token(
        seeded_world["employee_user_id"], datetime.now(timezone.utc) + timedelta(days=1), revoked=True,
    )
    async with AsyncSessionLocal() as session:
        repo = TokenRepository(session)
        record = await repo.get_active_by_hash(token_hash)
    assert record is None


async def test_token_expiring_in_one_second_is_still_active_now(seeded_world):
    """Boundary check: a token that has not yet crossed its expiry instant is active."""
    token_hash = await _insert_token(
        seeded_world["employee_user_id"], datetime.now(timezone.utc) + timedelta(seconds=1)
    )
    async with AsyncSessionLocal() as session:
        repo = TokenRepository(session)
        record = await repo.get_active_by_hash(token_hash)
    assert record is not None


async def test_real_refresh_flow_still_works_end_to_end(client: AsyncClient, seeded_world):
    """Regression: existing token lifetime/refresh/authentication behaviour is unchanged."""
    logged_in = await login(client, seeded_world["employee_email"], seeded_world["password"])
    assert logged_in.status_code == 200, logged_in.text
    raw_refresh = logged_in.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()
    assert "refresh_token" in resp.json()

    # Rotation: the old refresh token must now be revoked/unusable.
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert reused.status_code == 401, "a rotated-out refresh token must not be reusable"
