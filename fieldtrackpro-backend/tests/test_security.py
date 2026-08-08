"""
Security unit tests — password hashing, JWT creation/validation.
No database required.
"""
from __future__ import annotations

import time
import uuid

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import Role
from datetime import timedelta


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_password_returns_different_hash():
    h1 = hash_password("mypassword")
    h2 = hash_password("mypassword")
    # bcrypt adds salt, so hashes differ
    assert h1 != h2


def test_verify_password_correct():
    plain = "correcthorsebattery"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("rightpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_verify_password_empty():
    hashed = hash_password("some_pass")
    assert verify_password("", hashed) is False


def test_hash_is_bcrypt_format():
    h = hash_password("test")
    assert h.startswith("$2")


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

def test_create_and_decode_access_token():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, Role.ADMIN.value)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == Role.ADMIN.value


def test_access_token_contains_jti():
    token = create_access_token(str(uuid.uuid4()), Role.EMPLOYEE.value)
    payload = decode_access_token(token)
    assert "jti" in payload


def test_access_token_employee_role():
    token = create_access_token(str(uuid.uuid4()), Role.EMPLOYEE.value)
    payload = decode_access_token(token)
    assert payload["role"] == Role.EMPLOYEE.value


def test_expired_token_raises():
    token = create_access_token(
        str(uuid.uuid4()),
        Role.ADMIN.value,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_tampered_token_raises():
    token = create_access_token(str(uuid.uuid4()), Role.ADMIN.value)
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_access_token(tampered)


def test_malformed_token_raises():
    with pytest.raises(JWTError):
        decode_access_token("not.a.token")


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

def test_generate_refresh_token_returns_tuple():
    raw, hashed = generate_refresh_token()
    assert isinstance(raw, str)
    assert isinstance(hashed, str)
    assert len(raw) > 32
    assert len(hashed) == 64  # SHA-256 hex


def test_refresh_tokens_are_unique():
    raw1, _ = generate_refresh_token()
    raw2, _ = generate_refresh_token()
    assert raw1 != raw2


def test_hash_refresh_token_deterministic():
    raw, _ = generate_refresh_token()
    h1 = hash_refresh_token(raw)
    h2 = hash_refresh_token(raw)
    assert h1 == h2


def test_different_raw_different_hash():
    raw1, h1 = generate_refresh_token()
    raw2, h2 = generate_refresh_token()
    assert h1 != h2
