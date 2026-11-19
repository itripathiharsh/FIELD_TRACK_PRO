"""
FastAPI dependency: resolve and authenticate the current user from the
Bearer token in the Authorization header.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException, ForbiddenException, UnauthorizedException
from app.models.user import Role, User

_bearer = HTTPBearer(auto_error=True)


# Endpoints a user with a pending forced password change may still call (paths relative to
# the API prefix). Everything else answers 403 PASSWORD_CHANGE_REQUIRED.
_PASSWORD_CHANGE_EXEMPT: set[tuple[str, str]] = {
    ("GET", "/auth/me"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/change-password"),
    ("PATCH", "/users/me/password"),
}


# Self-service endpoints an ACCOUNTANT may call without an explicit role grant (own session, own
# password, own profile, own notifications). Every other endpoint must admit ACCOUNTANT by name
# through require_role(...); see _enforce_accountant_scope.
_ACCOUNTANT_SELF_SERVICE: set[tuple[str, str]] = _PASSWORD_CHANGE_EXEMPT | {
    ("GET", "/employees/me"),
    ("GET", "/notifications/me"),
    ("GET", "/notifications/unread-count"),
    ("PATCH", "/notifications/read-all"),
}

#: request.state flag set by a require_role(...) check that lists ACCOUNTANT, BEFORE the user resolves.
_ACCOUNTANT_GRANT_FLAG = "accountant_role_granted"


def _api_path(request: Request) -> str:
    path = request.url.path
    prefix = settings.api_v1_prefix.rstrip("/")
    if prefix and path.startswith(prefix):
        path = path[len(prefix):]
    return path.rstrip("/") or "/"


def _is_password_change_exempt(request: Request) -> bool:
    return (request.method.upper(), _api_path(request)) in _PASSWORD_CHANGE_EXEMPT


def _enforce_accountant_scope(user: User, request: Request) -> None:
    """
    ACCOUNTANT is read-only finance access and must never fall into code that treats "not an EMPLOYEE"
    as "an administrator". It therefore fails CLOSED: an accountant passes authentication only on an
    endpoint whose role check names ACCOUNTANT explicitly, or on the short self-service list above.
    Endpoints that merely require "any signed-in user" answer 403 to an accountant.
    """
    if user.role != Role.ACCOUNTANT:
        return
    if getattr(request.state, _ACCOUNTANT_GRANT_FLAG, False):
        return
    if (request.method.upper(), _api_path(request)) in _ACCOUNTANT_SELF_SERVICE:
        return
    raise ForbiddenException("Insufficient permissions")


def temp_password_expired(user: User) -> bool:
    """True when an admin-issued temporary password is pending AND its expiry has passed."""
    expires = user.temp_password_expires_at
    return expires is not None and expires <= datetime.now(tz=timezone.utc)


def temp_password_expired_error() -> BaseAPIException:
    return BaseAPIException(
        detail="Your temporary password has expired. Ask your administrator to reset it again.",
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_code="AUTH_TEMP_PASSWORD_EXPIRED",
    )


async def _enforce_password_change(user: User, request: Request, session: AsyncSession) -> None:
    # An admin-issued temporary password that has expired is dead everywhere - including the
    # change-password endpoints that a pending forced change normally still allows.
    temp_pending = user.temp_password_expires_at is not None
    if temp_pending and temp_password_expired(user):
        raise temp_password_expired_error()
    if _is_password_change_exempt(request):
        return
    # The forced-change gate is UNCONDITIONAL for an admin-issued temporary password; the
    # ENFORCE_PASSWORD_CHANGE setting only governs legacy "initial password" accounts.
    if not (settings.enforce_password_change or temp_pending):
        return
    from sqlalchemy import select
    from app.models.employee import Employee

    flagged = (
        await session.execute(select(Employee.must_change_password).where(Employee.user_id == user.id))
    ).scalar_one_or_none()
    if flagged:
        raise BaseAPIException(
            detail="You must change your temporary password before continuing.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PASSWORD_CHANGE_REQUIRED",
        )


async def _get_user_from_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Decode JWT and load User from DB. Raises 401 on any failure."""
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException("Could not validate credentials")
    except JWTError:
        raise UnauthorizedException("Could not validate credentials")

    from sqlalchemy import select

    try:
        result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
    except Exception:
        raise UnauthorizedException("Could not validate credentials")

    if user is None or not user.is_active:
        raise UnauthorizedException("Could not validate credentials")

    # Session invalidation: the token must have been issued under the account's CURRENT token
    # version (bumped by admin password reset / role change). Tokens minted before the `tv`
    # claim existed count as version 0, so existing sessions keep working until the first bump.
    if int(payload.get("tv", 0) or 0) != int(user.token_version or 0):
        raise UnauthorizedException("Could not validate credentials")

    from app.core.context import set_current_user_id
    set_current_user_id(str(user.id))

    return user


async def _get_enforced_user(
    request: Request,
    user: Annotated[User, Depends(_get_user_from_token)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Authenticated user + forced-password-change gate + accountant scope (every CurrentUser endpoint)."""
    await _enforce_password_change(user, request, session)
    _enforce_accountant_scope(user, request)
    return user


# ---------------------------------------------------------------------------
# Public dependency aliases
# ---------------------------------------------------------------------------

CurrentUser = Annotated[User, Depends(_get_enforced_user)]


def require_role(*roles: Role):
    """
    Return a FastAPI dependency that enforces the caller has one of *roles*.

    Privilege is hierarchical: asking for ADMIN also admits SUPER_ADMIN (a strict superset),
    while asking for SUPER_ADMIN admits only SUPER_ADMIN. The caller's role is the one stored in
    the database for the current request, never a claim from the token.
    """
    allowed = set(roles)
    if Role.ADMIN in allowed:
        allowed.add(Role.SUPER_ADMIN)
    grants_accountant = Role.ACCOUNTANT in allowed

    async def _grant(request: Request) -> None:
        # Runs before the user is resolved (declared first): tells _enforce_accountant_scope that this
        # endpoint names ACCOUNTANT explicitly. Grants nothing by itself - _check below still decides.
        if grants_accountant:
            setattr(request.state, _ACCOUNTANT_GRANT_FLAG, True)

    async def _check(_granted: None = Depends(_grant), current_user: User = Depends(_get_enforced_user)) -> User:
        if current_user.role not in allowed:
            raise ForbiddenException("Insufficient permissions")
        return current_user

    _check.allowed_roles = frozenset(allowed)  # type: ignore[attr-defined]  (introspection / tests)
    return _check


#: Convenience dependency: only a Super Admin (role management, privileged account operations).
SuperAdminOnly = Depends(require_role(Role.SUPER_ADMIN))
