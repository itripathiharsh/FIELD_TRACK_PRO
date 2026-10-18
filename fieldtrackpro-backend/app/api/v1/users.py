"""
Users router — /api/v1/users  (admin-only)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_client_ip
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.admin_security import RoleChangeRequest
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate, UserRead, UserUpdatePassword
from app.services import admin_security_service, user_service

router = APIRouter(prefix="/users", tags=["users"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


@router.post("", response_model=UserRead, status_code=201, dependencies=[AdminOnly])
async def create_user(data: UserCreate, request: Request, current_user: CurrentUser, session: DbSession):
    """Admin: create a new user account (EMPLOYEE only; ADMIN needs a Super Admin; SUPER_ADMIN is never allowed)."""
    return await user_service.create_user(data, session, current_user, get_client_ip(request))


@router.get("/{user_id}", response_model=UserRead, dependencies=[AdminOnly])
async def get_user(user_id: uuid.UUID, session: DbSession):
    """Admin: retrieve a user by ID."""
    return await user_service.get_user_by_id(user_id, session)


@router.patch("/{user_id}/activate", response_model=UserRead, dependencies=[AdminOnly])
async def activate_user(user_id: uuid.UUID, request: Request, current_user: CurrentUser, session: DbSession):
    """Admin: enable a user account (Super Admin accounts: Super Admin only)."""
    return await user_service.toggle_active(current_user, user_id, True, session, get_client_ip(request))


@router.patch("/{user_id}/deactivate", response_model=UserRead, dependencies=[AdminOnly])
async def deactivate_user(user_id: uuid.UUID, request: Request, current_user: CurrentUser, session: DbSession):
    """Admin: disable a user account. The last active Super Admin can never be disabled."""
    return await user_service.toggle_active(current_user, user_id, False, session, get_client_ip(request))


@router.patch("/{user_id}/role", response_model=UserRead, dependencies=[AdminOnly], summary="Super Admin: change a user's role")
async def change_user_role(
    user_id: uuid.UUID,
    data: RoleChangeRequest,
    request: Request,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Change an account's role (EMPLOYEE <-> ADMIN <-> SUPER_ADMIN, one step at a time).

    Super Admin only - an Admin reaching this endpoint is refused (403 SUPER_ADMIN_REQUIRED) and the attempt
    is audited. Requires the caller's own password (`current_password`) and, for anything that grants or
    removes SUPER_ADMIN, `confirm: true`. The last active Super Admin cannot be demoted. The affected
    account's sessions are ended so the new role (or loss of privilege) applies immediately.
    """
    return await admin_security_service.change_user_role(
        current_user, user_id, data.role, data.current_password, data.confirm, session, get_client_ip(request)
    )


@router.patch("/me/password", response_model=TokenResponse)
async def change_my_password(
    data: UserUpdatePassword,
    current_user: CurrentUser,
    session: DbSession,
    response: Response,
):
    """
    Authenticated user: change own password. Clears `must_change_password`, revokes every
    old session and returns a FRESH token pair (same shape as login, must_change_password=false).
    """
    from app.api.v1.auth import _set_refresh_cookie

    tokens = await user_service.update_password(current_user, data, session)
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens
