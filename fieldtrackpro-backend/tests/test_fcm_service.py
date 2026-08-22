"""
Unit tests for FCM Push Notification Service and NotificationService push trigger integration.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.notification import Notification, NotificationType
from app.services.fcm_service import FCMService, fcm_service
from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_fcm_send_multicast_dry_run():
    """When Firebase credentials are not provided, FCMService operates in dry-run mode."""
    service = FCMService()
    # Force dry-run mode by mocking _ensure_firebase_app to False
    with patch.object(service, "_ensure_firebase_app", return_value=False):
        tokens = ["token_1", "token_2", "token_3"]
        success, failure, invalid = await service.send_multicast(
            tokens=tokens,
            title="Test Title",
            body="Test Body",
            data={"notification_id": str(uuid.uuid4()), "visit_id": str(uuid.uuid4())},
        )

        assert success == 3
        assert failure == 0
        assert invalid == []


@pytest.mark.asyncio
async def test_fcm_send_multicast_empty_tokens():
    """Empty token list returns 0 count immediately without error."""
    service = FCMService()
    success, failure, invalid = await service.send_multicast(
        tokens=[],
        title="Test",
        body="Body",
    )
    assert success == 0
    assert failure == 0
    assert invalid == []


@pytest.mark.asyncio
async def test_fcm_send_to_user_fetches_tokens_and_dispatches():
    """send_to_user retrieves active tokens from device_service and calls send_multicast."""
    service = FCMService()
    user_id = uuid.uuid4()
    session = AsyncMock()

    active_tokens = ["fcm_token_device_a", "fcm_token_device_b"]

    with patch("app.services.device_service.device_service.get_active_tokens_for_user", new=AsyncMock(return_value=active_tokens)), \
         patch.object(service, "send_multicast", new=AsyncMock(return_value=(2, 0, []))) as mock_multicast:

        count = await service.send_to_user(
            user_id=user_id,
            title="Visit Assigned",
            body="You have a new visit",
            data={"type": "NEW_VISIT"},
            session=session,
        )

        assert count == 2
        mock_multicast.assert_called_once_with(
            tokens=active_tokens,
            title="Visit Assigned",
            body="You have a new visit",
            data={"type": "NEW_VISIT"},
        )


@pytest.mark.asyncio
async def test_fcm_send_to_user_deactivates_stale_tokens():
    """When FCM returns invalid/stale tokens, send_to_user deactivates them via device_service."""
    service = FCMService()
    user_id = uuid.uuid4()
    session = AsyncMock()

    active_tokens = ["valid_token_1", "dead_token_2"]
    invalid_tokens = ["dead_token_2"]

    with patch("app.services.device_service.device_service.get_active_tokens_for_user", new=AsyncMock(return_value=active_tokens)), \
         patch.object(service, "send_multicast", new=AsyncMock(return_value=(1, 1, invalid_tokens))), \
         patch("app.services.device_service.device_service.deactivate_stale_tokens", new=AsyncMock()) as mock_deactivate:

        count = await service.send_to_user(
            user_id=user_id,
            title="Reminder",
            body="Visit Reminder",
            session=session,
        )

        assert count == 1
        mock_deactivate.assert_called_once_with(invalid_tokens, session)


@pytest.mark.asyncio
async def test_notification_service_create_notification_triggers_fcm():
    """NotificationService.create_notification saves DB record and invokes FCM push."""
    service = NotificationService()
    session = AsyncMock()
    user_id = uuid.uuid4()
    visit_id = uuid.uuid4()

    with patch("app.services.fcm_service.fcm_service.send_to_user", new=AsyncMock(return_value=1)) as mock_fcm:
        notif = await service.create_notification(
            user_id=user_id,
            notification_type=NotificationType.NEW_VISIT,
            message="New Visit Assigned: Store A",
            visit_id=visit_id,
            session=session,
        )

        assert notif.user_id == user_id
        assert notif.type == NotificationType.NEW_VISIT
        assert notif.message == "New Visit Assigned: Store A"
        assert notif.visit_id == visit_id

        session.add.assert_called_once()
        session.commit.assert_called_once()

        mock_fcm.assert_called_once()
        call_kwargs = mock_fcm.call_args.kwargs
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["title"] == "New Visit Assigned"
        assert call_kwargs["body"] == "New Visit Assigned: Store A"
        assert call_kwargs["data"]["visit_id"] == str(visit_id)
        assert call_kwargs["data"]["type"] == "NEW_VISIT"
