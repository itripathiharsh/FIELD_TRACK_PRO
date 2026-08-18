"""
Authentication service — login, token refresh, logout.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import login_rate_limiter
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
    hash_password,
)
import hashlib
import secrets
import string
from sqlalchemy import select
from app.exceptions.custom import BaseAPIException
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from app.models.password_reset import PasswordResetToken
from app.schemas.user import CurrentUserRead


async def login(data: LoginRequest, session: AsyncSession) -> TokenResponse:
    """
    Authenticate a user and issue access + refresh tokens.

    FT-041: the rate-limit check runs *before* credentials are examined, so a
    locked-out identifier costs no password verification work and leaks no
    information about whether the account exists.
    """
    raw_identifier = data.email or data.mobile_number or ""
    identifier = raw_identifier.strip().lower() if data.email else raw_identifier.strip()
    await login_rate_limiter.check_allowed(identifier, session)

    user_repo = UserRepository(session)

    if data.email:
        user = await user_repo.get_by_email(data.email)
    else:
        user = await user_repo.get_by_mobile(data.mobile_number)

    if user is None or not verify_password(data.password, user.password_hash):
        # A missing account and a wrong password are recorded and reported
        # identically, so the endpoint cannot be used to enumerate users.
        await login_rate_limiter.record_failure(identifier, session)
        raise BaseAPIException(
            status_code=401,
            detail="Invalid credentials",
            error_code="AUTH_INVALID_CREDENTIALS",
        )
    if not user.is_active:
        # Correct credentials, so this is not a brute-force signal; the counter
        # is not incremented. Access is still refused.
        raise BaseAPIException(
            status_code=403,
            detail="Account is disabled",
            error_code="AUTH_ACCOUNT_DISABLED",
        )

    await login_rate_limiter.record_success(identifier, session)

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


async def build_current_user(user: User, session: AsyncSession) -> CurrentUserRead:
    """
    Assemble the `/auth/me` identity payload (FT-011).

    An EMPLOYEE has a profile row carrying the display name and territory. An
    ADMIN has no employee row, so the display name falls back to the account
    identity (email, then mobile number) rather than being omitted.
    """
    employee = await EmployeeRepository(session).get_by_user_id(user.id)

    if employee is not None:
        full_name = employee.full_name
        employee_code = employee.employee_code
        # P2-D: the currently EFFECTIVE territory (an active temporary
        # reassignment wins over the base assignment), not the raw column -
        # this is the one place the employee's own session actually reflects
        # the reassignment rules.
        from app.services.territory_assignment_service import get_effective_territory_id
        from app.repositories.territory_repo import TerritoryRepository

        territory_id = await get_effective_territory_id(employee.id, session)
        territory_name = None
        if territory_id:
            territory = await TerritoryRepository(session).get_by_id(territory_id)
            if territory:
                territory_name = territory.name
    else:
        full_name = user.email or user.mobile_number or str(user.id)
        employee_code = None
        territory_id = None
        territory_name = None

    return CurrentUserRead(
        id=user.id,
        email=user.email,
        mobile_number=user.mobile_number,
        full_name=full_name,
        role=user.role,
        is_active=user.is_active,
        territory_id=territory_id,
        territory_name=territory_name,
        employee_id=employee.id if employee else None,
        employee_code=employee_code,
    )


def generate_otp(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

async def forgot_password(email: str, session: AsyncSession) -> None:
    clean_email = email.strip().lower()
    await login_rate_limiter.check_allowed(f"forgot_pwd_{clean_email}", session)

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(clean_email)

    if not user or not user.is_active:
        await login_rate_limiter.record_failure(f"forgot_pwd_{clean_email}", session)
        return

    await login_rate_limiter.record_success(f"forgot_pwd_{clean_email}", session)

    otp = generate_otp()
    hashed = hash_otp(otp)

    record = PasswordResetToken(
        user_id=user.id,
        token_hash=hashed,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15)
    )
    session.add(record)
    await session.commit()

    from app.services.email_service import send_password_reset_email
    await send_password_reset_email(user.email or clean_email, otp)

async def reset_password(data: ResetPasswordRequest, session: AsyncSession) -> None:
    clean_email = data.email.strip().lower()
    await login_rate_limiter.check_allowed(f"reset_pwd_{clean_email}", session)

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(clean_email)

    if not user or not user.is_active:
        await login_rate_limiter.record_failure(f"reset_pwd_{clean_email}", session)
        raise BaseAPIException(status_code=400, detail="Invalid request", error_code="AUTH_INVALID_RESET")

    hashed = hash_otp(data.otp)

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.token_hash == hashed,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.now(tz=timezone.utc)
    )
    result = await session.execute(stmt)
    token = result.scalar_one_or_none()

    if not token:
        await login_rate_limiter.record_failure(f"reset_pwd_{data.email}", session)
        raise BaseAPIException(status_code=400, detail="Invalid or expired reset code", error_code="AUTH_INVALID_RESET_CODE")

    await login_rate_limiter.record_success(f"reset_pwd_{data.email}", session)

    user.password_hash = hash_password(data.new_password)
    session.add(user)

    token.used = True
    session.add(token)

    await TokenRepository(session).revoke_all_for_user(user.id)
    await session.commit()

