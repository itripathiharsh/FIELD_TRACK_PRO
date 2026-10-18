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
from app.core.deps.auth import temp_password_expired, temp_password_expired_error
from app.core.rate_limiter import (
    forgot_account_limiter,
    forgot_ip_limiter,
    login_rate_limiter,
    reset_account_limiter,
    reset_ip_limiter,
    throttle_key,
)
from app.models.login_attempt import LoginAttempt
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
    hash_password,
    dummy_verify_password,
)
import hashlib
import hmac
import secrets
import string
from sqlalchemy import delete, select, update
from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
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


async def get_must_change_password(user_id, session: AsyncSession) -> bool:
    """True if the user's employee profile is flagged for a forced password change (admins: False)."""
    flag = (
        await session.execute(
            select(Employee.must_change_password).where(Employee.user_id == user_id)
        )
    ).scalar_one_or_none()
    return bool(flag)


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

    if user is None:
        # Equalise timing with the wrong-password path so response time does not
        # reveal whether the identifier exists.
        dummy_verify_password(data.password)
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

    if temp_password_expired(user):
        # The credential is correct but the admin-issued temporary password has expired: refuse
        # (and tell the user why - they proved they know the password, so nothing is leaked).
        logger.warning(
            "event=auth_login result=failed reason=TEMP_PASSWORD_EXPIRED request_id=%s user_id=%s identifier=%s",
            req_id,
            user.id,
            masked_id,
        )
        raise temp_password_expired_error()

    await login_rate_limiter.record_success(identifier, session)
    set_current_user_id(str(user.id))

    logger.info(
        "event=auth_login result=success request_id=%s user_id=%s role=%s identifier=%s",
        req_id,
        user.id,
        user.role.value,
        masked_id,
    )

    access_token = create_access_token(str(user.id), user.role.value, token_version=user.token_version)
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        must_change_password=await get_must_change_password(user.id, session),
    )


async def refresh_tokens(raw_refresh: str, session: AsyncSession) -> TokenResponse:
    """
    Validate a refresh token and issue a new token pair (rotation).

    Hardening:
    * The token row is locked (SELECT ... FOR UPDATE) so two concurrent
      refreshes of the same token cannot both succeed.
    * Replay of an already-revoked token is treated as theft: every refresh
      token of that user is revoked (forcing re-login on all devices).
    """
    req_id = get_current_request_id()
    token_hash = hash_refresh_token(raw_refresh)
    token_repo = TokenRepository(session)
    user_repo = UserRepository(session)

    invalid = BaseAPIException(
        status_code=401,
        detail="Invalid or expired refresh token",
        error_code="AUTH_INVALID_REFRESH_TOKEN",
    )

    record = await token_repo.get_by_hash_for_update(token_hash)
    if record is None:
        logger.warning("event=auth_refresh result=failed reason=INVALID_REFRESH_TOKEN request_id=%s", req_id)
        raise invalid

    within_grace = False
    if record.revoked:
        now_check = datetime.now(tz=timezone.utc)
        age = (now_check - record.rotated_at) if record.rotated_at is not None else None
        if age is not None and age <= timedelta(seconds=settings.refresh_reuse_grace_seconds):
            # This token was revoked by a normal rotation (not logout/disable/
            # theft) a moment ago - almost certainly a race (two tabs, a
            # client retry), not a stolen token being replayed. Issue another
            # valid rotation instead of nuking every session.
            within_grace = True
            logger.info(
                "event=auth_refresh result=grace_reuse reason=TOKEN_RECENTLY_ROTATED request_id=%s user_id=%s age_seconds=%.3f",
                req_id,
                record.user_id,
                age.total_seconds(),
            )
        else:
            revoked = await token_repo.revoke_all_for_user(record.user_id)
            await token_repo.commit()
            logger.warning(
                "event=auth_refresh result=failed reason=REFRESH_TOKEN_REUSE_DETECTED request_id=%s user_id=%s revoked_tokens=%s",
                req_id,
                record.user_id,
                revoked,
            )
            raise invalid

    if record.expires_at <= datetime.now(tz=timezone.utc):
        logger.warning("event=auth_refresh result=failed reason=EXPIRED_REFRESH_TOKEN request_id=%s", req_id)
        raise invalid

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

    if temp_password_expired(user):
        logger.warning(
            "event=auth_refresh result=failed reason=TEMP_PASSWORD_EXPIRED request_id=%s user_id=%s",
            req_id,
            user.id,
        )
        raise temp_password_expired_error()

    # Revoke old token (rotation) and issue the new pair in ONE transaction.
    # Within the grace window `record` is already revoked from its original
    # rotation - leave it untouched and just issue another valid descendant.
    if not within_grace:
        record.revoked = True
        record.rotated_at = datetime.now(tz=timezone.utc)
        session.add(record)

    access_token = create_access_token(str(user.id), user.role.value, token_version=user.token_version)
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_new,
        must_change_password=await get_must_change_password(user.id, session),
    )


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
        must_change_password=bool(employee.must_change_password) if employee is not None else False,
    )


