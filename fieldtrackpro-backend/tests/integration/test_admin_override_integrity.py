"""
Integration: the admin status override must not create incoherent records.

FT-074. Found during the final forensic pass.

`PATCH /visits/{id}/status` documented itself as overriding "without normal
state machine guard" and assigned `visit.status` directly. Reproduced against
the running API: a COMPLETED visit was moved back to PENDING and persisted as

    status = PENDING, check_in_at = <set>, check_out_at = <set>

which is a state the domain cannot otherwise produce. Downstream that record is
actively misleading: the visit reappears as outstanding work while carrying
evidence that it was finished, and `/visits/me/today` would offer a check-in on
a visit that already has a check-out.

`19_business_logic.md` section 1 defines COMPLETED and MISSED as terminal. An
override is a legitimate administrative tool - the specification explicitly
mentions "mark as MISSED" - but it must not resurrect a terminal visit, and it
must leave the record self-consistent.

Rules asserted here:
  * a terminal visit (COMPLETED / MISSED) cannot be reopened;
  * an override that is allowed leaves timestamps coherent with the status;
  * a no-op override is harmless;
  * the override remains admin-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _complete_visit(client, admin_headers, employee_headers, seeded_world, track) -> str:
    """Drive a visit all the way to COMPLETED through the real endpoints."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], track,
    )
    at_site = {
        "latitude": seeded_world["customer_lat"],
        "longitude": seeded_world["customer_lng"],
        "accuracy_m": 8.0,
        "captured_at": _now_iso(),
    }
    assert (
        await client.post(
            f"/api/v1/visits/{visit_id}/check-in", json=at_site, headers=employee_headers
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/visits/{visit_id}/check-out", json=at_site, headers=employee_headers
        )
    ).status_code == 200
    return visit_id


async def test_completed_visit_cannot_be_reopened(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """FT-074: COMPLETED is terminal; an override must not resurrect it."""
    visit_id = await _complete_visit(
        client, admin_headers, employee_headers, seeded_world, created_visits
    )

    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "PENDING", "reason": "attempted reopen"},
        headers=admin_headers,
    )
    assert resp.status_code in (409, 422), (
        f"FT-074: a COMPLETED visit was reopened (HTTP {resp.status_code})"
    )

    row = db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))
    assert row["status"] == "COMPLETED", "the terminal state must be preserved"


async def test_completed_visit_cannot_be_forced_to_in_progress(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await _complete_visit(
        client, admin_headers, employee_headers, seeded_world, created_visits
    )

    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=admin_headers,
    )
    assert resp.status_code in (409, 422)
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "COMPLETED"


async def test_override_never_leaves_status_inconsistent_with_timestamps(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """
    FT-074, stated as the underlying invariant: a PENDING visit must not carry
    check-in or check-out timestamps, whatever route produced it.
    """
    visit_id = await _complete_visit(
        client, admin_headers, employee_headers, seeded_world, created_visits
    )

    await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "PENDING"},
        headers=admin_headers,
    )

    row = db.fetch_one(
        "SELECT status, check_in_at, check_out_at FROM visits WHERE id = %s", (visit_id,)
    )
    if row["status"] == "PENDING":
        assert row["check_in_at"] is None and row["check_out_at"] is None, (
            "FT-074: visit is PENDING but retains check-in/check-out timestamps"
        )


async def test_admin_can_still_mark_a_pending_visit_missed(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """The legitimate use documented in the API design must keep working."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )

    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "MISSED", "reason": "customer site closed"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "MISSED"


async def test_admin_can_resolve_a_flagged_visit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """FLAGGED is a pending judgement call; the admin must be able to close it."""
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
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "FLAGGED"

    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "COMPLETED", "reason": "reviewed; GPS drift accepted"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "COMPLETED"


async def test_setting_the_same_status_is_a_harmless_noop(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "PENDING"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "PENDING"


async def test_override_remains_admin_only(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/status",
        json={"status": "MISSED"},
        headers=employee_headers,
    )
    assert resp.status_code == 403
