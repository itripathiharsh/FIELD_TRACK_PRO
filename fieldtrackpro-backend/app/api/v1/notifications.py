"""
Notifications router: REST endpoints for user notifications.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.notification import NotificationCreate, NotificationRead
from app.services.notification_service import notification_service

router = APIRouter(tags=["Notifications"])


@router.get("/notifications/me", response_model=list[NotificationRead])
async def list_my_notifications(
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[NotificationRead]:
    """List notifications for the authenticated user."""
    notifications = await notification_service.list_user_notifications(
        current_user.id, session
    )
    return [NotificationRead.model_validate(n) for n in notifications]


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Mark a notification as read."""
    await notification_service.mark_as_read(notification_id, current_user.id, session)
    return {"status": "ok"}