def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _otp_hmac_key() -> bytes:
    """Server-side key for OTP hashing (OTP_HMAC_SECRET, else derived from JWT_SECRET)."""
    if settings.otp_hmac_secret:
        return settings.otp_hmac_secret.encode()
    return hmac.new(
        settings.jwt_secret.encode(), b"fieldtrackpro:password-reset-otp:v1", hashlib.sha256
    ).digest()


def hash_otp(otp: str, user_id: object | None = None) -> str:
    """
    Keyed (HMAC-SHA256) OTP digest, bound to the user. A leaked reset-token
    table cannot be brute-forced offline (6 digits = 1e6 guesses) without the
    server secret.
    """
    msg = f"{user_id or ''}:{otp.strip()}".encode()
    return hmac.new(_otp_hmac_key(), msg, hashlib.sha256).hexdigest()


def _split_identifier(raw: str) -> tuple[str, bool, str]:
    clean_id = (raw or "").strip()
    is_email = "@" in clean_id
    return clean_id, is_email, (clean_id.lower() if is_email else clean_id)


async def _find_user(clean_id: str, is_email: bool, session: AsyncSession) -> User | None:
    repo = UserRepository(session)
    user = await (repo.get_by_email(clean_id) if is_email else repo.get_by_mobile(clean_id))
    if user is None or not user.is_active:
        return None
    return user


async def _throttle_reset_step(normalized_key: str, client_ip: str | None, session: AsyncSession) -> None:
    """Shared per-account counter across verify-otp and reset-password, plus per-IP."""
    if client_ip:
        await reset_ip_limiter.hit(throttle_key("pwreset", "ip", client_ip), session)
    await reset_account_limiter.hit(throttle_key("pwreset", "acct", normalized_key), session)


async def _dispatch_otp(is_email: bool, dest: str, otp: str) -> None:
    """Deliver the OTP; never raises (delivery failure must not change the response)."""
    try:
        if is_email:
            await send_password_reset_email(dest, otp)
        else:
            await send_password_reset_sms(dest, otp)
    except Exception as exc:  # noqa: BLE001
        logger.error("event=auth_forgot_password result=delivery_failed error=%s", type(exc).__name__)


GENERIC_FORGOT_MESSAGE = "If that account is registered, a security code has been sent."


