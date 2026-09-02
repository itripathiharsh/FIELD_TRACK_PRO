import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import logging

from app.services.sms_service import (
    mask_mobile,
    mask_email,
    get_sms_provider,
    MockSmsProvider,
    send_password_reset_sms,
)
from app.services.email_service import send_password_reset_email
from app.models.user import User, Role
from app.core.security import hash_password
from app.repositories.user_repo import UserRepository
from app.database import AsyncSessionLocal
from app.config import Settings
from tests.conftest import requires_db


def test_mask_mobile():
    assert mask_mobile("9839011014") == "******1014"
    assert mask_mobile("+919839011014") == "*********1014"
    assert mask_mobile("123") == "****"


def test_mask_email():
    assert mask_email("deepak.soni@sgrgservices.com") == "d*********i@sgrgservices.com"
    assert mask_email("ab@test.com") == "a*@test.com"
    assert mask_email("invalid") == "***@***"


@pytest.mark.asyncio
async def test_mock_sms_provider_in_dev():
    with patch("app.config.settings.environment", "dev"), patch("app.config.settings.debug", True):
        provider = MockSmsProvider()
        result = await provider.send_sms("9839011014", "Your code is 123456", "123456")
        assert result is True


@pytest.mark.asyncio
async def test_mock_sms_provider_refuses_in_production(caplog):
    with patch("app.config.settings.environment", "production"):
        provider = MockSmsProvider()
        with caplog.at_level(logging.INFO):
            result = await provider.send_sms("9839011014", "Your code is 123456", "123456")
            assert result is False
            # OTP must NOT be anywhere in the logs
            for record in caplog.records:
                assert "123456" not in record.message
            assert any("MockSmsProvider cannot be used when ENVIRONMENT=production" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_mock_email_refuses_in_production_without_smtp(caplog):
    with patch("app.config.settings.environment", "production"), patch("app.config.settings.smtp_host", None):
        with caplog.at_level(logging.INFO):
            await send_password_reset_email("user@company.com", "998877")
            # OTP must NOT be in the logs
            for record in caplog.records:
                assert "998877" not in record.message
            assert any("SMTP_HOST not configured in production environment" in r.message for r in caplog.records)


def test_production_settings_rejects_mock_sms():
    with pytest.raises(ValueError, match="SMS_PROVIDER cannot be 'mock' when ENVIRONMENT=production"):
        Settings(
            database_url="postgresql+asyncpg://app:secret@localhost:5432/fieldtrackpro",
            jwt_secret="prod-super-secret-key-at-least-32-chars-long",
            media_signing_secret="prod-media-signing-secret-32-chars",
            environment="production",
            sms_provider="mock",
            smtp_host="smtp.sendgrid.net",
        )


def test_production_settings_rejects_missing_smtp():
    with pytest.raises(ValueError, match="SMTP_HOST must be configured when ENVIRONMENT=production"):
        Settings(
            database_url="postgresql+asyncpg://app:secret@localhost:5432/fieldtrackpro",
            jwt_secret="prod-super-secret-key-at-least-32-chars-long",
            media_signing_secret="prod-media-signing-secret-32-chars",
            environment="production",
            sms_provider="msg91",
            sms_api_key="valid_api_key",
            smtp_host=None,
        )


@requires_db
@pytest.mark.asyncio
async def test_unified_forgot_password_and_reset_flow_email(client: AsyncClient):
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email("test_reset_email@fieldtrack.test")
        if not user:
            user = User(
                email="test_reset_email@fieldtrack.test",
                mobile_number="9800000001",
                password_hash=hash_password("OldPassword123!"),
                role=Role.EMPLOYEE,
                is_active=True,
            )
            session.add(user)
            await session.commit()

    # 1. Request Forgot Password with Email
    with patch("app.services.auth_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        resp = await client.post("/api/v1/auth/forgot-password", json={"identifier": "test_reset_email@fieldtrack.test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "destination" in data
        assert data["delivery_channel"] == "EMAIL"
        mock_email.assert_called_once()
        sent_otp = mock_email.call_args[0][1]
        assert len(sent_otp) == 6

    # 2. Verify OTP
    verify_resp = await client.post("/api/v1/auth/verify-otp", json={
        "identifier": "test_reset_email@fieldtrack.test",
        "otp": sent_otp,
    })
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True

    # 3. Reset Password
    reset_resp = await client.post("/api/v1/auth/reset-password", json={
        "identifier": "test_reset_email@fieldtrack.test",
        "otp": sent_otp,
        "new_password": "NewSecurePassword123!",
    })
    assert reset_resp.status_code == 200

    # 4. Old password fails
    fail_login = await client.post("/api/v1/auth/login", json={
        "identifier": "test_reset_email@fieldtrack.test",
        "password": "OldPassword123!",
    })
    assert fail_login.status_code == 401

    # 5. New password succeeds
    success_login = await client.post("/api/v1/auth/login", json={
        "identifier": "test_reset_email@fieldtrack.test",
        "password": "NewSecurePassword123!",
    })
    assert success_login.status_code == 200


@requires_db
@pytest.mark.asyncio
async def test_unified_forgot_password_and_reset_flow_mobile(client: AsyncClient):
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_mobile("9800000002")
        if not user:
            user = User(
                email="test_mobile_user@fieldtrack.test",
                mobile_number="9800000002",
                password_hash=hash_password("OldPassword123!"),
                role=Role.EMPLOYEE,
                is_active=True,
            )
            session.add(user)
            await session.commit()

    # 1. Request Forgot Password with Mobile
    with patch("app.services.auth_service.send_password_reset_sms", new_callable=AsyncMock) as mock_sms:
        mock_sms.return_value = True
        resp = await client.post("/api/v1/auth/forgot-password", json={"identifier": "9800000002"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["delivery_channel"] == "SMS"
        assert "******0002" in data["destination"]
        mock_sms.assert_called_once()
        sent_otp = mock_sms.call_args[0][1]
        assert len(sent_otp) == 6

    # 2. Verify OTP
    verify_resp = await client.post("/api/v1/auth/verify-otp", json={
        "identifier": "9800000002",
        "otp": sent_otp,
    })
    assert verify_resp.status_code == 200

    # 3. Reset Password
    reset_resp = await client.post("/api/v1/auth/reset-password", json={
        "identifier": "9800000002",
        "otp": sent_otp,
        "new_password": "NewMobilePassword123!",
    })
    assert reset_resp.status_code == 200

    # 4. Login with new password and mobile
    success_login = await client.post("/api/v1/auth/login", json={
        "mobile_number": "9800000002",
        "password": "NewMobilePassword123!",
    })
    assert success_login.status_code == 200


@requires_db
@pytest.mark.asyncio
async def test_non_existent_identifier_prevents_enumeration(client: AsyncClient):
    resp = await client.post("/api/v1/auth/forgot-password", json={"identifier": "non_existent_user@fieldtrack.test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["delivery_channel"] == "EMAIL"
    assert "destination" in data
