"""
Integration: all requirement/requirement-category endpoints.

Covers:
  GET    /api/v1/requirement-categories
  POST   /api/v1/requirement-categories
  POST   /api/v1/visits/{visit_id}/requirement-form
  GET    /api/v1/visits/{visit_id}/requirement-form
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# -- GET /requirement-categories -------------------------------------------

async def test_list_categories_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/requirement-categories")
    assert resp.status_code == 401


async def test_list_categories_returns_success(client: AsyncClient, admin_headers):
    """Authenticated user gets a successful response."""
    resp = await client.get("/api/v1/requirement-categories", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_employee_can_list_categories(client: AsyncClient, employee_headers):
    """Any authenticated user can list categories."""
    resp = await client.get("/api/v1/requirement-categories", headers=employee_headers)
    assert resp.status_code == 200, resp.text


# -- POST /requirement-categories ------------------------------------------

async def test_create_category_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": "Should Fail Category"},
    )
    assert resp.status_code == 401


async def test_create_category_persists(client: AsyncClient, admin_headers, db):
    """A successfully created category is visible in the database."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    category_name = "__itest__Test Category"

    resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": category_name},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    cat_id = resp.json()["id"]

    # Verify persistence
    row = db.fetch_one("SELECT id, name FROM requirement_categories WHERE id = %s", (cat_id,))
    assert row is not None
    assert row["name"] == category_name

    # Cleanup
    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM requirement_categories WHERE id = %s", (cat_id,))
    conn.close()


