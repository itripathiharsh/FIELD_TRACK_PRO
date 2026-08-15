"""
Integration: all report endpoints under /api/v1/reports.

Covers:
  GET /api/v1/reports/employees
  GET /api/v1/reports/customers/{customer_id}/history
  GET /api/v1/reports/productivity
  GET /api/v1/reports/geo-verification

All endpoints are admin-only.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# -- GET /reports/employees -------------------------------------------------

async def test_employees_report_requires_admin(client: AsyncClient, employee_headers):
    """Non-admin users are forbidden."""
    resp = await client.get("/api/v1/reports/employees", headers=employee_headers)
    assert resp.status_code == 403


async def test_employees_report_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/reports/employees")
    assert resp.status_code == 401


async def test_employees_report_returns_success(client: AsyncClient, admin_headers):
    """Admin gets a successful response with the correct structure."""
    resp = await client.get("/api/v1/reports/employees", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)


async def test_employees_report_with_date_filter(client: AsyncClient, admin_headers):
    """Date-range filtering does not error and returns a list."""
    today = date.today()
    start = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()

    resp = await client.get(
        f"/api/v1/reports/employees?start_date={start}&end_date={end}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_employees_report_invalid_date_returns_422(client: AsyncClient, admin_headers):
    """Invalid date format returns 422."""
    resp = await client.get(
        "/api/v1/reports/employees?start_date=not-a-date",
        headers=admin_headers,
    )
    assert resp.status_code == 422


# -- GET /reports/customers/{id}/history ------------------------------------

async def test_customer_history_requires_admin(client: AsyncClient, employee_headers, seeded_world):
    """Non-admin users are forbidden."""
    resp = await client.get(
        f"/api/v1/reports/customers/{seeded_world['customer_id']}/history",
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_customer_history_requires_auth(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.get(
        f"/api/v1/reports/customers/{seeded_world['customer_id']}/history",
    )
    assert resp.status_code == 401


async def test_customer_history_returns_success(client: AsyncClient, admin_headers, seeded_world):
    """Admin gets a successful response for a valid customer."""
    resp = await client.get(
        f"/api/v1/reports/customers/{seeded_world['customer_id']}/history",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)


async def test_customer_history_nonexistent_returns_empty(client: AsyncClient, admin_headers):
    """Requesting history for a non-existent customer returns an empty list."""
    resp = await client.get(
        f"/api/v1/reports/customers/{uuid.uuid4()}/history",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# -- GET /reports/productivity ---------------------------------------------

async def test_productivity_requires_admin(client: AsyncClient, employee_headers):
    """Non-admin users are forbidden."""
    resp = await client.get("/api/v1/reports/productivity", headers=employee_headers)
    assert resp.status_code == 403


async def test_productivity_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/reports/productivity")
    assert resp.status_code == 401


async def test_productivity_returns_success(client: AsyncClient, admin_headers):
    """Admin gets a successful response with expected fields."""
    resp = await client.get("/api/v1/reports/productivity", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "total_employees" in data
    assert "active_employees" in data
    assert "total_visits_today" in data
    assert "completed_visits_today" in data
    assert "avg_visits_per_employee" in data


# -- GET /reports/geo-verification -----------------------------------------

async def test_geo_verification_requires_admin(client: AsyncClient, employee_headers):
    """Non-admin users are forbidden."""
    resp = await client.get("/api/v1/reports/geo-verification", headers=employee_headers)
    assert resp.status_code == 403


async def test_geo_verification_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/reports/geo-verification")
    assert resp.status_code == 401


async def test_geo_verification_returns_success(client: AsyncClient, admin_headers):
    """Admin gets a successful response."""
    resp = await client.get("/api/v1/reports/geo-verification", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_geo_verification_with_date_filter(client: AsyncClient, admin_headers):
    """Date-range filtering does not error and returns a list."""
    today = date.today()
    start = (today - timedelta(days=90)).isoformat()
    end = today.isoformat()

    resp = await client.get(
        f"/api/v1/reports/geo-verification?start_date={start}&end_date={end}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_geo_verification_empty_results(client: AsyncClient, admin_headers):
    """A date range in the future yields an empty list."""
    future = (date.today() + timedelta(days=365)).isoformat()
    future_end = (date.today() + timedelta(days=366)).isoformat()

    resp = await client.get(
        f"/api/v1/reports/geo-verification?start_date={future}&end_date={future_end}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []
