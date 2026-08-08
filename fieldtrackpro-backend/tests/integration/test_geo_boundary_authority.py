"""
Integration: PostGIS must be the geofence authority, especially at the boundary.

FT-072. Discovered by mutation testing during the final forensic pass.

`verify_device_against_customer` passes a PostGIS `ST_Distance` result into
`GeoVerificationService.verify_location` as `measured_distance_m`. The service
falls back to a spherical Haversine calculation when that argument is omitted.

Replacing the PostGIS distance with `None` did not fail a single existing test,
because at the distances those tests use (0 m, ~50 m, 290 km) both
implementations agree on the verdict. They do not agree everywhere:

    device 12.97250, 77.5946 vs customer 12.9716, 77.5946, radius 100 m
        PostGIS  (WGS-84 spheroid)  ->  99.57 m  -> INSIDE
        Haversine (sphere, R=6371km) -> 100.08 m -> OUTSIDE

A ~0.5% systematic difference is irrelevant at 290 km and decisive at the
geofence edge. Whichever implementation runs therefore changes a real
business outcome: whether a field representative can check in.

These tests pin PostGIS as the authority so the fallback can never silently
take over, and record the measurable divergence so a future refactor cannot
"simplify" the fallback away without noticing.

Nothing here changes behaviour - the current implementation already uses
PostGIS. This is the missing detection.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.geo_verification_service import GeoVerificationService
from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

# Chosen so that PostGIS and Haversine straddle a 100 m radius.
BOUNDARY_LAT = 12.97250
BOUNDARY_LNG = 77.5946


async def _customer(session, customer_id: str):
    from app.services.customer_service import get_customer

    return await get_customer(uuid.UUID(customer_id), session)


async def test_geofence_decision_uses_postgis_not_haversine(seeded_world):
    """
    At a point where the two implementations disagree, the service must follow
    PostGIS. If this fails, the Haversine fallback has taken over the decision.
    """
    from app.database import AsyncSessionLocal
    from app.services.customer_service import (
        measure_distance_to_customer,
        verify_device_against_customer,
    )

    async with AsyncSessionLocal() as session:
        customer = await _customer(session, seeded_world["customer_id"])

        postgis_distance = await measure_distance_to_customer(
            customer, BOUNDARY_LAT, BOUNDARY_LNG, session
        )
        result = await verify_device_against_customer(
            customer,
            session,
            device_lat=BOUNDARY_LAT,
            device_lng=BOUNDARY_LNG,
            accuracy_m=5.0,
        )

    haversine_distance = GeoVerificationService.calculate_haversine_distance(
        BOUNDARY_LAT, BOUNDARY_LNG, seeded_world["customer_lat"], seeded_world["customer_lng"]
    )

    # Guard the premise: if these ever converge, this test has stopped testing
    # anything and must be re-tuned rather than silently passing.
    assert postgis_distance != pytest.approx(haversine_distance, abs=0.05), (
        "test premise broken: the two implementations no longer diverge at this "
        f"point (postgis={postgis_distance}, haversine={haversine_distance})"
    )

    assert result.distance_m == pytest.approx(postgis_distance, abs=0.01), (
        "FT-072: the reported distance did not come from PostGIS "
        f"(service={result.distance_m}, postgis={postgis_distance}, "
        f"haversine={haversine_distance})"
    )


async def test_reported_distance_always_matches_postgis(seeded_world):
    """Across the whole range, the audited figure is the PostGIS figure."""
    from app.database import AsyncSessionLocal
    from app.services.customer_service import (
        measure_distance_to_customer,
        verify_device_against_customer,
    )

    points = [
        ("same point", seeded_world["customer_lat"], seeded_world["customer_lng"]),
        ("~50m", 12.97205, 77.5946),
        ("boundary", BOUNDARY_LAT, BOUNDARY_LNG),
        ("1km", 12.98060, 77.5946),
        ("290km", 13.0827, 80.2707),
    ]

    async with AsyncSessionLocal() as session:
        customer = await _customer(session, seeded_world["customer_id"])
        for label, lat, lng in points:
            expected = await measure_distance_to_customer(customer, lat, lng, session)
            result = await verify_device_against_customer(
                customer, session, device_lat=lat, device_lng=lng, accuracy_m=5.0
            )
            assert result.distance_m == pytest.approx(expected, abs=0.01), (
                f"FT-072 at {label}: service reported {result.distance_m}, "
                f"PostGIS says {expected}"
            )


async def test_check_in_persists_the_postgis_distance(
    client, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """
    The audit row must record the same authoritative distance the decision used.
    An audit trail that disagrees with the decision is not evidence.
    """
    from app.database import AsyncSessionLocal
    from app.services.customer_service import measure_distance_to_customer
    from tests.integration.conftest import create_visit

    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": BOUNDARY_LAT,
            "longitude": BOUNDARY_LNG,
            "accuracy_m": 5.0,
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, f"boundary point is inside per PostGIS: {resp.text}"

    async with AsyncSessionLocal() as session:
        customer = await _customer(session, seeded_world["customer_id"])
        expected = await measure_distance_to_customer(
            customer, BOUNDARY_LAT, BOUNDARY_LNG, session
        )

    row = db.fetch_one(
        "SELECT distance_from_customer_m FROM geo_verification_logs WHERE visit_id = %s",
        (visit_id,),
    )
    assert float(row["distance_from_customer_m"]) == pytest.approx(expected, abs=0.01), (
        "FT-072: the audit log recorded a distance the decision did not use"
    )
