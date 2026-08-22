"""
Validation tests — server-side rejection of invalid request payloads.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, requires_db, IS_DB_MIGRATED

# These tests POST directly against the real configured database (no
# separate test DB, no transaction rollback) and previously left every
# created row behind - repeated pytest runs had produced hundreds of
# "Phone Test Customer"/"Update Phone Test"/"Test" rows and dozens of
# "phone_valid_*@test.com"/"phone_invalid_*@test.com" users in the shared
# dev database. This fixture deletes exactly the rows this file creates
# (by name/email pattern) after each test, mirroring the cleanup discipline
# tests/integration/conftest.py already applies to its own fixtures.
_VALIDATION_TEST_CUSTOMER_NAMES = ("Phone Test Customer", "Update Phone Test", "Test")


@pytest.fixture(autouse=True)
def _cleanup_validation_test_rows():
    yield
    if not IS_DB_MIGRATED:
        return
    from sqlalchemy import create_engine, text
    from app.config import settings

    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url, connect_args={"connect_timeout": 3})
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM customers WHERE name = ANY(:names)"),
            {"names": list(_VALIDATION_TEST_CUSTOMER_NAMES)},
        )
        conn.execute(
            text("DELETE FROM refresh_tokens WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'phone_valid_%' OR email LIKE 'phone_invalid_%' OR email = 'new@x.com')"),
        )
        conn.execute(
            text("DELETE FROM users WHERE email LIKE 'phone_valid_%' OR email LIKE 'phone_invalid_%' OR email = 'new@x.com'"),
        )
    engine.dispose()


# ---------------------------------------------------------------------------
# Auth validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_login_empty_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": ""})
    # Empty password is valid JSON; real rejection happens at DB lookup
    assert resp.status_code in (401, 429, 500, 503)


@pytest.mark.asyncio
async def test_login_email_and_mobile_both_missing(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"password": "abc"})
    assert resp.status_code in (422, 500)


# ---------------------------------------------------------------------------
# Customer validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_customer_missing_name(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={"contact_number": "1234567890", "address": "somewhere", "location": {"latitude": 0, "longitude": 0}},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_invalid_latitude(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Test",
            "contact_number": "1234567890",
            "address": "somewhere",
            "location": {"latitude": 999, "longitude": 0},  # out of range
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_invalid_longitude(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Test",
            "contact_number": "1234567890",
            "address": "somewhere",
            "location": {"latitude": 0, "longitude": 999},  # out of range
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_customer_missing_location(client: AsyncClient):
    resp = await client.post(
        "/api/v1/customers",
        json={"name": "Test", "contact_number": "1234567890", "address": "somewhere"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Visit validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_visit_missing_fields(client: AsyncClient):
    resp = await client.post("/api/v1/visits", json={}, headers=admin_headers())
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_visit_invalid_uuid(client: AsyncClient):
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": "not-a-uuid",
            "employee_id": "not-a-uuid",
            "scheduled_at": "2030-01-01T00:00:00Z",
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Check-in validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_check_in_missing_coordinates(client: AsyncClient):
    import uuid
    visit_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User creation validation
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_create_user_missing_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users",
        json={"email": "new@x.com"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_create_user_no_identity(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users",
        json={"password": "secure123"},
        headers=admin_headers(),
    )
    # Should fail at service level (422) or DB level
    assert resp.status_code in (422, 500, 503)


# ---------------------------------------------------------------------------
# Phone number validation (contact_number / mobile_number)
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contact_number",
    [
        "+919876543210",
        "+1 555-123-4567",
        "1234567890",
        "(555) 123-4567",
        "+44 20 7946 0958",
        "1",
    ],
)
async def test_create_customer_valid_phone_numbers(client: AsyncClient, contact_number: str):
    """Valid phone number formats should be accepted."""
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Phone Test Customer",
            "contact_number": contact_number,
            "address": "123 Test St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 201, f"Expected 201 for '{contact_number}', got {resp.status_code}: {resp.text}"


@requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contact_number",
    [
        "ABCDEREZ@",
        "hello",
        "123abc",
        "!@#$%^&*",
        "abcdefghijklmnopqrst",
        "",
    ],
)
async def test_create_customer_invalid_phone_numbers(client: AsyncClient, contact_number: str):
    """Invalid phone number values should be rejected with 422."""
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Phone Test Customer",
            "contact_number": contact_number,
            "address": "123 Test St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422, f"Expected 422 for '{contact_number}', got {resp.status_code}: {resp.text}"


@requires_db
@pytest.mark.asyncio
async def test_create_customer_phone_too_long(client: AsyncClient):
    """Phone numbers exceeding 20 characters should be rejected."""
    resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Phone Test Customer",
            "contact_number": "+1-555-123-456789012345",
            "address": "123 Test St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers(),
    )
    assert resp.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_update_customer_invalid_phone(client: AsyncClient):
    """PATCH should also reject invalid phone numbers."""
    # First create a valid customer
    create_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Update Phone Test",
            "contact_number": "+919876543210",
            "address": "123 Test St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers(),
    )
    assert create_resp.status_code == 201
    customer_id = create_resp.json()["id"]

    # Try to update with invalid phone
    resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"contact_number": "ABCDEREZ@"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    # Verify the original phone was NOT changed
    get_resp = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers())
    assert get_resp.json()["contact_number"] == "+919876543210"


@requires_db
@pytest.mark.asyncio
async def test_create_user_valid_mobile_numbers(client: AsyncClient):
    """Valid mobile number formats should be accepted for user creation."""
    import uuid
    import uuid
    unique_suffix = uuid.uuid4().int % 100000000
    valid_numbers = [
        f"91{unique_suffix:08d}100",
        f"91{unique_suffix:08d}200",
        f"91{unique_suffix:08d}300",
        f"91{unique_suffix:08d}400",
    ]
    for mobile_number in valid_numbers:
        unique_email = f"phone_valid_{uuid.uuid4().hex[:8]}@test.com"
        resp = await client.post(
            "/api/v1/users",
            json={
                "email": unique_email,
                "mobile_number": mobile_number,
                "password": "securepassword123",
            },
            headers=admin_headers(),
        )
        assert resp.status_code == 201, f"Expected 201 for '{mobile_number}', got {resp.status_code}: {resp.text}"


@requires_db
@pytest.mark.asyncio
async def test_create_user_invalid_mobile_numbers(client: AsyncClient):
    """Invalid mobile number values should be rejected with 422."""
    import uuid
    invalid_numbers = [
        "ABCDEREZ@",
        "hello",
        "123abc",
        "!@#$%^&*",
        "abcdefghijklmnopqrstuvwxyz",
    ]
    for mobile_number in invalid_numbers:
        unique_email = f"phone_invalid_{uuid.uuid4().hex[:8]}@test.com"
        resp = await client.post(
            "/api/v1/users",
            json={
                "email": unique_email,
                "mobile_number": mobile_number,
                "password": "securepassword123",
            },
            headers=admin_headers(),
        )
        assert resp.status_code == 422, f"Expected 422 for '{mobile_number}', got {resp.status_code}: {resp.text}"
