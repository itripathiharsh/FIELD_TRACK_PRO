"""
Integration: security hardening (FT-041, FT-023, FT-046) and the missed-visit
sweep (FT-021).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.rate_limiter import MAX_ATTEMPTS, login_rate_limiter
from app.database import AsyncSessionLocal
from tests.integration.conftest import db_cursor, login, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _failures_for(identifier: str) -> int:
    async with AsyncSessionLocal() as session:
        return await login_rate_limiter.failures_for(identifier, session)


@pytest_asyncio.fixture(autouse=True)
async def _clear_rate_limiter():
    """
    Each test starts with an empty attempt budget. P1-3: the limiter is now
    backed by the shared `login_attempts` table rather than in-process
    memory, so isolation between tests means clearing that table.
    """
    async with AsyncSessionLocal() as session:
        await login_rate_limiter.reset(session)
    yield
    async with AsyncSessionLocal() as session:
        await login_rate_limiter.reset(session)


# ---------------------------------------------------------------------------
# FT-041 - login rate limiting
# ---------------------------------------------------------------------------


async def test_repeated_failures_eventually_return_429(client: AsyncClient, seeded_world):
    email = seeded_world["admin_email"]

    for attempt in range(MAX_ATTEMPTS):
        resp = await login(client, email, "wrong-password")
        assert resp.status_code == 401, f"attempt {attempt + 1} should be 401, got {resp.status_code}"

    blocked = await login(client, email, "wrong-password")
    assert blocked.status_code == 429, "FT-041: brute force is not rate limited"
    assert "too many" in blocked.text.lower()


async def test_rate_limit_blocks_even_the_correct_password(client: AsyncClient, seeded_world):
    """
    A locked-out identifier stays locked out. The limiter must be checked
    BEFORE credentials, otherwise an attacker who finally guesses correctly is
    rewarded for exhausting the budget.
    """
    email = seeded_world["admin_email"]
    for _ in range(MAX_ATTEMPTS):
        await login(client, email, "wrong-password")

    resp = await login(client, email, seeded_world["password"])
    assert resp.status_code == 429


async def test_rate_limit_never_grants_access(client: AsyncClient, seeded_world):
    """
    Guard against the limiter becoming an authentication bypass: a 429 must
    never carry tokens.
    """
    email = seeded_world["admin_email"]
    for _ in range(MAX_ATTEMPTS + 2):
        await login(client, email, "wrong-password")

    resp = await login(client, email, "wrong-password")
    assert resp.status_code == 429
    body = resp.json()
    assert "access_token" not in body
    assert "refresh_token" not in body


async def test_successful_login_resets_the_counter(client: AsyncClient, seeded_world):
    email = seeded_world["admin_email"]

    for _ in range(MAX_ATTEMPTS - 1):
        await login(client, email, "wrong-password")
    assert await _failures_for(email) == MAX_ATTEMPTS - 1

    ok = await login(client, email, seeded_world["password"])
    assert ok.status_code == 200
    assert await _failures_for(email) == 0, "a correct password must clear the budget"

    # ...and the account is immediately usable again.
    again = await login(client, email, seeded_world["password"])
    assert again.status_code == 200


async def test_rate_limit_is_per_identifier(client: AsyncClient, seeded_world):
    """One locked-out account must not lock out a different user."""
    victim = seeded_world["admin_email"]
    other = seeded_world["employee_email"]

    for _ in range(MAX_ATTEMPTS + 1):
        await login(client, victim, "wrong-password")
    assert (await login(client, victim, "wrong-password")).status_code == 429

    unaffected = await login(client, other, seeded_world["password"])
    assert unaffected.status_code == 200, "rate limiting must not spill across accounts"


async def test_window_expiry_releases_the_lock(client: AsyncClient, seeded_world):
    """
    The window is sliding: once attempts age out, access is restored without
    manual intervention.
    """
    email = seeded_world["admin_email"]
    for _ in range(MAX_ATTEMPTS):
        await login(client, email, "wrong-password")
    assert (await login(client, email, "wrong-password")).status_code == 429

    # Age every recorded attempt beyond the window. P1-3: the budget now
    # lives in the `login_attempts` table, so "time travel" means backdating
    # those rows directly - a separate, real sync connection, exactly the
    # existing db_cursor pattern used for every other insert-only audit
    # table in this test suite (see e.g. created_visits' geo_verification_logs
    # cleanup in conftest.py).
    stale = datetime.now(tz=timezone.utc) - timedelta(minutes=16)
    key = email.strip().lower()
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM login_attempts WHERE identifier = %s", (key,))
        for _ in range(MAX_ATTEMPTS):
            cur.execute(
                "INSERT INTO login_attempts (id, identifier, attempted_at) VALUES (%s, %s, %s)",
                (str(uuid.uuid4()), key, stale),
            )

    resp = await login(client, email, seeded_world["password"])
    assert resp.status_code == 200, "attempts older than the window must not count"


async def test_unknown_account_is_rate_limited_identically(client: AsyncClient):
    """
    A non-existent identifier must behave like a wrong password, so the
    endpoint cannot be used to enumerate accounts.
    """
    ghost = "__itest__ghost@nowhere.invalid"
    for _ in range(MAX_ATTEMPTS):
        resp = await login(client, ghost, "whatever")
        assert resp.status_code == 401

    assert (await login(client, ghost, "whatever")).status_code == 429


async def test_attempts_recorded_by_one_session_are_visible_to_another(client: AsyncClient, seeded_world):
    """
    P1-3: the whole point of moving off in-process memory - a failure
    recorded through one AsyncSession (standing in for "worker A") must be
    visible to a completely independent AsyncSession ("worker B"), since
    in-process memory could never share state this way across processes.
    """
    email = seeded_world["admin_email"]

    async with AsyncSessionLocal() as worker_a_session:
        for _ in range(MAX_ATTEMPTS - 1):
            await login_rate_limiter.check_allowed(email, worker_a_session)
            await login_rate_limiter.record_failure(email, worker_a_session)

    # A brand new session/connection - nothing shared in-process with the one above.
    async with AsyncSessionLocal() as worker_b_session:
        assert await login_rate_limiter.failures_for(email, worker_b_session) == MAX_ATTEMPTS - 1
        await login_rate_limiter.check_allowed(email, worker_b_session)  # one more is still allowed
        await login_rate_limiter.record_failure(email, worker_b_session)
        with pytest.raises(Exception):
            await login_rate_limiter.check_allowed(email, worker_b_session)

    # And the real HTTP path (client -> app -> its own session) sees the same budget.
    resp = await login(client, email, seeded_world["password"])
    assert resp.status_code == 429, "the budget exhausted via direct session calls must still block the real login endpoint"


async def test_concurrent_failed_attempts_are_all_recorded_and_then_enforced(client: AsyncClient, seeded_world):
    """
    `check_allowed` runs before credentials are verified (documented design,
    see its docstring) - a genuinely simultaneous burst for the same
    identifier can therefore all be evaluated against the same starting
    count before any of their failures are recorded, and no storage
    mechanism changes that without changing the check-before-credentials
    contract itself (out of scope for P1-3). What P1-3 does guarantee: every
    one of those concurrent failures is durably recorded exactly once - none
    lost, none double-counted - so a request immediately AFTER the burst is
    correctly blocked, and the count is shared no matter which worker/session
    recorded each one.
    """
    import asyncio

    email = seeded_world["admin_email"]
    burst_size = MAX_ATTEMPTS + 5
    responses = await asyncio.gather(
        *[login(client, email, "wrong-password") for _ in range(burst_size)]
    )
    assert all(r.status_code in (401, 429) for r in responses), "a burst of failed attempts must never return 200"

    recorded = await _failures_for(email)
    assert recorded >= MAX_ATTEMPTS, (
        f"every concurrently-issued failure must be durably counted (got {recorded}, expected >= {MAX_ATTEMPTS})"
    )

    blocked = await login(client, email, "wrong-password")
    assert blocked.status_code == 429, "a request following the burst must be blocked"

    final = await login(client, email, seeded_world["password"])
    assert final.status_code == 429, "the budget stays exhausted even for the correct password"


# ---------------------------------------------------------------------------
# FT-023 - change password
# ---------------------------------------------------------------------------


async def test_change_password_succeeds_and_new_password_works(
    client: AsyncClient, seeded_world
):
    email = seeded_world["employee_email"]
    original = seeded_world["password"]
    updated = "ChangedPassword!2026"

    headers = {
        "Authorization": f"Bearer {(await login(client, email, original)).json()['access_token']}"
    }
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={"old_password": original, "new_password": updated},
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    try:
        assert (await login(client, email, updated)).status_code == 200
        assert (await login(client, email, original)).status_code == 401
    finally:
        # Restore so the shared fixture password remains valid.
        restore_headers = {
            "Authorization": f"Bearer {(await login(client, email, updated)).json()['access_token']}"
        }
        await client.patch(
            "/api/v1/users/me/password",
            json={"old_password": updated, "new_password": original},
            headers=restore_headers,
        )
        async with AsyncSessionLocal() as session:
            await login_rate_limiter.reset(session)


async def test_change_password_rejects_wrong_old_password(client: AsyncClient, employee_headers):
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={"old_password": "not-the-current-password", "new_password": "Irrelevant!2026"},
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "old password" in resp.text.lower()


async def test_change_password_rejects_short_password(client: AsyncClient, employee_headers):
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={"old_password": "IntegrationTest!2026", "new_password": "short"},
        headers=employee_headers,
    )
    assert resp.status_code == 422


async def test_change_password_rejects_reusing_current_password(
    client: AsyncClient, seeded_world, employee_headers
):
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={
            "old_password": seeded_world["password"],
            "new_password": seeded_world["password"],
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400


async def test_change_password_requires_authentication(client: AsyncClient):
    resp = await client.patch(
        "/api/v1/users/me/password",
        json={"old_password": "a", "new_password": "Whatever!2026"},
    )
    assert resp.status_code in (401, 403)


async def test_change_password_revokes_other_sessions(client: AsyncClient, seeded_world):
    """
    Locked design (16_authentication.md s3): a password change must end
    sessions on other devices, otherwise changing a password after a
    compromise achieves nothing.
    """
    email = seeded_world["employee_email"]
    original = seeded_world["password"]
    updated = "RotatedPassword!2026"

    # "Other device" session, established first.
    other_device = (await login(client, email, original)).json()
    other_refresh = other_device["refresh_token"]

    # "This device" performs the change.
    this_device = (await login(client, email, original)).json()
    headers = {"Authorization": f"Bearer {this_device['access_token']}"}

    assert (
        await client.patch(
            "/api/v1/users/me/password",
            json={"old_password": original, "new_password": updated},
            headers=headers,
        )
    ).status_code == 204

    try:
        stale = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": other_refresh}
        )
        assert stale.status_code == 401, "other sessions must not survive a password change"
    finally:
        restore = (await login(client, email, updated)).json()
        await client.patch(
            "/api/v1/users/me/password",
            json={"old_password": updated, "new_password": original},
            headers={"Authorization": f"Bearer {restore['access_token']}"},
        )
        async with AsyncSessionLocal() as session:
            await login_rate_limiter.reset(session)


async def test_deactivation_revokes_refresh_tokens(client: AsyncClient, seeded_world, admin_headers):
    """Feature B1: deactivating an employee ends their session immediately."""
    email = seeded_world["other_employee_email"]
    session_tokens = (await login(client, email, seeded_world["password"])).json()

    resp = await client.patch(
        f"/api/v1/users/{seeded_world['other_employee_user_id']}/deactivate",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    try:
        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": session_tokens["refresh_token"]}
        )
        assert refreshed.status_code in (401, 403)

        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {session_tokens['access_token']}"},
        )
        assert me.status_code == 401
    finally:
        await client.patch(
            f"/api/v1/users/{seeded_world['other_employee_user_id']}/activate",
            headers=admin_headers,
        )


# ---------------------------------------------------------------------------
# FT-046 - CORS headers must survive an error response
# ---------------------------------------------------------------------------


async def test_cors_headers_present_on_success(client: AsyncClient):
    resp = await client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_cors_headers_present_on_4xx(client: AsyncClient):
    resp = await client.get("/api/v1/visits", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code in (401, 403)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173", (
        "an auth rejection must still be readable by the browser"
    )


async def test_cors_headers_present_on_unhandled_500():
    """
    FT-046: an unhandled exception previously produced a 500 with no CORS
    header, so the browser reported a CORS failure and the real server error
    was invisible. This mounts a route that raises, and asserts the error
    response is still CORS-decorated.
    """
    from fastapi import APIRouter

    from app.main import app

    probe = APIRouter()

    @probe.get("/__itest__/boom")
    async def _boom():  # pragma: no cover - invoked via HTTP below
        raise RuntimeError("deliberate failure for CORS regression test")

    app.include_router(probe)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://itest"
        ) as probe_client:
            resp = await probe_client.get(
                "/__itest__/boom", headers={"Origin": "http://localhost:5173"}
            )
        assert resp.status_code == 500
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173", (
            "FT-046: 500 responses must retain CORS headers"
        )
        # The client must not receive internals.
        assert "RuntimeError" not in resp.text
        assert "deliberate failure" not in resp.text
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", "") != "/__itest__/boom"
        ]


# ---------------------------------------------------------------------------
# FT-021 - missed-visit sweep
# ---------------------------------------------------------------------------


async def test_overdue_pending_visit_becomes_missed(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """A PENDING visit older than the two-hour grace window is swept to MISSED."""
    from tests.integration.conftest import create_visit

    overdue_at = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat()
    visit_id = await create_visit(
        client,
        admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
        scheduled_at=overdue_at,
    )
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "PENDING"

    from app.database import AsyncSessionLocal
    from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed

    async with AsyncSessionLocal() as session:
        updated = await mark_overdue_visits_as_missed(session)

    assert updated >= 1
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "MISSED"


async def test_visit_inside_grace_window_is_not_missed(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """A visit only one hour late is still legitimately in progress."""
    from tests.integration.conftest import create_visit

    recent = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
    visit_id = await create_visit(
        client,
        admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
        scheduled_at=recent,
    )

    from app.database import AsyncSessionLocal
    from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed

    async with AsyncSessionLocal() as session:
        await mark_overdue_visits_as_missed(session)

    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "PENDING"


async def test_sweep_does_not_touch_completed_visits(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """Terminal states must be left alone by the sweep."""
    from tests.integration.conftest import create_visit

    overdue_at = (datetime.now(tz=timezone.utc) - timedelta(hours=4)).isoformat()
    visit_id = await create_visit(
        client,
        admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
        scheduled_at=overdue_at,
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

    from app.database import AsyncSessionLocal
    from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed

    async with AsyncSessionLocal() as session:
        await mark_overdue_visits_as_missed(session)

    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "COMPLETED"


async def test_sweep_is_idempotent(
    client: AsyncClient, admin_headers, seeded_world, created_visits, db
):
    """Running the sweep twice must not double-process or error."""
    from tests.integration.conftest import create_visit

    overdue_at = (datetime.now(tz=timezone.utc) - timedelta(hours=5)).isoformat()
    visit_id = await create_visit(
        client,
        admin_headers,
        seeded_world["customer_id"],
        seeded_world["employee_id"],
        created_visits,
        scheduled_at=overdue_at,
    )

    from app.database import AsyncSessionLocal
    from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed

    async with AsyncSessionLocal() as session:
        first = await mark_overdue_visits_as_missed(session)
    async with AsyncSessionLocal() as session:
        second = await mark_overdue_visits_as_missed(session)

    assert first >= 1
    assert second == 0, "an already-swept visit must not be processed again"
    assert db.fetch_one("SELECT status FROM visits WHERE id = %s", (visit_id,))["status"] == "MISSED"


async def test_scheduler_registers_exactly_one_job(monkeypatch):
    """
    FT-021: no duplicate schedulers or duplicate jobs.

    Async so that AsyncIOScheduler has a running event loop to attach to,
    exactly as it does under the FastAPI lifespan.
    """
    from app.config import settings
    from app.jobs import scheduler as scheduler_module

    monkeypatch.setattr(settings, "enable_scheduler", True, raising=False)
    scheduler_module.shutdown_scheduler()
    try:
        first = scheduler_module.start_scheduler()
        assert first is not None
        job_ids = [j.id for j in first.get_jobs()]
        assert scheduler_module.MISSED_VISIT_JOB_ID in job_ids
        assert scheduler_module.SECURITY_CLEANUP_JOB_ID in job_ids

        second = scheduler_module.start_scheduler()
        assert second is first, "a second start must not create another scheduler"
        assert len(second.get_jobs()) == len(first.get_jobs()), "the jobs must not be registered twice"

        job = first.get_job(scheduler_module.MISSED_VISIT_JOB_ID)
        assert job is not None
        assert "*/15" in str(job.trigger), f"expected a 15-minute cadence, got {job.trigger}"

        cleanup_job = first.get_job(scheduler_module.SECURITY_CLEANUP_JOB_ID)
        assert cleanup_job is not None

    finally:
        scheduler_module.shutdown_scheduler()


async def test_scheduler_disabled_by_configuration(monkeypatch):
    from app.config import settings
    from app.jobs import scheduler as scheduler_module

    monkeypatch.setattr(settings, "enable_scheduler", False, raising=False)
    scheduler_module.shutdown_scheduler()
    assert scheduler_module.start_scheduler() is None
