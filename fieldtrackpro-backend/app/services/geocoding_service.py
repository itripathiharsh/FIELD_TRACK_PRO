"""
Geocoding service for converting addresses to coordinates.

Uses Nominatim (OpenStreetMap) as the default provider - no API key required.
Can be configured to use other providers via environment variables.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Raised when geocoding fails."""

    def __init__(self, message: str, reason: str = "GEOCODING_ERROR"):
        self.message = message
        self.reason = reason
        super().__init__(self.message)


async def geocode_address(address: str) -> tuple[float, float]:
    """
    Convert a free-text address to (latitude, longitude) coordinates.

    Args:
        address: Free-text address string

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        GeocodingError: If the address cannot be geocoded
    """
    if not address or not address.strip():
        raise GeocodingError(
            "Address is required for geocoding",
            reason="ADDRESS_REQUIRED",
        )

    provider = settings.geocoding_provider.lower()

    if provider == "nominatim":
        return await _geocode_nominatim(address)
    elif provider == "google":
        return await _geocode_google(address)
    else:
        # Default to Nominatim
        return await _geocode_nominatim(address)


async def _geocode_nominatim(address: str) -> tuple[float, float]:
    """
    Geocode using Nominatim (OpenStreetMap).
    No API key required. Usage policy: max 1 request/second.
    """
    base_url = settings.geocoding_base_url or "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }

    url = f"{base_url}?{urlencode(params)}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": settings.geocoding_user_agent or "FieldTrackPro/1.0",
                },
            )

        if response.status_code != 200:
            raise GeocodingError(
                f"Geocoding service returned status {response.status_code}",
                reason="SERVICE_ERROR",
            )

        data = response.json()

        if not data or len(data) == 0:
            raise GeocodingError(
                f"Address not found: '{address}'",
                reason="ADDRESS_NOT_FOUND",
            )

        result = data[0]
        lat = float(result["lat"])
        lng = float(result["lon"])

        _validate_coordinates(lat, lng)

        logger.info("Geocoded address '%s' to (%s, %s)", address, lat, lng)
        return (lat, lng)

    except (httpx.RequestError, httpx.TimeoutException) as e:
        raise GeocodingError(
            f"Geocoding service unavailable: {str(e)}",
            reason="NETWORK_ERROR",
        )
    except (KeyError, ValueError, TypeError) as e:
        raise GeocodingError(
            f"Unexpected response from geocoding service: {str(e)}",
            reason="INVALID_RESPONSE",
        )


async def _geocode_google(address: str) -> tuple[float, float]:
    """
    Geocode using Google Geocoding API.
    Requires GOOGLE_GEOCODING_API_KEY in settings.
    """
    api_key = settings.google_geocoding_api_key
    if not api_key:
        raise GeocodingError(
            "Google Geocoding API key not configured",
            reason="API_KEY_MISSING",
        )

    base_url = settings.geocoding_base_url or "https://maps.googleapis.com/maps/api/geocode/json"

    params = {
        "address": address,
        "key": api_key,
    }

    url = f"{base_url}?{urlencode(params)}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

        if response.status_code != 200:
            raise GeocodingError(
                f"Geocoding service returned status {response.status_code}",
                reason="SERVICE_ERROR",
            )

        data = response.json()

        if data.get("status") != "OK":
            raise GeocodingError(
                f"Geocoding failed: {data.get('status')} - {data.get('error_message', 'Unknown error')}",
                reason="ADDRESS_NOT_FOUND" if data.get("status") == "ZERO_RESULTS" else "SERVICE_ERROR",
            )

        location = data["results"][0]["geometry"]["location"]
        lat = float(location["lat"])
        lng = float(location["lng"])

        _validate_coordinates(lat, lng)

        logger.info("Geocoded address '%s' to (%s, %s)", address, lat, lng)
        return (lat, lng)

    except (httpx.RequestError, httpx.TimeoutException) as e:
        raise GeocodingError(
            f"Geocoding service unavailable: {str(e)}",
            reason="NETWORK_ERROR",
        )
    except (KeyError, ValueError, TypeError, IndexError) as e:
        raise GeocodingError(
            f"Unexpected response from geocoding service: {str(e)}",
            reason="INVALID_RESPONSE",
        )


def _validate_coordinates(lat: float, lng: float) -> None:
    """Validate that coordinates are within valid ranges."""
    if not (-90 <= lat <= 90):
        raise GeocodingError(
            f"Invalid latitude: {lat}. Must be between -90 and 90.",
            reason="INVALID_COORDINATES",
        )
    if not (-180 <= lng <= 180):
        raise GeocodingError(
            f"Invalid longitude: {lng}. Must be between -180 and 180.",
            reason="INVALID_COORDINATES",
        )
    if lat == 0 and lng == 0:
        raise GeocodingError(
            "Geocoding returned Null Island (0, 0), which is almost certainly incorrect",
            reason="INVALID_COORDINATES",
        )
