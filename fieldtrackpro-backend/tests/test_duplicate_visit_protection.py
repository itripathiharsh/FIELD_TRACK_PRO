"""
Duplicate Visit Protection — unit + integration tests.

Unit tests (first section) run without any database.
Integration tests (second section) follow the same pattern as
tests/integration/conftest.py: they create self-contained test data with a
TEST_MARKER, run assertions, then delete everything in teardown. No real seed
data is mutated.

Test inventory
--------------
Unit tests (no DB):
 U1. test_no_conflict_returns_none             — repo returns None → no raise
 U2. test_conflict_raises_duplicate_visit      — repo returns a visit → 409 raised
 U3. test_error_message_includes_visit_id      — visit.id in error detail
 U4. test_flagged_status_triggers_conflict     — FLAGGED counts as active

Integration tests (requires DB):
 I1. test_exact_duplicate_visit_blocked        — same employee + time → 409
 I2. test_within_window_blocked                — 30 min apart → 409
 I3. test_outside_window_allowed               — (window+1) min apart → 201
 I4. test_different_employee_same_time_allowed — different employees → both 201
 I5. test_bulk_conflict_blocked                — bulk create at conflicting time → 409
 I6. test_error_body_has_correct_fields        — 409 body has error_code + detail
 I7. test_concurrent_duplicate_prevention      — race condition → only 1 succeeds
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import psycopg2
import pytest

from app.exceptions.custom import DuplicateVisitException
from app.models.visit import Visit, VisitStatus
from app.repositories.visit_repo import VisitRepository
from app.services.visit_service import (
    _check_duplicate_visit,
    VISIT_CONFLICT_WINDOW_MINUTES,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TEST_MARKER = "__dvp_test__"
TEST_PASSWORD = "TestPass!2026"

NOW_UTC = datetime(2099, 3, 1, 10, 0, 0, tzinfo=timezone.utc)


def _make_visit_mock(
    employee_id: uuid.UUID,
    customer_id: uuid.UUID,
    scheduled_at: datetime,
    status: VisitStatus = VisitStatus.PENDING,
    visit_id: uuid.UUID | None = None,
) -> Visit:
    """Lightweight Visit mock — no DB."""
    v = MagicMock(spec=Visit)
    v.id = visit_id or uuid.uuid4()
    v.employee_id = employee_id
    v.customer_id = customer_id
    v.scheduled_at = scheduled_at
    v.status = status
    type(v).employee_name = PropertyMock(return_value="Test Employee")
    type(v).customer_name = PropertyMock(return_value="Test Customer")
    return v


def _mock_session() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# Database helpers for integration tests
# ---------------------------------------------------------------------------

def _sync_dsn() -> str:
    from app.config import settings
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def _db_available() -> bool:
    try:
        with psycopg2.connect(_sync_dsn(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users LIMIT 1")
        return True
    except Exception:
        return False


IS_DB_AVAILABLE = _db_available()

requires_db = pytest.mark.skipif(
    not IS_DB_AVAILABLE,
    reason="Duplicate-visit integration tests require a migrated PostgreSQL database",
)


class _TestWorld:
    """
    Self-contained test world: one admin user, one employee, one customer.
    All rows carry TEST_MARKER and are deleted in cleanup().
    """

    def __init__(self) -> None:
        self.admin_user_id = str(uuid.uuid4())
        self.employee_user_id = str(uuid.uuid4())
        self.employee_id = str(uuid.uuid4())
        self.employee2_user_id = str(uuid.uuid4())
        self.employee2_id = str(uuid.uuid4())
        self.territory_id = str(uuid.uuid4())
        self.customer_id = str(uuid.uuid4())
        self.customer2_id = str(uuid.uuid4())

    def setup(self) -> None:
        from app.core.security import hash_password
        pw = hash_password(TEST_PASSWORD)
        admin_email = f"{TEST_MARKER}admin@dvp.test"
        emp_email = f"{TEST_MARKER}emp1@dvp.test"
        emp2_email = f"{TEST_MARKER}emp2@dvp.test"

        with psycopg2.connect(_sync_dsn()) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Users
                cur.execute(
                    "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at)"
                    " VALUES (%s,%s,%s,'ADMIN',true,now(),now())",
                    (self.admin_user_id, admin_email, pw),
                )
                cur.execute(
                    "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at)"
                    " VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
                    (self.employee_user_id, emp_email, pw),
                )
                cur.execute(
                    "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at)"
                    " VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
                    (self.employee2_user_id, emp2_email, pw),
                )
                # Territory
                cur.execute(
                    "INSERT INTO territories (id,name,created_at) VALUES (%s,%s,now())",
                    (self.territory_id, f"{TEST_MARKER}Territory"),
                )
                # Employees
                cur.execute(
                    "INSERT INTO employees (id,user_id,full_name,territory_id,employee_code,created_at)"
                    " VALUES (%s,%s,%s,%s,%s,now())",
                    (self.employee_id, self.employee_user_id, f"{TEST_MARKER} Rep1",
                     self.territory_id, f"{TEST_MARKER}REP1"),
                )
                cur.execute(
                    "INSERT INTO employees (id,user_id,full_name,territory_id,employee_code,created_at)"
                    " VALUES (%s,%s,%s,%s,%s,now())",
                    (self.employee2_id, self.employee2_user_id, f"{TEST_MARKER} Rep2",
                     self.territory_id, f"{TEST_MARKER}REP2"),
                )
                # Customers (Bengaluru coords, 200m geofence)
                cur.execute(
                    "INSERT INTO customers (id,name,contact_number,address,"
                    " location,geofence_radius_m,created_by,created_at)"
                    " VALUES (%s,%s,'9999999999','Test St',"
                    " ST_SetSRID(ST_MakePoint(77.5946,12.9716),4326)::geography,"
                    " 200,%s,now())",
                    (self.customer_id, f"{TEST_MARKER} Outlet1", self.admin_user_id),
                )
                cur.execute(
                    "INSERT INTO customers (id,name,contact_number,address,"
                    " location,geofence_radius_m,created_by,created_at)"
                    " VALUES (%s,%s,'9999999998','Test St2',"
                    " ST_SetSRID(ST_MakePoint(77.5950,12.9720),4326)::geography,"
                    " 200,%s,now())",
                    (self.customer2_id, f"{TEST_MARKER} Outlet2", self.admin_user_id),
                )

    def cleanup(self) -> None:
        with psycopg2.connect(_sync_dsn()) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM visits WHERE employee_id IN (%s,%s)",
                    (self.employee_id, self.employee2_id),
                )
                cur.execute(
                    "DELETE FROM customers WHERE id IN (%s,%s)",
                    (self.customer_id, self.customer2_id),
                )
                cur.execute(
                    "DELETE FROM employee_territory_assignments"
                    " WHERE employee_id IN (%s,%s)",
                    (self.employee_id, self.employee2_id),
                )
                cur.execute(
                    "DELETE FROM employees WHERE id IN (%s,%s)",
                    (self.employee_id, self.employee2_id),
                )
                cur.execute(
                    "DELETE FROM territories WHERE id = %s",
                    (self.territory_id,),
                )
                cur.execute(
                    "DELETE FROM refresh_tokens WHERE user_id IN (%s,%s,%s)",
                    (self.admin_user_id, self.employee_user_id, self.employee2_user_id),
                )
                cur.execute(
                    "DELETE FROM users WHERE id IN (%s,%s,%s)",
                    (self.admin_user_id, self.employee_user_id, self.employee2_user_id),
                )

    def admin_headers(self) -> dict:
        from app.core.security import create_access_token
        from app.models.user import Role
        token = create_access_token(self.admin_user_id, Role.ADMIN.value)
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def world():
    """Create and tear down the test world once per module."""
    if not IS_DB_AVAILABLE:
        pytest.skip("DB unavailable")
    w = _TestWorld()
    w.setup()
    yield w
    w.cleanup()


# ---------------------------------------------------------------------------
# U1-U4 — Pure unit tests (no DB, no fixtures needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conflict_returns_none():
    """U1: repo returns None → helper does not raise."""
    session = _mock_session()
    with patch.object(VisitRepository, "find_conflicting_visit", new=AsyncMock(return_value=None)):
        await _check_duplicate_visit(uuid.uuid4(), NOW_UTC, session)  # no raise


@pytest.mark.asyncio
async def test_conflict_raises_duplicate_visit_exception():
    """U2: repo returns a visit → DuplicateVisitException raised with 409."""
    emp_id = uuid.uuid4()
    existing = _make_visit_mock(emp_id, uuid.uuid4(), NOW_UTC, VisitStatus.PENDING)
    session = _mock_session()
    with patch.object(VisitRepository, "find_conflicting_visit", new=AsyncMock(return_value=existing)):
        with pytest.raises(DuplicateVisitException) as exc_info:
            await _check_duplicate_visit(emp_id, NOW_UTC, session)
    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.error_code == "DUPLICATE_VISIT"
    assert str(VISIT_CONFLICT_WINDOW_MINUTES) in exc.detail
    assert "Test Employee" in exc.detail
    assert "Test Customer" in exc.detail


@pytest.mark.asyncio
async def test_error_message_includes_visit_id():
    """U3: error detail must name the conflicting visit's UUID."""
    emp_id = uuid.uuid4()
    conflict_id = uuid.uuid4()
    existing = _make_visit_mock(emp_id, uuid.uuid4(), NOW_UTC, VisitStatus.PENDING, visit_id=conflict_id)
    session = _mock_session()
    with patch.object(VisitRepository, "find_conflicting_visit", new=AsyncMock(return_value=existing)):
        with pytest.raises(DuplicateVisitException) as exc_info:
            await _check_duplicate_visit(emp_id, NOW_UTC, session)
    assert str(conflict_id) in exc_info.value.detail


