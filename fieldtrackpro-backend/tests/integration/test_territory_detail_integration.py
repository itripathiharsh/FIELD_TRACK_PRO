"""
Integration: territory detail endpoint.

Covers GET /api/v1/territories/{id} which previously had no direct test coverage.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_admin_can_get_territory_by_id(client: AsyncClient, admin_headers, seeded_world):
    """Admin can retrieve a territory by ID."""
    resp = await client.get(
        f"/api/v1/territories/{seeded_world['territory_id']}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(seeded_world["territory_id"])
    assert "name" in data
    assert "created_at" in data


async def test_employee_can_get_territory_by_id(client: AsyncClient, employee_headers, seeded_world):
    """Employee can also retrieve territory details (AnyAuth)."""
    resp = await client.get(
        f"/api/v1/territories/{seeded_world['territory_id']}",
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(seeded_world["territory_id"])


async def test_get_territory_not_found(client: AsyncClient, admin_headers):
    """Requesting a non-existent territory returns 404."""
    import uuid
    resp = await client.get(
        f"/api/v1/territories/{uuid.uuid4()}",
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_unauthenticated_cannot_get_territory(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.get(f"/api/v1/territories/{seeded_world['territory_id']}")
    assert resp.status_code == 401
