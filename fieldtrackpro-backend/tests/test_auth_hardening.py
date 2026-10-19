"""
A2 hardening tests: password-reset throttling / no-enumeration / keyed OTP,
refresh-token rotation + replay detection, cookie policy, CORS allow-list,
log scrubbing, and removal of the unauthenticated APK endpoints.
Uses only synthetic users (a2h_*@fieldtrack.test), removed after each test.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.config import Settings, settings
from app.core.security import hash_password, hash_refresh_token
from app.database import AsyncSessionLocal
from app.logging_config import AccessLogQueryStripFilter, scrub_sensitive, strip_query
from app.main import app
from app.models.login_attempt import LoginAttempt
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import Role, User
from app.services import auth_service
from tests.conftest import requires_db

PW = "OldPassword123!"


@pytest_asyncio.fixture(autouse=True)
async def _clean_throttle_rows():
    """All ASGI test clients share IP 127.0.0.1; start and end each test with a clean budget."""
    async def _wipe():
        try:
            async with AsyncSessionLocal() as s:
                await s.execute(delete(LoginAttempt))
                await s.commit()
        except Exception:  # DB not available -> DB tests are skipped anyway
            pass

    await _wipe()
    yield
    await _wipe()


@pytest_asyncio.fixture
async def synthetic_user():
    uid = uuid.uuid4()
    email = f"a2h_{uid.hex[:10]}@fieldtrack.test"
    mobile = "98" + str(int(uid.int % 10**8)).zfill(8)
    async with AsyncSessionLocal() as s:
        s.add(
            User(
                id=uid,
                email=email,
                mobile_number=mobile,
                password_hash=hash_password(PW),
                role=Role.EMPLOYEE,
                is_active=True,
            )
        )
        await s.commit()
    yield {"id": uid, "email": email, "mobile": mobile}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == uid))
        await s.execute(delete(RefreshToken).where(RefreshToken.user_id == uid))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


@pytest_asyncio.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------- OTP / reset

def test_hash_otp_is_keyed_and_user_bound():
    a = auth_service.hash_otp("123456", "u1")
    assert a != __import__("hashlib").sha256(b"123456").hexdigest()
    assert a == auth_service.hash_otp("123456", "u1")
    assert a != auth_service.hash_otp("123456", "u2")
    with patch.object(settings, "otp_hmac_secret", "another-secret"):
        assert auth_service.hash_otp("123456", "u1") != a


@requires_db
@pytest.mark.asyncio
async def test_forgot_password_identical_for_known_and_unknown(http, synthetic_user):
    ghost = f"a2h_ghost_{uuid.uuid4().hex[:8]}@fieldtrack.test"
    with patch("app.services.auth_service.send_password_reset_email", new_callable=AsyncMock) as mail:
        known = await http.post("/api/v1/auth/forgot-password", json={"identifier": synthetic_user["email"]})
        unknown = await http.post("/api/v1/auth/forgot-password", json={"identifier": ghost})
    assert known.status_code == unknown.status_code == 200
    kb, ub = known.json(), unknown.json()
    assert kb["message"] == ub["message"]
    assert kb["delivery_channel"] == ub["delivery_channel"] == "EMAIL"
    # masked destination derives from the input only -> same shape
    assert len(kb["destination"]) == len(ub["destination"]) - (len(ghost) - len(synthetic_user["email"]))
    assert mail.await_count == 1  # only the real account is mailed


@requires_db
@pytest.mark.asyncio
async def test_forgot_password_throttle_not_cleared_by_success(http, synthetic_user):
    """Per-account budget of 5: the 6th request is 429 even though earlier ones 'succeeded'."""
    with patch("app.services.auth_service.send_password_reset_email", new_callable=AsyncMock):
        codes = [
            (await http.post("/api/v1/auth/forgot-password", json={"identifier": synthetic_user["email"]})).status_code
            for _ in range(7)
        ]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429 and codes[6] == 429


@requires_db
@pytest.mark.asyncio
async def test_forgot_password_unknown_account_is_throttled_too(http):
    ghost = f"a2h_ghost_{uuid.uuid4().hex[:8]}@fieldtrack.test"
    codes = [
        (await http.post("/api/v1/auth/forgot-password", json={"identifier": ghost})).status_code for _ in range(6)
    ]
    assert codes[:5] == [200] * 5 and codes[5] == 429


@requires_db
@pytest.mark.asyncio
async def test_verify_and_reset_share_one_attempt_counter(http, synthetic_user):
    ident = synthetic_user["email"]
    statuses = []
    for i in range(10):
        path = "verify-otp" if i % 2 == 0 else "reset-password"
        body = {"identifier": ident, "otp": "000000"}
        if path == "reset-password":
            body["new_password"] = "NewPassword123!"
        statuses.append((await http.post(f"/api/v1/auth/{path}", json=body)).status_code)
    # budget is 8 combined attempts; both endpoints draw from the same pool
    assert statuses[:8] == [400] * 8
    assert statuses[8:] == [429, 429]


@requires_db
@pytest.mark.asyncio
async def test_reset_unknown_and_wrong_code_are_indistinguishable(http, synthetic_user):
    ghost = f"a2h_ghost_{uuid.uuid4().hex[:8]}@fieldtrack.test"
    body = {"otp": "000000", "new_password": "NewPassword123!"}
    a = await http.post("/api/v1/auth/reset-password", json={"identifier": ghost, **body})
    b = await http.post("/api/v1/auth/reset-password", json={"identifier": synthetic_user["email"], **body})
    assert a.status_code == b.status_code == 400
    assert a.json()["error"]["code"] == b.json()["error"]["code"]
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


@requires_db
@pytest.mark.asyncio
async def test_forgot_ip_throttle(http):
    """Per-IP: 20 sends / 15 min across DIFFERENT accounts, then 429."""
    from app.core.rate_limiter import forgot_ip_limiter, throttle_key

    async with AsyncSessionLocal() as s:
        for _ in range(20):
            await forgot_ip_limiter.hit(throttle_key("pwforgot", "ip", "127.0.0.1"), s)
    r = await http.post(
        "/api/v1/auth/forgot-password", json={"identifier": f"a2h_{uuid.uuid4().hex[:8]}@fieldtrack.test"}
    )
    assert r.status_code == 429
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(LoginAttempt).where(
                LoginAttempt.identifier == throttle_key("pwforgot", "ip", "127.0.0.1")
            )
        )
        await s.commit()


@requires_db
@pytest.mark.asyncio
async def test_full_reset_flow_uses_keyed_hash_and_revokes_sessions(http, synthetic_user):
    login = await http.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})
    assert login.status_code == 200
    old_refresh = login.json()["refresh_token"]

    with patch("app.services.auth_service.send_password_reset_email", new_callable=AsyncMock) as mail:
        await http.post("/api/v1/auth/forgot-password", json={"identifier": synthetic_user["email"]})
    otp = mail.call_args[0][1]

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == synthetic_user["id"]))
        ).scalar_one()
        assert row.token_hash == auth_service.hash_otp(otp, synthetic_user["id"])
        assert row.token_hash != __import__("hashlib").sha256(otp.encode()).hexdigest()

    ok = await http.post(
        "/api/v1/auth/reset-password",
        json={"identifier": synthetic_user["email"], "otp": otp, "new_password": "BrandNewPass123!"},
    )
    assert ok.status_code == 200
    again = await http.post(
        "/api/v1/auth/reset-password",
        json={"identifier": synthetic_user["email"], "otp": otp, "new_password": "AnotherPass123!"},
    )
    assert again.status_code == 400  # OTP is single-use
    refresh = await http.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh.status_code == 401


# ---------------------------------------------------------------- refresh

@requires_db
@pytest.mark.asyncio
async def test_refresh_replay_within_grace_window_is_tolerated(http, synthetic_user):
    """
    Replaying an already-rotated token a moment after rotation (two browser
    tabs, a client retry) must NOT nuke every session - only a replay older
    than the grace window is theft. See test_refresh_replay_past_grace_window_revokes_all_user_tokens.
    """
    r1 = (await http.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
    r2 = await http.post("/api/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]})
    assert r2.status_code == 200
    newest = r2.json()["refresh_token"]

    replay = await http.post("/api/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]})
    assert replay.status_code == 200
    replay_token = replay.json()["refresh_token"]

    # The winner's own rotated token is unaffected - no account-wide revoke happened.
    after = await http.post("/api/v1/auth/refresh", json={"refresh_token": newest})
    assert after.status_code == 200

    async with AsyncSessionLocal() as s:
        live = await s.scalar(
            select(func.count()).select_from(RefreshToken).where(
                RefreshToken.user_id == synthetic_user["id"], RefreshToken.revoked.is_(False)
            )
        )
    # Both the "after" rotation and the grace-window replay's own new token are live.
    assert live == 2
    assert replay_token != newest


@requires_db
@pytest.mark.asyncio
async def test_refresh_replay_past_grace_window_revokes_all_user_tokens(http, synthetic_user):
    """A replay older than the grace window is still treated as theft: revoke everything."""
    r1 = (await http.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
    r2 = await http.post("/api/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]})
    assert r2.status_code == 200
    newest = r2.json()["refresh_token"]

    with patch.object(settings, "refresh_reuse_grace_seconds", 0):
        replay = await http.post("/api/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]})
    assert replay.status_code == 401
    # the legitimately-rotated token is now dead too (whole family revoked)
    after = await http.post("/api/v1/auth/refresh", json={"refresh_token": newest})
    assert after.status_code == 401
    async with AsyncSessionLocal() as s:
        live = await s.scalar(
            select(func.count()).select_from(RefreshToken).where(
                RefreshToken.user_id == synthetic_user["id"], RefreshToken.revoked.is_(False)
            )
        )
    assert live == 0


@requires_db
@pytest.mark.asyncio
async def test_concurrent_refresh_all_succeed_within_grace_window(synthetic_user):
    """
    Multiple tabs/retries racing the same refresh token concurrently must all
    come back successfully (each gets its own new token), not log the user out.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tok = (await c.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
        results = await asyncio.gather(
            *[c.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}) for _ in range(4)]
        )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 4, codes

    async with AsyncSessionLocal() as s:
        live = await s.scalar(
            select(func.count()).select_from(RefreshToken).where(
                RefreshToken.user_id == synthetic_user["id"], RefreshToken.revoked.is_(False)
            )
        )
    assert live == 4


