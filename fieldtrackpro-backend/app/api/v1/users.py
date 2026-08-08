"""
Users router — /api/v1/users  (admin-only)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.user import UserCreate, UserRead, UserUpdatePassword
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


@router.post("", response_model=UserRead, status_code=201, dependencies=[AdminOnly])
async def create_user(data: UserCreate, session: DbSession):
    """Admin: create a new user account."""
    return await user_service.create_user(data, session)


@router.get("/{user_id}", response_model=UserRead, dependencies=[AdminOnly])
async def get_user(user_id: uuid.UUID, session: DbSession):
    """Admin: retrieve a user by ID."""
    return await user_service.get_user_by_id(user_id, session)


@router.patch("/{user_id}/activate", response_model=UserRead, dependencies=[AdminOnly])
async def activate_user(user_id: uuid.UUID, session: DbSession):
    """Admin: enable a user account."""
    return await user_service.toggle_active(user_id, True, session)


@router.patch("/{user_id}/deactivate", response_model=UserRead, dependencies=[AdminOnly])
async def deactivate_user(user_id: uuid.UUID, session: DbSession):
    """Admin: disable a user account."""
    return await user_service.toggle_active(user_id, False, session)


@router.patch("/me/password", status_code=204)
async def change_my_password(
    data: UserUpdatePassword,
    current_user: CurrentUser,
    session: DbSession,
):
    """Authenticated user: change own password."""
    await user_service.update_password(current_user, data, session)
