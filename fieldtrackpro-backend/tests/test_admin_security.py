"""
Admin password reset + Super Admin role management (end to end through the HTTP API).

Uses synthetic users (adm_sec_*@fieldtrack.test) and removes everything it creates. Tests that need to
reason about "the last active Super Admin" are skipped when the database already holds Super Admins that
this test module did not create (they must never be touched).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, func, select, text, update

from app.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_temporary_password,
    hash_password,
    verify_password,
)
from app.database import AsyncSessionLocal
from app.main import app
from app.models.employee import Employee
from app.models.login_attempt import LoginAttempt
from app.models.refresh_token import RefreshToken
from app.models.security_audit import SecurityAuditLog
from app.models.user import Role, User
from tests.conftest import requires_db

PW = "StartPassword123!"
NEW_PW = "BrandNewPassword456!"

pytestmark = [pytest.mark.asyncio, requires_db]


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _wipe_throttle():
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(LoginAttempt))
            await s.commit()
    except Exception:
        pass


@pytest_asyncio.fixture(autouse=True)
async def _clean_throttle_rows():
    await _wipe_throttle()
    yield
    await _wipe_throttle()


class Cast:
    """Creates synthetic accounts and removes them (and their audit/token rows) afterwards."""

    def __init__(self) -> None:
        self.user_ids: list[uuid.UUID] = []

    async def make(self, role: Role = Role.EMPLOYEE, *, employee: bool = True, active: bool = True, password: str = PW) -> dict:
        uid = uuid.uuid4()
        email = f"adm_sec_{uid.hex[:10]}@fieldtrack.test"
        eid = uuid.uuid4()
        async with AsyncSessionLocal() as s:
            s.add(User(id=uid, email=email, password_hash=hash_password(password), role=role, is_active=active))
            await s.flush()
            if employee:
                s.add(Employee(id=eid, user_id=uid, full_name=f"Adm Sec {uid.hex[:6]}", must_change_password=False))
            await s.commit()
        self.user_ids.append(uid)
        return {"id": uid, "email": email, "password": password, "employee_id": eid if employee else None}

    async def cleanup(self) -> None:
        if not self.user_ids:
            return
        try:
            async with AsyncSessionLocal() as s:
                await s.execute(delete(SecurityAuditLog).where(
                    (SecurityAuditLog.actor_user_id.in_(self.user_ids)) | (SecurityAuditLog.target_user_id.in_(self.user_ids))
                ))
                await s.commit()
        except Exception:
            # The runtime DB role may be append-only on security_audit_logs (scripts/grant_runtime_role.sql);
            # the rows then stay behind, detached from the deleted users by ON DELETE SET NULL.
            pass
        async with AsyncSessionLocal() as s:
            await s.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(self.user_ids)))
            await s.execute(delete(Employee).where(Employee.user_id.in_(self.user_ids)))
            await s.execute(delete(User).where(User.id.in_(self.user_ids)))
            await s.commit()


@pytest_asyncio.fixture
async def cast():
    c = Cast()
    yield c
    await c.cleanup()


async def _foreign_active_super_admins(own_ids: list[uuid.UUID]) -> int:
    async with AsyncSessionLocal() as s:
        stmt = select(func.count()).select_from(User).where(User.role == Role.SUPER_ADMIN, User.is_active.is_(True))
        if own_ids:
            stmt = stmt.where(User.id.not_in(own_ids))
        return (await s.execute(stmt)).scalar_one()


@pytest_asyncio.fixture
async def isolated_super_admins(cast):
    """Skip when real Super Admins exist that these tests must not reason about / touch."""
    if await _foreign_active_super_admins([]) > 0:
        pytest.skip("database already contains Super Admin accounts; last-Super-Admin tests need an empty set")
    return cast


def bearer(user: dict, role: Role, token_version: int = 0) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user['id']), role.value, token_version=token_version)}"}


async def login(http: AsyncClient, email: str, password: str):
    return await http.post("/api/v1/auth/login", json={"identifier": email, "password": password})


async def tokens(http: AsyncClient, user: dict) -> dict:
    r = await login(http, user["email"], user["password"])
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def db_user(uid: uuid.UUID) -> User:
    async with AsyncSessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        s.expunge(u)
        return u


async def audit_rows(event_type: str, *, target: uuid.UUID | None = None, actor: uuid.UUID | None = None) -> list[SecurityAuditLog]:
    async with AsyncSessionLocal() as s:
        stmt = select(SecurityAuditLog).where(SecurityAuditLog.event_type == event_type).order_by(SecurityAuditLog.created_at)
        if target:
            stmt = stmt.where(SecurityAuditLog.target_user_id == target)
        if actor:
            stmt = stmt.where(SecurityAuditLog.actor_user_id == actor)
        return list((await s.execute(stmt)).scalars().all())


async def reset(http: AsyncClient, admin_headers: dict, employee_id: uuid.UUID):
    return await http.post(f"/api/v1/employees/{employee_id}/reset-password", headers=admin_headers)


async def change_role(http: AsyncClient, headers: dict, user_id, role: str, password: str = PW, confirm: bool = False):
    return await http.patch(
        f"/api/v1/users/{user_id}/role",
        json={"role": role, "current_password": password, "confirm": confirm},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# unit-level
# ---------------------------------------------------------------------------

def test_generated_temporary_password_is_random_and_policy_compliant():
    seen = {generate_temporary_password() for _ in range(200)}
    assert len(seen) == 200  # CSPRNG: no collisions in 200 draws
    for pw in seen:
        assert len(pw) == 14 and pw.count("-") == 2
        flat = pw.replace("-", "")
        assert any(c.isupper() for c in flat) and any(c.islower() for c in flat) and any(c.isdigit() for c in flat)
        assert not set(flat) & set("0O1lIo")  # no look-alikes
        assert len(pw.encode()) <= 72


def test_access_token_carries_version_but_role_claim_is_not_authority():
    payload = decode_access_token(create_access_token("u", "ADMIN", token_version=3))
    assert payload["tv"] == 3


def test_role_enum_hierarchy_helpers():
    u = User(role=Role.SUPER_ADMIN)
    assert u.is_admin and u.is_super_admin
    a = User(role=Role.ADMIN)
    assert a.is_admin and not a.is_super_admin
    e = User(role=Role.EMPLOYEE)
    assert not e.is_admin and not e.is_super_admin


# ---------------------------------------------------------------------------
# Part A - admin password reset
# ---------------------------------------------------------------------------

async def test_admin_resets_employee_password_and_plaintext_is_never_stored(http, cast, caplog):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)

    caplog.set_level(logging.DEBUG)
    r = await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    temp = body["temporary_password"]
    assert body["expires_in_minutes"] == settings.temp_password_expiry_minutes == 30
    assert body["must_change_password"] is True
    assert body["employee_id"] == str(emp["employee_id"]) and body["user_id"] == str(emp["id"])
    assert r.headers["cache-control"] == "no-store"

    u = await db_user(emp["id"])
    assert u.password_hash != temp and temp not in u.password_hash
    assert verify_password(temp, u.password_hash)                       # stored as a real bcrypt hash
    assert u.temp_password_expires_at is not None
    assert timedelta(minutes=29) < u.temp_password_expires_at - datetime.now(tz=timezone.utc) <= timedelta(minutes=30)
    async with AsyncSessionLocal() as s:
        assert (await s.execute(select(Employee.must_change_password).where(Employee.id == emp["employee_id"]))).scalar_one() is True

    # never logged, never in the audit trail
    assert temp not in caplog.text
    rows = await audit_rows("ADMIN_PASSWORD_RESET", target=emp["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.outcome == "SUCCESS" and row.actor_user_id == admin["id"] and row.target_user_id == emp["id"]
    assert temp not in str(row.details) and "password" not in str(row.details).lower().replace("password_reset", "")
    assert row.details["sessions_revoked"] >= 0 and row.details["access_tokens_invalidated"] is True

    # no endpoint exposes the temporary password / hash again
    admin_h = bearer(admin, Role.ADMIN)
    for path in (f"/api/v1/employees/{emp['employee_id']}", "/api/v1/employees?limit=5000"):
        got = await http.get(path, headers=admin_h)
        assert got.status_code == 200
        assert temp not in got.text and "password_hash" not in got.text and "temporary_password" not in got.text


async def test_reset_kills_existing_sessions(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    old_login = await login(http, emp["email"], emp["password"])
    old_access = {"Authorization": f"Bearer {old_login.json()['access_token']}"}
    old_refresh = old_login.json()["refresh_token"]
    assert (await http.get("/api/v1/auth/me", headers=old_access)).status_code == 200

    assert (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).status_code == 200

    assert (await http.get("/api/v1/auth/me", headers=old_access)).status_code == 401        # access token dead
    r = await http.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401                                                                # refresh token dead
    assert (await login(http, emp["email"], emp["password"])).status_code == 401              # old password dead


async def test_temporary_login_is_restricted_until_password_is_changed(http, cast):
    assert settings.enforce_password_change is False  # the gate must work even with the legacy switch OFF
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    temp = (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).json()["temporary_password"]

    r = await login(http, emp["email"], temp)
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ordinary protected endpoints are refused for the restricted session
    for path in ("/api/v1/employees/me", "/api/v1/customers", "/api/v1/visits", "/api/v1/territories"):
        blocked = await http.get(path, headers=h)
        assert blocked.status_code == 403, (path, blocked.text)
        assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    # only the identity + change-password + logout operations remain available
    me = await http.get("/api/v1/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["must_change_password"] is True

    # complete the mandatory change
    ch = await http.post("/api/v1/auth/change-password", json={"old_password": temp, "new_password": NEW_PW}, headers=h)
    assert ch.status_code == 200 and ch.json()["must_change_password"] is False
    fresh = {"Authorization": f"Bearer {ch.json()['access_token']}"}
    assert (await http.get("/api/v1/employees/me", headers=fresh)).status_code == 200      # normal access restored

    u = await db_user(emp["id"])
    assert u.temp_password_expires_at is None
    # the temporary password is permanently dead; the new one works
    assert (await login(http, emp["email"], temp)).status_code == 401
    ok = await login(http, emp["email"], NEW_PW)
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    # the restricted session's own token is dead too (token version bumped by the change)
    assert (await http.get("/api/v1/auth/me", headers=h)).status_code == 401


async def test_temporary_password_cannot_be_reused_after_replacement(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    temp = (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).json()["temporary_password"]
    h = await tokens(http, {"email": emp["email"], "password": temp})
    ch = await http.post("/api/v1/auth/change-password", json={"old_password": temp, "new_password": NEW_PW}, headers=h)
    assert ch.status_code == 200
    # replaying the same change with the temp password as "old" password fails
    replay = await http.post("/api/v1/auth/change-password",
                             json={"old_password": temp, "new_password": "AnotherPassword789!"},
                             headers={"Authorization": f"Bearer {ch.json()['access_token']}"})
    assert replay.status_code == 400 and replay.json()["error"]["code"] == "AUTH_WRONG_OLD_PASSWORD"


async def test_expired_temporary_password_is_rejected_everywhere(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    temp = (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).json()["temporary_password"]
    # a restricted session opened while the credential was still valid ...
    h = await tokens(http, {"email": emp["email"], "password": temp})
    refresh = (await login(http, emp["email"], temp)).json()["refresh_token"]

    # ... then time runs out
    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.id == emp["id"]).values(
            temp_password_expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1)))
        await s.commit()

    r = await login(http, emp["email"], temp)
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_TEMP_PASSWORD_EXPIRED"
    assert (await http.get("/api/v1/auth/me", headers=h)).status_code == 401
    ch = await http.post("/api/v1/auth/change-password", json={"old_password": temp, "new_password": NEW_PW}, headers=h)
    assert ch.status_code == 401 and ch.json()["error"]["code"] == "AUTH_TEMP_PASSWORD_EXPIRED"
    rf = await http.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert rf.status_code == 401
    # a wrong password on an expired account still looks like any other bad login (no leak)
    bad = await login(http, emp["email"], "definitely-wrong")
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    # an admin can issue a fresh one
    again = await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])
    assert again.status_code == 200
    assert (await login(http, emp["email"], again.json()["temporary_password"])).status_code == 200


async def test_concurrent_password_changes_cannot_both_succeed(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    temp = (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).json()["temporary_password"]
    h = await tokens(http, {"email": emp["email"], "password": temp})

    results = await asyncio.gather(*[
        http.post("/api/v1/auth/change-password", json={"old_password": temp, "new_password": f"ConcurrentPass{i}!x"}, headers=h)
        for i in range(4)
    ])
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes            # single-use: exactly one change wins
    assert all(c in (200, 400, 401) for c in codes)
    winners = [i for i, r in enumerate(results) if r.status_code == 200]
    assert (await login(http, emp["email"], f"ConcurrentPass{winners[0]}!x")).status_code == 200
    assert (await login(http, emp["email"], temp)).status_code == 401


async def test_concurrent_resets_leave_exactly_one_valid_temporary_password(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    h = bearer(admin, Role.ADMIN)
    results = await asyncio.gather(*[reset(http, h, emp["employee_id"]) for _ in range(3)])
    assert all(r.status_code == 200 for r in results)
    temps = [r.json()["temporary_password"] for r in results]
    u = await db_user(emp["id"])
    valid = [t for t in temps if verify_password(t, u.password_hash)]
    assert len(valid) == 1                         # the last committed reset wins; the others are dead
    assert u.token_version >= 3


async def test_reset_authorization_matrix(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    adm = await cast.make(Role.ADMIN)
    adm2 = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    emp2 = await cast.make(Role.EMPLOYEE)

    # unauthenticated / employee
    assert (await http.post(f"/api/v1/employees/{emp['employee_id']}/reset-password")).status_code in (401, 403)
    assert (await reset(http, bearer(emp2, Role.EMPLOYEE), emp["employee_id"])).status_code == 403

    # Admin: employees yes; admins / super admins / self no
    assert (await reset(http, bearer(adm, Role.ADMIN), emp["employee_id"])).status_code == 200
    r = await reset(http, bearer(adm, Role.ADMIN), adm2["employee_id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "TARGET_PRIVILEGE_TOO_HIGH"
    r = await reset(http, bearer(adm, Role.ADMIN), sa["employee_id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "TARGET_PRIVILEGE_TOO_HIGH"
    r = await reset(http, bearer(adm, Role.ADMIN), adm["employee_id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_PASSWORD_RESET_FORBIDDEN"

    # Super Admin: employees and admins yes; super admins (incl. self) no
    assert (await reset(http, bearer(sa, Role.SUPER_ADMIN), adm2["employee_id"])).status_code == 200
    assert (await reset(http, bearer(sa, Role.SUPER_ADMIN), emp2["employee_id"])).status_code == 200
    assert (await reset(http, bearer(sa, Role.SUPER_ADMIN), sa["employee_id"])).status_code == 403

    # unknown employee
    assert (await reset(http, bearer(sa, Role.SUPER_ADMIN), uuid.uuid4())).status_code == 404

    # refusals are audited with the actor, the target and a reason - never a credential
    denied = await audit_rows("ADMIN_PASSWORD_RESET", target=sa["id"])
    assert any(d.outcome == "DENIED" and d.actor_user_id == adm["id"] and d.reason_code == "TARGET_PRIVILEGE_TOO_HIGH" for d in denied)


async def test_reset_of_inactive_account_is_refused(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE, active=False)
    r = await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACCOUNT_INACTIVE"
    assert (await db_user(emp["id"])).temp_password_expires_at is None


async def test_reset_requires_an_employee_profile_target(http, cast):
    admin = await cast.make(Role.ADMIN)
    assert (await reset(http, bearer(admin, Role.ADMIN), uuid.uuid4())).status_code == 404


async def test_admin_cannot_waive_the_forced_change_while_a_temporary_password_is_pending(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    assert (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).status_code == 200
    r = await http.patch(f"/api/v1/employees/{emp['employee_id']}", json={"must_change_password": False},
                         headers=bearer(admin, Role.ADMIN))
    assert r.status_code == 409 and r.json()["error"]["code"] == "TEMP_PASSWORD_PENDING"


async def test_reset_lifts_a_sign_in_lockout(http, cast):
    admin = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    for _ in range(5):
        await login(http, emp["email"], "wrong-password")
    assert (await login(http, emp["email"], emp["password"])).status_code == 429
    temp = (await reset(http, bearer(admin, Role.ADMIN), emp["employee_id"])).json()["temporary_password"]
    assert (await login(http, emp["email"], temp)).status_code == 200


async def test_normal_login_and_self_service_password_change_still_work(http, cast):
    emp = await cast.make(Role.EMPLOYEE)
    h = await tokens(http, emp)
    assert (await http.get("/api/v1/employees/me", headers=h)).status_code == 200
    r = await http.patch("/api/v1/users/me/password", json={"old_password": PW, "new_password": NEW_PW}, headers=h)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert (await login(http, emp["email"], NEW_PW)).status_code == 200
    assert (await login(http, emp["email"], PW)).status_code == 401
    # wrong old password is throttled
    h2 = await tokens(http, {"email": emp["email"], "password": NEW_PW})
    last = None
    for _ in range(11):
        last = await http.post("/api/v1/auth/change-password", json={"old_password": "nope-nope", "new_password": "WhateverNew123!"}, headers=h2)
    assert last.status_code == 429


# ---------------------------------------------------------------------------
# Part B - roles
# ---------------------------------------------------------------------------

async def test_super_admin_passes_every_admin_only_endpoint(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    h = bearer(sa, Role.SUPER_ADMIN)
    assert (await http.get("/api/v1/employees", headers=h)).status_code == 200
    assert (await http.get("/api/v1/territories", headers=h)).status_code == 200
    assert (await http.get("/api/v1/auth/me", headers=h)).json()["role"] == "SUPER_ADMIN"


async def test_token_role_claim_is_not_authority(http, cast):
    """A forged/stale role claim is irrelevant: the role comes from the database."""
    emp = await cast.make(Role.EMPLOYEE)
    forged = {"Authorization": f"Bearer {create_access_token(str(emp['id']), 'SUPER_ADMIN')}"}
    assert (await http.get("/api/v1/employees", headers=forged)).status_code == 403
    assert (await http.get("/api/v1/security-audit-logs", headers=forged)).status_code == 403


async def test_super_admin_promotes_and_demotes_with_audit_and_immediate_effect(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    sah = bearer(sa, Role.SUPER_ADMIN)
    emp_old = await tokens(http, emp)

    r = await change_role(http, sah, emp["id"], "ADMIN")
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"
    assert (await db_user(emp["id"])).role == Role.ADMIN
    # takes effect immediately: the employee's old token is dead, a fresh login is an admin
    assert (await http.get("/api/v1/auth/me", headers=emp_old)).status_code == 401
    fresh = await tokens(http, emp)
    assert (await http.get("/api/v1/employees", headers=fresh)).status_code == 200

    rows = await audit_rows("ROLE_CHANGE", target=emp["id"])
    assert len(rows) == 1
    assert (rows[0].outcome, rows[0].previous_role, rows[0].new_role) == ("SUCCESS", "EMPLOYEE", "ADMIN")
    assert rows[0].actor_user_id == sa["id"]
    assert PW not in str(rows[0].details)

    # and back down
    assert (await change_role(http, sah, emp["id"], "EMPLOYEE")).status_code == 200
    assert (await http.get("/api/v1/employees", headers=await tokens(http, emp))).status_code == 403


async def test_plain_admin_and_employee_cannot_change_roles_even_with_direct_api_calls(http, cast):
    adm = await cast.make(Role.ADMIN)
    adm2 = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)

    # Admin -> another user, themselves (self-promotion), and straight to SUPER_ADMIN
    for target, role in ((emp, "ADMIN"), (adm2, "SUPER_ADMIN"), (adm, "SUPER_ADMIN"), (adm2, "EMPLOYEE")):
        r = await change_role(http, bearer(adm, Role.ADMIN), target["id"], role, confirm=True)
        assert r.status_code == 403, (role, r.text)
        assert r.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"
    # Employee
    r = await change_role(http, bearer(emp, Role.EMPLOYEE), emp["id"], "ADMIN", confirm=True)
    assert r.status_code == 403
    # nothing changed
    assert (await db_user(adm["id"])).role == Role.ADMIN
    assert (await db_user(emp["id"])).role == Role.EMPLOYEE
    assert (await db_user(adm2["id"])).role == Role.ADMIN
    # the Admin attempts are audited as denied
    rows = await audit_rows("ROLE_CHANGE", actor=adm["id"])
    assert len(rows) == 4 and all(r.outcome == "DENIED" and r.reason_code == "SUPER_ADMIN_REQUIRED" for r in rows)
    # unauthenticated
    assert (await http.patch(f"/api/v1/users/{emp['id']}/role", json={"role": "ADMIN", "current_password": "x"})).status_code in (401, 403)


async def test_role_change_requires_reauthentication_and_is_rate_limited(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    h = bearer(sa, Role.SUPER_ADMIN)
    r = await change_role(http, h, emp["id"], "ADMIN", password="wrong-password")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_PASSWORD"
    assert (await db_user(emp["id"])).role == Role.EMPLOYEE
    for _ in range(5):
        r = await change_role(http, h, emp["id"], "ADMIN", password="wrong-password")
    assert r.status_code == 429
    # even the right password is refused while locked
    assert (await change_role(http, h, emp["id"], "ADMIN")).status_code == 429


async def test_role_transition_rules_and_privileged_confirmation(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    adm = await cast.make(Role.ADMIN)
    h = bearer(sa, Role.SUPER_ADMIN)

    r = await change_role(http, h, emp["id"], "SUPER_ADMIN", confirm=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_ROLE_TRANSITION"
    r = await change_role(http, h, adm["id"], "SUPER_ADMIN")                      # no explicit confirmation
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert (await db_user(adm["id"])).role == Role.ADMIN
    r = await change_role(http, h, emp["id"], "EMPLOYEE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ROLE_UNCHANGED"
    assert (await change_role(http, h, uuid.uuid4(), "ADMIN")).status_code == 404
    assert (await change_role(http, h, adm["id"], "MANAGER")).status_code == 422   # not a role

    assert (await change_role(http, h, adm["id"], "SUPER_ADMIN", confirm=True)).status_code == 200
    rows = await audit_rows("ROLE_CHANGE", target=adm["id"])
    assert any(r.outcome == "DENIED" and r.reason_code == "CONFIRMATION_REQUIRED" for r in rows)
    assert any(r.outcome == "SUCCESS" and r.new_role == "SUPER_ADMIN" for r in rows)


async def test_inactive_account_cannot_be_promoted(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    emp = await cast.make(Role.EMPLOYEE, active=False)
    r = await change_role(http, bearer(sa, Role.SUPER_ADMIN), emp["id"], "ADMIN")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACCOUNT_INACTIVE"


async def test_last_active_super_admin_cannot_be_demoted_or_deactivated(http, isolated_super_admins):
    cast = isolated_super_admins
    only = await cast.make(Role.SUPER_ADMIN)
    h = bearer(only, Role.SUPER_ADMIN)

    r = await change_role(http, h, only["id"], "ADMIN", confirm=True)               # self-demotion
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_SUPER_ADMIN"
    assert (await db_user(only["id"])).role == Role.SUPER_ADMIN

    r = await http.patch(f"/api/v1/users/{only['id']}/deactivate", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_SUPER_ADMIN"
    assert (await db_user(only["id"])).is_active is True

    # self-service account deletion is refused as well
    r = await http.request("DELETE", "/api/v1/auth/me", json={"password": PW}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_SUPER_ADMIN_CANNOT_DELETE"

    # with a second active Super Admin the first can step down
    other = await cast.make(Role.SUPER_ADMIN)
    assert (await change_role(http, h, only["id"], "ADMIN", confirm=True)).status_code == 200
    # ... and now `other` is the last one
    oh = bearer(other, Role.SUPER_ADMIN)
    r = await change_role(http, oh, other["id"], "ADMIN", confirm=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_SUPER_ADMIN"


async def test_concurrent_demotions_can_never_remove_every_super_admin(http, isolated_super_admins):
    cast = isolated_super_admins
    a = await cast.make(Role.SUPER_ADMIN)
    b = await cast.make(Role.SUPER_ADMIN)
    ha, hb = bearer(a, Role.SUPER_ADMIN), bearer(b, Role.SUPER_ADMIN)

    # each tries to demote the other (and themselves) at the same moment, repeatedly
    results = await asyncio.gather(
        change_role(http, ha, b["id"], "ADMIN", confirm=True),
        change_role(http, hb, a["id"], "ADMIN", confirm=True),
        change_role(http, ha, a["id"], "ADMIN", confirm=True),
        change_role(http, hb, b["id"], "ADMIN", confirm=True),
    )
    async with AsyncSessionLocal() as s:
        remaining = (await s.execute(
            select(func.count()).select_from(User).where(User.id.in_([a["id"], b["id"]]), User.role == Role.SUPER_ADMIN, User.is_active.is_(True))
        )).scalar_one()
    assert remaining >= 1, [r.text for r in results]
    assert sum(1 for r in results if r.status_code == 200) <= 1


async def test_super_admin_demotion_removes_privileges_immediately(http, isolated_super_admins):
    cast = isolated_super_admins
    keep = await cast.make(Role.SUPER_ADMIN)
    gone = await cast.make(Role.SUPER_ADMIN)
    gone_h = await tokens(http, gone)
    assert (await http.get("/api/v1/security-audit-logs", headers=gone_h)).status_code == 200

    assert (await change_role(http, bearer(keep, Role.SUPER_ADMIN), gone["id"], "ADMIN", confirm=True)).status_code == 200
    # the old session is dead at once ...
    assert (await http.get("/api/v1/security-audit-logs", headers=gone_h)).status_code == 401
    # ... and a fresh login is only an Admin
    fresh = await tokens(http, gone)
    assert (await http.get("/api/v1/security-audit-logs", headers=fresh)).status_code == 403
    assert (await http.get("/api/v1/employees", headers=fresh)).status_code == 200
    assert (await change_role(http, fresh, keep["id"], "ADMIN", confirm=True)).status_code == 403


async def test_privileged_roles_cannot_be_granted_by_account_creation(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    adm = await cast.make(Role.ADMIN)

    def payload(role: str):
        u = uuid.uuid4().hex[:10]
        return {"user": {"email": f"adm_sec_new_{u}@fieldtrack.test", "password": "NewAccount123!", "role": role},
                "full_name": "Created Person", "employee_code": f"ASC{u[:6].upper()}"}

    created: list[str] = []

    async def register(headers, role):
        r = await http.post("/api/v1/employees/register", json=payload(role), headers=headers)
        if r.status_code == 201:
            created.append(r.json()["user_id"])
        return r

    try:
        # Admin: employee only
        assert (await register(bearer(adm, Role.ADMIN), "EMPLOYEE")).status_code == 201
        r = await register(bearer(adm, Role.ADMIN), "ADMIN")
        assert r.status_code == 403 and r.json()["error"]["code"] == "ROLE_ASSIGNMENT_FORBIDDEN"
        assert (await register(bearer(adm, Role.ADMIN), "SUPER_ADMIN")).status_code == 403
        # nobody (not even a Super Admin) can create a SUPER_ADMIN directly
        r = await register(bearer(sa, Role.SUPER_ADMIN), "SUPER_ADMIN")
        assert r.status_code == 403 and r.json()["error"]["code"] == "ROLE_ASSIGNMENT_FORBIDDEN"
        # only a Super Admin creates an Admin
        assert (await register(bearer(sa, Role.SUPER_ADMIN), "ADMIN")).status_code == 201

        # POST /users has the same rules
        base = {"email": f"adm_sec_u_{uuid.uuid4().hex[:8]}@fieldtrack.test", "password": "NewAccount123!"}
        r = await http.post("/api/v1/users", json={**base, "role": "ADMIN"}, headers=bearer(adm, Role.ADMIN))
        assert r.status_code == 403
        r = await http.post("/api/v1/users", json={**base, "role": "SUPER_ADMIN"}, headers=bearer(sa, Role.SUPER_ADMIN))
        assert r.status_code == 403
        r = await http.post("/api/v1/users", json={**base, "role": "EMPLOYEE"}, headers=bearer(adm, Role.ADMIN))
        assert r.status_code == 201
        created.append(r.json()["id"])
    finally:
        cast.user_ids.extend(uuid.UUID(c) for c in created)


async def test_plain_admin_cannot_touch_a_super_admin_account(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    spare = await cast.make(Role.SUPER_ADMIN)  # so the account is not "the last"
    adm = await cast.make(Role.ADMIN)
    h = bearer(adm, Role.ADMIN)

    r = await http.patch(f"/api/v1/employees/{sa['employee_id']}", json={"email": "hijack@fieldtrack.test"}, headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"
    assert (await db_user(sa["id"])).email == sa["email"]
    r = await http.patch(f"/api/v1/users/{sa['id']}/deactivate", headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"
    assert (await db_user(sa["id"])).is_active is True
    # a Super Admin can
    sh = bearer(spare, Role.SUPER_ADMIN)
    assert (await http.patch(f"/api/v1/users/{sa['id']}/deactivate", headers=sh)).status_code == 200
    assert (await http.patch(f"/api/v1/users/{sa['id']}/activate", headers=sh)).status_code == 200


async def test_security_audit_endpoint_is_super_admin_only(http, cast):
    sa = await cast.make(Role.SUPER_ADMIN)
    adm = await cast.make(Role.ADMIN)
    emp = await cast.make(Role.EMPLOYEE)
    assert (await change_role(http, bearer(sa, Role.SUPER_ADMIN), emp["id"], "ADMIN")).status_code == 200
    r = await http.get(f"/api/v1/security-audit-logs?target_user_id={emp['id']}", headers=bearer(sa, Role.SUPER_ADMIN))
    assert r.status_code == 200
    ev = r.json()
    assert ev and ev[0]["event_type"] == "ROLE_CHANGE" and ev[0]["new_role"] == "ADMIN"
    assert "password" not in r.text.lower().replace("current_password", "")
    assert (await http.get("/api/v1/security-audit-logs", headers=bearer(adm, Role.ADMIN))).status_code == 403
    plain = await cast.make(Role.EMPLOYEE)
    assert (await http.get("/api/v1/security-audit-logs", headers=bearer(plain, Role.EMPLOYEE))).status_code == 403


async def test_there_is_no_public_signup_endpoint(http):
    for path in ("/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/auth/sign-up", "/api/v1/signup"):
        r = await http.post(path, json={"email": "x@example.com", "password": "Password123!", "role": "SUPER_ADMIN"})
        assert r.status_code in (404, 405), path


# ---------------------------------------------------------------------------
# bootstrap script
# ---------------------------------------------------------------------------

def _sync_engine():
    return create_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))


async def test_bootstrap_promotes_only_the_named_admin_once(isolated_super_admins):
    from scripts.bootstrap_super_admin import BootstrapRefused, bootstrap_super_admin

    cast = isolated_super_admins
    target = await cast.make(Role.ADMIN)
    bystander = await cast.make(Role.ADMIN)
    employee = await cast.make(Role.EMPLOYEE)
    engine = _sync_engine()
    try:
        # not eligible / not found / blank identifier
        with pytest.raises(BootstrapRefused) as e:
            bootstrap_super_admin(employee["email"], engine=engine)
        assert e.value.code == "ACCOUNT_NOT_ELIGIBLE"
        with pytest.raises(BootstrapRefused) as e:
            bootstrap_super_admin("nobody-here@fieldtrack.test", engine=engine)
        assert e.value.code == "ACCOUNT_NOT_FOUND"
        with pytest.raises(BootstrapRefused):
            bootstrap_super_admin("  ", engine=engine)

        # dry run: every check passes but nothing is written
        assert bootstrap_super_admin(target["email"], engine=engine, execute=False) == "dry-run"
        assert (await db_user(target["id"])).role == Role.ADMIN
        assert await audit_rows("SUPER_ADMIN_BOOTSTRAP", target=target["id"]) == []

        assert bootstrap_super_admin(target["email"].upper(), engine=engine) == "promoted"
        assert (await db_user(target["id"])).role == Role.SUPER_ADMIN
        assert (await db_user(bystander["id"])).role == Role.ADMIN        # nobody else was promoted
        assert (await db_user(employee["id"])).role == Role.EMPLOYEE

        # a second run must refuse - bootstrap cannot mint additional Super Admins
        with pytest.raises(BootstrapRefused) as e:
            bootstrap_super_admin(bystander["email"], engine=engine)
        assert e.value.code == "SUPER_ADMIN_EXISTS"
        # recovery is refused while an active Super Admin exists
        with pytest.raises(BootstrapRefused) as e:
            bootstrap_super_admin(bystander["email"], engine=engine, recovery=True)
        assert e.value.code == "ACTIVE_SUPER_ADMIN_EXISTS"
        assert (await db_user(bystander["id"])).role == Role.ADMIN

        rows = await audit_rows("SUPER_ADMIN_BOOTSTRAP", target=target["id"])
        assert len(rows) == 1 and rows[0].outcome == "SUCCESS" and rows[0].actor_user_id is None
        assert rows[0].details["method"] == "bootstrap_script"
        assert PW not in str(rows[0].details)

        # recovery path: allowed only when NO active Super Admin remains
        async with AsyncSessionLocal() as s:
            await s.execute(update(User).where(User.id == target["id"]).values(is_active=False))
            await s.commit()
        assert bootstrap_super_admin(bystander["email"], engine=engine, recovery=True) == "promoted"
        assert (await db_user(bystander["id"])).role == Role.SUPER_ADMIN
    finally:
        engine.dispose()


def test_bootstrap_cli_requires_explicit_matching_identifier_and_production_ack(monkeypatch, capsys):
    from scripts import bootstrap_super_admin as script

    monkeypatch.delenv("SUPER_ADMIN_BOOTSTRAP_IDENTIFIER", raising=False)
    assert script.main(["--confirm-identifier", "a@b.test"]) == 2
    monkeypatch.setenv("SUPER_ADMIN_BOOTSTRAP_IDENTIFIER", "a@b.test")
    assert script.main(["--confirm-identifier", "other@b.test"]) == 2           # typo guard
    assert script.main(["--confirm-identifier", "a@b.test", "--recovery"]) == 2  # recovery needs its phrase
    monkeypatch.setattr(settings, "environment", "production")
    assert script.main(["--confirm-identifier", "a@b.test"]) == 2
    out = capsys.readouterr().out
    assert "REFUSING" in out
