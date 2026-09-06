"""
Notification service — business logic for notifications and real-time push delivery.
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import ForbiddenException, ResourceNotFoundException
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
    NotificationType.PLANNED_VISIT_MISSED: "Planned Visit Missed",
    NotificationType.EMPLOYEE_SCHEDULE_CHANGED: "Employee Schedule Changed",
    NotificationType.PLANNED_VISIT_CANCELLED: "Planned Visit Cancelled",
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

    async def get_unread_count(
        self, user_id: uuid.UUID, session: AsyncSession
    ) -> int:
        """Return the count of unread notifications for a user."""
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def mark_as_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
    ) -> None:
        """Mark a notification as read. Only the owner can mark it."""
        result = await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            raise ResourceNotFoundException("Notification not found")
        if notification.user_id != user_id:
            raise ForbiddenException("Cannot mark another user's notification as read")

        notification.is_read = True
        await session.commit()

    async def mark_all_read(
        self, user_id: uuid.UUID, session: AsyncSession
    ) -> int:
        """Mark all unread notifications for a user as read."""
        from sqlalchemy import update
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        count = result.rowcount
        await session.commit()
        return count

    async def create_notification(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        message: str,
        title: str | None = None,
        visit_id: uuid.UUID | None = None,
        planned_visit_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> Notification:
        """
        Create a new notification in the database and trigger real-time FCM push delivery.
        """
        resolved_title = title or _NOTIFICATION_TITLES.get(notification_type, "FieldTrack Notification")
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=resolved_title,
            message=message,
            visit_id=visit_id,
            planned_visit_id=planned_visit_id,
        )
        if session is not None:
            session.add(notification)
            await session.commit()
            await session.refresh(notification)

            # Trigger FCM Push notification to user's registered devices
            try:
                from app.services.fcm_service import fcm_service

                data_payload = {
                    "notification_id": str(notification.id),
                    "visit_id": str(visit_id) if visit_id else "",
                    "planned_visit_id": str(planned_visit_id) if planned_visit_id else "",
                    "type": notification_type.value if hasattr(notification_type, "value") else str(notification_type),
                    "title": resolved_title,
                    "message": message,
                    "sent_at": notification.sent_at.isoformat() if notification.sent_at else "",
                }

                await fcm_service.send_to_user(
                    user_id=user_id,
                    title=resolved_title,
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

    async def create_planning_notification(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        message: str,
        title: str | None = None,
        planned_visit_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> Notification | None:
        """
        Create a planning notification with duplicate protection.
        If a notification already exists for (user_id, planned_visit_id, notification_type),
        returns the existing notification without creating a duplicate.
        """
        if session is not None and planned_visit_id is not None:
            stmt = select(Notification).where(
                Notification.user_id == user_id,
                Notification.planned_visit_id == planned_visit_id,
                Notification.type == notification_type,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                logger.debug(
                    "Duplicate planning notification skipped: user_id=%s pv_id=%s type=%s",
                    user_id,
                    planned_visit_id,
                    notification_type,
                )
                return existing

        return await self.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            message=message,
            title=title,
            planned_visit_id=planned_visit_id,
            session=session,
        )

    async def create_planning_notifications_bulk(
        self,
        recipients: list[tuple[uuid.UUID, str, str]],
        notification_type: NotificationType,
        planned_visit_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[Notification]:
        """
        Bulk-insert planning notifications for multiple recipients in a single transaction.

        ``recipients`` is a list of ``(user_id, title, message)`` tuples.

        Duplicate protection is performed with ONE query covering all recipients.
        The method stages all new ``Notification`` objects via ``session.add_all`` but
        does NOT call ``session.commit()`` — the caller must commit after this returns.
        FCM push delivery is intentionally NOT performed here; the caller is responsible
        for firing push notifications **after** the transaction commits, so that a slow
        or unavailable FCM service cannot delay or roll back database persistence.

        Returns the list of newly staged ``Notification`` objects (pre-commit).
        """
        if not recipients or planned_visit_id is None:
            return []

        resolved_title_default = _NOTIFICATION_TITLES.get(notification_type, "FieldTrack Notification")
        recipient_user_ids = [uid for uid, _, _ in recipients]

        # ONE query to find all already-existing notifications for these recipients + this pv + type
        existing_stmt = select(Notification.user_id).where(
            Notification.user_id.in_(recipient_user_ids),
            Notification.planned_visit_id == planned_visit_id,
            Notification.type == notification_type,
        )
        already_notified: set[uuid.UUID] = set(
            (await session.execute(existing_stmt)).scalars().all()
        )

        new_notifications: list[Notification] = []
        for user_id, title, message in recipients:
            if user_id in already_notified:
                logger.debug(
                    "Bulk duplicate skipped: user_id=%s pv_id=%s type=%s",
                    user_id,
                    planned_visit_id,
                    notification_type,
                )
                continue
            resolved_title = title or resolved_title_default
            new_notifications.append(
                Notification(
                    user_id=user_id,
                    type=notification_type,
                    title=resolved_title,
                    message=message,
                    planned_visit_id=planned_visit_id,
                )
            )

        if new_notifications:
            session.add_all(new_notifications)
            logger.debug(
                "Bulk staging %d planning notifications (type=%s, pv_id=%s)",
                len(new_notifications),
                notification_type,
                planned_visit_id,
            )

        return new_notifications


notification_service = NotificationService()

