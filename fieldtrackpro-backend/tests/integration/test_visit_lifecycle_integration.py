"""
Integration: visit lifecycle (scenarios 21-25).

Targets FT-006 (employee identity confusion), FT-002 (scoping), and the
end-to-end PENDING -> IN_PROGRESS -> COMPLETED workflow that no existing test
exercises.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, iso_in, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Scenario 21: admin creates a visit with a real Employee ID -------------

async def test_admin_creates_visit_with_employee_id(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    visit_id = resp.json()["id"]
    created_visits.append(visit_id)

    row = db.fetch_one(
        "SELECT employee_id, customer_id, status FROM visits WHERE id = %s", (visit_id,)
    )
    assert row is not None, "visit must be persisted, not merely returned"
    assert str(row["employee_id"]) == seeded_world["employee_id"]
    assert row["status"] == "PENDING"


async def test_visit_create_with_user_id_is_rejected_cleanly(
    client: AsyncClient, admin_headers, seeded_world
):
    """
    FT-006: the web client passes users.id where employees.id is required.
    That must surface as a validated 4xx, never an unhandled FK 500.
    """
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"],
            "employee_id": seeded_world["employee_user_id"],  # wrong entity
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code != 500, (
        "FT-006: unknown employee_id must not cause an unhandled 500"
    )
    assert resp.status_code in (400, 404, 422)


async def test_visit_create_with_unknown_customer_is_rejected_cleanly(
    client: AsyncClient, admin_headers, seeded_world
):
    import uuid

    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": str(uuid.uuid4()),
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code != 500
    assert resp.status_code in (400, 404, 422)


async def test_employee_cannot_create_visit(
    client: AsyncClient, employee_headers, seeded_world
):
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": iso_in(2),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 403


# --- Scenario 22: employee sees only their own visits -----------------------

async def test_employee_today_endpoint_returns_only_own_visits(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    mine = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits, scheduled_at=iso_in(1),
    )
    theirs = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["other_employee_id"], created_visits, scheduled_at=iso_in(1),
    )

    resp = await client.get("/api/v1/visits/me/today", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    ids = [v["id"] for v in resp.json()]
    assert mine in ids, "employee must see their own visit scheduled today"
    assert theirs not in ids, "employee must not see another employee's visit"


# --- Scenarios 23-25: state transitions and the full workflow ---------------

async def test_check_in_transitions_pending_to_in_progress(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "PENDING"

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 8.0,
            "captured_at": _now_iso(),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200, f"FT-004: {resp.text}"
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "IN_PROGRESS"


async def test_check_out_transitions_in_progress_to_completed(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    at_site = {
        "latitude": seeded_world["customer_lat"],
        "longitude": seeded_world["customer_lng"],
        "accuracy_m": 8.0,
        "captured_at": _now_iso(),
    }
    assert (await client.post(
        f"/api/v1/visits/{visit_id}/check-in", json=at_site, headers=employee_headers
    )).status_code == 200, "FT-004 blocks precondition"

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-out", json=at_site, headers=employee_headers
    )
    assert resp.status_code == 200, resp.text

    row = db.fetch_one(
        "SELECT status, check_in_at, check_out_at FROM visits WHERE id = %s", (visit_id,)
    )
    assert row["status"] == "COMPLETED"
    assert row["check_in_at"] is not None and row["check_out_at"] is not None


async def test_cannot_check_in_to_another_employees_visit(
    client: AsyncClient, admin_headers, other_employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 8.0,
            "captured_at": _now_iso(),
        },
        headers=other_employee_headers,
    )
    assert resp.status_code == 403
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "PENDING"


async def test_completed_visit_cannot_be_checked_in_again(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    at_site = {
        "latitude": seeded_world["customer_lat"],
        "longitude": seeded_world["customer_lng"],
        "accuracy_m": 8.0,
        "captured_at": _now_iso(),
    }
    assert (await client.post(
        f"/api/v1/visits/{visit_id}/check-in", json=at_site, headers=employee_headers
    )).status_code == 200, "FT-004 blocks precondition"
    assert (await client.post(
        f"/api/v1/visits/{visit_id}/check-out", json=at_site, headers=employee_headers
    )).status_code == 200

    again = await client.post(
        f"/api/v1/visits/{visit_id}/check-in", json=at_site, headers=employee_headers
    )
    assert again.status_code == 422
    assert "transition" in again.text.lower()


# --- Scenario 25: the complete workflow -------------------------------------

async def test_full_visit_workflow_reaches_completed(
    client: AsyncClient, admin_headers, employee_headers, seeded_world,
    created_visits, created_media, db
):
    """
    Schedule -> check-in -> attach evidence -> check-out -> COMPLETED,
    with the audit trail readable at the end. This is the product's core promise.
    """
    from tests.integration.conftest import VALID_JPEG

    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    at_site = {
        "latitude": seeded_world["customer_lat"],
        "longitude": seeded_world["customer_lng"],
        "accuracy_m": 8.0,
        "captured_at": _now_iso(),
    }

    ci = await client.post(
        f"/api/v1/visits/{visit_id}/check-in", json=at_site, headers=employee_headers
    )
    assert ci.status_code == 200, f"FT-004: {ci.text}"

    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("site.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert up.status_code == 201, up.text
    created_media.append(up.json()["id"])

    co = await client.post(
        f"/api/v1/visits/{visit_id}/check-out", json=at_site, headers=employee_headers
    )
    assert co.status_code == 200, co.text

    row = db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))
    assert row["status"] == "COMPLETED"
    assert db.count("visit_media", "visit_id = %s", (visit_id,)) == 1

    logs = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers)
    assert logs.status_code == 200, f"FT-005: audit trail unreadable: {logs.status_code}"
    assert len(logs.json()) == 2, "check-in and check-out must both be audited"


# --- Admin override ---------------------------------------------------------

async def test_admin_can_force_status(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "MISSED", "reason": "integration test"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "MISSED"


async def test_employee_cannot_force_status(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "COMPLETED"},
        headers=employee_headers,
    )
    assert resp.status_code == 403
