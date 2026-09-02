"""
FastAPI dependency: resolve and authenticate the current user from the
Bearer token in the Authorization header.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.database import get_async_session
from app.exceptions.custom import ForbiddenException, UnauthorizedException
from app.models.user import Role, User

_bearer = HTTPBearer(auto_error=True)


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

    from app.core.context import set_current_user_id
    set_current_user_id(str(user.id))

    return user


# ---------------------------------------------------------------------------
# Public dependency aliases
# ---------------------------------------------------------------------------

CurrentUser = Annotated[User, Depends(_get_user_from_token)]


def require_role(*roles: Role):
    """Return a FastAPI dependency that enforces the caller has one of *roles*."""

    async def _check(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise ForbiddenException("Insufficient permissions")
        return current_user

    return _check
