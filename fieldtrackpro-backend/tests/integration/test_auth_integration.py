"""
Integration: authentication success paths (scenarios 1-5).

The existing unit suite only proves that BAD requests are rejected. Nothing
proved that a GOOD login actually works. These tests close that gap.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import login, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# --- Scenario 1 -------------------------------------------------------------

async def test_valid_admin_credentials_login_succeeds(client: AsyncClient, seeded_world):
    resp = await login(client, seeded_world["admin_email"], seeded_world["password"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_admin_me_returns_admin_role(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "ADMIN"
    assert resp.json()["is_active"] is True


# --- Scenario 2 -------------------------------------------------------------

async def test_valid_employee_credentials_login_succeeds(client: AsyncClient, seeded_world):
    resp = await login(client, seeded_world["employee_email"], seeded_world["password"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_employee_me_returns_employee_role(client: AsyncClient, employee_headers):
    resp = await client.get("/api/v1/auth/me", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "EMPLOYEE"


# --- Scenario 3 -------------------------------------------------------------

async def test_invalid_password_returns_401(client: AsyncClient, seeded_world):
    resp = await login(client, seeded_world["admin_email"], "definitely-not-the-password")
    assert resp.status_code == 401


async def test_unknown_email_returns_401(client: AsyncClient):
    resp = await login(client, "__itest__nobody@nowhere.invalid", "irrelevant")
    assert resp.status_code == 401


async def test_failed_login_issues_no_tokens(client: AsyncClient, seeded_world):
    """A rejected login must not leak a usable credential of any kind."""
    resp = await login(client, seeded_world["admin_email"], "wrong-password")
    assert resp.status_code == 401
    body = resp.json()
    assert "access_token" not in body
    assert "refresh_token" not in body


# --- Scenario 5 -------------------------------------------------------------

async def test_invalid_token_never_yields_a_user(client: AsyncClient):
    """An unverifiable token must produce 401 - never a fabricated identity."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.INVALID.SIGNATURE"},
    )
    assert resp.status_code in (401, 403)
    assert "role" not in resp.text


async def test_token_signed_with_wrong_secret_is_rejected(client: AsyncClient, seeded_world):
    """Defence against secret-rotation regressions and forged tokens."""
    from jose import jwt

    forged = jwt.encode(
        {"sub": seeded_world["admin_user_id"], "role": "ADMIN", "exp": 9_999_999_999},
        "this-is-not-the-real-signing-secret",
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code in (401, 403)


async def test_deactivated_user_cannot_use_existing_token(
    client: AsyncClient, seeded_world, db
):
    """
    Spec 09 s2: role/active state is re-checked against the DB, so deactivating
    a user takes effect immediately rather than at token expiry.
    """
    from tests.integration.conftest import auth_headers, db_cursor

    headers = await auth_headers(
        client, seeded_world["other_employee_email"], seeded_world["password"]
    )
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    with db_cursor() as cur:
        cur.execute(
            "UPDATE users SET is_active = false WHERE id = %s",
            (seeded_world["other_employee_user_id"],),
        )
    try:
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401, "deactivated user must lose access immediately"
    finally:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE users SET is_active = true WHERE id = %s",
                (seeded_world["other_employee_user_id"],),
            )


# --- Refresh / logout lifecycle (FT-008 / FT-009) ---------------------------

async def test_refresh_token_returns_new_usable_pair(client: AsyncClient, seeded_world):
    resp = await login(client, seeded_world["employee_email"], seeded_world["password"])
    assert resp.status_code == 200
    refresh = resp.json()["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200, rotated.text
    new_access = rotated.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["role"] == "EMPLOYEE"


async def test_refresh_token_is_rotated_and_old_one_revoked(client: AsyncClient, seeded_world):
    resp = await login(client, seeded_world["employee_email"], seeded_world["password"])
    original = resp.json()["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401, "a rotated refresh token must not be reusable"


async def test_logout_revokes_refresh_token_server_side(client: AsyncClient, seeded_world):
    """FT-009: logout must invalidate the server-side session, not just local storage."""
    resp = await login(client, seeded_world["employee_email"], seeded_world["password"])
    refresh = resp.json()["refresh_token"]

    out = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204, out.text

    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401, "refresh token must be dead after logout"


# --- FT-010: login field contract ------------------------------------------

async def test_login_by_mobile_number_is_supported(client: AsyncClient, seeded_world):
    """
    FT-010: backend accepts `mobile_number`. The web client currently sends
    `mobile`, which pydantic silently drops. This test pins the backend
    contract so the frontend can be corrected against it.
    """
    from tests.integration.conftest import TEST_MARKER, db_cursor

    mobile = "+919999900077"
    with db_cursor() as cur:
        cur.execute(
            "UPDATE users SET mobile_number = %s WHERE id = %s",
            (mobile, seeded_world["employee_user_id"]),
        )
    try:
        ok = await client.post(
            "/api/v1/auth/login",
            json={"mobile_number": mobile, "password": seeded_world["password"]},
        )
        assert ok.status_code == 200, f"mobile_number login must work: {ok.text}"

        wrong_key = await client.post(
            "/api/v1/auth/login",
            json={"mobile": mobile, "password": seeded_world["password"]},
        )
        assert wrong_key.status_code == 422, (
            "FT-010: `mobile` is not part of the contract and must be rejected, "
            "not silently ignored"
        )
    finally:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE users SET mobile_number = NULL WHERE id = %s",
                (seeded_world["employee_user_id"],),
            )


# --- FT-011: /auth/me identity completeness ---------------------------------

async def test_me_exposes_identity_fields_the_ui_requires(client: AsyncClient, employee_headers):
    """
    FT-011: the web client's User type expects `full_name`. /auth/me does not
    return it, so the UI can never show a real name.
    """
    resp = await client.get("/api/v1/auth/me", headers=employee_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "full_name" in body, "FT-011: /auth/me must expose full_name for the UI"
    assert body["full_name"], "FT-011: full_name must not be empty"
