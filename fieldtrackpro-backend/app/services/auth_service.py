"""
Authentication service — login, token refresh, logout.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.context import get_current_request_id, set_current_user_id
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
from sqlalchemy import select, update
from app.exceptions.custom import BaseAPIException
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.schemas.user import CurrentUserRead
from app.services.email_service import send_password_reset_email
from app.services.sms_service import mask_email, mask_mobile, send_password_reset_sms

logger = logging.getLogger("fieldtrackpro")


def _mask_identifier(val: str) -> str:
    if not val:
        return "-"
    cleaned = val.strip()
    return mask_email(cleaned) if "@" in cleaned else mask_mobile(cleaned)


async def login(data: LoginRequest, session: AsyncSession) -> TokenResponse:
    """
    Authenticate a user and issue access + refresh tokens.

    FT-041: the rate-limit check runs *before* credentials are examined, so a
    locked-out identifier costs no password verification work and leaks no
    information about whether the account exists.
    """
    if data.identifier:
        cleaned = data.identifier.strip()
        if "@" in cleaned:
            data.email = cleaned
        else:
            data.mobile_number = cleaned

    raw_identifier = data.email or data.mobile_number or ""
    identifier = raw_identifier.strip().lower() if data.email else raw_identifier.strip()
    masked_id = _mask_identifier(raw_identifier)
    req_id = get_current_request_id()

    try:
        await login_rate_limiter.check_allowed(identifier, session)
    except BaseAPIException:
        logger.warning(
            "event=auth_login result=failed reason=RATE_LIMITED request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise

    user_repo = UserRepository(session)

    if data.email:
        user = await user_repo.get_by_email(data.email)
    else:
        user = await user_repo.get_by_mobile(data.mobile_number)

    if user is None or not verify_password(data.password, user.password_hash):
        # A missing account and a wrong password are recorded and reported
        # identically, so the endpoint cannot be used to enumerate users.
        await login_rate_limiter.record_failure(identifier, session)
        logger.warning(
            "event=auth_login result=failed reason=INVALID_CREDENTIALS request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=401,
            detail="Invalid credentials",
            error_code="AUTH_INVALID_CREDENTIALS",
        )
    if not user.is_active:
        # Correct credentials, so this is not a brute-force signal; the counter
        # is not incremented. Access is still refused.
        logger.warning(
            "event=auth_login result=failed reason=ACCOUNT_DISABLED request_id=%s user_id=%s identifier=%s",
            req_id,
            user.id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=403,
            detail="Account is disabled",
            error_code="AUTH_ACCOUNT_DISABLED",
        )

    await login_rate_limiter.record_success(identifier, session)
    set_current_user_id(str(user.id))

    logger.info(
        "event=auth_login result=success request_id=%s user_id=%s role=%s identifier=%s",
        req_id,
        user.id,
        user.role.value,
        masked_id,
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
    req_id = get_current_request_id()
    token_hash = hash_refresh_token(raw_refresh)
    token_repo = TokenRepository(session)
    user_repo = UserRepository(session)

    record = await token_repo.get_active_by_hash(token_hash)
    if record is None:
        logger.warning("event=auth_refresh result=failed reason=INVALID_REFRESH_TOKEN request_id=%s", req_id)
        raise BaseAPIException(
            status_code=401,
            detail="Invalid or expired refresh token",
            error_code="AUTH_INVALID_REFRESH_TOKEN",
        )

    user = await user_repo.get_by_id(record.user_id)
    if user is None or not user.is_active:
        logger.warning(
            "event=auth_refresh result=failed reason=ACCOUNT_DISABLED request_id=%s user_id=%s",
            req_id,
            record.user_id,
        )
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

    set_current_user_id(str(user.id))
    logger.info("event=auth_refresh result=success request_id=%s user_id=%s", req_id, user.id)

    return TokenResponse(access_token=access_token, refresh_token=raw_new)


async def logout(raw_refresh: str, session: AsyncSession) -> None:
    """Revoke the given refresh token."""
    req_id = get_current_request_id()
    token_hash = hash_refresh_token(raw_refresh)
    token_repo = TokenRepository(session)
    record = await token_repo.get_by_hash(token_hash)
    if record and not record.revoked:
        record.revoked = True
        session.add(record)
        await token_repo.commit()
        logger.info("event=auth_logout request_id=%s user_id=%s", req_id, record.user_id)
    else:
        logger.info("event=auth_logout request_id=%s", req_id)


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


def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


async def forgot_password(identifier: str, session: AsyncSession) -> ForgotPasswordResponse:
    """
    Unified forgot password recovery for either email or mobile number.
    Generates single-use 6-digit OTP, invalidates previous active tokens,
    dispatches via Email or SMS, and returns masked destination.
    """
    clean_id = identifier.strip()
    is_email = "@" in clean_id
    normalized_key = clean_id.lower() if is_email else clean_id
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    await login_rate_limiter.check_allowed(f"forgot_pwd_{normalized_key}", session)

    user_repo = UserRepository(session)
    if is_email:
        user = await user_repo.get_by_email(clean_id)
    else:
        user = await user_repo.get_by_mobile(clean_id)

    # Prevent account enumeration: return generic message and masked input for invalid accounts
    if not user or not user.is_active:
        await login_rate_limiter.record_failure(f"forgot_pwd_{normalized_key}", session)
        masked_dest = mask_email(clean_id) if is_email else mask_mobile(clean_id)
        logger.info(
            "event=auth_forgot_password request_id=%s identifier=%s result=non_existent_or_inactive",
            req_id,
            masked_id,
        )
        return ForgotPasswordResponse(
            message="If that account is registered, a security code has been sent.",
            destination=masked_dest,
            delivery_channel="EMAIL" if is_email else "SMS",
        )

    await login_rate_limiter.record_success(f"forgot_pwd_{normalized_key}", session)

    # Invalidate any previously unexpired/unused reset tokens for this user
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used == False)
        .values(used=True)
    )

    otp = generate_otp(6)
    hashed = hash_otp(otp)

    record = PasswordResetToken(
        user_id=user.id,
        token_hash=hashed,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15),
    )
    session.add(record)
    await session.commit()

    if is_email:
        dest = user.email or clean_id
        masked_dest = mask_email(dest)
        channel = "EMAIL"
        await send_password_reset_email(dest, otp)
    else:
        dest = user.mobile_number or clean_id
        masked_dest = mask_mobile(dest)
        channel = "SMS"
        await send_password_reset_sms(dest, otp)

    logger.info(
        "event=auth_forgot_password request_id=%s identifier=%s destination=%s delivery_channel=%s",
        req_id,
        masked_id,
        masked_dest,
        channel,
    )

    return ForgotPasswordResponse(
        message="Security code sent successfully.",
        destination=masked_dest,
        delivery_channel=channel,
    )


async def verify_otp(data: VerifyOtpRequest, session: AsyncSession) -> VerifyOtpResponse:
    """
    Pre-validates 6-digit OTP during multi-step password recovery.
    """
    raw_identifier = data.identifier or data.email or data.mobile_number or ""
    clean_id = raw_identifier.strip()
    is_email = "@" in clean_id
    normalized_key = clean_id.lower() if is_email else clean_id
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    await login_rate_limiter.check_allowed(f"verify_otp_{normalized_key}", session)

    user_repo = UserRepository(session)
    if is_email:
        user = await user_repo.get_by_email(clean_id)
    else:
        user = await user_repo.get_by_mobile(clean_id)

    if not user or not user.is_active:
        await login_rate_limiter.record_failure(f"verify_otp_{normalized_key}", session)
        logger.warning(
            "event=auth_verify_otp result=failed reason=USER_NOT_FOUND_OR_INACTIVE request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=400,
            detail="Invalid or expired verification code",
            error_code="AUTH_INVALID_RESET_CODE",
        )

    hashed = hash_otp(data.otp.strip())
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.token_hash == hashed,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.now(tz=timezone.utc),
    )
    result = await session.execute(stmt)
    token = result.scalar_one_or_none()

    if not token:
        await login_rate_limiter.record_failure(f"verify_otp_{normalized_key}", session)
        logger.warning(
            "event=auth_verify_otp result=failed reason=INVALID_OR_EXPIRED_CODE request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=400,
            detail="Invalid or expired verification code",
            error_code="AUTH_INVALID_RESET_CODE",
        )

    await login_rate_limiter.record_success(f"verify_otp_{normalized_key}", session)
    logger.info("event=auth_verify_otp result=success request_id=%s identifier=%s", req_id, masked_id)
    return VerifyOtpResponse(valid=True, message="Verification code confirmed.")


async def reset_password(data: ResetPasswordRequest, session: AsyncSession) -> None:
    """
    Verifies reset OTP, updates password, marks token used, and revokes all active refresh tokens.
    """
    raw_identifier = data.identifier or data.email or data.mobile_number or ""
    clean_id = raw_identifier.strip()
    is_email = "@" in clean_id
    normalized_key = clean_id.lower() if is_email else clean_id
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    await login_rate_limiter.check_allowed(f"reset_pwd_{normalized_key}", session)

    user_repo = UserRepository(session)
    if is_email:
        user = await user_repo.get_by_email(clean_id)
    else:
        user = await user_repo.get_by_mobile(clean_id)

    if not user or not user.is_active:
        await login_rate_limiter.record_failure(f"reset_pwd_{normalized_key}", session)
        logger.warning(
            "event=auth_reset_password result=failed reason=USER_NOT_FOUND_OR_INACTIVE request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=400,
            detail="Invalid request",
            error_code="AUTH_INVALID_RESET",
        )

    hashed = hash_otp(data.otp.strip())

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.token_hash == hashed,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.now(tz=timezone.utc),
    )
    result = await session.execute(stmt)
    token = result.scalar_one_or_none()

    if not token:
        await login_rate_limiter.record_failure(f"reset_pwd_{normalized_key}", session)
        logger.warning(
            "event=auth_reset_password result=failed reason=INVALID_OR_EXPIRED_CODE request_id=%s identifier=%s",
            req_id,
            masked_id,
        )
        raise BaseAPIException(
            status_code=400,
            detail="Invalid or expired reset code",
            error_code="AUTH_INVALID_RESET_CODE",
        )

    await login_rate_limiter.record_success(f"reset_pwd_{normalized_key}", session)

    user.password_hash = hash_password(data.new_password)
    session.add(user)

    token.used = True
    session.add(token)

    # Revoke all existing sessions for this user
    await TokenRepository(session).revoke_all_for_user(user.id)
    await session.commit()
    logger.info("event=auth_reset_password result=success request_id=%s user_id=%s", req_id, user.id)

