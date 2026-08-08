"""
API route registration tests — verifies every expected endpoint is reachable.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, employee_headers

# Map: (method, path) → expected status when called with no auth
ROUTES = [
    ("GET",  "/api/v1/health"),
    ("GET",  "/api/v1/health/db"),
    ("GET",  "/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET",  "/api/v1/auth/me"),
    ("GET",  "/api/v1/employees"),
    ("POST", "/api/v1/employees"),
    ("GET",  "/api/v1/employees/me"),
    ("GET",  "/api/v1/territories"),
    ("POST", "/api/v1/territories"),
    ("GET",  "/api/v1/customers"),
    ("POST", "/api/v1/customers"),
    ("GET",  "/api/v1/visits"),
    ("POST", "/api/v1/visits"),
    ("GET",  "/api/v1/visits/me/today"),
]


@pytest.mark.asyncio
async def test_all_routes_exist(client: AsyncClient):
    """
    Verify every expected API path responds — even if with auth error (401/403/422).
    A 404 means the route is NOT registered.
    A 405 means method not allowed (wrong method used).
    Anything else (401/403/422/500) means the route IS registered.
    """
    for method, path in ROUTES:
        resp = await client.request(method, path, json={})
        assert resp.status_code != 404, (
            f"Route NOT FOUND: {method} {path} → 404"
        )
        assert resp.status_code != 405, (
            f"Method Not Allowed: {method} {path} → 405"
        )


@pytest.mark.asyncio
async def test_openapi_schema_generated(client: AsyncClient):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    paths = list(schema["paths"].keys())
    # Verify key paths are present
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/visits" in paths
    assert "/api/v1/employees" in paths
    assert "/api/v1/customers" in paths
    assert "/api/v1/territories" in paths
