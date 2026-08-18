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
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.schemas.user import CurrentUserRead
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


@router.get("/me", response_model=CurrentUserRead, summary="Current user")
async def me(current_user: CurrentUser, session: DbSession) -> CurrentUserRead:
    """
    Return identity information for the authenticated caller.

    FT-011: includes `full_name`, `territory_id` and `employee_id` so the client
    can render the user shell and scope employee views without guessing.
    """
    return await auth_service.build_current_user(current_user, session)


@router.post("/forgot-password", status_code=202, summary="Request password reset")
async def forgot_password_request(data: ForgotPasswordRequest, session: DbSession):
    """Initiate the password recovery flow via email."""
    await auth_service.forgot_password(data.email, session)
    return {"message": "If that email is registered, you will receive a reset code shortly."}


@router.post("/reset-password", status_code=200, summary="Complete password reset")
async def reset_password(data: ResetPasswordRequest, session: DbSession):
    """Verify reset code and update password."""
    await auth_service.reset_password(data, session)
    return {"message": "Password updated successfully"}
