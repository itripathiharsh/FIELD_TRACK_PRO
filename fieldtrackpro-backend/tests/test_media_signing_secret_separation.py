"""
Unit: media presigned-URL signing secret is independent of the JWT secret
(P1-2). Previously `local_provider._sign` used `settings.jwt_secret`
directly, so rotating either secret unintentionally invalidated the other's
trust boundary. No database required.
"""
from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.core.security import create_access_token, decode_access_token
from app.services.storage import local_provider


def test_media_signing_uses_dedicated_secret_not_jwt_secret(monkeypatch):
    monkeypatch.setattr(local_provider.settings, "media_signing_secret", "media-secret-A")
    monkeypatch.setattr(local_provider.settings, "jwt_secret", "jwt-secret-A")
    sig_before = local_provider._sign("some/key.jpg", 12345)

    # Changing ONLY the JWT secret must not move the media signature at all.
    monkeypatch.setattr(local_provider.settings, "jwt_secret", "a-completely-different-jwt-secret")
    sig_after = local_provider._sign("some/key.jpg", 12345)

    assert sig_before == sig_after, "P1-2: media signing must not depend on jwt_secret"


def test_media_signing_secret_change_does_change_the_signature(monkeypatch):
    monkeypatch.setattr(local_provider.settings, "media_signing_secret", "media-secret-A")
    sig_a = local_provider._sign("some/key.jpg", 12345)

    monkeypatch.setattr(local_provider.settings, "media_signing_secret", "media-secret-B")
    sig_b = local_provider._sign("some/key.jpg", 12345)

    assert sig_a != sig_b, "changing the dedicated media secret must actually change the signature"


def test_jwt_signing_uses_jwt_secret_not_media_signing_secret(monkeypatch):
    from app.core import security as security_module

    monkeypatch.setattr(security_module.settings, "jwt_secret", "jwt-secret-A")
    monkeypatch.setattr(security_module.settings, "media_signing_secret", "media-secret-A")
    token = create_access_token("11111111-1111-1111-1111-111111111111", "ADMIN")

    # Changing ONLY the media signing secret must not affect JWT validity.
    monkeypatch.setattr(security_module.settings, "media_signing_secret", "a-completely-different-media-secret")
    decoded = decode_access_token(token)
    assert decoded["sub"] == "11111111-1111-1111-1111-111111111111"


def test_changing_jwt_secret_does_not_affect_media_signing(monkeypatch):
    """The reverse direction of test_media_signing_uses_dedicated_secret_not_jwt_secret, stated explicitly."""
    from app.core import security as security_module

    monkeypatch.setattr(local_provider.settings, "media_signing_secret", "stable-media-secret")
    sig_before = local_provider._sign("k", 999)

    monkeypatch.setattr(security_module.settings, "jwt_secret", "rotated-jwt-secret")
    sig_after = local_provider._sign("k", 999)
    assert sig_before == sig_after


def test_signature_verification_round_trips_with_dedicated_secret(monkeypatch):
    monkeypatch.setattr(local_provider.settings, "media_signing_secret", "round-trip-secret")
    expires_at = int(time.time()) + 900
    sig = local_provider._sign("media/key.png", expires_at)
    assert local_provider.verify_local_media_signature("media/key.png", expires_at, sig)
    assert not local_provider.verify_local_media_signature("media/key.png", expires_at, "wrong-signature")


def test_production_requires_media_signing_secret_explicitly():
    """P1-2: production must fail to start rather than fall back to an insecure default."""
    with pytest.raises(ValueError, match="MEDIA_SIGNING_SECRET"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            jwt_secret="some-jwt-secret",
            media_signing_secret=None,
        )


def test_production_accepts_an_explicitly_configured_media_signing_secret():
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        jwt_secret="some-jwt-secret",
        media_signing_secret="a-real-production-secret",
    )
    assert settings.media_signing_secret == "a-real-production-secret"


def test_dev_environment_falls_back_to_a_placeholder_when_unset():
    settings = Settings(
        environment="dev",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        jwt_secret="some-jwt-secret",
    )
    assert settings.media_signing_secret is not None
    assert settings.media_signing_secret != settings.jwt_secret
