"""
Auth router — /api/v1/auth
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(data: LoginRequest, session: DbSession):
    """Authenticate and receive access + refresh token pair."""
    return await auth_service.login(data, session)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh tokens")
async def refresh(data: RefreshRequest, session: DbSession):
    """Exchange a valid refresh token for a new token pair (rotation)."""
    return await auth_service.refresh_tokens(data.refresh_token, session)


@router.post("/logout", status_code=204, summary="Logout")
async def logout(data: RefreshRequest, session: DbSession):
    """Revoke the supplied refresh token."""
    await auth_service.logout(data.refresh_token, session)


@router.get("/me", response_model=dict, summary="Current user")
async def me(current_user: CurrentUser):
    """Return identity information for the authenticated caller."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "mobile_number": current_user.mobile_number,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
    }