@requires_db
@pytest.mark.asyncio
async def test_concurrent_refresh_past_grace_window_only_one_wins(synthetic_user):
    """With the grace window disabled, the pre-existing serialize-and-revoke behavior still holds."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tok = (await c.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
        with patch.object(settings, "refresh_reuse_grace_seconds", 0):
            results = await asyncio.gather(
                *[c.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}) for _ in range(4)]
            )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes
    assert codes.count(401) == 3, codes


@requires_db
@pytest.mark.asyncio
async def test_expired_refresh_token_rejected(http, synthetic_user):
    tok = (await http.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import update

    async with AsyncSessionLocal() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(tok["refresh_token"]))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await s.commit()
    r = await http.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_cookie_refresh_rejects_foreign_origin(http, synthetic_user):
    tok = (await http.post("/api/v1/auth/login", json={"identifier": synthetic_user["email"], "password": PW})).json()
    r = await http.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "https://evil.vercel.app"},
        cookies={"refresh_token": tok["refresh_token"]},
    )
    assert r.status_code == 403
    allowed = settings.cors_allowed_origins[0]
    r2 = await http.post(
        "/api/v1/auth/refresh", headers={"Origin": allowed}, cookies={"refresh_token": tok["refresh_token"]}
    )
    assert r2.status_code == 200


# ---------------------------------------------------------------- cookie policy

def test_cookie_policy_production_is_secure_samesite_none():
    from app.api.v1 import auth as auth_router

    with patch.object(settings, "environment", "production"), patch.object(settings, "refresh_cookie_samesite", None):
        assert auth_router._cookie_policy() == (True, "none")
    with patch.object(settings, "environment", "dev"), patch.object(settings, "refresh_cookie_samesite", None):
        assert auth_router._cookie_policy() == (False, "lax")
    with patch.object(settings, "environment", "production"), patch.object(settings, "refresh_cookie_samesite", "strict"):
        assert auth_router._cookie_policy() == (True, "strict")


@pytest.mark.asyncio
async def test_login_cookie_flags_in_production(http):
    from app.schemas.auth import TokenResponse

    with patch.object(settings, "environment", "production"), patch.object(
        settings, "refresh_cookie_samesite", None
    ), patch("app.services.auth_service.login", new=AsyncMock(return_value=TokenResponse(access_token="a", refresh_token="r"))):
        resp = await http.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "Whatever123!"})
    sc = resp.headers["set-cookie"]
    assert "HttpOnly" in sc and "Secure" in sc and "SameSite=none" in sc
    # CHIPS: the live cookie is Partitioned (still sent when third-party cookies are blocked); the legacy
    # unpartitioned cookie of the same name is expired in the same response.
    cookies = resp.headers.get_list("set-cookie")
    live = [c for c in cookies if "Max-Age=0" not in c]
    legacy = [c for c in cookies if "Max-Age=0" in c]
    assert len(live) == 1 and "Partitioned" in live[0] and "Path=/api/v1/auth" in live[0]
    assert cookies[-1] == live[0], "the live cookie must be the LAST header so a browser ignoring Partitioned keeps it"
    assert len(legacy) == 1 and "Partitioned" not in legacy[0] and "Secure" in legacy[0] and "SameSite=none" in legacy[0]


def _set_cookie_headers(fn, *args):
    from starlette.responses import Response as StarletteResponse

    r = StarletteResponse()
    fn(r, *args)
    return [v.decode() for k, v in r.raw_headers if k == b"set-cookie"]


def test_refresh_cookie_is_partitioned_in_production_and_expires_legacy_cookie():
    from app.api.v1 import auth as auth_router

    with patch.object(settings, "environment", "production"), patch.object(settings, "refresh_cookie_samesite", None):
        legacy, live = _set_cookie_headers(auth_router._set_refresh_cookie, "tok")  # legacy expiry FIRST, live cookie LAST
    assert "refresh_token=tok" in live and "Partitioned" in live and "Secure" in live and "SameSite=none" in live
    assert "HttpOnly" in live and "Path=/api/v1/auth" in live
    assert "Max-Age=0" in legacy and "Partitioned" not in legacy
    assert "Path=/api/v1/auth" in legacy and "Secure" in legacy and "SameSite=none" in legacy and "HttpOnly" in legacy


def test_clear_refresh_cookie_removes_partitioned_and_legacy_with_matching_attributes():
    from app.api.v1 import auth as auth_router

    with patch.object(settings, "environment", "production"), patch.object(settings, "refresh_cookie_samesite", None):
        headers = _set_cookie_headers(auth_router._clear_refresh_cookie)
    assert len(headers) == 2
    assert sum("Partitioned" in h for h in headers) == 1
    for h in headers:
        assert h.startswith("refresh_token=;") or h.startswith('refresh_token="";')
        assert "Max-Age=0" in h and "Path=/api/v1/auth" in h and "Secure" in h and "SameSite=none" in h and "HttpOnly" in h


def test_refresh_cookie_not_partitioned_in_dev_http():
    from app.api.v1 import auth as auth_router

    with patch.object(settings, "environment", "dev"), patch.object(settings, "refresh_cookie_samesite", None):
        headers = _set_cookie_headers(auth_router._set_refresh_cookie, "tok")
    assert all("Partitioned" not in h for h in headers)  # Partitioned requires Secure; dev is plain http
    assert "SameSite=lax" in headers[-1] and "refresh_token=tok" in headers[-1]


@pytest.mark.asyncio
async def test_account_deletion_clears_both_refresh_cookies():
    from starlette.responses import Response as StarletteResponse

    from app.api.v1 import account as account_router

    r = StarletteResponse()
    with patch.object(settings, "environment", "production"), patch.object(
        settings, "refresh_cookie_samesite", None
    ), patch.object(account_router.account_deletion_service, "delete_own_account", new=AsyncMock()):
        await account_router.delete_my_account(
            r, object(), object(), account_router.DeleteAccountRequest(password="x")
        )
    headers = [v.decode() for k, v in r.raw_headers if k == b"set-cookie"]
    assert len(headers) == 2 and sum("Partitioned" in h for h in headers) == 1
    assert all("Max-Age=0" in h and "Secure" in h and "SameSite=none" in h and "Path=/api/v1/auth" in h for h in headers)


# ---------------------------------------------------------------- CORS / endpoints

@pytest.mark.asyncio
async def test_cors_rejects_vercel_preview_not_in_allow_list(http):
    evil = "https://attacker-preview.vercel.app"
    r = await http.get("/health", headers={"Origin": evil})
    assert "access-control-allow-origin" not in r.headers
    ok = settings.cors_allowed_origins[0]
    r2 = await http.get("/health", headers={"Origin": ok})
    assert r2.headers.get("access-control-allow-origin") == ok


def test_default_cors_has_no_vercel_or_wildcard():
    for o in Settings.model_fields["cors_allowed_origins"].default:
        assert "vercel.app" not in o and o != "*"


def test_production_cors_misconfig_only_warns():
    with pytest.warns(UserWarning, match="localhost"):
        Settings(
            database_url="postgresql+asyncpg://u:p@h/db",
            jwt_secret="x" * 40,
            environment="production",
            media_signing_secret="m" * 40,
            sms_provider="msg91",
            smtp_host="smtp.example.com",
            cors_allowed_origins=["http://localhost:5173"],
        )


@pytest.mark.asyncio
async def test_apk_endpoints_removed(http):
    for path in ("/download/app", "/app-latest.apk"):
        assert (await http.get(path)).status_code == 404


def test_no_machine_specific_paths_in_app():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    pat = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:\\[A-Za-z]|/Users/[A-Za-z]")
    offenders = [str(p) for p in root.rglob("*.py") if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == []


# ---------------------------------------------------------------- log scrubbing

@pytest.mark.parametrize(
    "raw,forbidden",
    [
        ("Authorization: Bearer abc.def.ghi-123", "abc.def.ghi-123"),
        ("token=SECRETTOKENVALUE123 ok", "SECRETTOKENVALUE123"),
        ("refresh_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sigsigsig", "eyJhbGci"),
        ("otp=482913 sent", "482913"),
        ("GET https://s3.example.com/b/k.jpg?X-Amz-Signature=deadbeef&X-Amz-Credential=AKIA", "deadbeef"),
        ("GET /api/v1/media/1/file?sig=abc123&exp=99", "abc123"),
        ("visit lat=12.971599 lng=77.594566 checked", "12.971599"),
        ("payload {'latitude': 12.971599, 'longitude': 77.594566}", "77.594566"),
        ("Geocoded to (12.971599, 77.594566)", "12.971599"),
        ("password: hunter2hunter2", "hunter2hunter2"),
    ],
)
def test_scrubber_removes_sensitive_values(raw, forbidden):
    out = scrub_sensitive(raw)
    assert forbidden not in out
    assert "[REDACTED]" in out


def test_scrubber_keeps_benign_text():
    msg = "event=http_request method=GET path=/api/v1/customers status=200 duration_ms=12.5 latency=3 error_code=X"
    assert scrub_sensitive(msg) == msg


def test_strip_query_and_access_filter():
    assert strip_query("/a/b?x=1#f") == "/a/b"
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/media/1?sig=SECRET", "1.1", 200), None)
    AccessLogQueryStripFilter().filter(rec)
    assert "SECRET" not in rec.getMessage()


@pytest.mark.asyncio
async def test_request_log_never_contains_query_string(http, caplog):
    caplog.set_level(logging.INFO, logger="fieldtrackpro")
    await http.get("/api/v1/customers?lat=12.9716&lng=77.5946&token=SHOULDNOTLOG")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "SHOULDNOTLOG" not in text and "12.9716" not in text and "?" not in text.split("path=")[1].split()[0]


def test_formatter_scrubs_exception_tracebacks():
    from app.logging_config import ScrubbingFormatter

    fmt = ScrubbingFormatter("%(message)s")
    try:
        raise RuntimeError("failed url https://x.example/y?X-Amz-Signature=LEAKED")
    except RuntimeError:
        import sys

        rec = logging.LogRecord("t", logging.ERROR, "", 0, "boom", None, sys.exc_info())
    assert "LEAKED" not in fmt.format(rec)
