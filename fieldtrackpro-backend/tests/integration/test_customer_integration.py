"""
Integration: customer contract and persistence.

Targets FT-012 (CustomerRead omits the coordinates the UI must display) and
FT-013 (a realistic "Contact Person" value overflows contact_number varchar(20)
and produces an unhandled 500).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_MARKER, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_admin_creates_customer_and_it_persists(
    client: AsyncClient, admin_headers, seeded_world, created_customers, db
):
    name = f"{TEST_MARKER}Acme Persistence Co"
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": name,
            "contact_number": "+919876500011",
            "address": "12 Integration Way",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "geofence_radius_m": 100,
            "territory_id": seeded_world["territory_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    created_customers.append(resp.json()["id"])

    row = db.fetch_one(
        "SELECT name, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
        "FROM customers WHERE id = %s",
        (resp.json()["id"],),
    )
    assert row is not None, "a 201 must mean the row is committed"
    assert row["name"] == name
    assert float(row["lat"]) == pytest.approx(12.9716, abs=1e-6)
    assert float(row["lng"]) == pytest.approx(77.5946, abs=1e-6)


async def test_created_customer_is_returned_by_list(
    client: AsyncClient, admin_headers, created_customers
):
    name = f"{TEST_MARKER}Listed Co"
    created = await client.post(
        "/api/v1/customers",
        json={
            "name": name,
            "contact_number": "+919876500012",
            "address": "13 Integration Way",
            "location": {"latitude": 12.97, "longitude": 77.59},
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    created_customers.append(created.json()["id"])

    customer_id = created.json()["id"]
    listing = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["id"] == customer_id


# --- FT-012: the read contract must carry the geofence coordinates ----------

async def test_customer_read_exposes_coordinates(
    client: AsyncClient, admin_headers, seeded_world
):
    """
    FT-012: the admin UI has a "GPS & Geofence" column but CustomerRead never
    returns latitude/longitude, so the column is permanently blank.
    """
    resp = await client.get(
        f"/api/v1/customers/{seeded_world['customer_id']}", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    has_nested = isinstance(body.get("location"), dict) and {
        "latitude", "longitude"
    } <= set(body["location"])
    has_flat = "latitude" in body and "longitude" in body
    assert has_nested or has_flat, (
        "FT-012: customer responses must expose the geofence coordinates"
    )

    lat = body["location"]["latitude"] if has_nested else body["latitude"]
    lng = body["location"]["longitude"] if has_nested else body["longitude"]
    assert float(lat) == pytest.approx(seeded_world["customer_lat"], abs=1e-6)
    assert float(lng) == pytest.approx(seeded_world["customer_lng"], abs=1e-6)


# --- FT-013: contact person overflow ----------------------------------------

async def test_long_contact_value_does_not_cause_500(
    client: AsyncClient, admin_headers, created_customers
):
    """
    FT-013: the UI labels the field "Contact Person" but it maps to
    contact_number varchar(20). A 30-char human name currently produces an
    unhandled 500 and the UI shows only "Failed to fetch".
    """
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"{TEST_MARKER}Overflow Co",
            "contact_number": "Jonathan Wellington Smythe III",  # 30 chars
            "address": "14 Integration Way",
            "location": {"latitude": 12.97, "longitude": 77.59},
        },
        headers=admin_headers,
    )
    if resp.status_code == 201:
        created_customers.append(resp.json()["id"])

    assert resp.status_code != 500, (
        "FT-013: over-long contact value must be a validation error, not a crash"
    )
    assert resp.status_code in (201, 400, 422)


async def test_invalid_coordinates_rejected(client: AsyncClient, admin_headers):
    for lat, lng in ((999.0, 77.5), (12.9, 999.0)):
        resp = await client.post(
            "/api/v1/customers",
            json={
                "name": f"{TEST_MARKER}Bad Coords",
                "contact_number": "+919876500013",
                "address": "15 Integration Way",
                "location": {"latitude": lat, "longitude": lng},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422


async def test_customer_update_persists(
    client: AsyncClient, admin_headers, created_customers, db
):
    created = await client.post(
        "/api/v1/customers",
        json={
            "name": f"{TEST_MARKER}Before Update",
            "contact_number": "+919876500014",
            "address": "16 Integration Way",
            "location": {"latitude": 12.97, "longitude": 77.59},
            "geofence_radius_m": 75,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    created_customers.append(cid)

    updated = await client.patch(
        f"/api/v1/customers/{cid}",
        json={"name": f"{TEST_MARKER}After Update", "geofence_radius_m": 150},
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text

    row = db.fetch_one("SELECT name, geofence_radius_m FROM customers WHERE id = %s", (cid,))
    assert row["name"] == f"{TEST_MARKER}After Update"
    assert row["geofence_radius_m"] == 150
