"""
Integration (real DB): forced password change, account-deletion re-auth limiter and advisory
lock, ad-hoc scope bypass, upload caps, login hardening, Employee.is_active repair.
Synthetic data only (TEST_MARKER).
"""
from __future__ import annotations

import asyncio
import uuid

import psycopg2
import pytest

from app.config import settings
from app.services.account_deletion_service import ADMIN_DELETE_ADVISORY_LOCK_KEY
from tests.integration.conftest import (
    TEST_PASSWORD,
    VALID_JPEG,
    _owner_dsn,
    auth_headers,
    create_visit,
    db_cursor,
    iso_in,
    requires_db,
)
from tests.integration.test_access_scoping_integration import (
    _cleanup_user,
    _make_customer,
    _make_user,
)

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

API = "/api/v1"
NEW_PW = "BrandNewPass#2026"


def _clear_attempts():
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM login_attempts")


@pytest.fixture(autouse=True)
def _fresh_limiter():
    _clear_attempts()
    yield
    _clear_attempts()


# ============================================================ 1. forced password change

async def _flagged_employee(flag: bool = True):
    uid, eid, email = await _make_user("EMPLOYEE", True)
    with db_cursor() as cur:
        cur.execute("UPDATE employees SET must_change_password=%s WHERE id=%s", (flag, eid))
    return uid, eid, email


async def test_flag_defaults_false_and_is_reported_but_not_enforced_by_default(client):
    assert settings.enforce_password_change is False  # regression: default OFF
    uid, _, email = await _flagged_employee(True)
    try:
        login = await client.post(f"{API}/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert login.status_code == 200 and login.json()["must_change_password"] is True
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        me = await client.get(f"{API}/auth/me", headers=h)
        assert me.status_code == 200 and me.json()["must_change_password"] is True
        # enforcement disabled -> everything else still works
        assert (await client.get(f"{API}/customers", headers=h)).status_code == 200
    finally:
        _cleanup_user(uid)


async def test_forced_password_change_enforced_and_cleared(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "enforce_password_change", True)
    uid, eid, email = await _flagged_employee(True)
    try:
        login = await client.post(f"{API}/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert login.status_code == 200 and login.json()["must_change_password"] is True
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        refresh_token = login.json()["refresh_token"]

        # Blocked everywhere ...
        for method, path in [
            ("GET", "/customers"),
            ("GET", "/visits"),
            ("GET", "/notifications/me"),
            ("DELETE", "/auth/me"),
        ]:
            r = await client.request(method, f"{API}{path}", headers=h, **({"json": {"password": TEST_PASSWORD}} if method == "DELETE" else {}))
            assert r.status_code == 403, (path, r.text)
            assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED", (path, r.text)
        # ... except identity, refresh and change-password.
        me = await client.get(f"{API}/auth/me", headers=h)
        assert me.status_code == 200 and me.json()["must_change_password"] is True
        rf = await client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
        assert rf.status_code == 200 and rf.json()["must_change_password"] is True
        h = {"Authorization": f"Bearer {rf.json()['access_token']}"}

        # Password policy on the change endpoint.
        bad = [
            ({"old_password": "wrong-old-pw", "new_password": NEW_PW}, 400, "AUTH_WRONG_OLD_PASSWORD"),
            ({"old_password": TEST_PASSWORD, "new_password": TEST_PASSWORD}, 400, "AUTH_PASSWORD_UNCHANGED"),
            ({"old_password": TEST_PASSWORD, "new_password": "short1"}, 422, "VALIDATION_ERROR"),
            ({"old_password": TEST_PASSWORD, "new_password": "p" * 73}, 422, "PASSWORD_TOO_LONG"),
        ]
        for body, status, code in bad:
            r = await client.post(f"{API}/auth/change-password", json=body, headers=h)
            assert r.status_code == status and r.json()["error"]["code"] == code, (body, r.text)
        with db_cursor() as cur:
            cur.execute("SELECT must_change_password FROM employees WHERE id=%s", (eid,))
            assert cur.fetchone()["must_change_password"] is True

        ok = await client.post(
            f"{API}/auth/change-password",
            json={"old_password": TEST_PASSWORD, "new_password": NEW_PW},
            headers=h,
        )
        assert ok.status_code == 200, ok.text
        fresh = ok.json()
        assert fresh["must_change_password"] is False and fresh["access_token"] and fresh["refresh_token"]
        # the fresh pair keeps the user signed in
        assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": fresh["refresh_token"]})).status_code == 200
        with db_cursor() as cur:
            cur.execute("SELECT must_change_password FROM employees WHERE id=%s", (eid,))
            assert cur.fetchone()["must_change_password"] is False
            cur.execute("SELECT count(*) AS n FROM refresh_tokens WHERE user_id=%s AND revoked=false", (uid,))
            assert cur.fetchone()["n"] == 1  # every OLD session revoked; only the fresh pair is live
        assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})).status_code == 401

        relogin = await client.post(f"{API}/auth/login", json={"email": email, "password": NEW_PW})
        assert relogin.status_code == 200 and relogin.json()["must_change_password"] is False
        h2 = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
        assert (await client.get(f"{API}/customers", headers=h2)).status_code == 200
        # An admin (no employee row) is never affected.
        assert (await client.get(f"{API}/customers", headers=admin_headers)).status_code == 200
    finally:
        _cleanup_user(uid)


