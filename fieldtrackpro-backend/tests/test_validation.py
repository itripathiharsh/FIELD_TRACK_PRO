"""
Validation tests — server-side rejection of invalid request payloads.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, requires_db


# ---------------------------------------------------------------------------
# Auth validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_login_empty_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": ""})
    # Empty password is valid JSON; real rejection happens at DB lookup
    assert resp.status_code in (401, 500, 503)


@pytest.mark.asyncio
async def test_login_email_and_mobile_both_missing(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"password": "abc"})
    assert resp.status_code in (422, 500)


# ---------------------------------------------------------------------------
# Customer validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_customer_missing_name(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={"contact_number": "1234567890", "address": "somewhere", "location": {"latitude": 0, "longitude": 0}},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_invalid_latitude(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Test",
            "contact_number": "1234567890",
            "address": "somewhere",
            "location": {"latitude": 999, "longitude": 0},  # out of range
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_invalid_longitude(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Test",
            "contact_number": "1234567890",
            "address": "somewhere",
            "location": {"latitude": 0, "longitude": 999},  # out of range
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_missing_location(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={"name": "Test", "contact_number": "1234567890", "address": "somewhere"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Visit validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_visit_missing_fields(client: AsyncClient):
    resp = await client.post("/api/v1/visits", json={}, headers=admin_headers())
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_visit_invalid_uuid(client: AsyncClient):
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": "not-a-uuid",
            "employee_id": "not-a-uuid",
            "scheduled_at": "2030-01-01T00:00:00Z",
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Check-in validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_check_in_missing_coordinates(client: AsyncClient):
    import uuid
    visit_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User creation validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_user_missing_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users",
        json={"email": "new@x.com"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_user_no_identity(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users",
        json={"password": "secure123"},
        headers=admin_headers(),
    )
    # Should fail at service level (422) or DB level
    assert resp.status_code in (422, 500, 503)
