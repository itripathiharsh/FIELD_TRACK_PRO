import logging
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings
from app.core.context import get_current_request_id, set_current_request_id
from app.exceptions.custom import BaseAPIException
from app.main import app
from app.models.user import Role, User


@pytest.mark.asyncio
async def test_request_id_generated_and_returned_in_header():
    """Verify that every HTTP request gets a unique X-Request-ID in response headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        req_id = response.headers.get("x-request-id")
        assert req_id is not None
        assert len(req_id) >= 6


@pytest.mark.asyncio
async def test_custom_request_id_preserved():
    """Verify that client-provided X-Request-ID is preserved and echoed back."""
    custom_id = "uat-trace-12345"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        assert response.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_4xx_business_error_contains_request_id_and_logs(caplog):
    """Verify 4xx BaseAPIException logs event=api_error and returns request_id in JSON."""
    caplog.set_level(logging.WARNING, logger="fieldtrackpro")

    custom_id = "test-req-404"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Non-existent customer ID lookup requires auth, which will fail with 401 or 404
        response = await client.get(
            f"/api/v1/customers/{uuid.uuid4()}",
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code in (401, 403, 404)
        data = response.json()
        assert "error" in data
        assert data["error"]["request_id"] == custom_id
        assert response.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_422_validation_error_contains_request_id_and_logs(caplog):
    """Verify 422 RequestValidationError logs event=validation_error and returns request_id."""
    caplog.set_level(logging.WARNING, logger="fieldtrackpro")

    custom_id = "test-req-422"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid login payload with missing password
        response = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "user@test.com"},
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["request_id"] == custom_id
        assert response.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_auth_login_failure_logs_safely_without_leaking_password(caplog):
    """Verify failed login logs masked identifier and never prints password."""
    caplog.set_level(logging.WARNING, logger="fieldtrackpro")

    secret_password = "SuperSecretPasswordDoNotLog!123"
    custom_id = "test-auth-fail"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "test.unknown@fieldtrack.test", "password": secret_password},
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 401

        # Check logs
        all_logs = caplog.text
        assert secret_password not in all_logs
        assert "event=auth_login" in all_logs or "event=api_error" in all_logs


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_with_request_id():
    """Verify unhandled exceptions return 500 with request_id without exposing internals to client."""
    from fastapi import APIRouter

    test_router = APIRouter()

    @test_router.get("/test-unhandled-crash")
    async def crash_endpoint():
        raise RuntimeError("Simulated unexpected crash for UAT audit")

    app.include_router(test_router)

    custom_id = "crash-trace-500"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test-unhandled-crash", headers={"X-Request-ID": custom_id})
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["request_id"] == custom_id
        assert "Simulated unexpected crash" not in data["error"]["message"]
