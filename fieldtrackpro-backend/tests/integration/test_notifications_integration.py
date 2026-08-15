"""
Integration: all notification endpoints.

Covers:
  GET  /api/v1/notifications/me
  PATCH /api/v1/notifications/{notification_id}/read
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# -- Seed notifications directly in the DB for deterministic testing ---------

def _seed_notification(user_id: str, message: str = "Test notification") -> str:
    """Insert a notification directly and return its ID."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    notif_id = str(uuid.uuid4())
    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO notifications (id, user_id, type, message, is_read, sent_at) "
            "VALUES (%s, %s, 'NEW_VISIT', %s, false, now())",
            (notif_id, user_id, message),
        )
    conn.close()
    return notif_id


def _cleanup_notifications():
    """Remove all test notifications."""
    import psycopg2
    from tests.integration.conftest import _sync_dsn
    conn = psycopg2.connect(_sync_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM notifications WHERE message LIKE '__itest__%'")
    conn.close()


# -- GET /notifications/me --------------------------------------------------

async def test_list_notifications_requires_auth(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/notifications/me")
    assert resp.status_code == 401


async def test_list_notifications_returns_own(client: AsyncClient, admin_headers, seeded_world):
    """User gets only their own notifications."""
    # Seed a notification for the admin
    notif_id = _seed_notification(seeded_world["admin_user_id"], "__itest__Admin notification")

    try:
        resp = await client.get("/api/v1/notifications/me", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        # The seeded notification should appear
        assert any(n["id"] == notif_id for n in data), "seeded notification should be in the list"
    finally:
        _cleanup_notifications()


async def test_list_notifications_user_scoping(client: AsyncClient, admin_headers, employee_headers, seeded_world):
    """One user cannot see another user's notifications."""
    # Seed a notification for the employee
    _seed_notification(seeded_world["employee_user_id"], "__itest__Employee private notification")

    try:
        # Admin should not see employee's notification
        resp = await client.get("/api/v1/notifications/me", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        messages = [n["message"] for n in data]
        assert "__itest__Employee private notification" not in messages
    finally:
        _cleanup_notifications()


async def test_list_notifications_empty(client: AsyncClient, admin_headers):
    """When user has no notifications, an empty list is returned."""
    resp = await client.get("/api/v1/notifications/me", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


# -- PATCH /notifications/{id}/read ----------------------------------------

async def test_mark_read_requires_auth(client: AsyncClient, seeded_world):
    """Unauthenticated requests are rejected."""
    notif_id = _seed_notification(seeded_world["admin_user_id"], "__itest__Unauth read test")
    try:
        resp = await client.patch(f"/api/v1/notifications/{notif_id}/read")
        assert resp.status_code == 401
    finally:
        _cleanup_notifications()


async def test_mark_read_persists(client: AsyncClient, admin_headers, seeded_world, db):
    """Marking a notification as read persists the state."""
    notif_id = _seed_notification(seeded_world["admin_user_id"], "__itest__Read state test")

    try:
        resp = await client.patch(
            f"/api/v1/notifications/{notif_id}/read",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text

        # Verify persistence
        row = db.fetch_one("SELECT is_read FROM notifications WHERE id = %s", (notif_id,))
        assert row is not None
        assert row["is_read"] is True
    finally:
        _cleanup_notifications()


async def test_mark_read_user_scoping(client: AsyncClient, employee_headers, seeded_world, db):
    """User cannot mark another user's notification as read."""
    # Seed a notification for the admin
    notif_id = _seed_notification(seeded_world["admin_user_id"], "__itest__Scoped read test")

    try:
        # Employee tries to mark admin's notification as read
        resp = await client.patch(
            f"/api/v1/notifications/{notif_id}/read",
            headers=employee_headers,
        )
        # Should succeed (200) but not actually mark it as read (silent no-op)
        assert resp.status_code == 200, resp.text

        # Verify it was NOT marked as read
        row = db.fetch_one("SELECT is_read FROM notifications WHERE id = %s", (notif_id,))
        assert row is not None
        assert row["is_read"] is False, "notification should not be marked as read by a different user"
    finally:
        _cleanup_notifications()


async def test_mark_read_nonexistent_returns_200(client: AsyncClient, admin_headers):
    """Marking a non-existent notification as read returns 200 (idempotent no-op)."""
    resp = await client.patch(
        f"/api/v1/notifications/{uuid.uuid4()}/read",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
