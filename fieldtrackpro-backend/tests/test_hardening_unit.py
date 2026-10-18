"""
Hardening batch (no database needed): client-IP resolution, password byte guard,
validation-error redaction, CORS env parsing, SMTP transport rules, bounded uploads,
request body cap and config defaults.
"""
from __future__ import annotations

import io
import logging

import pytest
from fastapi import FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient

from app.config import Settings, settings
from app.core import client_ip as client_ip_mod
from app.core.client_ip import resolve_client_ip
from app.core.security import (
    MAX_PASSWORD_BYTES,
    PasswordTooLongException,
    hash_password,
    verify_password,
)
from app.core.uploads import BodySizeLimitMiddleware, read_upload_limited
from app.exceptions.custom import BaseAPIException
from app.exceptions.handlers import sanitize_validation_errors


# --------------------------------------------------------------- config defaults

def test_forced_password_change_is_off_by_default():
    """Deploying the code must not lock staff out: enforcement is opt-in (render.yaml turns it on)."""
    assert Settings.model_fields["enforce_password_change"].default is False
    assert Settings.model_fields["trusted_proxy_hops"].default == 1
    assert Settings.model_fields["smtp_allow_insecure"].default is False


def test_render_yaml_enables_enforcement_and_does_not_trust_star():
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "..", "render.yaml")
    text = open(path, encoding="utf-8").read()
    assert "ENFORCE_PASSWORD_CHANGE" in text
    start = next(l for l in text.splitlines() if l.strip().startswith("startCommand:"))
    assert "--forwarded-allow-ips" not in start
    assert "--proxy-headers" not in start.replace("--no-proxy-headers", "")


# ------------------------------------------------------------------- client IP

@pytest.mark.parametrize(
    "xff,peer,hops,expected",
    [
        # hops=1 (Render): the rightmost entry is what OUR edge appended.
        ("203.0.113.9", "10.0.0.1", 1, "203.0.113.9"),
        # attacker prepends fakes on the left: key must not change
        ("1.2.3.4, 203.0.113.9", "10.0.0.1", 1, "203.0.113.9"),
        ("6.6.6.6, 7.7.7.7, 203.0.113.9", "10.0.0.1", 1, "203.0.113.9"),
        # hops=2 (CDN + LB): second from the right
        ("1.2.3.4, 198.51.100.7, 10.1.1.1", "10.0.0.1", 2, "198.51.100.7"),
        ("8.8.8.8, 1.2.3.4, 198.51.100.7, 10.1.1.1", "10.0.0.1", 2, "198.51.100.7"),
        # header shorter than hops / absent / hops=0 -> socket peer
        ("203.0.113.9", "10.0.0.1", 2, "10.0.0.1"),
        (None, "10.0.0.1", 1, "10.0.0.1"),
        ("203.0.113.9", "10.0.0.1", 0, "10.0.0.1"),
        # garbage in the trusted slot is never used as a key
        ("1.2.3.4, <script>", "10.0.0.1", 1, "10.0.0.1"),
        ("", "10.0.0.1", 1, "10.0.0.1"),
    ],
)
def test_resolve_client_ip(xff, peer, hops, expected):
    assert resolve_client_ip(xff, peer, hops) == expected


def test_spoofed_leftmost_entries_do_not_change_the_rate_limit_key(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)

    class _Req:
        def __init__(self, xff):
            self.headers = {"x-forwarded-for": xff}
            self.client = type("C", (), {"host": "10.0.0.1"})()

    keys = {client_ip_mod.get_client_ip(_Req(f"{fake}, 203.0.113.9")) for fake in ("1.1.1.1", "2.2.2.2", "9.9.9.9")}
    assert keys == {"203.0.113.9"}


def test_auth_router_uses_the_safe_helper():
    from app.api.v1 import auth as auth_router

    class _Req:
        headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert auth_router._client_ip(_Req()) == "203.0.113.9"


# --------------------------------------------------------------- password bytes

def test_password_over_72_bytes_is_rejected_cleanly_and_never_verifies():
    too_long = "a" * (MAX_PASSWORD_BYTES + 1)
    with pytest.raises(PasswordTooLongException) as exc:
        hash_password(too_long)
    assert exc.value.status_code == 422 and exc.value.error_code == "PASSWORD_TOO_LONG"
    good = hash_password("a" * MAX_PASSWORD_BYTES)
    assert verify_password("a" * MAX_PASSWORD_BYTES, good) is True
    assert verify_password(too_long, good) is False  # no exception / 500


