"""Server-side distance / fix rules. The expected numbers match the Android test GpsDistanceAndFixPolicyTest."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.geo_verification_service import GeoVerificationService as G

LAT, LON = 26.7341061, 80.9435936


def dist(lat, lon):
    return G.calculate_haversine_distance(LAT, LON, lat, lon)


def test_same_point_is_zero():
    assert dist(LAT, LON) == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("lat,lon,expected,tol", [
    (26.7341511, LON, 5.0, 0.1),          # a few metres
    (26.7350054, LON, 100.0, 0.1),        # 100 m north
    (26.7386027, LON, 500.0, 0.5),        # 500 m north
    (LAT, 80.9445982, 99.77, 0.1),        # 100 m east
])
def test_known_separations(lat, lon, expected, tol):
    assert dist(lat, lon) == pytest.approx(expected, abs=tol)


def test_latitude_longitude_order_matters():
    assert G.calculate_haversine_distance(LAT, LON, LON, LAT) > 1_000_000  # swapped = another continent


def _verify(device_lat, device_lon, **kw):
    return G.verify_location(device_lat, device_lon, LAT, LON, 75.0, **kw)


def test_inside_and_outside_radius_use_the_saved_coordinates():
    assert _verify(26.7341511, LON, accuracy_m=10.0).is_valid          # ~5 m
    r = _verify(26.7350054, LON, accuracy_m=10.0)                       # ~100 m
    assert not r.is_valid and "exceeds allowed radius" in r.failure_reason
    assert r.distance_m == pytest.approx(100.0, abs=0.1)


def test_poor_accuracy_is_rejected_not_hidden():
    r = _verify(LAT, LON, accuracy_m=464.0)
    assert not r.is_valid and "accuracy" in r.failure_reason.lower()


def test_stale_capture_is_rejected():
    now = datetime.now(timezone.utc)
    r = _verify(LAT, LON, accuracy_m=10.0, captured_at=now - timedelta(hours=25), now=now)
    assert not r.is_valid and "too old" in r.failure_reason
