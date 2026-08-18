"""
Geo Verification Service: central spatial calculations, geofencing,
and server-side mock/GPS anomaly detection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class GeoVerificationResult:
    """Server-side location decision object."""

    is_valid: bool
    distance_m: float
    geofence_radius_m: float
    is_mock: bool
    accuracy_m: float | None = None
    failure_reason: str | None = None


class GeoVerificationService:
    """Central GIS service for coordinate validation, geodesic math, and geofencing."""

    MAX_ACCURACY_THRESHOLD_M: float = 100.0
    # A GPS fix older than this is rejected. Deliberately generous rather than
    # tight: the app supports checking in while offline and syncing later
    # (see OfflineQueueManager on Android), so a fix captured hours ago and
    # only just transmitted is a legitimate, expected case, not fraud. This
    # threshold exists to catch clearly-implausible replay (a fix from days/
    # weeks ago), not to police realistic dead-zone delays.
    MAX_LOCATION_AGE = timedelta(hours=24)

    @staticmethod
    def calculate_haversine_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Calculate geodesic distance in meters using Haversine formula.
        
        Parameters
        ----------
        lat1, lon1 : Device coordinates in decimal degrees.
        lat2, lon2 : Target/Customer coordinates in decimal degrees.
        
        Returns
        -------
        Distance in meters rounded to 2 decimal places.
        """
        R = 6371000.0  # Earth's mean radius in meters

        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = (
            math.sin(dphi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        distance = R * c
        return round(distance, 2)

    @classmethod
    def verify_location(
        cls,
        device_lat: float,
        device_lon: float,
        target_lat: float,
        target_lon: float,
        geofence_radius_m: float,
        accuracy_m: float | None = None,
        is_mock_location: bool = False,
        measured_distance_m: float | None = None,
        captured_at: datetime | None = None,
        now: datetime | None = None,
    ) -> GeoVerificationResult:
        """
        Execute comprehensive server-side verification:

        1. Coordinate range validation
        2. Mock provider detection
        3. GPS fix freshness (age) validation
        4. GPS accuracy threshold validation
        5. Geofence radius check

        ``measured_distance_m`` lets the caller supply an authoritative distance
        computed by PostGIS (``ST_Distance`` on ``geography``). When omitted the
        Haversine approximation is used, which keeps this class independently
        testable. Callers that touch the database must pass the PostGIS value so
        the decision is made on the same figure that is written to the audit log
        (FT-004).

        ``captured_at`` is when the device's GPS sensor actually took the
        reading (not when the request reached the server - those can differ
        by hours if the device was offline and queued the attempt). ``now``
        defaults to the current time and exists as a parameter purely so this
        check is deterministically testable.
        """

        def distance_to_target() -> float:
            if measured_distance_m is not None:
                return measured_distance_m
            return cls.calculate_haversine_distance(
                device_lat, device_lon, target_lat, target_lon
            )

        # 1. Coordinate range validation
        if not (-90.0 <= device_lat <= 90.0) or not (-180.0 <= device_lon <= 180.0):
            return GeoVerificationResult(
                is_valid=False,
                distance_m=0.0,
                geofence_radius_m=geofence_radius_m,
                is_mock=is_mock_location,
                accuracy_m=accuracy_m,
                failure_reason=f"Invalid device coordinates: lat={device_lat}, lon={device_lon}",
            )

        # 2. Mock provider detection
        if is_mock_location:
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance_to_target(),
                geofence_radius_m=geofence_radius_m,
                is_mock=True,
                accuracy_m=accuracy_m,
                failure_reason="Mock location provider detected on device",
            )

        # 3. GPS fix freshness validation. A missing captured_at is treated as
        # "now" (nothing to compare) rather than rejected here - the request
        # schema is what makes the field mandatory for the endpoints that
        # need it (check-in/check-out); this service stays usable by callers
        # that don't track capture time at all.
        if captured_at is not None:
            reference_now = now if now is not None else datetime.now(timezone.utc)
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=timezone.utc)
            if reference_now.tzinfo is None:
                reference_now = reference_now.replace(tzinfo=timezone.utc)
            age = reference_now - captured_at
            if age < timedelta(minutes=-5):
                return GeoVerificationResult(
                    is_valid=False,
                    distance_m=distance_to_target(),
                    geofence_radius_m=geofence_radius_m,
                    is_mock=False,
                    accuracy_m=accuracy_m,
                    failure_reason="GPS capture timestamp is in the future",
                )
            if age > cls.MAX_LOCATION_AGE:
                return GeoVerificationResult(
                    is_valid=False,
                    distance_m=distance_to_target(),
                    geofence_radius_m=geofence_radius_m,
                    is_mock=False,
                    accuracy_m=accuracy_m,
                    failure_reason=(
                        f"GPS fix is too old ({age.total_seconds() / 3600:.1f}h) - "
                        f"maximum age is {cls.MAX_LOCATION_AGE.total_seconds() / 3600:.0f}h"
                    ),
                )

        # 4. GPS accuracy threshold validation
        if accuracy_m is not None and accuracy_m > cls.MAX_ACCURACY_THRESHOLD_M:
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance_to_target(),
                geofence_radius_m=geofence_radius_m,
                is_mock=False,
                accuracy_m=accuracy_m,
                failure_reason=(
                    f"GPS accuracy ({accuracy_m:.1f}m) exceeds maximum threshold "
                    f"({cls.MAX_ACCURACY_THRESHOLD_M:.1f}m)"
                ),
            )

        # 5. Geofence radius check
        distance = distance_to_target()
        if distance > geofence_radius_m:
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance,
                geofence_radius_m=geofence_radius_m,
                is_mock=False,
                accuracy_m=accuracy_m,
                failure_reason=(
                    f"Distance ({distance:.1f}m) exceeds allowed radius "
                    f"({geofence_radius_m:.1f}m)"
                ),
            )

        # All checks passed
        return GeoVerificationResult(
            is_valid=True,
            distance_m=distance,
            geofence_radius_m=geofence_radius_m,
            is_mock=False,
            accuracy_m=accuracy_m,
            failure_reason=None,
        )


geo_verification_service = GeoVerificationService()
