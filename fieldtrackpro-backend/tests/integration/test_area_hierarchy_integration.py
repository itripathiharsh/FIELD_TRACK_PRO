"""
Integration tests for the Zone (Territory) -> Area -> Outlet (Customer)
hierarchy and Employee <-> Area coverage (brand-agnostic many-to-many),
introduced to correctly model the client's real business hierarchy
(Meeting 3). See docs of app/models/area.py and
app/models/employee_area_assignment.py for why this exists alongside,
rather than instead of, the older single-Zone Employee.territory_id model.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# -- Area CRUD ------------------------------------------------------------------

async def test_admin_can_create_area_under_a_zone(client: AsyncClient, admin_headers, seeded_world):
    resp = await client.post(
        "/api/v1/areas",
        json={"name": f"__itest__Area-{uuid.uuid4().hex[:8]}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["territory_id"] == seeded_world["territory_id"]
    assert body["territory_name"]


async def test_employee_cannot_create_area(client: AsyncClient, employee_headers, seeded_world):
    resp = await client.post(
        "/api/v1/areas",
        json={"name": "__itest__ShouldFail", "territory_id": seeded_world["territory_id"]},
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_create_area_under_nonexistent_zone_404s(client: AsyncClient, admin_headers):
    resp = await client.post(
        "/api/v1/areas",
        json={"name": "__itest__Orphan", "territory_id": str(uuid.uuid4())},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_case_insensitive_duplicate_area_name_in_same_zone_is_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    tag = uuid.uuid4().hex[:8]
    name = f"__itest__Area-{tag}"
    first = await client.post(
        "/api/v1/areas", json={"name": name, "territory_id": seeded_world["territory_id"]}, headers=admin_headers
    )
    assert first.status_code == 201, first.text

    dup = await client.post(
        "/api/v1/areas",
        json={"name": name.upper(), "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["code"] == "AREA_ALREADY_EXISTS"


async def test_same_area_name_allowed_in_a_different_zone(client: AsyncClient, admin_headers, seeded_world, created_territories):
    tag = uuid.uuid4().hex[:8]
    name = f"__itest__Area-{tag}"
    zone_b = await client.post("/api/v1/territories", json={"name": f"__itest__ZoneB-{tag}"}, headers=admin_headers)
    zone_b_id = zone_b.json()["id"]
    created_territories.append(zone_b_id)

    first = await client.post(
        "/api/v1/areas", json={"name": name, "territory_id": seeded_world["territory_id"]}, headers=admin_headers
    )
    second = await client.post(
        "/api/v1/areas", json={"name": name, "territory_id": zone_b_id}, headers=admin_headers
    )
    assert first.status_code == 201 and second.status_code == 201


async def test_list_areas_filters_by_zone(client: AsyncClient, admin_headers, seeded_world, created_territories):
    tag = uuid.uuid4().hex[:8]
    zone_b = await client.post("/api/v1/territories", json={"name": f"__itest__ZoneB-{tag}"}, headers=admin_headers)
    zone_b_id = zone_b.json()["id"]
    created_territories.append(zone_b_id)

    in_seeded = await client.post(
        "/api/v1/areas", json={"name": f"__itest__A-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    in_b = await client.post(
        "/api/v1/areas", json={"name": f"__itest__B-{tag}", "territory_id": zone_b_id}, headers=admin_headers
    )
    assert in_seeded.status_code == 201 and in_b.status_code == 201

    resp = await client.get(
        "/api/v1/areas", params={"territory_id": seeded_world["territory_id"]}, headers=admin_headers
    )
    ids = {a["id"] for a in resp.json()}
    assert in_seeded.json()["id"] in ids
    assert in_b.json()["id"] not in ids


async def test_rename_area_to_a_duplicate_name_in_same_zone_is_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    tag = uuid.uuid4().hex[:8]
    a = await client.post(
        "/api/v1/areas", json={"name": f"__itest__RenA-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    b = await client.post(
        "/api/v1/areas", json={"name": f"__itest__RenB-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    resp = await client.patch(
        f"/api/v1/areas/{b.json()['id']}", json={"name": a.json()["name"]}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_cannot_delete_zone_with_areas_under_it(client: AsyncClient, admin_headers, created_territories):
    tag = uuid.uuid4().hex[:8]
    zone = await client.post("/api/v1/territories", json={"name": f"__itest__ZoneC-{tag}"}, headers=admin_headers)
    zone_id = zone.json()["id"]
    created_territories.append(zone_id)
    await client.post("/api/v1/areas", json={"name": f"__itest__C-{tag}", "territory_id": zone_id}, headers=admin_headers)

    resp = await client.delete(f"/api/v1/territories/{zone_id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "TERRITORY_IN_USE"


async def test_cannot_delete_area_assigned_to_an_outlet(
    client: AsyncClient, admin_headers, seeded_world, created_customers
):
    tag = uuid.uuid4().hex[:8]
    area = await client.post(
        "/api/v1/areas", json={"name": f"__itest__InUse-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    area_id = area.json()["id"]

    customer = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__Outlet-{tag}", "contact_number": "+919999900003",
            "address": "__itest__ addr", "location": {"latitude": 12.9716, "longitude": 77.5946},
            "area_id": area_id,
        },
        headers=admin_headers,
    )
    assert customer.status_code == 201, customer.text
    created_customers.append(customer.json()["id"])

    resp = await client.delete(f"/api/v1/areas/{area_id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "AREA_IN_USE"


# -- Customer/Outlet: Area is the source of truth for Zone --------------------

async def test_creating_customer_with_area_id_derives_territory_id_from_it(
    client: AsyncClient, admin_headers, seeded_world, created_customers
):
    tag = uuid.uuid4().hex[:8]
    area = await client.post(
        "/api/v1/areas", json={"name": f"__itest__Derive-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    area_id = area.json()["id"]

    # Deliberately supply a DIFFERENT (nonexistent) territory_id - the Area's
    # own Zone must win, never a separately-supplied, possibly-inconsistent one.
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__Outlet-{tag}", "contact_number": "+919999900004",
            "address": "__itest__ addr", "location": {"latitude": 12.9716, "longitude": 77.5946},
            "area_id": area_id, "territory_id": str(uuid.uuid4()),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    created_customers.append(resp.json()["id"])
    assert resp.json()["territory_id"] == seeded_world["territory_id"]
    assert resp.json()["area_id"] == area_id
    assert resp.json()["area_name"]


async def test_customer_with_no_area_has_null_area_fields(
    client: AsyncClient, admin_headers, seeded_world, created_customers
):
    tag = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__NoArea-{tag}", "contact_number": "+919999900005",
            "address": "__itest__ addr", "location": {"latitude": 12.9716, "longitude": 77.5946},
            "territory_id": seeded_world["territory_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    created_customers.append(resp.json()["id"])
    assert resp.json()["area_id"] is None
    assert resp.json()["area_name"] is None
    assert resp.json()["territory_id"] == seeded_world["territory_id"]


# -- Employee <-> Area coverage (brand-agnostic many-to-many) ------------------

async def test_assign_and_list_employee_area_coverage(client: AsyncClient, admin_headers, seeded_world):
    tag = uuid.uuid4().hex[:8]
    area = await client.post(
        "/api/v1/areas", json={"name": f"__itest__Cov-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    area_id = area.json()["id"]

    assign = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas", json={"area_id": area_id}, headers=admin_headers
    )
    assert assign.status_code == 201, assign.text
    assert assign.json()["area_id"] == area_id

    listing = await client.get(f"/api/v1/employees/{seeded_world['employee_id']}/areas", headers=admin_headers)
    assert listing.status_code == 200
    assert any(a["area_id"] == area_id for a in listing.json())


async def test_duplicate_area_assignment_is_rejected(client: AsyncClient, admin_headers, seeded_world):
    tag = uuid.uuid4().hex[:8]
    area = await client.post(
        "/api/v1/areas", json={"name": f"__itest__Dup-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    area_id = area.json()["id"]
    first = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas", json={"area_id": area_id}, headers=admin_headers
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas", json={"area_id": area_id}, headers=admin_headers
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "AREA_ASSIGNMENT_ALREADY_EXISTS"


async def test_unassign_area_coverage(client: AsyncClient, admin_headers, seeded_world):
    tag = uuid.uuid4().hex[:8]
    area = await client.post(
        "/api/v1/areas", json={"name": f"__itest__Unassign-{tag}", "territory_id": seeded_world["territory_id"]},
        headers=admin_headers,
    )
    area_id = area.json()["id"]
    await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas", json={"area_id": area_id}, headers=admin_headers
    )

    unassign = await client.delete(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas/{area_id}", headers=admin_headers
    )
    assert unassign.status_code == 204

    listing = await client.get(f"/api/v1/employees/{seeded_world['employee_id']}/areas", headers=admin_headers)
    assert not any(a["area_id"] == area_id for a in listing.json())


async def test_unassign_nonexistent_coverage_404s(client: AsyncClient, admin_headers, seeded_world):
    resp = await client.delete(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas/{uuid.uuid4()}", headers=admin_headers
    )
    assert resp.status_code == 404


async def test_employee_cannot_manage_area_assignments(client: AsyncClient, employee_headers, seeded_world):
    resp = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas",
        json={"area_id": str(uuid.uuid4())},
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_unauthenticated_cannot_access_areas(client: AsyncClient, seeded_world):
    resp = await client.get("/api/v1/areas")
    assert resp.status_code == 401