async def test_create_category_missing_name_returns_422(client: AsyncClient, admin_headers):
    """Creating a category without a name returns 422."""
    resp = await client.post(
        "/api/v1/requirement-categories",
        json={},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_category_empty_name_returns_422(client: AsyncClient, admin_headers):
    """Creating a category with an empty name returns 422."""
    resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": ""},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_duplicate_category_succeeds(client: AsyncClient, admin_headers):
    """Creating a category with a duplicate name succeeds.

    NOTE: The requirement_categories.name column has no UNIQUE constraint in the
    database schema, so the service-level IntegrityError guard never fires. This
    is a known limitation; duplicate category names are permitted.
    """
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    category_name = "__itest__Dup Category"

    # First creation
    resp1 = await client.post(
        "/api/v1/requirement-categories",
        json={"name": category_name},
        headers=admin_headers,
    )
    assert resp1.status_code == 201, resp1.text

    # Duplicate creation also succeeds (no unique constraint on name)
    resp2 = await client.post(
        "/api/v1/requirement-categories",
        json={"name": category_name},
        headers=admin_headers,
    )
    assert resp2.status_code == 201

    # Cleanup
    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM requirement_categories WHERE name = %s", (category_name,))
    conn.close()


async def test_employee_cannot_create_category(client: AsyncClient, employee_headers):
    """Employees are forbidden from creating categories (admin-only)."""
    resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": "__itest__Employee Category"},
        headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text


# -- POST /visits/{visit_id}/requirement-form ------------------------------

async def test_submit_form_requires_auth(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.post(
        f"/api/v1/visits/{seeded_world['customer_id']}/requirement-form",
        json={
            "category_id": str(uuid.uuid4()),
            "description": "Should fail",
            "priority": "MEDIUM",
            "expected_timeline": "1 week",
        },
    )
    assert resp.status_code == 401


async def test_submit_form_invalid_priority_returns_422(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Submitting a form with an invalid priority returns 422."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn

    # Create a category
    cat_resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": "__itest__Form Test Category"},
        headers=admin_headers,
    )
    cat_id = cat_resp.json()["id"]

    # Create a valid visit
    visit_id = await create_visit(
        client, admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
    )

    try:
        resp = await client.post(
            f"/api/v1/visits/{visit_id}/requirement-form",
            json={
                "category_id": cat_id,
                "description": "Invalid priority test",
                "priority": "URGENT",
                "expected_timeline": "1 week",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422, resp.text
    finally:
        conn = psycopg2.connect(_sync_dsn())
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM requirement_categories WHERE id = %s", (cat_id,))
        conn.close()


async def test_submit_form_nonexistent_category_returns_404(
    client: AsyncClient, admin_headers, seeded_world, created_visits
):
    """Submitting a form with a non-existent category returns 404."""
    # Create a valid visit
    visit_id = await create_visit(
        client, admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
    )

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/requirement-form",
        json={
            "category_id": str(uuid.uuid4()),
            "description": "Ghost category test",
            "priority": "MEDIUM",
            "expected_timeline": "1 week",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


# -- POST /visits/{visit_id}/requirement-form (authz) -----------------------

async def test_submit_form_nonexistent_visit_returns_404(
    client: AsyncClient, admin_headers
):
    """Submitting a form for a non-existent visit returns 404."""
    resp = await client.post(
        f"/api/v1/visits/{uuid.uuid4()}/requirement-form",
        json={
            "category_id": str(uuid.uuid4()),
            "description": "Ghost visit test",
            "priority": "MEDIUM",
            "expected_timeline": "1 week",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_employee_cannot_submit_form_for_others_visit(
    client: AsyncClient, employee_headers, other_employee_headers, admin_headers, seeded_world, db, created_visits
):
    """Employee cannot submit a form for another employee's visit."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn

    # Create a category (admin only)
    cat_resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": "__itest__Authz Form Category"},
        headers=admin_headers,
    )
    cat_id = cat_resp.json()["id"]

    # Create a visit assigned to the primary employee
    visit_id = await create_visit(
        client, admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
    )

    try:
        # Other employee tries to submit a form for this visit (should be forbidden)
        resp = await client.post(
            f"/api/v1/visits/{visit_id}/requirement-form",
            json={
                "category_id": cat_id,
                "description": "Unauthorized form submission",
                "priority": "MEDIUM",
                "expected_timeline": "1 week",
            },
            headers=other_employee_headers,
        )
        assert resp.status_code == 403, resp.text
    finally:
        # Cleanup category
        conn = psycopg2.connect(_sync_dsn())
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM requirement_categories WHERE id = %s", (cat_id,))
        conn.close()


async def test_employee_can_submit_form_for_own_visit(
    client: AsyncClient, employee_headers, admin_headers, seeded_world, created_visits
):
    """Employee can submit a form for their own visit."""
    # Create a category (admin only)
    cat_resp = await client.post(
        "/api/v1/requirement-categories",
        json={"name": "__itest__Own Visit Category"},
        headers=admin_headers,
    )
    cat_id = cat_resp.json()["id"]

    # Create a visit assigned to this employee
    visit_id = await create_visit(
        client, admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
    )

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/requirement-form",
        json={
            "category_id": cat_id,
            "description": "Authorized form submission",
            "priority": "MEDIUM",
            "expected_timeline": "1 week",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text

    # Cleanup category (visit cleanup handled by created_visits fixture, but
    # the requirement_form row created will block category deletion if not removed)
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        # Delete the form first to avoid FK violation, then the category
        cur.execute("DELETE FROM requirement_forms WHERE visit_id = %s", (visit_id,))
        cur.execute("DELETE FROM requirement_categories WHERE id = %s", (cat_id,))
    conn.close()


# -- GET /visits/{visit_id}/requirement-form -------------------------------

async def test_get_form_requires_auth(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    resp = await client.get(
        f"/api/v1/visits/{seeded_world['customer_id']}/requirement-form",
    )
    assert resp.status_code == 401


async def test_get_form_nonexistent_returns_null(client: AsyncClient, admin_headers, seeded_world):
    """Getting a form for a visit without one returns null."""
    resp = await client.get(
        f"/api/v1/visits/{seeded_world['customer_id']}/requirement-form",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_form_nonexistent_visit_returns_null(client: AsyncClient, admin_headers):
    """Getting a form for a non-existent visit returns null (no form exists)."""
    resp = await client.get(
        f"/api/v1/visits/{uuid.uuid4()}/requirement-form",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json() is None
