"""
Integration: user management and employee self-profile.

Covers the user detail, activate, deactivate, and /employees/me endpoints
that previously had no direct test coverage.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# --- GET /api/v1/users/{id} -------------------------------------------------


async def test_admin_can_get_user_by_id(client: AsyncClient, admin_headers, seeded_world):
    """Admin can retrieve any user's details by ID."""
    resp = await client.get(
        f"/api/v1/users/{seeded_world['employee_user_id']}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(seeded_world["employee_user_id"])
    assert data["email"] == seeded_world["employee_email"]
    assert data["role"] == "EMPLOYEE"
    assert "is_active" in data


async def test_employee_is_forbidden_from_get_user(client: AsyncClient, employee_headers, seeded_world):
    """Employee cannot access the admin-only user detail endpoint."""
    resp = await client.get(
        f"/api/v1/users/{seeded_world['admin_user_id']}",
        headers=employee_headers,
    )
    assert resp.status_code == 403, f"employee should be forbidden, got {resp.status_code}"


async def test_get_user_not_found(client: AsyncClient, admin_headers):
    """Requesting a non-existent user returns 404."""
    import uuid
    resp = await client.get(
        f"/api/v1/users/{uuid.uuid4()}",
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_unauthenticated_cannot_get_user(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.get(f"/api/v1/users/{seeded_world['employee_user_id']}")
    assert resp.status_code == 401


# --- PATCH /api/v1/users/{id}/activate -------------------------------------


async def test_admin_can_activate_user(client: AsyncClient, admin_headers, seeded_world, db):
    """Admin can activate a user and the change persists."""
    # Use other_employee to avoid breaking employee_headers login in later tests
    user_id = seeded_world["other_employee_user_id"]

    # First deactivate
    await client.patch(f"/api/v1/users/{user_id}/deactivate", headers=admin_headers)

    # Then activate
    resp = await client.patch(f"/api/v1/users/{user_id}/activate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(user_id)
    assert data["is_active"] is True

    # Verify persistence
    row = db.fetch_one("SELECT is_active FROM users WHERE id = %s", (user_id,))
    assert row is not None
    assert row["is_active"] is True

    # Ensure user remains active for other tests
    final = db.fetch_one("SELECT is_active FROM users WHERE id = %s", (user_id,))
    if final and not final["is_active"]:
        await client.patch(f"/api/v1/users/{user_id}/activate", headers=admin_headers)


async def test_employee_cannot_activate_user(client: AsyncClient, employee_headers, seeded_world):
    """Employee cannot activate users."""
    resp = await client.patch(
        f"/api/v1/users/{seeded_world['admin_user_id']}/activate",
        headers=employee_headers,
    )
    assert resp.status_code == 403


# --- PATCH /api/v1/users/{id}/deactivate -----------------------------------


async def test_admin_can_deactivate_user(client: AsyncClient, admin_headers, seeded_world, db):
    """Admin can deactivate a user and the change persists."""
    # Use other_employee to avoid breaking employee_headers login in later tests
    user_id = seeded_world["other_employee_user_id"]

    resp = await client.patch(f"/api/v1/users/{user_id}/deactivate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(user_id)
    assert data["is_active"] is False

    # Verify persistence
    row = db.fetch_one("SELECT is_active FROM users WHERE id = %s", (user_id,))
    assert row is not None
    assert row["is_active"] is False

    # Re-activate so other tests using other_employee_headers still work
    await client.patch(f"/api/v1/users/{user_id}/activate", headers=admin_headers)


async def test_employee_cannot_deactivate_user(client: AsyncClient, employee_headers, seeded_world):
    """Employee cannot deactivate users."""
    resp = await client.patch(
        f"/api/v1/users/{seeded_world['admin_user_id']}/deactivate",
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_deactivate_nonexistent_user_returns_404(client: AsyncClient, admin_headers):
    """Deactivating a non-existent user returns 404."""
    import uuid
    resp = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}/deactivate",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --- GET /api/v1/employees/me ----------------------------------------------


async def test_employee_can_get_own_profile(client: AsyncClient, employee_headers, seeded_world):
    """Employee can retrieve their own profile via /employees/me."""
    resp = await client.get("/api/v1/employees/me", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(seeded_world["employee_id"])
    assert data["user_id"] == str(seeded_world["employee_user_id"])
    assert data["full_name"] == seeded_world.get("employee_name", f"__itest__ Primary Rep")
    assert "user" in data
    assert data["user"]["id"] == str(seeded_world["employee_user_id"])


async def test_employees_me_returns_authenticated_employees_profile(
    client: AsyncClient, employee_headers, seeded_world
):
    """/employees/me returns the profile of the authenticated user, not another."""
    resp = await client.get("/api/v1/employees/me", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Must be the authenticated employee's ID, not the other employee's
    assert data["id"] == str(seeded_world["employee_id"])
    assert data["id"] != str(seeded_world["other_employee_id"])


async def test_admin_without_employee_profile_gets_404(client: AsyncClient, admin_headers):
    """Admin without an employee profile gets 404 from /employees/me."""
    resp = await client.get("/api/v1/employees/me", headers=admin_headers)
    assert resp.status_code == 404


async def test_unauthenticated_cannot_access_employees_me(client: AsyncClient):
    """Unauthenticated requests to /employees/me are rejected."""
    resp = await client.get("/api/v1/employees/me")
    assert resp.status_code == 401