async def test_legacy_patch_users_me_password_path_also_clears_the_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "enforce_password_change", True)
    uid, eid, email = await _flagged_employee(True)
    try:
        h = await auth_headers(client, email, TEST_PASSWORD)
        r = await client.patch(
            f"{API}/users/me/password", json={"old_password": TEST_PASSWORD, "new_password": NEW_PW}, headers=h
        )
        assert r.status_code == 200 and r.json()["must_change_password"] is False, r.text
        with db_cursor() as cur:
            cur.execute("SELECT must_change_password FROM employees WHERE id=%s", (eid,))
            assert cur.fetchone()["must_change_password"] is False
    finally:
        _cleanup_user(uid)


async def test_password_reset_via_otp_also_clears_flag_and_rejects_long_password(client):
    from app.services import auth_service
    from app.database import AsyncSessionLocal

    uid, eid, email = await _flagged_employee(True)
    try:
        async with AsyncSessionLocal() as s:
            from datetime import datetime, timedelta, timezone

            from app.models.password_reset import PasswordResetToken

            s.add(
                PasswordResetToken(
                    user_id=uuid.UUID(uid) if isinstance(uid, str) else uid,
                    token_hash=auth_service.hash_otp("123456", uuid.UUID(uid) if isinstance(uid, str) else uid),
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=10),
                )
            )
            await s.commit()
        long_ = await client.post(
            f"{API}/auth/reset-password", json={"identifier": email, "otp": "123456", "new_password": "q" * 80}
        )
        assert long_.status_code == 422 and long_.json()["error"]["code"] == "PASSWORD_TOO_LONG"
        ok = await client.post(
            f"{API}/auth/reset-password", json={"identifier": email, "otp": "123456", "new_password": NEW_PW}
        )
        assert ok.status_code == 200, ok.text
        with db_cursor() as cur:
            cur.execute("SELECT must_change_password FROM employees WHERE id=%s", (eid,))
            assert cur.fetchone()["must_change_password"] is False
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM password_reset_tokens WHERE user_id=%s", (uid,))
        _cleanup_user(uid)


# ============================================================ 2. account deletion re-auth

async def test_delete_account_wrong_passwords_are_rate_limited(client):
    uid, _, email = await _make_user("EMPLOYEE", False)
    try:
        h = await auth_headers(client, email, TEST_PASSWORD)
        for _ in range(5):
            r = await client.request("DELETE", f"{API}/auth/me", json={"password": "nope-nope"}, headers=h)
            assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_PASSWORD"
        locked = await client.request("DELETE", f"{API}/auth/me", json={"password": TEST_PASSWORD}, headers=h)
        assert locked.status_code == 429 and locked.json()["error"]["code"] == "AUTH_RATE_LIMITED"
        with db_cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE id=%s", (uid,))
            assert cur.fetchone()["is_active"] is True
        # missing / empty password -> validation error (password is required for ALL roles)
        no_body = await client.request("DELETE", f"{API}/auth/me", headers=h)
        assert no_body.status_code == 422
        assert (await client.request("DELETE", f"{API}/auth/me", json={"reason": "x"}, headers=h)).status_code == 422
    finally:
        _cleanup_user(uid)


