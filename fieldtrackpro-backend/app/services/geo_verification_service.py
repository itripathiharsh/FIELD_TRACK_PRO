"""
Geo Verification Service: central spatial calculations, geofencing,
and server-side mock/GPS anomaly detection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
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

    MAX_ACCURACY_THRESHOLD_M: float = 100.0  # Reject GPS reads with accuracy worse than 100 meters

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
    ) -> GeoVerificationResult:
        """
        Execute comprehensive server-side verification:
        1. Coordinate range validation
        2. Mock provider detection
        3. GPS accuracy threshold validation
        4. Geofence radius check
        """
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
            distance = cls.calculate_haversine_distance(
                device_lat, device_lon, target_lat, target_lon
            )
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance,
                geofence_radius_m=geofence_radius_m,
                is_mock=True,
                accuracy_m=accuracy_m,
                failure_reason="Mock location provider detected on device",
            )

        # 3. GPS accuracy threshold validation
        if accuracy_m is not None and accuracy_m > cls.MAX_ACCURACY_THRESHOLD_M:
            distance = cls.calculate_haversine_distance(
                device_lat, device_lon, target_lat, target_lon
            )
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance,
                geofence_radius_m=geofence_radius_m,
                is_mock=False,
                accuracy_m=accuracy_m,
                failure_reason=f"GPS accuracy ({accuracy_m:.1f}m) exceeds maximum threshold ({cls.MAX_ACCURACY_THRESHOLD_M:.1f}m)",
            )

        # 4. Calculate distance & verify geofence
        distance = cls.calculate_haversine_distance(
            device_lat, device_lon, target_lat, target_lon
        )

        if distance > geofence_radius_m:
            return GeoVerificationResult(
                is_valid=False,
                distance_m=distance,
                geofence_radius_m=geofence_radius_m,
                is_mock=False,
                accuracy_m=accuracy_m,
                failure_reason=f"Distance ({distance:.1f}m) exceeds allowed radius ({geofence_radius_m:.1f}m)",
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
