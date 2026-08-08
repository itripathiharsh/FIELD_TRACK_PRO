"""
Authentication service — login, token refresh, logout.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.exceptions.custom import BaseAPIException
from app.models.refresh_token import RefreshToken
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse


async def login(data: LoginRequest, session: AsyncSession) -> TokenResponse:
    """Authenticate a user and issue access + refresh tokens."""
    user_repo = UserRepository(session)

    if data.email:
        user = await user_repo.get_by_email(data.email)
    else:
        user = await user_repo.get_by_mobile(data.mobile_number)

    if user is None or not verify_password(data.password, user.password_hash):
        raise BaseAPIException(
            status_code=401,
            detail="Invalid credentials",
            error_code="AUTH_INVALID_CREDENTIALS",
        )
    if not user.is_active:
        raise BaseAPIException(
            status_code=403,
            detail="Account is disabled",
            error_code="AUTH_ACCOUNT_DISABLED",
        )

    access_token = create_access_token(str(user.id), user.role.value)
    raw_refresh, token_hash = generate_refresh_token()

    token_repo = TokenRepository(session)
    record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expiry_days
        ),
    )
    await token_repo.add(record)
    await token_repo.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


async def refresh_tokens(raw_refresh: str, session: AsyncSession) -> TokenResponse:
    """Validate a refresh token and issue new token pair (rotation)."""
    token_hash = hash_refresh_token(raw_refresh)
    token_repo = TokenRepository(session)
    user_repo = UserRepository(session)

    record = await token_repo.get_active_by_hash(token_hash)
    if record is None:
        raise BaseAPIException(
            status_code=401,
            detail="Invalid or expired refresh token",
            error_code="AUTH_INVALID_REFRESH_TOKEN",
        )

    user = await user_repo.get_by_id(record.user_id)
    if user is None or not user.is_active:
        raise BaseAPIException(
            status_code=403,
            detail="Account is disabled",
            error_code="AUTH_ACCOUNT_DISABLED",
        )

    # Revoke old token (rotation)
    record.revoked = True
    session.add(record)

    # Issue new pair
    access_token = create_access_token(str(user.id), user.role.value)
    raw_new, new_hash = generate_refresh_token()
    new_record = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expiry_days
        ),
    )
    await token_repo.add(new_record)
    await token_repo.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_new)


async def logout(raw_refresh: str, session: AsyncSession) -> None:
    """Revoke the given refresh token."""
    token_hash = hash_refresh_token(raw_refresh)
    token_repo = TokenRepository(session)
    record = await token_repo.get_by_hash(token_hash)
    if record and not record.revoked:
        record.revoked = True
        session.add(record)
        await token_repo.commit()