def test_multibyte_passwords_are_counted_in_bytes():
    pw = "é" * 37  # 37 chars, 74 bytes
    assert len(pw) < 72 and len(pw.encode()) > 72
    with pytest.raises(PasswordTooLongException):
        hash_password(pw)


# --------------------------------------------------------- validation redaction

def test_validation_errors_never_echo_secrets():
    errors = [
        {"type": "string_too_short", "loc": ("body", "new_password"), "msg": "short", "input": "hunter2-secret"},
        {"type": "x", "loc": ("body", "otp"), "msg": "m", "input": "123456"},
        {"type": "x", "loc": ("body", "refresh_token"), "msg": "m", "input": "tok-abc"},
        {"type": "missing", "loc": ("body", "identifier"), "msg": "m", "input": {"password": "p4ss", "identifier": "a@b.c"}},
        {"type": "x", "loc": ("body", "amount"), "msg": "m", "input": "abc"},
    ]
    out = sanitize_validation_errors(errors)
    dumped = str(out)
    for secret in ("hunter2-secret", "123456", "tok-abc", "p4ss"):
        assert secret not in dumped
    assert out[0]["input"] == "[REDACTED]" and out[1]["input"] == "[REDACTED]"
    assert out[3]["input"]["identifier"] == "a@b.c"  # non-sensitive keys survive
    assert out[4]["input"] == "abc"


@pytest.mark.asyncio
async def test_422_response_and_log_do_not_contain_the_submitted_password(caplog):
    from app.main import app

    secret = "Sup3rSecret-" + "x" * 130  # > 128 chars -> LoginRequest max_length violation
    caplog.set_level(logging.WARNING, logger="fieldtrackpro")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/v1/auth/login", json={"identifier": "a@b.co", "password": secret})
    assert r.status_code == 422
    assert secret not in r.text
    assert all(secret not in rec.getMessage() for rec in caplog.records)


# ------------------------------------------------------------------ CORS parsing

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://a.example.com,https://b.example.com", ["https://a.example.com", "https://b.example.com"]),
        ('["https://a.example.com", "https://b.example.com"]', ["https://a.example.com", "https://b.example.com"]),
        (" https://a.example.com ", ["https://a.example.com"]),
    ],
)
def test_cors_origins_accept_comma_separated_or_json_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", raw)
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret-not-real")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/x")
    s = Settings(_env_file=None)
    assert s.cors_allowed_origins == expected


# -------------------------------------------------------------------------- SMTP

class _FakeSMTPBase:
    instances: list = []
    starttls_offered = True

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls: list = []
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def has_extn(self, name):
        return name == "starttls" and type(self).starttls_offered

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, u, p):
        self.calls.append("login")

    def send_message(self, msg):
        self.calls.append("send")


class _FakeSMTP(_FakeSMTPBase):
    pass


class _FakeSMTPSSL(_FakeSMTPBase):
    pass


class _FakeSmtplib:
    SMTP = _FakeSMTP
    SMTP_SSL = _FakeSMTPSSL


@pytest.fixture
def fake_smtp(monkeypatch):
    from app.services import email_service

    _FakeSMTPBase.instances = []
    _FakeSMTPBase.starttls_offered = True
    monkeypatch.setattr(email_service, "smtplib", _FakeSmtplib)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_user", "user")
    monkeypatch.setattr(settings, "smtp_password", "pw")
    monkeypatch.setattr(settings, "smtp_allow_insecure", False)
    monkeypatch.setattr(settings, "environment", "dev")
    return email_service


