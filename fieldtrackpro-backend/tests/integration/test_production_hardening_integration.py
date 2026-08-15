"""
Integration: P1-4 - production API docs gating and baseline security headers.

Docs-gating is tested two ways without mutating the shared `app.main.app`
singleton (reloading it would leak into every other test module that already
holds a reference to it):
  1. The exact decision function `main._docs_urls_for_environment` is a pure
     unit test - proves the logic the real app is built with.
  2. A throwaway FastAPI app constructed with docs_url=None (mirroring
     exactly what production does) proves FastAPI's actual mechanism really
     returns 404, not just that the logic function says so.
The real, currently-running dev-mode app (the shared `client` fixture) proves
dev/test behaviour is unaffected.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import _docs_urls_for_environment
from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# --- Decision logic ----------------------------------------------------------

def test_docs_urls_disabled_for_production():
    assert _docs_urls_for_environment("production") == (None, None, None)


@pytest.mark.parametrize("environment", ["dev", "test", "staging", "local"])
def test_docs_urls_enabled_outside_production(environment):
    assert _docs_urls_for_environment(environment) == ("/docs", "/redoc", "/openapi.json")


# --- Mechanism: FastAPI genuinely 404s when docs_url=None -------------------

def test_docs_endpoints_are_genuinely_unavailable_when_disabled():
    """Mirrors exactly how app/main.py constructs the app in production."""
    docs_url, redoc_url, openapi_url = _docs_urls_for_environment("production")
    isolated_app = FastAPI(docs_url=docs_url, redoc_url=redoc_url, openapi_url=openapi_url)
    client = TestClient(isolated_app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_endpoints_are_available_when_enabled():
    docs_url, redoc_url, openapi_url = _docs_urls_for_environment("dev")
    isolated_app = FastAPI(docs_url=docs_url, redoc_url=redoc_url, openapi_url=openapi_url)
    client = TestClient(isolated_app)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


# --- The real, currently-running (dev) app: behaviour must be unaffected ----

async def test_real_dev_app_still_serves_docs(client: AsyncClient):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200


# --- Security headers ---------------------------------------------------------

async def test_security_headers_present_on_a_normal_json_response(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/territories", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in resp.headers


async def test_security_headers_present_on_error_responses_too(client: AsyncClient):
    """Headers must survive the CORS/catch-all middleware stack even on a 404/401."""
    resp = await client.get("/api/v1/territories")  # no auth -> 401
    assert resp.status_code == 401
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_csp_is_not_applied_to_the_interactive_docs(client: AsyncClient):
    """Swagger UI/ReDoc load JS/CSS from a CDN - a strict CSP there would break them."""
    resp = await client.get("/docs")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers
    # The universally-safe headers still apply even here.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


async def test_hsts_is_not_sent_outside_production(client: AsyncClient):
    """This test suite runs with ENVIRONMENT=dev - HSTS must not appear, or a
    local HTTP-only dev server would become unreachable to browsers that cache it."""
    resp = await client.get("/api/v1/territories")
    assert "Strict-Transport-Security" not in resp.headers
