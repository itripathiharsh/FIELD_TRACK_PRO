"""
Integration: geo verification audit trail (scenarios 17-20).

Targets FT-005 (CRITICAL): `visit_service.get_visit_geo_logs` calls
`GeoLogRepository.list_by_visit`, which does not exist -> AttributeError -> 500.
The audit trail is the system's legal defensibility and cannot currently be read.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Scenario 17: successful geo event writes a log -------------------------

async def test_successful_check_in_writes_geo_log(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
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
        headers=employee_headers,
    )
    assert resp.status_code == 200, f"FT-004 blocks this precondition: {resp.text}"

    logs = db.fetch_all(
        "SELECT is_valid, distance_from_customer_m, failure_reason "
        "FROM geo_verification_logs WHERE visit_id = %s",
        (visit_id,),
    )
    assert len(logs) == 1, "every check-in attempt must write exactly one audit row"
    assert logs[0]["is_valid"] is True
    assert logs[0]["failure_reason"] is None
    assert float(logs[0]["distance_from_customer_m"]) < 100.0


# --- Scenario 18: failed geo event writes a log too -------------------------

async def test_failed_check_in_writes_audit_record(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """A rejected attempt must still be recorded - that is the anti-fraud evidence."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0, "captured_at": _now_iso()},
        headers=employee_headers,
    )
    assert resp.status_code == 422

    logs = db.fetch_all(
        "SELECT is_valid, failure_reason, distance_from_customer_m "
        "FROM geo_verification_logs WHERE visit_id = %s",
        (visit_id,),
    )
    assert len(logs) == 1
    assert logs[0]["is_valid"] is False
    assert logs[0]["failure_reason"], "a failure must record a human-readable reason"
    assert float(logs[0]["distance_from_customer_m"]) > 100.0


async def test_mock_location_attempt_is_recorded_distinctly(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """Spec: 'mock GPS suspected' must be distinguishable from 'out of radius'."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"],
            "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0,
            "is_mock_location": True,
            "captured_at": _now_iso(),
        },
        headers=employee_headers,
    )
    log = db.fetch_one(
        "SELECT failure_reason FROM geo_verification_logs WHERE visit_id = %s", (visit_id,)
    )
    assert log is not None
    assert "mock" in log["failure_reason"].lower()


# --- Scenario 19: logs can be read back (FT-005) ----------------------------

async def test_geo_logs_can_be_read_back_by_admin(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """
    FT-005 (CRITICAL): this endpoint currently raises AttributeError -> 500.
    """
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0, "captured_at": _now_iso()},
        headers=employee_headers,
    )

    resp = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers)
    assert resp.status_code == 200, f"FT-005: geo-logs endpoint failed: {resp.status_code}"
    logs = resp.json()
    assert isinstance(logs, list) and len(logs) >= 1
    assert logs[0]["visit_id"] == visit_id
    assert "is_valid" in logs[0]


async def test_assigned_employee_can_read_own_geo_logs(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0, "captured_at": _now_iso()},
        headers=employee_headers,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=employee_headers)
    assert resp.status_code == 200, f"FT-005: {resp.status_code}"


async def test_geo_logs_endpoint_never_returns_500(
    client: AsyncClient, admin_headers, seeded_world, created_visits
):
    """Explicit guard: a visit with no attempts must return [], not crash."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers)
    assert resp.status_code != 500, "FT-005: server error reading the audit trail"
    assert resp.status_code == 200
    assert resp.json() == []


# --- Scenario 20: deterministic ordering ------------------------------------

async def test_geo_log_ordering_is_deterministic(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """Three attempts must come back in a stable, documented order."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    for lon in (80.2707, 80.2708, 80.2709):
        await client.post(
            f"/api/v1/visits/{visit_id}/check-in",
            json={"latitude": 13.0827, "longitude": lon, "accuracy_m": 8.0, "captured_at": _now_iso()},
            headers=employee_headers,
        )

    first = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers)
    second = await client.get(f"/api/v1/visits/{visit_id}/geo-logs", headers=admin_headers)
    assert first.status_code == 200 and second.status_code == 200, "FT-005"

    a = [row["id"] for row in first.json()]
    b = [row["id"] for row in second.json()]
    assert len(a) == 3
    assert a == b, "geo log ordering must be stable across identical requests"

    stamps = [row["attempted_at"] for row in first.json()]
    assert stamps == sorted(stamps, reverse=True) or stamps == sorted(stamps), (
        "geo logs must be sorted by attempted_at (either direction, but consistently)"
    )


# --- Repeated failures escalate to FLAGGED ----------------------------------

async def test_three_failures_flag_the_visit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    for _ in range(3):
        await client.post(
            f"/api/v1/visits/{visit_id}/check-in",
            json={"latitude": 13.0827, "longitude": 80.2707, "accuracy_m": 8.0, "captured_at": _now_iso()},
            headers=employee_headers,
        )

    assert db.count("geo_verification_logs", "visit_id = %s", (visit_id,)) == 3
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "FLAGGED"
