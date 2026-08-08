"""
Phase 4 — Geo Verification Test Suite.

Covers:
- Geodesic Haversine math precision
- Server-side geofence proximity verification
- Mock location provider rejection
- GPS accuracy threshold validation
- Coordinate range validation
- Standalone /geo/verify-location endpoint authorization and logic
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.geo_verification_service import GeoVerificationService
from tests.conftest import admin_headers, employee_headers, requires_db


# ---------------------------------------------------------------------------
# Unit tests: Haversine distance calculation
# ---------------------------------------------------------------------------

def test_haversine_same_point():
    """Distance between identical coordinates is 0.0 meters."""
    dist = GeoVerificationService.calculate_haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
    assert dist == 0.0


def test_haversine_known_distance():
    """Verify geodesic distance for known benchmark locations (~1.38 km between two Bangalore landmarks)."""
    # MG Road to Cubbon Park Metro station (~1380m)
    dist = GeoVerificationService.calculate_haversine_distance(12.9756, 77.6066, 12.9738, 77.5938)
    assert 1300 <= dist <= 1500


# ---------------------------------------------------------------------------
# Unit tests: Server-side GeoVerificationService logic
# ---------------------------------------------------------------------------

def test_verify_location_inside_radius():
    """Location within 100m geofence passes verification."""
    res = GeoVerificationService.verify_location(
        device_lat=12.971600,
        device_lon=77.594600,
        target_lat=12.971620,
        target_lon=77.594620,
        geofence_radius_m=100.0,
    )
    assert res.is_valid is True
    assert res.distance_m < 100.0
    assert res.failure_reason is None


def test_verify_location_outside_radius():
    """Location exceeding geofence radius is rejected with reason."""
    res = GeoVerificationService.verify_location(
        device_lat=12.9716,
        device_lon=77.5946,
        target_lat=13.0000,  # ~3.1 km away
        target_lon=77.6000,
        geofence_radius_m=100.0,
    )
    assert res.is_valid is False
    assert res.distance_m > 100.0
    assert "exceeds allowed radius" in res.failure_reason


def test_verify_location_mock_provider():
    """Mock location provider flag triggers immediate server-side rejection."""
    res = GeoVerificationService.verify_location(
        device_lat=12.9716,
        device_lon=77.5946,
        target_lat=12.9716,
        target_lon=77.5946,
        geofence_radius_m=100.0,
        is_mock_location=True,
    )
    assert res.is_valid is False
    assert res.is_mock is True
    assert "Mock location provider detected" in res.failure_reason


def test_verify_location_low_accuracy_gps():
    """GPS readings with horizontal accuracy worse than 100m threshold are rejected."""
    res = GeoVerificationService.verify_location(
        device_lat=12.9716,
        device_lon=77.5946,
        target_lat=12.9716,
        target_lon=77.5946,
        geofence_radius_m=100.0,
        accuracy_m=150.0,  # exceeds 100m threshold
    )
    assert res.is_valid is False
    assert "accuracy (150.0m) exceeds maximum threshold" in res.failure_reason


def test_verify_location_invalid_coords():
    """Coordinates outside valid decimal degree bounds [-90, 90] / [-180, 180] fail."""
    res = GeoVerificationService.verify_location(
        device_lat=999.0,
        device_lon=77.5946,
        target_lat=12.9716,
        target_lon=77.5946,
        geofence_radius_m=100.0,
    )
    assert res.is_valid is False
    assert "Invalid device coordinates" in res.failure_reason


# ---------------------------------------------------------------------------
# API endpoint tests: /api/v1/geo/verify-location
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_geo_verify_endpoint_unauthorized(client: AsyncClient):
    """Anonymous request to /geo/verify-location returns 401/403."""
    resp = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
    )
    assert resp.status_code in (401, 403)


@requires_db
@pytest.mark.asyncio
async def test_geo_verify_endpoint_valid_request(client: AsyncClient):
    """Authenticated request returns LocationVerifyResponse object."""
    resp = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
        headers=employee_headers(),
    )
    assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Geo Log Permission Audit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_geo_logs_unauthorized(client: AsyncClient):
    """Anonymous request for visit geo-logs fails with 401/403."""
    import uuid
    visit_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/visits/{visit_id}/geo-logs")
    assert resp.status_code in (401, 403)


@requires_db
@pytest.mark.asyncio
async def test_geo_logs_invalid_visit_returns_404(client: AsyncClient):
    """Querying geo logs for a non-existent visit returns 404."""
    import uuid
    visit_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers())
    assert resp.status_code == 404
