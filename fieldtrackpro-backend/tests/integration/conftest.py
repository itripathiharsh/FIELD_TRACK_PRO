"""
Integration test infrastructure for FieldTrack Pro.

Design goals (Phase 0):
  * Exercise REAL business success paths, not just auth/validation failures.
  * Authenticate as REAL seeded users through the REAL /auth/login endpoint.
  * Assert COMMITTED database state via an INDEPENDENT synchronous connection,
    so a passing HTTP response can never be mistaken for real persistence.
  * Create every fixture record with a traceable marker and delete it afterwards,
    leaving the developer's seed data byte-for-byte untouched.

This suite is additive: it does not modify or replace the existing unit suite.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import psycopg2
import psycopg2.extras
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.security import hash_password
from app.main import app

# ---------------------------------------------------------------------------
# Everything this suite creates is tagged so cleanup is exact and reversible.
# ---------------------------------------------------------------------------

TEST_MARKER = "__itest__"
TEST_PASSWORD = "IntegrationTest!2026"

# Bengaluru reference point, matching the existing seed customer location.
SEED_LAT = 12.9716
SEED_LNG = 77.5946


def _sync_dsn() -> str:
    """
    Plain psycopg2 DSN for reading committed state as the application sees it.
    """
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def _owner_dsn() -> str:
    """
    Privileged DSN used ONLY for fixture teardown.

    FT-032 makes `geo_verification_logs` insert-only for the application role,
    so the app itself cannot delete audit rows - which is the point. Test
    fixtures must therefore clean up as the schema owner. Using the owner here
    is deliberate and is confined to setup/teardown; every assertion about
    application behaviour still runs through the restricted role.
    """
    url = settings.migration_database_url or settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


def db_available() -> bool:
    try:
        with psycopg2.connect(_sync_dsn(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users LIMIT 1")
                cur.execute("SELECT PostGIS_Version()")
        return True
    except Exception:
        return False


DB_AVAILABLE = db_available()

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="Integration tests require a migrated PostGIS database (see docs/REPAIR_BASELINE.md)",
)


# ---------------------------------------------------------------------------
# Independent synchronous DB access â€” the source of truth for persistence
# ---------------------------------------------------------------------------


@contextmanager
def db_cursor(privileged: bool = False) -> Iterator[psycopg2.extras.RealDictCursor]:
    """
    Yield a cursor on a connection completely separate from the app's async
    engine. If a row is visible here, it was genuinely COMMITTED.

    ``privileged=True`` connects as the schema owner and is reserved for
    fixture teardown of insert-only tables (see :func:`_owner_dsn`).
    """
    conn = psycopg2.connect(_owner_dsn() if privileged else _sync_dsn())
    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


class DbAsserts:
    """Helpers for asserting real, committed database state."""

    @staticmethod
    def fetch_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with db_cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with db_cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def count(table: str, where: str = "TRUE", params: tuple = ()) -> int:
        # `table` is never user-supplied; call sites pass literals only.
        with db_cursor() as cur:
            cur.execute(f"SELECT count(*) AS c FROM {table} WHERE {where}", params)  # noqa: S608
            return int(cur.fetchone()["c"])

    @staticmethod
    def customer_coords(customer_id: str) -> tuple[float, float]:
        """Return (lat, lng) straight from PostGIS for the given customer."""
        row = DbAsserts.fetch_one(
            "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
            "FROM customers WHERE id = %s",
            (customer_id,),
        )
        assert row is not None, f"customer {customer_id} not found"
        return float(row["lat"]), float(row["lng"])


@pytest.fixture(scope="session")
def db() -> type[DbAsserts]:
    return DbAsserts


# ---------------------------------------------------------------------------
# HTTP client bound to the real ASGI app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://itest"
    ) as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine():
    """Dispose the async engine per test so no pooled socket outlives its loop."""
    yield
    from app.database import engine

    await engine.dispose()


# ---------------------------------------------------------------------------
# Seeded principals â€” created here, owned here, destroyed here
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(uuid.uuid4())


def _purge_test_artifacts() -> None:
    """
    Remove anything tagged with TEST_MARKER.

    Runs before AND after the session so an interrupted run can never poison the
    next one. Only rows created by this suite are touched; developer seed data
    carries no marker and is therefore never matched.
    """
    with db_cursor(privileged=True) as cur:
        cur.execute(
            "DELETE FROM geo_verification_logs WHERE visit_id IN ("
            "  SELECT v.id FROM visits v"
            "  JOIN employees e ON e.id = v.employee_id"
            "  WHERE e.employee_code LIKE %s)",
            (f"{TEST_MARKER}%",),
        )
        cur.execute(
            "DELETE FROM visit_media WHERE visit_id IN ("
            "  SELECT v.id FROM visits v"
            "  JOIN employees e ON e.id = v.employee_id"
            "  WHERE e.employee_code LIKE %s)",
            (f"{TEST_MARKER}%",),
        )
        cur.execute(
            "DELETE FROM visits WHERE employee_id IN ("
            "  SELECT id FROM employees WHERE employee_code LIKE %s)",
            (f"{TEST_MARKER}%",),
        )
        cur.execute(
            "DELETE FROM visits WHERE customer_id IN ("
            "  SELECT id FROM customers WHERE name LIKE %s)",
            (f"{TEST_MARKER}%",),
        )
        cur.execute("DELETE FROM customers WHERE name LIKE %s", (f"{TEST_MARKER}%",))
        cur.execute("DELETE FROM employees WHERE employee_code LIKE %s", (f"{TEST_MARKER}%",))
        cur.execute(
            "DELETE FROM refresh_tokens WHERE user_id IN ("
            "  SELECT id FROM users WHERE email LIKE %s)",
            (f"{TEST_MARKER}%",),
        )
        cur.execute("DELETE FROM territories WHERE name LIKE %s", (f"{TEST_MARKER}%",))
        cur.execute("DELETE FROM users WHERE email LIKE %s", (f"{TEST_MARKER}%",))


@pytest.fixture(scope="session")
def seeded_world() -> Iterator[dict[str, Any]]:
    """
    Provision a self-contained world: admin user, employee user + profile,
    territory, and customer with a real PostGIS geofence.

    Every row is created by this fixture and removed at teardown. Pre-existing
    developer seed data is never read for mutation and never deleted.
    """
    if not DB_AVAILABLE:
        pytest.skip("integration DB unavailable")

    # Self-heal: clear residue from any previously interrupted run.
    _purge_test_artifacts()

    ids = {
        "admin_user_id": _new_id(),
        "employee_user_id": _new_id(),
        "other_employee_user_id": _new_id(),
        "employee_id": _new_id(),
        "other_employee_id": _new_id(),
        "territory_id": _new_id(),
        "customer_id": _new_id(),
    }
    pw_hash = hash_password(TEST_PASSWORD)
    admin_email = f"{TEST_MARKER}admin@fieldtrack.test"
    emp_email = f"{TEST_MARKER}employee@fieldtrack.test"
    other_email = f"{TEST_MARKER}other@fieldtrack.test"

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'ADMIN',true,now(),now())",
            (ids["admin_user_id"], admin_email, pw_hash),
        )
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
            (ids["employee_user_id"], emp_email, pw_hash),
        )
        cur.execute(
            "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
            "VALUES (%s,%s,%s,'EMPLOYEE',true,now(),now())",
            (ids["other_employee_user_id"], other_email, pw_hash),
        )
        cur.execute(
            "INSERT INTO territories (id,name,created_at) VALUES (%s,%s,now())",
            (ids["territory_id"], f"{TEST_MARKER}Territory"),
        )
        cur.execute(
            "INSERT INTO employees (id,user_id,full_name,territory_id,employee_code,created_at) "
            "VALUES (%s,%s,%s,%s,%s,now())",
            (
                ids["employee_id"],
                ids["employee_user_id"],
                f"{TEST_MARKER} Primary Rep",
                ids["territory_id"],
                f"{TEST_MARKER}EMP1",
            ),
        )
        cur.execute(
            "INSERT INTO employees (id,user_id,full_name,territory_id,employee_code,created_at) "
            "VALUES (%s,%s,%s,%s,%s,now())",
            (
                ids["other_employee_id"],
                ids["other_employee_user_id"],
                f"{TEST_MARKER} Other Rep",
                ids["territory_id"],
                f"{TEST_MARKER}EMP2",
            ),
        )
        cur.execute(
            "INSERT INTO customers "
            "(id,name,contact_number,address,location,geofence_radius_m,created_by,territory_id,created_at) "
            "VALUES (%s,%s,%s,%s, ST_GeogFromText(%s), %s, %s, %s, now())",
            (
                ids["customer_id"],
                f"{TEST_MARKER}Customer",
                "+919999900001",
                f"{TEST_MARKER} 1 Test Road",
                f"POINT({SEED_LNG} {SEED_LAT})",
                100,
                ids["admin_user_id"],
                ids["territory_id"],
            ),
        )

    ids.update(
        {
            "admin_email": admin_email,
            "employee_email": emp_email,
            "other_employee_email": other_email,
            "password": TEST_PASSWORD,
            "customer_lat": SEED_LAT,
            "customer_lng": SEED_LNG,
            "geofence_radius_m": 100,
        }
    )

    yield ids

    # ---- teardown: remove only what this suite created ----
    _purge_test_artifacts()


@pytest.fixture
def created_visits() -> Iterator[list[str]]:
    """Track visit ids created inside a test so they are always cleaned up."""
    ids: list[str] = []
    yield ids
    if not ids:
        return
    # Owner connection: audit rows are insert-only for the application role.
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM geo_verification_logs WHERE visit_id = ANY(%s::uuid[])", (ids,))
        cur.execute("DELETE FROM visit_media WHERE visit_id = ANY(%s::uuid[])", (ids,))
        cur.execute("DELETE FROM visits WHERE id = ANY(%s::uuid[])", (ids,))


@pytest.fixture
def created_customers() -> Iterator[list[str]]:
    ids: list[str] = []
    yield ids
    if not ids:
        return
    with db_cursor() as cur:
        cur.execute("DELETE FROM customers WHERE id = ANY(%s::uuid[])", (ids,))


@pytest.fixture
def created_media() -> Iterator[list[str]]:
    """Remove media rows AND any bytes they wrote to local storage."""
    ids: list[str] = []
    yield ids
    if not ids:
        return
    keys: list[str] = []
    with db_cursor() as cur:
        cur.execute("SELECT storage_key FROM visit_media WHERE id = ANY(%s::uuid[])", (ids,))
        keys = [r["storage_key"] for r in cur.fetchall()]
        cur.execute("DELETE FROM visit_media WHERE id = ANY(%s::uuid[])", (ids,))
    base = os.path.abspath(settings.media_storage_path)
    for key in keys:
        path = os.path.abspath(os.path.join(base, key))
        if not path.startswith(base):
            continue
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
        # Remove the now-empty per-visit directory so storage is left pristine.
        parent = os.path.dirname(path)
        if parent.startswith(base) and parent != base and os.path.isdir(parent):
            try:
                os.rmdir(parent)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Authentication helpers â€” real login through the real endpoint
# ---------------------------------------------------------------------------


async def login(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


async def auth_headers(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    """Log in for real and return an Authorization header. Fails loudly."""
    resp = await login(client, email, password)
    assert resp.status_code == 200, (
        f"integration login failed for {email}: {resp.status_code} {resp.text}"
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient, seeded_world) -> dict[str, str]:
    return await auth_headers(client, seeded_world["admin_email"], seeded_world["password"])


@pytest_asyncio.fixture
async def employee_headers(client: AsyncClient, seeded_world) -> dict[str, str]:
    return await auth_headers(
        client, seeded_world["employee_email"], seeded_world["password"]
    )


@pytest_asyncio.fixture
async def other_employee_headers(client: AsyncClient, seeded_world) -> dict[str, str]:
    return await auth_headers(
        client, seeded_world["other_employee_email"], seeded_world["password"]
    )


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def iso_in(hours: float = 1.0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(hours=hours)).isoformat()


async def create_visit(
    client: AsyncClient,
    admin_headers: dict[str, str],
    customer_id: str,
    employee_id: str,
    track: list[str],
    scheduled_at: str | None = None,
) -> str:
    """Create a visit via the real API and register it for cleanup."""
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": customer_id,
            "employee_id": employee_id,
            "scheduled_at": scheduled_at or iso_in(0.5),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"visit setup failed: {resp.status_code} {resp.text}"
    visit_id = resp.json()["id"]
    track.append(visit_id)
    return visit_id


# Minimal valid JPEG (magic bytes + padding) accepted by FileValidationService.
VALID_JPEG = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00" + b"\x00" * 256


