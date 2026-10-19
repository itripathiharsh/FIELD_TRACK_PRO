"""
Auth router — /api/v1/auth
"""
from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.client_ip import get_client_ip
from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.schemas.user import CurrentUserRead, UserUpdatePassword
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _cookie_policy() -> tuple[bool, str]:
    """
    (secure, samesite) for the refresh cookie.

    Production: the web app (Vercel) and API (Render) are different SITES, so
    the cookie only travels on fetch(credentials: 'include') with
    SameSite=None; Secure. Cross-site CSRF exposure is limited by the exact
    CORS allow-list and the Origin check in `_reject_foreign_origin`.
    Dev/test: Lax, not Secure (plain http://localhost).
    """
    is_prod = settings.environment == "production"
    samesite = (settings.refresh_cookie_samesite or ("none" if is_prod else "lax")).lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    secure = is_prod or samesite == "none"
    return secure, samesite


def _refresh_cookie_header(value: str, *, max_age: int, partitioned: bool) -> str:
    """
    Build the Set-Cookie header value for the refresh cookie.

    Starlette's `set_cookie(partitioned=...)` raises ValueError on Python < 3.14 (http.cookies only learned the
    attribute in 3.14) and this service runs on 3.11, so the header is rendered with SimpleCookie (same escaping and
    date format Starlette uses) and `Partitioned` is appended explicitly. `Partitioned` is only emitted together with
    `Secure` (browsers reject it otherwise), i.e. in production.
    """
    secure, samesite = _cookie_policy()
    cookie: SimpleCookie = SimpleCookie()
    cookie[REFRESH_COOKIE_NAME] = value
    morsel = cookie[REFRESH_COOKIE_NAME]
    morsel["path"] = REFRESH_COOKIE_PATH
    morsel["max-age"] = max_age
    if max_age == 0:
        morsel["expires"] = 0
    morsel["httponly"] = True
    if secure:
        morsel["secure"] = True
    morsel["samesite"] = samesite
    header = morsel.OutputString()
    if partitioned and secure:
        header += "; Partitioned"
    return header


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """
    Set the HttpOnly (+Secure in production) refresh token cookie.

    `Partitioned` (CHIPS): the web app (Vercel) and the API are different sites, so this is a third-party
    cookie. Partitioned cookies are still stored/sent when the browser blocks ordinary third-party cookies
    (Chrome/Edge 114+, Firefox 141+, Safari 26.2+). The older unpartitioned cookie of the same name is expired in
    the same response so only one is ever sent (browsers that do not know `Partitioned` still end up with the live one).
    """
    # Order matters: expire the legacy cookie FIRST. A browser that ignores `Partitioned` would treat the live cookie
    # as the same cookie as the legacy one, and expiring it afterwards would delete the session it just received.
    response.headers.append("set-cookie", _refresh_cookie_header("", max_age=0, partitioned=False))
    response.headers.append(
        "set-cookie",
        _refresh_cookie_header(refresh_token, max_age=settings.jwt_refresh_token_expiry_days * 86400, partitioned=True),
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie: the partitioned one and any legacy unpartitioned one (distinct cookies).

    Same name, path, Secure, SameSite (and Partitioned) as the cookie being removed, or the browser keeps it."""
    response.headers.append("set-cookie", _refresh_cookie_header("", max_age=0, partitioned=True))
    response.headers.append("set-cookie", _refresh_cookie_header("", max_age=0, partitioned=False))


def _client_ip(request: Request) -> str | None:
    # Never trust the client-controlled leftmost X-Forwarded-For entry (see app/core/client_ip.py).
    return get_client_ip(request)


def _reject_foreign_origin(request: Request) -> None:
    """
    Cookie-authenticated refresh/logout: if the browser sent an Origin header it
    must be an allowed origin (CSRF defence for SameSite=None). Requests with no
    Origin header (native/mobile clients, curl) are not browser-driven and pass.
    """
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_allowed_origins:
        raise BaseAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
            error_code="AUTH_ORIGIN_NOT_ALLOWED",
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
    """
    Exchange a valid refresh token for a new token pair (rotation).

    Token transport: the web app relies on the HttpOnly cookie. The JSON body
    (`refresh_token` in the request and response) is intentionally kept for the
    Android client, which has no cookie jar and stores the token in encrypted
    storage. A replayed (already-rotated) token revokes all of the user's sessions.
    """
    raw_refresh = None
    if data and data.refresh_token:
        raw_refresh = data.refresh_token.strip()
    if not raw_refresh:
        raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
        if raw_refresh:
            _reject_foreign_origin(request)

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
            _reject_foreign_origin(request)

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


@router.post("/change-password", response_model=TokenResponse, summary="Change my password")
async def change_password(
    data: UserUpdatePassword, current_user: CurrentUser, session: DbSession, response: Response
) -> TokenResponse:
    """
    Change the caller's own password (same behaviour as PATCH /users/me/password; this is the
    canonical path for the forced-change flow). Requires `old_password` + `new_password`
    (8-128 chars, <= 72 bytes, different from the current one). Clears
    `must_change_password`, revokes ALL old refresh tokens and returns a fresh token pair.
    """
    tokens = await user_service.update_password(current_user, data, session)
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=200, summary="Request password reset")
async def forgot_password_request(
    data: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
) -> ForgotPasswordResponse:
    """Initiate the password recovery flow via email or SMS."""
    identifier = data.identifier or data.email or data.mobile_number or ""
    return await auth_service.forgot_password(
        identifier, session, client_ip=_client_ip(request), schedule=background.add_task
    )


@router.post("/verify-otp", response_model=VerifyOtpResponse, status_code=200, summary="Pre-verify reset OTP")
async def verify_otp_request(data: VerifyOtpRequest, request: Request, session: DbSession) -> VerifyOtpResponse:
    """Validate 6-digit OTP code before proceeding to password reset."""
    return await auth_service.verify_otp(data, session, client_ip=_client_ip(request))


@router.post("/reset-password", status_code=200, summary="Complete password reset")
async def reset_password(data: ResetPasswordRequest, request: Request, session: DbSession):
    """Verify reset code, update password, and revoke active refresh tokens."""
    await auth_service.reset_password(data, session, client_ip=_client_ip(request))
    return {"message": "Password updated successfully"}
