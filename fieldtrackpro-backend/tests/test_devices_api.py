"""
Unit and API tests for device token registration, unregistration, and listing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps.auth import _get_user_from_token
from app.main import app
from app.models.user import Role, User
from app.models.user_device import UserDevice
from app.services.device_service import DeviceService


@pytest.mark.asyncio
async def test_device_service_register_new_device():
    """Registering a new token creates an active UserDevice record."""
    service = DeviceService()
    session = AsyncMock()

    # Mock no existing token found
    exec_result_empty = MagicMock()
    exec_result_empty.scalar_one_or_none.return_value = None
    session.execute.return_value = exec_result_empty

    user_id = uuid.uuid4()
    fcm_token = "fcm_test_token_1234567890_abcdef"

    device = await service.register_device(
        user_id=user_id,
        fcm_token=fcm_token,
        device_type="ANDROID",
        device_id="device_hardware_001",
        session=session,
    )

    assert device.user_id == user_id
    assert device.fcm_token == fcm_token
    assert device.device_type == "ANDROID"
    assert device.device_id == "device_hardware_001"
    assert device.is_active is True
    session.add.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_device_service_register_existing_token_updates_user():
    """Registering an existing token (e.g. user switch on same phone) updates user_id and activates."""
    service = DeviceService()
    session = AsyncMock()

    old_user_id = uuid.uuid4()
    new_user_id = uuid.uuid4()
    fcm_token = "fcm_test_token_1234567890_abcdef"

    existing_device = UserDevice(
        id=uuid.uuid4(),
        user_id=old_user_id,
        fcm_token=fcm_token,
        device_type="ANDROID",
        is_active=False,
    )

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = existing_device
    session.execute.return_value = exec_result

    device = await service.register_device(
        user_id=new_user_id,
        fcm_token=fcm_token,
        device_type="ANDROID",
        session=session,
    )

    assert device.user_id == new_user_id
    assert device.is_active is True
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_device_service_unregister_device():
    """Unregistering a device token sets is_active to False."""
    service = DeviceService()
    session = AsyncMock()

    user_id = uuid.uuid4()
    fcm_token = "fcm_test_token_to_unregister_123"

    existing_device = UserDevice(
        id=uuid.uuid4(),
        user_id=user_id,
        fcm_token=fcm_token,
        is_active=True,
    )

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = existing_device
    session.execute.return_value = exec_result

    unregistered = await service.unregister_device(
        fcm_token=fcm_token,
        user_id=user_id,
        session=session,
    )

    assert unregistered is True
    assert existing_device.is_active is False
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_api_register_device_endpoint():
    """POST /api/v1/devices/register successfully registers a device for the logged-in user."""
    user_id = uuid.uuid4()
    fake_user = User(
        id=user_id,
        email="emp@example.com",
        role=Role.EMPLOYEE,
        is_active=True,
    )

    fake_device = UserDevice(
        id=uuid.uuid4(),
        user_id=user_id,
        fcm_token="fcm_valid_sample_token_for_api_test",
        device_type="ANDROID",
        device_id="hardware_id_test_99",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    app.dependency_overrides[_get_user_from_token] = lambda: fake_user
    try:
        with patch("app.services.device_service.device_service.register_device", new=AsyncMock(return_value=fake_device)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/devices/register",
                    json={
                        "fcm_token": "fcm_valid_sample_token_for_api_test",
                        "device_type": "ANDROID",
                        "device_id": "hardware_id_test_99",
                    },
                    headers={"Authorization": "Bearer mock_token"},
                )

                assert resp.status_code == 200, resp.text
                data = resp.json()
                assert data["fcm_token"] == "fcm_valid_sample_token_for_api_test"
                assert data["device_type"] == "ANDROID"
                assert data["is_active"] is True
    finally:
        app.dependency_overrides.pop(_get_user_from_token, None)


@pytest.mark.asyncio
async def test_api_unregister_device_endpoint():
    """POST /api/v1/devices/unregister deactivates the device token."""
    user_id = uuid.uuid4()
    fake_user = User(
        id=user_id,
        email="emp@example.com",
        role=Role.EMPLOYEE,
        is_active=True,
    )

    app.dependency_overrides[_get_user_from_token] = lambda: fake_user
    try:
        with patch("app.services.device_service.device_service.unregister_device", new=AsyncMock(return_value=True)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/devices/unregister",
                    json={"fcm_token": "fcm_valid_sample_token_for_api_test"},
                    headers={"Authorization": "Bearer mock_token"},
                )

                assert resp.status_code == 200, resp.text
                data = resp.json()
                assert data["status"] == "ok"
                assert data["unregistered"] is True
    finally:
        app.dependency_overrides.pop(_get_user_from_token, None)


@pytest.mark.asyncio
async def test_api_list_my_devices_endpoint():
    """GET /api/v1/devices/me lists registered devices for current user."""
    user_id = uuid.uuid4()
    fake_user = User(
        id=user_id,
        email="emp@example.com",
        role=Role.EMPLOYEE,
        is_active=True,
    )

    fake_devices = [
        UserDevice(
            id=uuid.uuid4(),
            user_id=user_id,
            fcm_token="fcm_token_device_1",
            device_type="ANDROID",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    app.dependency_overrides[_get_user_from_token] = lambda: fake_user
    try:
        with patch("app.services.device_service.device_service.list_user_devices", new=AsyncMock(return_value=fake_devices)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/v1/devices/me",
                    headers={"Authorization": "Bearer mock_token"},
                )

                assert resp.status_code == 200, resp.text
                data = resp.json()
                assert len(data) == 1
                assert data[0]["fcm_token"] == "fcm_token_device_1"
    finally:
        app.dependency_overrides.pop(_get_user_from_token, None)
