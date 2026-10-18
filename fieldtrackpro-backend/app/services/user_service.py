"""
User management service — refactored to use UserRepository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.deps.auth import temp_password_expired, temp_password_expired_error
from app.core.rate_limiter import LoginRateLimiter, throttle_key
from app.core.security import create_access_token, generate_refresh_token, hash_password, verify_password
from app.models.refresh_token import RefreshToken
from app.schemas.auth import TokenResponse
from app.exceptions.custom import BaseAPIException, DuplicateResourceException
from app.models.employee import Employee
from app.models.user import Role, User
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdatePassword
from app.services import admin_security_service, security_audit_service

#: Wrong "current password" attempts on the change-password endpoints, per account / 15 min.
change_password_limiter = LoginRateLimiter(max_attempts=10)


async def create_user(data: UserCreate, session: AsyncSession, actor: User, client_ip: str | None = None) -> User:
    # Creating an account with a privileged role is a grant of privilege: gate it first.
    await admin_security_service.assert_may_assign_role_on_create(actor, data.role, session, client_ip)
    repo = UserRepository(session)

    clean_email = data.email.strip().lower() if data.email else None
    clean_mobile = data.mobile_number.strip() if data.mobile_number else None

    if not clean_email and not clean_mobile:
        raise BaseAPIException(
            status_code=422,
            detail="email or mobile_number is required",
            error_code="USER_IDENTITY_REQUIRED",
        )
    if clean_email and await repo.email_exists(clean_email):
        raise DuplicateResourceException("Email already registered")
    if clean_mobile and await repo.mobile_exists(clean_mobile):
        raise DuplicateResourceException("Mobile number already registered")

    user = User(
        email=clean_email,
        mobile_number=clean_mobile,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    await repo.add(user)
    await session.flush()
    if data.role == Role.ADMIN:
        security_audit_service.record(
            session, "USER_CREATE_PRIVILEGED", "SUCCESS",
            actor_user_id=actor.id, target_user_id=user.id, new_role=data.role.value, client_ip=client_ip,
        )
    await repo.commit()
    return user


async def get_user_by_id(user_id: uuid.UUID, session: AsyncSession) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")
    return user


async def update_password(user: User, data: UserUpdatePassword, session: AsyncSession) -> TokenResponse:
    """
    Change the caller's own password.

    FT-023. Security consequences applied per `16_authentication.md` section 3:
    every outstanding refresh token for the user is revoked, so a password
    change immediately ends sessions on other devices. This is the entire point
    of changing a password after a suspected compromise.

    This is also the ONLY way out of the admin-issued temporary-password state. The user row is locked
    (SELECT ... FOR UPDATE) and the old password is verified against the locked, current hash, so two
    concurrent requests carrying the same temporary password cannot both succeed: the loser sees the
    new hash and is refused. A successful change clears the temporary-password expiry, so the
    temporary credential is permanently dead and can never be replayed.
    """
    user_id = user.id
    limiter_key = throttle_key("pwchange", "user", str(user_id))
    await change_password_limiter.check_allowed(limiter_key, session)

    locked = (
        await session.execute(
            select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()

    if locked.temp_password_expires_at is not None and temp_password_expired(locked):
        await session.rollback()
        raise temp_password_expired_error()

    if not verify_password(data.old_password, locked.password_hash):
        await session.rollback()
        await change_password_limiter.record_failure(limiter_key, session)
        raise BaseAPIException(
            status_code=400,
            detail="Old password is incorrect",
            error_code="AUTH_WRONG_OLD_PASSWORD",
        )
    if verify_password(data.new_password, locked.password_hash):
        await session.rollback()
        raise BaseAPIException(
            status_code=400,
            detail="New password must be different from the current password",
            error_code="AUTH_PASSWORD_UNCHANGED",
        )

    locked.password_hash = hash_password(data.new_password)
    locked.temp_password_expires_at = None
    locked.token_version = int(locked.token_version or 0) + 1
    session.add(locked)
    # A successful self-service change ends any forced-change state.
    await session.execute(
        update(Employee).where(Employee.user_id == locked.id).values(must_change_password=False)
    )

    token_repo = TokenRepository(session)
    await token_repo.revoke_all_for_user(locked.id)
    # All sessions were just revoked: hand the caller a fresh pair so the app stays signed in.
    access_token = create_access_token(str(locked.id), locked.role.value, token_version=locked.token_version)
    raw_refresh, token_hash = generate_refresh_token()
    await token_repo.add(
        RefreshToken(
            user_id=locked.id,
            token_hash=token_hash,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=settings.jwt_refresh_token_expiry_days),
        )
    )
    await session.commit()
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh, must_change_password=False)


async def toggle_active(
    actor: User, user_id: uuid.UUID, active: bool, session: AsyncSession, client_ip: str | None = None
) -> User:
    """
    Enable or disable an account.

    Deactivation revokes outstanding refresh tokens so the session ends at once
    rather than surviving until the token expires. This is the behaviour the
    auth design attaches to feature B1 ("deactivate employee").

    Super Admin accounts are protected (see admin_security_service.set_user_active): only a Super
    Admin may change them and the last active Super Admin can never be deactivated.
    """
    return await admin_security_service.set_user_active(actor, user_id, active, session, client_ip)