@pytest.mark.asyncio
async def test_flagged_status_triggers_conflict():
    """U4: FLAGGED is non-terminal → must trigger a conflict."""
    emp_id = uuid.uuid4()
    existing = _make_visit_mock(emp_id, uuid.uuid4(), NOW_UTC, VisitStatus.FLAGGED)
    session = _mock_session()
    with patch.object(VisitRepository, "find_conflicting_visit", new=AsyncMock(return_value=existing)):
        with pytest.raises(DuplicateVisitException):
            await _check_duplicate_visit(emp_id, NOW_UTC, session)


# ---------------------------------------------------------------------------
# I1-I7 — Integration tests (require real DB)
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_exact_duplicate_visit_blocked(client, world):
    """I1: same employee + exact same scheduled_at → second call is 409."""
    scheduled_at = "2099-03-10T08:00:00+00:00"
    payload = {
        "employee_id": world.employee_id,
        "customer_id": world.customer_id,
        "scheduled_at": scheduled_at,
    }
    headers = world.admin_headers()

    r1 = await client.post("/api/v1/visits", json=payload, headers=headers)
    assert r1.status_code == 201, f"First create failed: {r1.text}"

    r2 = await client.post("/api/v1/visits", json=payload, headers=headers)
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
    body = r2.json()
    # Error envelope: {"error": {"code": "DUPLICATE_VISIT", "message": "..."}}
    assert body["error"]["code"] == "DUPLICATE_VISIT"