async def test_admin_self_deletion_waits_for_the_advisory_lock(client, seeded_world):
    """A holder of the constant advisory lock blocks a deleting admin until it is released."""
    with db_cursor(privileged=True) as cur:
        cur.execute("SELECT id FROM users WHERE role='ADMIN' AND is_active=true")
        parked = [r["id"] for r in cur.fetchall()]
        if parked:
            cur.execute("UPDATE users SET is_active=false WHERE id = ANY(%s::uuid[])", (parked,))
    uid1, _, email1 = await _make_user("ADMIN", False)
    uid2, _, _ = await _make_user("ADMIN", False)
    holder = psycopg2.connect(_owner_dsn())
    try:
        h1 = await auth_headers(client, email1, TEST_PASSWORD)
        holder.autocommit = True
        cur = holder.cursor()
        cur.execute("SELECT pg_advisory_lock(%s)", (ADMIN_DELETE_ADVISORY_LOCK_KEY,))
        task = asyncio.create_task(
            client.request("DELETE", f"{API}/auth/me", json={"password": TEST_PASSWORD}, headers=h1)
        )
        await asyncio.sleep(1.5)
        assert not task.done(), "deletion must block on the admin-deletion advisory lock"
        cur.execute("SELECT pg_advisory_unlock(%s)", (ADMIN_DELETE_ADVISORY_LOCK_KEY,))
        resp = await asyncio.wait_for(task, timeout=15)
        assert resp.status_code == 200 and resp.json()["status"] == "DELETED"
    finally:
        holder.close()
        with db_cursor(privileged=True) as cur:
            if parked:
                cur.execute("UPDATE users SET is_active=true WHERE id = ANY(%s::uuid[])", (parked,))
        for u in (uid1, uid2):
            _cleanup_user(u)


# ============================================================ 5. ad-hoc scope bypass

