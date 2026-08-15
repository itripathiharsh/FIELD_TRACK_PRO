"""
Integration: DELETE /api/v1/territories/{id}.

Covers the territory deletion endpoint which previously had no direct test coverage.

Creates its own territory for deletion to avoid mutating the shared seeded_world.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def _create_territory(client: AsyncClient, admin_headers, name: str) -> str:
    """Create a territory and return its ID."""
    resp = await client.post(
        "/api/v1/territories",
        json={"name": name},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_admin_can_delete_territory(client: AsyncClient, admin_headers):
    """Admin can delete an existing territory."""
    territory_id = await _create_territory(client, admin_headers, "__itest__Delete Me")

    resp = await client.delete(
        f"/api/v1/territories/{territory_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 204, resp.text


async def test_delete_territory_removes_from_database(client: AsyncClient, admin_headers, db):
    """After deletion, the territory row is actually gone from the database."""
    territory_id = await _create_territory(client, admin_headers, "__itest__Delete Persist")

    resp = await client.delete(
        f"/api/v1/territories/{territory_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 204, resp.text

    # Verify persistence: row must be absent from the database.
    row = db.fetch_one("SELECT id FROM territories WHERE id = %s", (territory_id,))
    assert row is None, "territory row should be deleted from the database"


async def test_employee_cannot_delete_territory(client: AsyncClient, employee_headers, admin_headers):
    """Non-admin users are forbidden from deleting territories."""
    territory_id = await _create_territory(client, admin_headers, "__itest__Employee Cant Delete")

    resp = await client.delete(
        f"/api/v1/territories/{territory_id}",
        headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text


async def test_unauthenticated_cannot_delete_territory(client: AsyncClient, admin_headers):
    """Unauthenticated requests are rejected with 401."""
    territory_id = await _create_territory(client, admin_headers, "__itest__Unauth Delete")

    resp = await client.delete(f"/api/v1/territories/{territory_id}")
    assert resp.status_code == 401


async def test_delete_nonexistent_territory_returns_404(client: AsyncClient, admin_headers):
    """Deleting a territory that does not exist returns 404."""
    resp = await client.delete(
        f"/api/v1/territories/{uuid.uuid4()}",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --- P0-5: reference guard - previously an unguarded delete either silently
# nulled Employee/Customer.territory_id (ondelete=SET NULL) or crashed with an
# unhandled IntegrityError -> 500 when EmployeeTerritoryAssignment history
# referenced it (ondelete=RESTRICT). Mirrors the explicit reference-guard
# pattern already used by FormTemplateService.delete_template.

async def test_cannot_delete_territory_assigned_to_an_employee(
    client: AsyncClient, admin_headers, seeded_world
):
    """seeded_world's employee is live-assigned to seeded_world's territory."""
    resp = await client.delete(
        f"/api/v1/territories/{seeded_world['territory_id']}",
        headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TERRITORY_IN_USE"


async def test_cannot_delete_territory_assigned_to_a_customer(
    client: AsyncClient, admin_headers, created_territories, created_customers
):
    territory_resp = await client.post(
        "/api/v1/territories", json={"name": "__itest__Customer Territory"}, headers=admin_headers
    )
    assert territory_resp.status_code == 201, territory_resp.text
    territory_id = territory_resp.json()["id"]
    created_territories.append(territory_id)

    customer_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "__itest__Territory Bound Outlet",
            "contact_number": "+919876500098",
            "address": "1 Territory Test Road",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "territory_id": territory_id,
        },
        headers=admin_headers,
    )
    assert customer_resp.status_code == 201, customer_resp.text
    created_customers.append(customer_resp.json()["id"])

    resp = await client.delete(f"/api/v1/territories/{territory_id}", headers=admin_headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TERRITORY_IN_USE"


async def test_cannot_delete_territory_in_reassignment_history(
    client: AsyncClient, admin_headers, seeded_world, created_territories
):
    """
    Reproduces the original crash: a territory that a *live* Employee.territory_id
    no longer points at, but that still appears in EmployeeTerritoryAssignment
    history (ondelete=RESTRICT there, by design - history must never silently
    lose which territory it recorded). Before the fix this raised an unhandled
    IntegrityError (HTTP 500); it must now be a clean 409.
    """
    emp_id = seeded_world["employee_id"]

    history_territory_resp = await client.post(
        "/api/v1/territories", json={"name": "__itest__History Territory"}, headers=admin_headers
    )
    assert history_territory_resp.status_code == 201, history_territory_resp.text
    history_territory_id = history_territory_resp.json()["id"]
    created_territories.append(history_territory_id)

    assign_resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": history_territory_id,
            "assignment_type": "PERMANENT",
            "start_date": date.today().isoformat(),
        },
        headers=admin_headers,
    )
    assert assign_resp.status_code == 201, assign_resp.text

    # Move the employee's live territory elsewhere so Employee.territory_id
    # no longer references history_territory_id - only the assignment history
    # row does, isolating exactly the RESTRICT path this test targets.
    reassign_resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": seeded_world["territory_id"],
            "assignment_type": "PERMANENT",
            "start_date": date.today().isoformat(),
        },
        headers=admin_headers,
    )
    assert reassign_resp.status_code == 201, reassign_resp.text

    resp = await client.delete(f"/api/v1/territories/{history_territory_id}", headers=admin_headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TERRITORY_IN_USE"
    assert resp.status_code != 500, "P0-5: must never surface as an unhandled 500"
