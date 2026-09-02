from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.fcm_service import FCMService, fcm_service


@pytest.mark.asyncio
async def test_fcm_zero_tokens_returns_zero():
    service = FCMService()
    success, failure, invalid = await service.send_multicast([], "Title", "Body")
    assert success == 0
    assert failure == 0
    assert invalid == []

    success, failure, invalid = await service.send_multicast(["", "   "], "Title", "Body")
    assert success == 0
    assert failure == 0
    assert invalid == []


@pytest.mark.asyncio
async def test_fcm_unconfigured_firebase_reports_failure_not_false_success():
    service = FCMService()
    # Force _ensure_firebase_app to return False
    with patch.object(service, "_ensure_firebase_app", return_value=False):
        tokens = ["token_1", "token_2", "token_3"]
        success, failure, invalid = await service.send_multicast(
            tokens=tokens,
            title="Visit Assigned",
            body="New visit assigned for today",
        )
        assert success == 0
        assert failure == 3
        assert invalid == []


@pytest.mark.asyncio
async def test_fcm_configured_successful_send():
    service = FCMService()

    mock_resp1 = MagicMock()
    mock_resp1.success = True
    mock_resp2 = MagicMock()
    mock_resp2.success = True

    mock_batch = MagicMock()
    mock_batch.success_count = 2
    mock_batch.failure_count = 0
    mock_batch.responses = [mock_resp1, mock_resp2]

    with patch.object(service, "_ensure_firebase_app", return_value=True):
        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_batch):
            tokens = ["token_1", "token_2"]
            success, failure, invalid = await service.send_multicast(
                tokens=tokens,
                title="Test Title",
                body="Test Body",
                data={"key": "val"},
            )
            assert success == 2
            assert failure == 0
            assert invalid == []


@pytest.mark.asyncio
async def test_fcm_detects_invalid_unregistered_tokens():
    service = FCMService()

    from firebase_admin import messaging

    mock_resp_success = MagicMock()
    mock_resp_success.success = True

    mock_resp_invalid = MagicMock()
    mock_resp_invalid.success = False
    mock_resp_invalid.exception = messaging.UnregisteredError("Requested entity was not found.")

    mock_batch = MagicMock()
    mock_batch.success_count = 1
    mock_batch.failure_count = 1
    mock_batch.responses = [mock_resp_success, mock_resp_invalid]

    with patch.object(service, "_ensure_firebase_app", return_value=True):
        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_batch):
            tokens = ["valid_token_1", "dead_token_2"]
            success, failure, invalid = await service.send_multicast(
                tokens=tokens,
                title="Alert",
                body="Message",
            )
            assert success == 1
            assert failure == 1
            assert "dead_token_2" in invalid


@pytest.mark.asyncio
async def test_fcm_send_to_user_prunes_stale_tokens():
    service = FCMService()
    mock_session = AsyncMock()

    with patch("app.services.device_service.device_service.get_active_tokens_for_user", new=AsyncMock(return_value=["tok_1", "tok_bad"])):
        with patch.object(service, "send_multicast", new=AsyncMock(return_value=(1, 1, ["tok_bad"]))):
            with patch("app.services.device_service.device_service.deactivate_stale_tokens", new=AsyncMock()) as mock_deactivate:
                import uuid
                user_id = uuid.uuid4()
                success_count = await service.send_to_user(
                    user_id=user_id,
                    title="Notice",
                    body="Hello",
                    session=mock_session,
                )
                assert success_count == 1
                mock_deactivate.assert_awaited_once_with(["tok_bad"], mock_session)
