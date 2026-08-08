"""
Integration: authorization / RBAC (scenarios 6-9).

Existing unit tests only assert that an employee gets 403 on admin routes.
Nothing proved the POSITIVE path (admin succeeds) or object-level ownership
(FT-002 IDOR).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# --- Scenario 6: employee blocked from admin-only resources -----------------

@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/api/v1/customers", {"name": "x", "contact_number": "1",
                                       "address": "y",
                                       "location": {"latitude": 1.0, "longitude": 1.0}}),
        ("POST", "/api/v1/territories", {"name": "x"}),
        ("GET", "/api/v1/employees", None),
        ("POST", "/api/v1/users", {"email": "a@b.co", "password": "secret123"}),
    ],
)
async def test_employee_forbidden_on_admin_routes(
    client: AsyncClient, employee_headers, method, path, payload
):
    resp = await client.request(method, path, json=payload, headers=employee_headers)
    assert resp.status_code == 403, f"{method} {path} should be admin-only, got {resp.status_code}"


# --- Scenario 8: admin positive path (never previously tested) --------------

async def test_admin_can_list_employees(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/employees", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_admin_can_read_visit(
    client: AsyncClient, admin_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == visit_id


async def test_assigned_employee_can_read_own_visit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}", headers=employee_headers)
    assert resp.status_code == 200, "the assigned employee must be able to read their visit"


# --- Scenario 7: FT-002 IDOR ------------------------------------------------

async def test_employee_cannot_read_another_employees_visit(
    client: AsyncClient, admin_headers, other_employee_headers, seeded_world, created_visits
):
    """
    FT-002 (CRITICAL): GET /visits/{id} uses AnyAuth with no ownership check,
    so any employee can read any other employee's visit.
    Spec 09 s2 requires ownership enforcement on every {id}-scoped endpoint.
    """
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}", headers=other_employee_headers)
    assert resp.status_code in (403, 404), (
        "FT-002: an employee must not read a visit assigned to someone else"
    )


async def test_employee_visit_list_is_scoped_to_self(
    client: AsyncClient, admin_headers, other_employee_headers, seeded_world, created_visits
):
    """FT-002: GET /visits must not disclose the whole roster to an employee."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get("/api/v1/visits", headers=other_employee_headers)
    assert resp.status_code == 200
    ids = [v["id"] for v in resp.json()]
    assert visit_id not in ids, (
        "FT-002: employee visit list leaked another employee's visit"
    )


async def test_employee_cannot_read_geo_logs_of_others_visit(
    client: AsyncClient, admin_headers, other_employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(
        f"/api/v1/visits/{visit_id}/geo-logs", headers=other_employee_headers
    )
    assert resp.status_code in (403, 404), "location history must not leak across employees"


# --- Scenario 9: unauthenticated access -------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/visits"),
        ("GET", "/api/v1/customers"),
        ("GET", "/api/v1/employees"),
        ("GET", "/api/v1/territories"),
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/visits"),
    ],
)
async def test_unauthenticated_is_rejected(client: AsyncClient, method, path):
    resp = await client.request(method, path, json={})
    assert resp.status_code in (401, 403), f"{method} {path} must require auth"


async def test_nonexistent_visit_is_404_for_admin(client: AsyncClient, admin_headers):
    resp = await client.get(f"/api/v1/visits/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404
