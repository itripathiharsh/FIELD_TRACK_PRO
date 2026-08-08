"""
Integration: geolocation + geofencing (scenarios 10-16).

These target FT-004 (CRITICAL): `_extract_coords_from_wkt` receives a
geoalchemy2 WKBElement, fails to parse it, and silently returns (0.0, 0.0).
Every geofence decision is therefore measured against Null Island, which
INVERTS the check: the correct location is rejected and a location on the
other side of the planet is accepted.

The existing unit tests pass only because they feed coordinates directly to
the pure Haversine function, bypassing the one function that is broken.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.geo_verification_service import GeoVerificationService
from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# --- Scenario 13: WKB -> coordinates (the actual root cause) ----------------

async def test_customer_location_round_trips_from_postgis(seeded_world, db):
    """PostGIS itself stores the coordinates correctly - proving the DB is fine."""
    lat, lng = db.customer_coords(seeded_world["customer_id"])
    assert lat == pytest.approx(seeded_world["customer_lat"], abs=1e-6)
    assert lng == pytest.approx(seeded_world["customer_lng"], abs=1e-6)


async def test_coordinate_extraction_from_orm_value_is_correct(seeded_world):
    """
    FT-004 root cause, isolated.

    Loads the customer through the real ORM path and asserts the helper used by
    check-in/check-out returns the true coordinates. Currently returns (0.0, 0.0).
    """
    import uuid as _uuid

    from app.database import AsyncSessionLocal
    from app.services.customer_service import _extract_coords_from_wkt, get_customer

    async with AsyncSessionLocal() as session:
        customer = await get_customer(_uuid.UUID(seeded_world["customer_id"]), session)
        lat, lng = _extract_coords_from_wkt(getattr(customer, "location", None))

    assert (lat, lng) != (0.0, 0.0), (
        "FT-004: coordinate extraction silently degraded to Null Island (0,0)"
    )
    assert lat == pytest.approx(seeded_world["customer_lat"], abs=1e-4)
    assert lng == pytest.approx(seeded_world["customer_lng"], abs=1e-4)


# --- Scenario 12: no silent (0,0) fallback ----------------------------------

async def test_unparseable_location_must_not_silently_become_origin():
    """
    FT-004 / Rule 9: a parsing failure on security-critical data must raise or
    return an explicit 'unknown', never a permissive default that silently
    relocates the geofence to (0,0).
    """
    from app.services.customer_service import _extract_coords_from_wkt

    with pytest.raises(Exception):
        _extract_coords_from_wkt("this-is-not-a-location")


# --- Scenario 10 & 11: distance decisions via the real API ------------------

async def test_verify_location_at_exact_customer_coordinates_is_valid(
    client: AsyncClient, employee_headers, seeded_world
):
    """Scenario 10: standing exactly on the customer pin must verify as valid."""
    resp = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["distance_m"] == pytest.approx(0.0, abs=5.0), (
        f"FT-004: distance to own coordinates should be ~0m, got {body['distance_m']}m"
    )
    assert body["is_valid"] is True, f"FT-004: exact location rejected: {body}"


async def test_verify_location_far_away_is_invalid(
    client: AsyncClient, employee_headers, seeded_world
):
    """Scenario 11: a genuinely distant location must be rejected."""
    resp = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": 13.0827,   # Chennai, ~290 km away
            "longitude": 80.2707,
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_valid"] is False
    assert body["distance_m"] > seeded_world["geofence_radius_m"]


async def test_null_island_is_not_treated_as_the_customer_site(
    client: AsyncClient, employee_headers, seeded_world
):
    """
    FT-004, stated as an attack: (0,0) is ~8,663 km from the customer and must
    be rejected. Today it is ACCEPTED because the target degrades to (0,0).
    """
    resp = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": 0.0,
            "longitude": 0.0,
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_valid"] is False, (
        "FT-004: check at Null Island accepted - geofence is inverted"
    )


async def test_just_inside_and_just_outside_radius(
    client: AsyncClient, employee_headers, seeded_world
):
    """Boundary behaviour around the 100 m geofence (~0.00045 deg lat = ~50 m)."""
    inside = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": seeded_world["customer_lat"] + 0.00045,
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert inside.json()["is_valid"] is True, f"~50m must be inside 100m: {inside.json()}"

    outside = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": seeded_world["customer_lat"] + 0.00900,  # ~1 km
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert outside.json()["is_valid"] is False


# --- Scenario 14 & 15: check-in through the real endpoint -------------------

async def test_check_in_at_correct_location_succeeds(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """Scenario 14: the core happy path of the entire product."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 8.0,
            "is_mock_location": False,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, f"FT-004: valid check-in rejected: {resp.text}"
    assert resp.json()["status"] == "IN_PROGRESS"

    row = db.fetch_one("SELECT status, check_in_at FROM visits WHERE id = %s", (visit_id,))
    assert row["status"] == "IN_PROGRESS", "check-in must be persisted"
    assert row["check_in_at"] is not None