@requires_db
@pytest.mark.asyncio
async def test_within_window_blocked(client, world):
    """I2: same employee, visits 30 min apart (< window) → 409 on second."""
    t1 = "2099-03-11T09:00:00+00:00"
    t2 = "2099-03-11T09:30:00+00:00"  # 30 min apart — within 60-min window
    headers = world.admin_headers()

    r1 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer_id, "scheduled_at": t1},
        headers=headers,
    )
    assert r1.status_code == 201, f"First visit failed: {r1.text}"

    r2 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer2_id, "scheduled_at": t2},
        headers=headers,
    )
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
    assert r2.json()["error"]["code"] == "DUPLICATE_VISIT"


@requires_db
@pytest.mark.asyncio
async def test_outside_window_allowed(client, world):
    """I3: same employee, visits (window+1) minutes apart → both 201."""
    gap = VISIT_CONFLICT_WINDOW_MINUTES + 1
    t1_dt = datetime(2099, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
    t2_dt = t1_dt + timedelta(minutes=gap)
    t1 = t1_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    t2 = t2_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    headers = world.admin_headers()

    r1 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer_id, "scheduled_at": t1},
        headers=headers,
    )
    assert r1.status_code == 201, f"First visit failed: {r1.text}"

    r2 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer2_id, "scheduled_at": t2},
        headers=headers,
    )
    assert r2.status_code == 201, f"Second visit (outside window) failed: {r2.text}"