async def test_adhoc_visit_does_not_leave_lasting_access_to_a_foreign_outlet(
    client, admin_headers, employee_headers, created_customers, created_visits
):
    foreign = await _make_customer(client, admin_headers, created_customers, "AdhocExploit")
    fid = foreign["id"]
    # Before any visit: invisible.
    assert (await client.get(f"{API}/customers/{fid}", headers=employee_headers)).status_code == 404

    # Employee mints an ad-hoc visit to an outlet found via directory search.
    resp = await client.post(
        f"{API}/visits/ad-hoc",
        json={"customer_id": fid, "adhoc_reason": "Walk-in", "adhoc_notes": "n"},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    visit_id = resp.json()["id"]
    created_visits.append(visit_id)

    # Same day while PENDING: scope is granted so the visit/collection can happen.
    for suffix in ("", "/account", "/invoices"):
        r = await client.get(f"{API}/customers/{fid}{suffix}", headers=employee_headers)
        assert r.status_code == 200, (suffix, r.text)

    # Visit completed -> no lasting exposure (same day or next day).
    with db_cursor(privileged=True) as cur:
        cur.execute("UPDATE visits SET status='COMPLETED' WHERE id=%s", (visit_id,))
    for suffix in ("", "/account", "/invoices"):
        r = await client.get(f"{API}/customers/{fid}{suffix}", headers=employee_headers)
        assert r.status_code == 404, (suffix, r.text)

    # A stale PENDING ad-hoc visit created on a previous day does not count either.
    with db_cursor(privileged=True) as cur:
        cur.execute(
            "UPDATE visits SET status='PENDING', created_at = now() - interval '2 days' WHERE id=%s", (visit_id,)
        )
    assert (await client.get(f"{API}/customers/{fid}", headers=employee_headers)).status_code == 404
    # ... and the admin 'outside assignment' flag stays consistent with that.
    d = (await client.get(f"{API}/visits/{visit_id}", headers=admin_headers)).json()
    assert d["outside_assignment"] is True


async def test_planned_visit_still_grants_scope_after_completion(
    client, admin_headers, employee_headers, seeded_world, created_customers, created_visits
):
    cust = await _make_customer(client, admin_headers, created_customers, "PlannedScope")
    visit_id = await create_visit(
        client, admin_headers, cust["id"], seeded_world["employee_id"], created_visits, iso_in(2)
    )
    with db_cursor(privileged=True) as cur:
        cur.execute("UPDATE visits SET status='COMPLETED' WHERE id=%s", (visit_id,))
    assert (await client.get(f"{API}/customers/{cust['id']}", headers=employee_headers)).status_code == 200


# ============================================================ 4. upload limits

async def test_media_upload_over_cap_is_413_file_too_large(client, admin_headers, employee_headers, seeded_world, created_visits):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits
    )
    big = VALID_JPEG + b"\x00" * (10 * 1024 * 1024 + 10)
    r = await client.post(
        f"{API}/visits/{visit_id}/media",
        files={"file": ("big.jpg", big, "image/jpeg")},
        headers=employee_headers,
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE", r.text


async def test_global_body_cap_rejects_before_parsing(client, employee_headers, monkeypatch):
    monkeypatch.setattr(settings, "max_request_body_bytes", 512 * 1024)
    r = await client.post(
        f"{API}/visits/{uuid.uuid4()}/media",
        files={"file": ("big.jpg", VALID_JPEG + b"\x00" * (600 * 1024), "image/jpeg")},
        headers=employee_headers,
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "REQUEST_TOO_LARGE", r.text


async def test_signature_base64_payload_is_length_capped(client, employee_headers):
    r = await client.post(
        f"{API}/visits/{uuid.uuid4()}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": "A" * 1_600_000},
        headers=employee_headers,
    )
    assert r.status_code == 422


# ============================================================ 7. auth polish

async def test_login_with_oversized_identifier_is_422_not_500(client):
    r = await client.post(f"{API}/auth/login", json={"identifier": "a" * 300 + "@x.co", "password": "whatever1"})
    assert r.status_code == 422


async def test_login_with_over_72_byte_password_is_clean_401(client):
    uid, _, email = await _make_user("EMPLOYEE", False)
    try:
        r = await client.post(f"{API}/auth/login", json={"email": email, "password": "z" * 100})
        assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    finally:
        _cleanup_user(uid)


async def test_unknown_identifier_login_runs_a_dummy_bcrypt_verify(client, monkeypatch):
    from app.core import security
    from app.services import auth_service

    calls = []
    monkeypatch.setattr(auth_service, "dummy_verify_password", lambda pw: calls.append(pw))
    r = await client.post(f"{API}/auth/login", json={"email": f"nobody-{uuid.uuid4().hex}@fieldtrack.test", "password": "Password123!"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert calls == ["Password123!"]
    # and the helper itself never raises, even for >72 bytes
    security.dummy_verify_password("x" * 200)


async def test_create_user_with_over_72_byte_password_is_422_password_too_long(client, admin_headers):
    r = await client.post(
        f"{API}/users",
        json={"email": f"__itest__long{uuid.uuid4().hex[:6]}@fieldtrack.test", "password": "L" * 90, "role": "EMPLOYEE"},
        headers=admin_headers,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "PASSWORD_TOO_LONG", r.text


async def test_validation_error_body_never_echoes_the_password(client):
    secret = "Tr0ub4dor&3-visible?" + "q" * 140
    r = await client.post(f"{API}/auth/login", json={"identifier": "a@b.co", "password": secret})
    assert r.status_code == 422 and secret not in r.text


# ============================================================ 10. Employee.is_active repair

async def test_field_exception_admin_fallback_picks_an_active_employee(
    client, admin_headers, created_customers, seeded_world
):
    """Was an AttributeError (Employee.is_active does not exist) -> 500 for admins filing without a visit."""
    cust = await _make_customer(client, admin_headers, created_customers, "FieldExc")
    r = await client.post(
        f"{API}/field-exceptions",
        json={"customer_id": cust["id"], "exception_type": "OTHER", "description": "admin filed on behalf"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM field_exceptions WHERE id=%s", (r.json()["id"],))