async def test_check_in_far_from_site_is_rejected_and_state_unchanged(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """Scenario 15: a distant check-in must fail AND must not mutate the visit."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0},
        headers=employee_headers,
    )
    assert resp.status_code == 422

    row = db.fetch_one("SELECT status, check_in_at FROM visits WHERE id = %s", (visit_id,))
    assert row["status"] == "PENDING"
    assert row["check_in_at"] is None


async def test_check_in_at_null_island_is_rejected(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """FT-004 end-to-end: the fraud path must not reach IN_PROGRESS."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={"latitude": 0.0, "longitude": 0.0, "accuracy_m": 5.0},
        headers=employee_headers,
    )
    assert resp.status_code == 422, "FT-004: check-in from (0,0) was accepted"

    row = db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))
    assert row["status"] == "PENDING"


async def test_mock_location_is_rejected_at_check_in(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """Spec 09 non-negotiable #4 - must hold even at the correct coordinates."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0,
            "is_mock_location": True,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422
    assert "mock" in resp.text.lower()


async def test_poor_gps_accuracy_is_rejected(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 500.0,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422
    assert "accuracy" in resp.text.lower()


# --- Scenario 16: check-out uses the same geofence logic --------------------

async def test_check_out_uses_same_geofence_rules(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    good = {
        "latitude": seeded_world["customer_lat"],
        "longitude": seeded_world["customer_lng"],
        "accuracy_m": 8.0,
    }
    assert (await client.post(
        f"/api/v1/visits/{visit_id}/check-in", json=good, headers=employee_headers
    )).status_code == 200, "FT-004 blocks the check-in precondition"

    far = await client.post(
        f"/api/v1/visits/{visit_id}/check-out",
        json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0},
        headers=employee_headers,
    )
    assert far.status_code == 422, "check-out must enforce the geofence too"
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "IN_PROGRESS"

    near = await client.post(
        f"/api/v1/visits/{visit_id}/check-out", json=good, headers=employee_headers
    )
    assert near.status_code == 200, near.text
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "COMPLETED"


# --- Consistency between the two competing distance implementations ---------

async def test_postgis_and_haversine_agree(seeded_world):
    """
    FT-004 / duplication audit: `verify_geo_proximity` (PostGIS, correct but
    never called) and the Haversine service must agree within tolerance.
    """
    import uuid as _uuid

    from app.database import AsyncSessionLocal
    from app.services.customer_service import get_customer, verify_geo_proximity

    device_lat = seeded_world["customer_lat"] + 0.00045
    device_lng = seeded_world["customer_lng"]

    async with AsyncSessionLocal() as session:
        customer = await get_customer(_uuid.UUID(seeded_world["customer_id"]), session)
        is_valid, postgis_distance = await verify_geo_proximity(
            customer, device_lat, device_lng, session
        )

    haversine = GeoVerificationService.calculate_haversine_distance(
        device_lat, device_lng, seeded_world["customer_lat"], seeded_world["customer_lng"]
    )
    assert postgis_distance == pytest.approx(haversine, rel=0.02), (
        f"distance implementations disagree: PostGIS={postgis_distance} Haversine={haversine}"
    )
    assert is_valid is True
