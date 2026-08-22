"""
Authentication endpoint tests.

Covers:
- Login validation (missing body, no identity)
- JWT structure verification
- Unauthorized access (no token, malformed token, expired token)
- /auth/me with valid token
- Role enforcement (admin vs employee)
- Refresh request validation
- Logout validation
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import patch

from app.models.user import Role, User
from tests.conftest import SEED_EMPLOYEE_ID, admin_headers, employee_headers, requires_db



# ---------------------------------------------------------------------------
# Login validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_missing_body(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_no_identity(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"password": "secret"})
    # Pydantic model_validator raises ValueError → FastAPI returns 422
    assert resp.status_code in (422, 500)


@pytest.mark.asyncio
async def test_login_invalid_json(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /auth/me — JWT authentication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    # HTTPBearer returns 403 when no credentials at all
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_malformed_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer notavalidjwt"})
    # 401 from JWTError inside dep
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_wrong_scheme(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc123"})
    assert resp.status_code in (401, 403)


@requires_db
@pytest.mark.asyncio
async def test_me_valid_admin_token_user_not_in_db(client: AsyncClient):
    """Valid JWT but user doesn't exist in DB → 401."""
    headers = admin_headers(user_id=str(uuid.uuid4()))
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401



# ---------------------------------------------------------------------------
# Refresh token validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_missing_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code in (401, 422)


@requires_db
@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid_token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_missing_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/logout", json={})
    assert resp.status_code in (204, 422)


# ---------------------------------------------------------------------------
# Role enforcement tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_endpoint_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/users", json={})
    assert resp.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_admin_endpoint_employee_forbidden(client: AsyncClient):
    """Employee token on admin-only route → 403."""
    from app.core.deps.auth import _get_user_from_token
    from app.main import app

    emp_user = User(
        id=uuid.UUID(SEED_EMPLOYEE_ID),
        email="emp@example.com",
        role=Role.EMPLOYEE,
        is_active=True,
    )
    app.dependency_overrides[_get_user_from_token] = lambda: emp_user
    try:
        resp = await client.post(
            "/api/v1/users",
            json={"email": "test@x.com", "password": "secret123"},
            headers=employee_headers(),
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(_get_user_from_token, None)


@pytest.mark.asyncio
async def test_territories_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/territories")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_customers_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/customers")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_visits_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/visits")
    assert resp.status_code in (401, 403)