async def forgot_password(
    identifier: str,
    session: AsyncSession,
    client_ip: str | None = None,
    schedule=None,
) -> ForgotPasswordResponse:
    """
    Password recovery for an email or mobile identifier.

    * Every request counts against a per-account (5/15min) and per-IP (20/15min)
      budget, whether or not the account exists, and the budget is never reset
      by a "success" - so the endpoint cannot be used to spam or enumerate.
    * Known and unknown accounts get a byte-identical response (message,
      masked destination derived from the INPUT, channel). Delivery is handed
      to `schedule` (e.g. FastAPI BackgroundTasks.add_task) so response time
      does not depend on SMTP/SMS latency.
    """
    clean_id, is_email, normalized_key = _split_identifier(identifier)
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    if client_ip:
        await forgot_ip_limiter.hit(throttle_key("pwforgot", "ip", client_ip), session)
    await forgot_account_limiter.hit(throttle_key("pwforgot", "acct", normalized_key), session)

    response = ForgotPasswordResponse(
        message=GENERIC_FORGOT_MESSAGE,
        destination=mask_email(clean_id) if is_email else mask_mobile(clean_id),
        delivery_channel="EMAIL" if is_email else "SMS",
    )

    user = await _find_user(clean_id, is_email, session)
    if user is None:
        logger.info(
            "event=auth_forgot_password request_id=%s identifier=%s result=non_existent_or_inactive",
            req_id,
            masked_id,
        )
        return response

    # Invalidate any previously unused reset tokens for this user
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used == False)  # noqa: E712
        .values(used=True)
    )

    otp = generate_otp(6)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_otp(otp, user.id),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15),
        )
    )
    await session.commit()

    dest = (user.email or clean_id) if is_email else (user.mobile_number or clean_id)
    if schedule is not None:
        schedule(_dispatch_otp, is_email, dest, otp)
    else:
        await _dispatch_otp(is_email, dest, otp)

    logger.info(
        "event=auth_forgot_password request_id=%s identifier=%s delivery_channel=%s result=sent",
        req_id,
        masked_id,
        response.delivery_channel,
    )
    return response


async def _find_valid_reset_token(user: User, otp: str, session: AsyncSession) -> PasswordResetToken | None:
    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == hash_otp(otp, user.id),
            PasswordResetToken.used == False,  # noqa: E712
            PasswordResetToken.expires_at > datetime.now(tz=timezone.utc),
        )
    )
    return result.scalars().first()


async def verify_otp(
    data: VerifyOtpRequest, session: AsyncSession, client_ip: str | None = None
) -> VerifyOtpResponse:
    """Pre-validate the OTP. Shares one attempt counter with reset_password."""
    clean_id, is_email, normalized_key = _split_identifier(
        data.identifier or data.email or data.mobile_number or ""
    )
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    await _throttle_reset_step(normalized_key, client_ip, session)

    user = await _find_user(clean_id, is_email, session)
    token = await _find_valid_reset_token(user, data.otp, session) if user else None
    if token is None:
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

    logger.info("event=auth_verify_otp result=success request_id=%s identifier=%s", req_id, masked_id)
    return VerifyOtpResponse(valid=True, message="Verification code confirmed.")


async def reset_password(
    data: ResetPasswordRequest, session: AsyncSession, client_ip: str | None = None
) -> None:
    """Verify OTP, set the new password, consume the OTP, revoke all refresh tokens."""
    clean_id, is_email, normalized_key = _split_identifier(
        data.identifier or data.email or data.mobile_number or ""
    )
    masked_id = _mask_identifier(clean_id)
    req_id = get_current_request_id()

    await _throttle_reset_step(normalized_key, client_ip, session)

    user = await _find_user(clean_id, is_email, session)
    token = await _find_valid_reset_token(user, data.otp, session) if user else None
    if token is None:
        # Same status/body for unknown account and wrong/expired code.
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

    user.password_hash = hash_password(data.new_password)
    # Any admin-issued temporary credential is superseded; all outstanding access tokens die with it.
    user.temp_password_expires_at = None
    user.token_version = int(user.token_version or 0) + 1
    session.add(user)
    # The user just chose their own password via a verified OTP: no longer temporary.
    await session.execute(
        update(Employee).where(Employee.user_id == user.id).values(must_change_password=False)
    )
    token.used = True
    session.add(token)

    # Revoke all existing sessions for this user
    await TokenRepository(session).revoke_all_for_user(user.id)
    # The OTP is consumed; clear this account's reset budget.
    await session.execute(
        delete(LoginAttempt).where(
            LoginAttempt.identifier == throttle_key("pwreset", "acct", normalized_key)
        )
    )
    await session.commit()
    logger.info("event=auth_reset_password result=success request_id=%s user_id=%s", req_id, user.id)
