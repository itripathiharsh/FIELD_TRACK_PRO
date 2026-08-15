"""
Integration: POST /api/v1/employees and PATCH /api/v1/employees/{id}.

Covers employee creation and update which previously had no direct integration test coverage.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import db_cursor, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# -- Create -----------------------------------------------------------------

async def test_admin_can_create_employee(client: AsyncClient, admin_headers, db):
    """Admin can create a new employee profile linked to a fresh user."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    new_user_id = str(uuid.uuid4())
    from app.core.security import hash_password
    from tests.integration.conftest import TEST_PASSWORD

    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
            (new_user_id, f"__itest__emp_create_{new_user_id[:8]}@fieldtrack.test", hash_password(TEST_PASSWORD)),
        )
    conn.close()

    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": new_user_id,
            "full_name": "New Test Employee",
            "employee_code": f"__itest__NEWEMP_{new_user_id[:8]}",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["full_name"] == "New Test Employee"

    # Cleanup
    emp_id = resp.json()["id"]
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM employees WHERE id = %s", (emp_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (new_user_id,))


async def test_create_employee_persists_in_database(client: AsyncClient, admin_headers, db):
    """A successfully created employee is visible in the database."""
    # Create a fresh user to link the employee to.
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    new_user_id = str(uuid.uuid4())
    from app.core.security import hash_password
    from tests.integration.conftest import TEST_PASSWORD

    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
            (new_user_id, f"__itest__newuser_{new_user_id[:8]}@fieldtrack.test", hash_password(TEST_PASSWORD)),
        )
    conn.close()

    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": new_user_id,
            "full_name": "Persist Test Employee",
            "employee_code": f"__itest__PERSIST_{new_user_id[:8]}",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    emp_id = resp.json()["id"]

    # Verify persistence
    row = db.fetch_one("SELECT id, full_name FROM employees WHERE id = %s", (emp_id,))
    assert row is not None, "employee should exist in database"
    assert row["full_name"] == "Persist Test Employee"

    # Cleanup
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM employees WHERE id = %s", (emp_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (new_user_id,))


async def test_create_employee_missing_user_id_returns_422(client: AsyncClient, admin_headers):
    """Creating an employee without user_id returns 422."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "No User Employee",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_employee_nonexistent_user_returns_404(client: AsyncClient, admin_headers):
    """Creating an employee for a non-existent user returns 404."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Ghost Employee",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_create_duplicate_employee_returns_409(client: AsyncClient, admin_headers, seeded_world):
    """Creating an employee for a user that already has a profile returns 409."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": str(seeded_world["employee_user_id"]),
            "full_name": "Duplicate Employee",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_employee_cannot_create_employee(client: AsyncClient, employee_headers):
    """Non-admin users are forbidden from creating employees."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Unauthorized Employee",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_unauthenticated_cannot_create_employee(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.post(
        "/api/v1/employees",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Anonymous Employee",
        },
    )
    assert resp.status_code == 401


# -- Update -----------------------------------------------------------------

async def test_admin_can_update_employee(client: AsyncClient, admin_headers, seeded_world):
    """Admin can update an existing employee's profile."""
    emp_id = seeded_world["other_employee_id"]

    resp = await client.patch(
        f"/api/v1/employees/{emp_id}",
        json={"full_name": "Updated Other Employee"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Updated Other Employee"


async def test_update_employee_persists_in_database(client: AsyncClient, admin_headers, seeded_world, db):
    """Updated employee values are committed to the database."""
    emp_id = seeded_world["other_employee_id"]

    resp = await client.patch(
        f"/api/v1/employees/{emp_id}",
        json={"full_name": "Persist Update Test", "employee_code": "__itest__UPD1"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    row = db.fetch_one("SELECT full_name, employee_code FROM employees WHERE id = %s", (str(emp_id),))
    assert row is not None
    assert row["full_name"] == "Persist Update Test"
    assert row["employee_code"] == "__itest__UPD1"


async def test_update_nonexistent_employee_returns_404(client: AsyncClient, admin_headers):
    """Updating a non-existent employee returns 404."""
    resp = await client.patch(
        f"/api/v1/employees/{uuid.uuid4()}",
        json={"full_name": "Ghost Update"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_employee_cannot_update_employee(client: AsyncClient, employee_headers, seeded_world):
    """Non-admin users are forbidden from updating employees."""
    resp = await client.patch(
        f"/api/v1/employees/{seeded_world['employee_id']}",
        json={"full_name": "Unauthorized Update"},
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_unauthenticated_cannot_update_employee(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.patch(
        f"/api/v1/employees/{seeded_world['employee_id']}",
        json={"full_name": "Anonymous Update"},
    )
    assert resp.status_code == 401
