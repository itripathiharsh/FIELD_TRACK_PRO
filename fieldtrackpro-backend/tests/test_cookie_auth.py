"""
Tests for HttpOnly cookie-based refresh token authentication, rotation, and logout.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.user import Role, User
from app.schemas.auth import TokenResponse


@pytest.mark.asyncio
async def test_login_sets_httponly_refresh_cookie():
    """POST /auth/login sets an HttpOnly refresh_token cookie and returns TokenResponse."""
    fake_token_response = TokenResponse(
        access_token="test_access_token_123",
        refresh_token="test_raw_refresh_token_abc",
    )

    with patch("app.services.auth_service.login", new=AsyncMock(return_value=fake_token_response)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "cookie_user@example.com", "password": "ValidPassword123!"},
            )

            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["access_token"] == "test_access_token_123"
            assert data["refresh_token"] == "test_raw_refresh_token_abc"

            # Check Set-Cookie header attributes
            set_cookie_header = resp.headers.get("set-cookie", "")
            assert "refresh_token=" in set_cookie_header
            assert "HttpOnly" in set_cookie_header
            assert "Path=/api/v1/auth" in set_cookie_header


@pytest.mark.asyncio
async def test_refresh_with_cookie_only():
    """POST /auth/refresh reads refresh token from HttpOnly cookie, rotates token, and updates cookie."""
    fake_rotated_response = TokenResponse(
        access_token="new_access_token_456",
        refresh_token="new_rotated_refresh_token_def",
    )

    with patch("app.services.auth_service.refresh_tokens", new=AsyncMock(return_value=fake_rotated_response)) as mock_refresh:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={},
                cookies={"refresh_token": "existing_cookie_token_123"},
            )

            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["access_token"] == "new_access_token_456"

            mock_refresh.assert_called_once()
            assert mock_refresh.call_args[0][0] == "existing_cookie_token_123"

            # Verify updated cookie
            set_cookie_header = resp.headers.get("set-cookie", "")
            assert "new_rotated_refresh_token_def" in set_cookie_header


@pytest.mark.asyncio
async def test_refresh_with_body_payload_for_mobile():
    """POST /auth/refresh accepts refresh token from request body for Android/mobile clients."""
    fake_rotated_response = TokenResponse(
        access_token="mobile_access_token_789",
        refresh_token="mobile_refresh_token_ghi",
    )

    with patch("app.services.auth_service.refresh_tokens", new=AsyncMock(return_value=fake_rotated_response)) as mock_refresh:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "body_refresh_token_mobile"},
            )

            assert resp.status_code == 200, resp.text
            assert resp.json()["access_token"] == "mobile_access_token_789"
            mock_refresh.assert_called_once()
            assert mock_refresh.call_args[0][0] == "body_refresh_token_mobile"


@pytest.mark.asyncio
async def test_refresh_without_cookie_or_body_fails():
    """POST /auth/refresh without cookie or body returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 401
        assert "Refresh token required" in resp.text


@pytest.mark.asyncio
async def test_logout_clears_cookie_and_revokes():
    """POST /auth/logout revokes token and clears the HttpOnly cookie."""
    with patch("app.services.auth_service.logout", new=AsyncMock()) as mock_logout:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/logout",
                json={},
                cookies={"refresh_token": "cookie_to_logout_123"},
            )

            assert resp.status_code == 204
            mock_logout.assert_called_once()
            assert mock_logout.call_args[0][0] == "cookie_to_logout_123"

            # Verify Set-Cookie clears or expires the cookie
            set_cookie_header = resp.headers.get("set-cookie", "")
            assert 'refresh_token=""' in set_cookie_header or 'Max-Age=0' in set_cookie_header or 'expires=' in set_cookie_header.lower()
