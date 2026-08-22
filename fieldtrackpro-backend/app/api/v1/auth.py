"""
Auth router — /api/v1/auth
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import CurrentUserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set HttpOnly, Secure, SameSite refresh token cookie."""
    is_prod = settings.environment == "production"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expiry_days * 86400,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    is_prod = settings.environment == "production"
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(data: LoginRequest, response: Response, session: DbSession) -> TokenResponse:
    """Authenticate and receive access token + set HttpOnly refresh token cookie."""
    result = await auth_service.login(data, session)
    _set_refresh_cookie(response, result.refresh_token)
    return result


@router.post("/refresh", response_model=TokenResponse, summary="Refresh tokens")
async def refresh(
    request: Request,
    response: Response,
    session: DbSession,
    data: RefreshRequest | None = None,
) -> TokenResponse:
    """Exchange a valid refresh token (from body or HttpOnly cookie) for a new token pair (rotation)."""
    raw_refresh = None
    if data and data.refresh_token:
        raw_refresh = data.refresh_token.strip()
    if not raw_refresh:
        raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)

    if not raw_refresh:
        raise BaseAPIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            error_code="AUTH_INVALID_REFRESH_TOKEN",
        )

    result = await auth_service.refresh_tokens(raw_refresh, session)
    _set_refresh_cookie(response, result.refresh_token)
    return result


@router.post("/logout", status_code=204, summary="Logout")
async def logout(
    request: Request,
    response: Response,
    session: DbSession,
    data: RefreshRequest | None = None,
) -> None:
    """Revoke the supplied refresh token (from body or HttpOnly cookie) and clear cookie."""
    raw_refresh = None
    if data and data.refresh_token:
        raw_refresh = data.refresh_token.strip()
    if not raw_refresh:
        raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)

    if raw_refresh:
        await auth_service.logout(raw_refresh, session)

    _clear_refresh_cookie(response)


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
