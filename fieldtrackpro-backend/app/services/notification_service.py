"""
Notification service — business logic for notifications and real-time push delivery.
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType

logger = logging.getLogger("fieldtrackpro")

_NOTIFICATION_TITLES: dict[NotificationType, str] = {
    NotificationType.NEW_VISIT: "New Visit Assigned",
    NotificationType.RESCHEDULED: "Visit Rescheduled",
    NotificationType.CANCELLED: "Visit Cancelled",
    NotificationType.REMINDER: "Visit Reminder",
    NotificationType.OVERDUE: "Visit Overdue",
    NotificationType.COMPLETED: "Visit Completed",
    NotificationType.GEO_FAILURE_ALERT: "Geofence Verification Alert",
    NotificationType.GEO_ALERT: "Geofence Alert",
}


class NotificationService:
    """Service managing user notifications and push dispatch."""

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
        """
        Create a new notification in the database and trigger real-time FCM push delivery.
        """
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            message=message,
            visit_id=visit_id,
        )
        if session is not None:
            session.add(notification)
            await session.commit()
            await session.refresh(notification)

            # Trigger FCM Push notification to user's registered devices
            try:
                from app.services.fcm_service import fcm_service

                title = _NOTIFICATION_TITLES.get(notification_type, "FieldTrack Notification")
                data_payload = {
                    "notification_id": str(notification.id),
                    "visit_id": str(visit_id) if visit_id else "",
                    "type": notification_type.value if hasattr(notification_type, "value") else str(notification_type),
                    "title": title,
                    "message": message,
                    "sent_at": notification.sent_at.isoformat() if notification.sent_at else "",
                }

                await fcm_service.send_to_user(
                    user_id=user_id,
                    title=title,
                    body=message,
                    data=data_payload,
                    session=session,
                )
            except Exception as e:
                # Failure in FCM push must never break the persisted database notification
                logger.error(
                    f"Non-fatal error delivering FCM push for notification {notification.id}: {e}",
                    exc_info=True,
                )

        return notification


notification_service = NotificationService()
