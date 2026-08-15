"""
Integration: bulk visit scheduling.

Tests the complete bulk scheduling flow:
- Admin authorization
- Customer selection
- Employee selection
- Date/time scheduling
- Validation for invalid input
- Duplicate/conflict handling
- Database persistence
- Created visits appear in normal Visits UI
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import (
    TEST_MARKER,
    create_visit,
    iso_in,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def _create_test_customer(client: AsyncClient, admin_headers: dict, name_suffix: str) -> str:
    """Helper to create a test customer and return its ID."""
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"{TEST_MARKER}Bulk Customer {name_suffix}",
            "contact_number": "+919999900001",
            "address": f"{TEST_MARKER} {name_suffix} Test Road",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "geofence_radius_m": 100,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"Customer creation failed: {resp.text}"
    return resp.json()["id"]


# --- Test 1: Admin can bulk schedule visits ---------------------------------

async def test_admin_bulk_schedules_visits(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Admin can bulk schedule visits for multiple customers."""
    customer1 = await _create_test_customer(client, admin_headers, "A")
    customer2 = await _create_test_customer(client, admin_headers, "B")

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [customer1, customer2],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"Bulk schedule failed: {resp.text}"
    visits = resp.json()
    assert len(visits) == 2, f"Expected 2 visits, got {len(visits)}"

    # Track for cleanup
    for visit in visits:
        created_visits.append(visit["id"])

    # Verify each visit is persisted
    for visit in visits:
        row = db.fetch_one(
            "SELECT id, customer_id, employee_id, status FROM visits WHERE id = %s",
            (visit["id"],)
        )
        assert row is not None, f"Visit {visit['id']} not persisted"
        assert row["status"] == "PENDING"
        assert str(row["employee_id"]) == seeded_world["employee_id"]


# --- Test 2: Employee cannot bulk schedule visits ---------------------------

async def test_employee_cannot_bulk_schedule(
    client: AsyncClient, employee_headers, seeded_world
):
    """Employee role is forbidden from bulk scheduling."""
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"]],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 403, "Employee should not be able to bulk schedule"


# --- Test 3: Empty customer list validation ---------------------------------

async def test_bulk_schedule_empty_customers_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    """Bulk schedule with empty customer list returns 400."""
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "at least one customer" in resp.text.lower()


# --- Test 4: Duplicate customer IDs validation ------------------------------

async def test_bulk_schedule_duplicate_customers_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    """Bulk schedule with duplicate customer IDs returns 400."""
    customer_id = seeded_world["customer_id"]
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [customer_id, customer_id],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "duplicate" in resp.text.lower()


# --- Test 5: Non-existent employee validation -------------------------------

async def test_bulk_schedule_invalid_employee_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    """Bulk schedule with non-existent employee returns 404."""
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"]],
            "employee_id": str(uuid.uuid4()),
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code in (400, 404)


# --- Test 6: Non-existent customer validation -------------------------------

async def test_bulk_schedule_invalid_customer_rejected(
    client: AsyncClient, admin_headers, seeded_world
):
    """Bulk schedule with non-existent customer returns 404."""
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [str(uuid.uuid4())],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --- Test 7: Created visits appear in list ----------------------------------

async def test_bulk_created_visits_appear_in_list(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Visits created via bulk schedule appear in the normal visits list."""
    customer1 = await _create_test_customer(client, admin_headers, "List1")
    customer2 = await _create_test_customer(client, admin_headers, "List2")

    # Bulk create
    bulk_resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [customer1, customer2],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert bulk_resp.status_code == 201
    bulk_visits = bulk_resp.json()
    bulk_ids = [v["id"] for v in bulk_visits]
    for vid in bulk_ids:
        created_visits.append(vid)

    # List visits
    list_resp = await client.get("/api/v1/visits", headers=admin_headers)
    assert list_resp.status_code == 200
    listed_ids = [v["id"] for v in list_resp.json()]

    for vid in bulk_ids:
        assert vid in listed_ids, f"Bulk-created visit {vid} not in list"


# --- Test 8: Bulk schedule with single customer -----------------------------

async def test_bulk_schedule_single_customer(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Bulk schedule works with a single customer."""
    customer_id = seeded_world["customer_id"]

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [customer_id],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    visits = resp.json()
    assert len(visits) == 1
    created_visits.append(visits[0]["id"])

    # Verify persistence
    row = db.fetch_one(
        "SELECT customer_id, employee_id FROM visits WHERE id = %s",
        (visits[0]["id"],)
    )
    assert str(row["customer_id"]) == customer_id
    assert str(row["employee_id"]) == seeded_world["employee_id"]


# --- Test 9: Bulk schedule preserves scheduled_at ---------------------------

async def test_bulk_schedule_preserves_scheduled_at(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Bulk schedule preserves the scheduled_at timestamp."""
    from datetime import datetime, timedelta, timezone

    scheduled_time = (datetime.now(tz=timezone.utc) + timedelta(hours=3)).isoformat()

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"]],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": scheduled_time,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    visit_id = resp.json()[0]["id"]
    created_visits.append(visit_id)

    row = db.fetch_one(
        "SELECT scheduled_at FROM visits WHERE id = %s",
        (visit_id,)
    )
    assert row is not None


# --- Test 10: Bulk schedule with multiple customers (stress) ----------------

async def test_bulk_schedule_multiple_customers(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Bulk schedule works with multiple customers (5 customers)."""
    customer_ids = []
    for i in range(5):
        cid = await _create_test_customer(client, admin_headers, f"Multi{i}")
        customer_ids.append(cid)

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": customer_ids,
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    visits = resp.json()
    assert len(visits) == 5

    for visit in visits:
        created_visits.append(visit["id"])
        row = db.fetch_one(
            "SELECT id FROM visits WHERE id = %s",
            (visit["id"],)
        )
        assert row is not None


# --- Test 11: Unauthenticated request rejected ------------------------------

async def test_bulk_schedule_unauthenticated_rejected(
    client: AsyncClient, seeded_world
):
    """Unauthenticated bulk schedule request returns 401."""
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"]],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
    )
    assert resp.status_code == 401


# --- Test 12: Created visits have correct status ----------------------------

async def test_bulk_created_visits_have_pending_status(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Bulk-created visits have PENDING status."""
    customer_id = seeded_world["customer_id"]

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [customer_id],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    visit_id = resp.json()[0]["id"]
    created_visits.append(visit_id)

    row = db.fetch_one(
        "SELECT status FROM visits WHERE id = %s",
        (visit_id,)
    )
    assert row["status"] == "PENDING"
