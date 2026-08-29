"""
Integration tests for Maps, Geo & Location fixes (WEB-MAP-001 through WEB-MAP-014).
"""
import uuid
import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_MARKER, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_customer_map_locations_territory_filter(
    client: AsyncClient,
    admin_headers: dict[str, str],
    seeded_world: dict,
    created_customers: list,
):
    """
    WEB-MAP-004: getCustomerMapLocations with territory_id returns only scoped customer pins
    with lightweight coordinate fields.
    """
    # Create a customer in the seeded territory
    res1 = await client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={
            "name": f"{TEST_MARKER}Map Filtered Outlet",
            "contact_number": "+919876543210",
            "location": {"latitude": 26.8467, "longitude": 80.9462},
            "geofence_radius_m": 75,
            "territory_id": seeded_world["territory_id"],
        },
    )
    assert res1.status_code == 201
    cust_id = res1.json()["id"]
    created_customers.append(cust_id)

    res = await client.get(
        f"/api/v1/customers/map-locations?territory_id={seeded_world['territory_id']}",
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    matching = [c for c in data if c["id"] == cust_id]
    assert len(matching) == 1
    assert matching[0]["name"] == f"{TEST_MARKER}Map Filtered Outlet"
    assert round(matching[0]["latitude"], 4) == 26.8467
    assert round(matching[0]["longitude"], 4) == 80.9462


async def test_paginated_geo_logs_endpoint(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    """
    WEB-MAP-012: GET /api/v1/geo/logs provides paginated audit log entries with customer/employee context
    and X-Total-Count header, eliminating N+1 requests.
    """
    res = await client.get(
        "/api/v1/geo/logs?skip=0&limit=10",
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert "X-Total-Count" in res.headers
    total = int(res.headers["X-Total-Count"])
    assert total >= 0

    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        log_entry = data[0]
        assert "verification_type" in log_entry
        assert "attempted_at" in log_entry
        assert "is_valid" in log_entry
        assert "distance_from_customer_m" in log_entry


async def test_zero_zero_coordinates_handling(
    client: AsyncClient,
    admin_headers: dict[str, str],
    created_customers: list,
):
    """
    WEB-MAP-005: 0,0 coordinates are accepted as valid without silent corruption.
    """
    res = await client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={
            "name": f"{TEST_MARKER}Zero Coord Customer {uuid.uuid4().hex[:6]}",
            "contact_number": "+919876543214",
            "location": {"latitude": 0.0, "longitude": 0.0},
            "geofence_radius_m": 100,
        },
    )
    assert res.status_code == 201
    cust_data = res.json()
    created_customers.append(cust_data["id"])
    assert cust_data["location"] is not None
    assert cust_data["location"]["latitude"] == 0.0
    assert cust_data["location"]["longitude"] == 0.0