@requires_db
@pytest.mark.asyncio
async def test_different_employee_same_time_allowed(client, world):
    """I4: different employees at the same time → both 201 (no conflict)."""
    scheduled_at = "2099-03-13T10:00:00+00:00"
    headers = world.admin_headers()

    r1 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer_id, "scheduled_at": scheduled_at},
        headers=headers,
    )
    assert r1.status_code == 201, f"Employee 1 visit failed: {r1.text}"

    r2 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee2_id, "customer_id": world.customer2_id, "scheduled_at": scheduled_at},
        headers=headers,
    )
    assert r2.status_code == 201, f"Employee 2 visit failed: {r2.text}"


@requires_db
@pytest.mark.asyncio
async def test_bulk_conflict_blocked(client, world):
    """I5: bulk create at a time already booked for employee → 409."""
    scheduled_at = "2099-03-14T14:00:00+00:00"
    headers = world.admin_headers()

    # Create a conflict-seeding single visit first
    r1 = await client.post(
        "/api/v1/visits",
        json={"employee_id": world.employee_id, "customer_id": world.customer_id, "scheduled_at": scheduled_at},
        headers=headers,
    )
    assert r1.status_code == 201, f"Seed visit failed: {r1.text}"

    # Bulk create at the same time should be rejected
    r2 = await client.post(
        "/api/v1/visits/bulk",
        json={
            "employee_id": world.employee_id,
            "customer_ids": [world.customer2_id],
            "scheduled_at": scheduled_at,
        },
        headers=headers,
    )
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
    assert r2.json()["error"]["code"] == "DUPLICATE_VISIT"


@requires_db
@pytest.mark.asyncio
async def test_error_body_has_correct_fields(client, world):
    """I6: 409 response body must contain error_code=DUPLICATE_VISIT and detail."""
    scheduled_at = "2099-03-15T11:00:00+00:00"
    payload = {
        "employee_id": world.employee_id,
        "customer_id": world.customer_id,
        "scheduled_at": scheduled_at,
    }
    headers = world.admin_headers()

    r1 = await client.post("/api/v1/visits", json=payload, headers=headers)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/visits", json=payload, headers=headers)
    assert r2.status_code == 409
    body = r2.json()
    # Error envelope: {"error": {"code": "...", "message": "..."}}
    assert "error" in body, f"Missing 'error' envelope: {body}"
    assert body["error"]["code"] == "DUPLICATE_VISIT"
    # The message must mention the window size
    assert str(VISIT_CONFLICT_WINDOW_MINUTES) in body["error"]["message"]


@requires_db
@pytest.mark.asyncio
async def test_concurrent_duplicate_prevention(world):
    """
    I7: concurrent duplicate detection — two independent POST /visits at the
    same slot using TWO separate HTTPX AsyncClient instances so the event loop
    can truly interleave them.

    NOTE: using a single shared client serialises requests inside ASGI test
    mode, which makes both succeed.  Two clients share the same underlying
    app + DB, so the second INSERT either hits the service-layer check (which
    sees the first committed row) or the DB partial unique index, producing a
    409 or 500.  Exactly 1 must succeed.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    scheduled_at = "2099-03-16T15:00:00+00:00"
    payload = {
        "employee_id": world.employee_id,
        "customer_id": world.customer_id,
        "scheduled_at": scheduled_at,
    }
    headers = world.admin_headers()

    async def post_with_own_client():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test-concurrent"
        ) as c:
            return await c.post("/api/v1/visits", json=payload, headers=headers)

    responses = await asyncio.gather(
        post_with_own_client(),
        post_with_own_client(),
        return_exceptions=True,
    )

    status_codes = [r.status_code for r in responses if not isinstance(r, Exception)]
    success_count = sum(1 for s in status_codes if s == 201)
    failure_count = sum(1 for s in status_codes if s in (409, 500, 503))

    assert success_count == 1, (
        f"Expected exactly 1 success, got {success_count}. "
        f"Status codes: {status_codes}"
    )
    assert failure_count >= 1, (
        f"Expected at least 1 conflict/error, got {failure_count}. "
        f"Status codes: {status_codes}"
    )

