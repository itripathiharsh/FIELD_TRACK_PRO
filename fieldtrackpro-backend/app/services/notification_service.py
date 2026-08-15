"""
Notification service — business logic for notifications.
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType

logger = logging.getLogger("fieldtrackpro")


class NotificationService:
    """Service managing user notifications."""

    async def list_user_notifications(
        self, user_id: uuid.UUID, session: AsyncSession
    ) -> Sequence[Notification]:
        """Return all notifications for a user, newest first."""
        result = await session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.sent_at.desc())
        )
        return result.scalars().all()

    async def mark_as_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
    ) -> None:
        """Mark a notification as read. Only the owner can mark it."""
        result = await session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification is not None:
            notification.is_read = True
            await session.commit()

    async def create_notification(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        message: str,
        visit_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            message=message,
            visit_id=visit_id,
        )
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        return notification


notification_service = NotificationService()
