"""
Unit tests for the geocoding service.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.geocoding_service import GeocodingError, _validate_coordinates, geocode_address


class TestValidateCoordinates:
    def test_valid_coordinates(self):
        # Should not raise
        _validate_coordinates(12.9716, 77.5946)

    def test_invalid_latitude_too_high(self):
        with pytest.raises(GeocodingError, match="Invalid latitude"):
            _validate_coordinates(91, 77.5946)

    def test_invalid_latitude_too_low(self):
        with pytest.raises(GeocodingError, match="Invalid latitude"):
            _validate_coordinates(-91, 77.5946)

    def test_invalid_longitude_too_high(self):
        with pytest.raises(GeocodingError, match="Invalid longitude"):
            _validate_coordinates(12.9716, 181)

    def test_invalid_longitude_too_low(self):
        with pytest.raises(GeocodingError, match="Invalid longitude"):
            _validate_coordinates(12.9716, -181)

    def test_null_island(self):
        with pytest.raises(GeocodingError, match="Null Island"):
            _validate_coordinates(0, 0)


class TestGeocodeAddress:
    @pytest.mark.asyncio
    async def test_empty_address_raises_error(self):
        with pytest.raises(GeocodingError, match="Address is required"):
            await geocode_address("")

    @pytest.mark.asyncio
    async def test_whitespace_address_raises_error(self):
        with pytest.raises(GeocodingError, match="Address is required"):
            await geocode_address("   ")

    @pytest.mark.asyncio
    async def test_successful_geocoding_nominatim(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"lat": "12.9716", "lon": "77.5946"}
        ]

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding_service.settings") as mock_settings:
                mock_settings.geocoding_provider = "nominatim"
                mock_settings.geocoding_base_url = None
                mock_settings.geocoding_user_agent = "Test/1.0"

                lat, lng = await geocode_address("Bangalore, India")

        assert lat == 12.9716
        assert lng == 77.5946

    @pytest.mark.asyncio
    async def test_address_not_found(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding_service.settings") as mock_settings:
                mock_settings.geocoding_provider = "nominatim"
                mock_settings.geocoding_base_url = None
                mock_settings.geocoding_user_agent = "Test/1.0"

                with pytest.raises(GeocodingError, match="Address not found"):
                    await geocode_address("NonexistentPlace12345")

    @pytest.mark.asyncio
    async def test_service_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding_service.settings") as mock_settings:
                mock_settings.geocoding_provider = "nominatim"
                mock_settings.geocoding_base_url = None
                mock_settings.geocoding_user_agent = "Test/1.0"

                with pytest.raises(GeocodingError, match="status 500"):
                    await geocode_address("Bangalore, India")

    @pytest.mark.asyncio
    async def test_network_error(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with patch("app.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding_service.settings") as mock_settings:
                mock_settings.geocoding_provider = "nominatim"
                mock_settings.geocoding_base_url = None
                mock_settings.geocoding_user_agent = "Test/1.0"

                with pytest.raises(GeocodingError, match="unavailable"):
                    await geocode_address("Bangalore, India")

    @pytest.mark.asyncio
    async def test_google_geocoding_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {"lat": 12.9716, "lng": 77.5946}
                    }
                }
            ],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding_service.settings") as mock_settings:
                mock_settings.geocoding_provider = "google"
                mock_settings.geocoding_base_url = None
                mock_settings.google_geocoding_api_key = "test-key"

                lat, lng = await geocode_address("Bangalore, India")

        assert lat == 12.9716
        assert lng == 77.5946

    @pytest.mark.asyncio
    async def test_google_missing_api_key(self):
        with patch("app.services.geocoding_service.settings") as mock_settings:
            mock_settings.geocoding_provider = "google"
            mock_settings.google_geocoding_api_key = None

            with pytest.raises(GeocodingError, match="API key not configured"):
                await geocode_address("Bangalore, India")
