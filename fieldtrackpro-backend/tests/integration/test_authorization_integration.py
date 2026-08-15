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


# --- P0-1: customer/outlet directory scoping --------------------------------
#
# GET /customers and GET /customers/{id} previously had no employee/territory
# scoping at all - any authenticated employee could list or fetch any outlet
# nationwide. The fix reuses the exact ownership rule account_service already
# established for the (more sensitive) account/invoices/orders endpoints: an
# EMPLOYEE may see an outlet only if they have at least one visit assigned to
# it. These tests create their own customer (not seeded_world's, which every
# other test file also reads) so this file's cleanup doesn't race others.

async def _create_customer(client: AsyncClient, admin_headers, name: str, created_customers) -> str:
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": name,
            "contact_number": "+919876500099",
            "address": "1 Ownership Test Road",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    customer_id = resp.json()["id"]
    created_customers.append(customer_id)
    return customer_id


async def test_employee_can_view_outlet_they_have_a_visit_for(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}", headers=employee_headers)
    assert resp.status_code == 200, resp.text


async def test_employee_cannot_view_outlet_they_have_no_visit_for(
    client: AsyncClient, admin_headers, employee_headers, created_customers
):
    """P0-1: direct ID manipulation must not bypass authorization - an
    employee who simply guesses/enumerates a customer_id they were never
    assigned a visit for must be refused, not served the outlet's PII/GPS."""
    other_customer_id = await _create_customer(
        client, admin_headers, "__itest__Unassigned Outlet", created_customers
    )
    resp = await client.get(f"/api/v1/customers/{other_customer_id}", headers=employee_headers)
    assert resp.status_code == 403, (
        "P0-1: an employee must not be able to view an outlet they have no visit assigned to"
    )
    assert resp.json()["error"]["code"] == "OUTLET_NOT_ASSIGNED"


async def test_customer_list_is_scoped_to_employees_own_visits(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, created_customers
):
    await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    unassigned_customer_id = await _create_customer(
        client, admin_headers, "__itest__Not In My List", created_customers
    )

    resp = await client.get("/api/v1/customers", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    ids = [c["id"] for c in resp.json()]
    assert seeded_world["customer_id"] in ids, "employee must see an outlet they have a visit for"
    assert unassigned_customer_id not in ids, (
        "P0-1: employee customer list leaked an outlet they have no visit assigned to"
    )


async def test_admin_customer_list_and_detail_remain_unrestricted(
    client: AsyncClient, admin_headers, created_customers, created_territories
):
    """
    Preserve existing behaviour for the role that legitimately has broader
    access: an ADMIN must see an outlet with zero visits assigned to anyone.
    Scoped to a dedicated fresh territory (rather than an unfiltered list) so
    the assertion doesn't depend on default, unordered pagination picking up
    this row among whatever other test data currently exists.
    """
    territory_resp = await client.post(
        "/api/v1/territories", json={"name": "__itest__Admin Unrestricted Territory"}, headers=admin_headers
    )
    assert territory_resp.status_code == 201, territory_resp.text
    territory_id = territory_resp.json()["id"]
    created_territories.append(territory_id)

    customer_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "__itest__Admin Sees Everything",
            "contact_number": "+919876500099",
            "address": "1 Ownership Test Road",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "territory_id": territory_id,
        },
        headers=admin_headers,
    )
    assert customer_resp.status_code == 201, customer_resp.text
    customer_id = customer_resp.json()["id"]
    created_customers.append(customer_id)

    detail = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text

    listing = await client.get(
        "/api/v1/customers", params={"territory_id": territory_id}, headers=admin_headers
    )
    assert listing.status_code == 200
    assert customer_id in [c["id"] for c in listing.json()]


async def test_geo_verify_location_is_scoped_to_visited_outlet(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, created_customers
):
    """P0-1 (secondary surface): the standalone pre-check endpoint shares the
    same customer-ownership scoping as the base profile endpoints."""
    await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    allowed = await client.post(
        "/api/v1/geo/verify-location",
        json={
            "customer_id": seeded_world["customer_id"],
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
        },
        headers=employee_headers,
    )
    assert allowed.status_code == 200, allowed.text

    other_customer_id = await _create_customer(
        client, admin_headers, "__itest__Geo Not Assigned", created_customers
    )
    denied = await client.post(
        "/api/v1/geo/verify-location",
        json={"customer_id": other_customer_id, "latitude": 12.9716, "longitude": 77.5946},
        headers=employee_headers,
    )
    assert denied.status_code == 403, (
        "P0-1: an employee must not be able to probe an outlet's geofence without a visit assigned to it"
    )


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