def test_smtp_port_465_uses_implicit_tls(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_port", 465)
    fake_smtp._send_smtp_email("x@y.com", "s", "b")
    inst = _FakeSMTPBase.instances[-1]
    assert isinstance(inst, _FakeSMTPSSL)
    assert inst.calls == ["ehlo", "login", "send"] and "starttls" not in inst.calls


@pytest.mark.parametrize("port", [587, 2525])
def test_smtp_starttls_when_advertised(fake_smtp, monkeypatch, port):
    monkeypatch.setattr(settings, "smtp_port", port)
    fake_smtp._send_smtp_email("x@y.com", "s", "b")
    inst = _FakeSMTPBase.instances[-1]
    assert isinstance(inst, _FakeSMTP)
    assert inst.calls == ["ehlo", "starttls", "ehlo", "login", "send"]


def test_smtp_refuses_cleartext_credentials(fake_smtp, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_port", 587)
    _FakeSMTPBase.starttls_offered = False
    caplog.set_level(logging.ERROR)
    with pytest.raises(fake_smtp.SmtpInsecureError):
        fake_smtp._send_smtp_email("person@example.com", "s", "b")
    inst = _FakeSMTPBase.instances[-1]
    assert "login" not in inst.calls and "send" not in inst.calls
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "person@example.com" not in logged  # masked
    assert "smtp_delivery_failed" in logged


def test_smtp_allow_insecure_only_outside_production(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_port", 587)
    _FakeSMTPBase.starttls_offered = False
    monkeypatch.setattr(settings, "smtp_allow_insecure", True)
    fake_smtp._send_smtp_email("x@y.com", "s", "b")  # dev + opt-in: allowed
    assert "login" in _FakeSMTPBase.instances[-1].calls
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(fake_smtp.SmtpInsecureError):  # never in production
        fake_smtp._send_smtp_email("x@y.com", "s", "b")


@pytest.mark.asyncio
async def test_failed_delivery_does_not_change_the_response(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_port", 587)
    _FakeSMTPBase.starttls_offered = False
    # swallowed by the async wrapper: no exception reaches the caller
    await fake_smtp.send_password_reset_email("x@y.com", "123456")


# ------------------------------------------------------------------- uploads

def _upload(data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename="f.bin", size=len(data))


@pytest.mark.asyncio
async def test_read_upload_limited_ok_and_413_when_exceeded():
    assert await read_upload_limited(_upload(b"x" * 100), 100) == b"x" * 100
    with pytest.raises(BaseAPIException) as exc:
        await read_upload_limited(_upload(b"x" * 101), 100)
    assert exc.value.status_code == 413 and exc.value.error_code == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_read_upload_limited_stops_reading_as_soon_as_cap_is_crossed():
    reads: list[int] = []

    class _Streamy:
        size = None  # unknown up front (chunked)

        async def read(self, n=-1):
            reads.append(n)
            return b"y" * n if len(reads) < 1000 else b""

    with pytest.raises(BaseAPIException) as exc:
        await read_upload_limited(_Streamy(), 3 * 1024, chunk_size=1024)
    assert exc.value.error_code == "FILE_TOO_LARGE"
    assert len(reads) == 4  # 3 chunks fit, the 4th crosses the cap -> stop immediately


@pytest.mark.asyncio
async def test_body_size_middleware_rejects_oversized_content_length_before_the_app_runs():
    called = {"n": 0}
    inner = FastAPI()

    @inner.post("/up")
    async def up():
        called["n"] += 1
        return {"ok": True}

    app = BodySizeLimitMiddleware(inner, max_bytes=1000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        big = await c.post("/up", content=b"x" * 2000)
        small = await c.post("/up", content=b"x" * 10)
    assert big.status_code == 413 and big.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert small.status_code == 200
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_body_size_middleware_aborts_streamed_bodies_without_content_length():
    inner = FastAPI()

    @inner.post("/up")
    async def up(request_body: dict | None = None):  # pragma: no cover - never reached
        return {"ok": True}

    app = BodySizeLimitMiddleware(inner, max_bytes=1000)
    sent: list = []

    async def receive():
        return {"type": "http.request", "body": b"z" * 600, "more_body": True}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": "POST", "path": "/up", "headers": [], "query_string": b""}
    await app(scope, receive, send)
    assert sent[0]["status"] == 413


def test_text_fields_have_length_caps_and_login_fields_are_bounded():
    from pydantic import ValidationError

    from app.schemas.auth import LoginRequest
    from app.schemas.payment import PaymentCreate

    with pytest.raises(ValidationError):
        LoginRequest(identifier="a" * 256, password="x")
    with pytest.raises(ValidationError):
        LoginRequest(identifier="a@b.co", password="x" * 129)
    assert PaymentCreate.model_fields["notes"].metadata[0].max_length == 1000
