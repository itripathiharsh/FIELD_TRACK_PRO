"""
Integration tests for Geographic Territory and Coverage functionality.
"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_MARKER, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_create_territory_with_geographic_data(client: AsyncClient, admin_headers):
    """Admin can create a territory with latitude, longitude, and radius_km."""
    payload = {
        "name": f"{TEST_MARKER}Lucknow Sales Zone",
        "center_latitude": 26.8467,
        "center_longitude": 80.9462,
        "radius_km": 10.0,
        "status": "ACTIVE",
    }
    resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == f"{TEST_MARKER}Lucknow Sales Zone"
    assert data["center_latitude"] == 26.8467
    assert data["center_longitude"] == 80.9462
    assert data["radius_km"] == 10.0
    assert data["status"] == "ACTIVE"


async def test_reject_invalid_latitude(client: AsyncClient, admin_headers):
    """API rejects latitude outside [-90, 90]."""
    payload = {
        "name": "Invalid Lat Territory",
        "center_latitude": 95.0,
        "center_longitude": 80.0,
        "radius_km": 5.0,
    }
    resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_reject_invalid_longitude(client: AsyncClient, admin_headers):
    """API rejects longitude outside [-180, 180]."""
    payload = {
        "name": "Invalid Lng Territory",
        "center_latitude": 26.0,
        "center_longitude": 185.0,
        "radius_km": 5.0,
    }
    resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_reject_zero_or_negative_radius(client: AsyncClient, admin_headers):
    """API rejects zero or negative radius."""
    for r in [0, -10]:
        payload = {
            "name": "Bad Radius Territory",
            "center_latitude": 26.0,
            "center_longitude": 80.0,
            "radius_km": r,
        }
        resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
        assert resp.status_code == 422


async def test_territory_radius_accepts_whole_numbers(client: AsyncClient, admin_headers):
    """Territory distance/radius must be a whole number: 10, 25, 50, 100 all accepted."""
    for whole_km in (10, 25, 50, 100):
        payload = {
            "name": f"{TEST_MARKER}Whole Km Territory {whole_km}",
            "center_latitude": 26.0,
            "center_longitude": 80.0,
            "radius_km": whole_km,
        }
        resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["radius_km"] == whole_km
        assert isinstance(data["radius_km"], int)


async def test_territory_radius_rejects_fractional_values_on_create(client: AsyncClient, admin_headers):
    """Territory distance/radius must be a whole number: 10.1/10.5/25.75 all rejected."""
    for fractional_km in (10.1, 10.5, 25.75):
        payload = {
            "name": "Fractional Radius Territory",
            "center_latitude": 26.0,
            "center_longitude": 80.0,
            "radius_km": fractional_km,
        }
        resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
        assert resp.status_code == 422, resp.text


async def test_territory_radius_rejects_fractional_value_on_update(
    client: AsyncClient, admin_headers, seeded_world
):
    """A fractional radius must also be rejected on PATCH, not just create."""
    tid = seeded_world["territory_id"]
    resp = await client.patch(
        f"/api/v1/territories/{tid}",
        json={"radius_km": 10.5},
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text


async def test_reject_excessive_radius(client: AsyncClient, admin_headers):
    """API rejects radius exceeding MAX_TERRITORY_RADIUS_KM (500 km)."""
    payload = {
        "name": "Huge Territory",
        "center_latitude": 26.0,
        "center_longitude": 80.0,
        "radius_km": 501.0,
    }
    resp = await client.post("/api/v1/territories", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_update_territory_center_radius_name(client: AsyncClient, admin_headers):
    """Admin can update territory center, radius, and name."""
    create_resp = await client.post(
        "/api/v1/territories",
        json={
            "name": f"{TEST_MARKER}Initial Territory",
            "center_latitude": 26.8,
            "center_longitude": 80.9,
            "radius_km": 10.0,
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["id"]

    # Update radius and name
    patch_resp = await client.patch(
        f"/api/v1/territories/{tid}",
        json={
            "name": f"{TEST_MARKER}Updated Lucknow Zone",
            "radius_km": 15.0,
            "center_latitude": 26.85,
            "center_longitude": 80.95,
        },
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    pdata = patch_resp.json()
    assert pdata["name"] == f"{TEST_MARKER}Updated Lucknow Zone"
    assert pdata["radius_km"] == 15.0
    assert pdata["center_latitude"] == 26.85
    assert pdata["center_longitude"] == 80.95


async def test_existing_territory_without_geographic_data_remains_valid(client: AsyncClient, admin_headers):
    """Creating a territory without lat/lon/radius leaves them null without breaking."""
    create_resp = await client.post(
        "/api/v1/territories",
        json={"name": f"{TEST_MARKER}Legacy Unconfigured Territory"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["name"] == f"{TEST_MARKER}Legacy Unconfigured Territory"
    assert data["center_latitude"] is None
    assert data["center_longitude"] is None
    assert data["radius_km"] is None
    assert data["status"] == "ACTIVE"


async def test_unauthorized_user_cannot_create_or_modify_territory(
    client: AsyncClient, employee_headers, seeded_world
):
    """Employees cannot create or modify territories."""
    tid = seeded_world["territory_id"]
    create_resp = await client.post(
        "/api/v1/territories",
        json={"name": "Forbidden Territory"},
        headers=employee_headers,
    )
    assert create_resp.status_code == 403

    patch_resp = await client.patch(
        f"/api/v1/territories/{tid}",
        json={"name": "Hacked Name"},
        headers=employee_headers,
    )
    assert patch_resp.status_code == 403


async def test_representative_assignment_and_removal(client: AsyncClient, admin_headers, seeded_world):
    """Admin can assign and remove a field representative from a territory via PATCH /employees/{id}."""
    emp_id = seeded_world["employee_id"]
    tid = seeded_world["territory_id"]

    # Assign employee to territory
    assign_resp = await client.patch(
        f"/api/v1/employees/{emp_id}",
        json={"territory_id": str(tid)},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["territory_id"] == str(tid)

    # Remove employee from territory
    remove_resp = await client.patch(
        f"/api/v1/employees/{emp_id}",
        json={"territory_id": None},
        headers=admin_headers,
    )
    assert remove_resp.status_code == 200
    assert remove_resp.json()["territory_id"] is None
