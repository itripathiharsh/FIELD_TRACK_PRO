"""
Notifications router: REST endpoints for user notifications.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.notification import NotificationCreate, NotificationRead, UnreadCountResponse
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


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_my_unread_count(
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> UnreadCountResponse:
    """Get the unread notifications count for the authenticated user."""
    count = await notification_service.get_unread_count(current_user.id, session)
    return UnreadCountResponse(unread_count=count)


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Mark a notification as read."""
    await notification_service.mark_as_read(notification_id, current_user.id, session)
    return {"status": "ok"}


@router.patch("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Mark all unread notifications for current user as read."""
    updated = await notification_service.mark_all_read(current_user.id, session)
    return {"status": "ok", "marked_read": updated}


@router.post("/notifications/sweep-missed", dependencies=[Depends(require_role(Role.ADMIN))])
async def trigger_missed_planned_visit_sweep(
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Admin endpoint to manually trigger a sweep of missed planned visits and dispatch warnings."""
    from app.services.visit_analytics_service import sweep_missed_planned_visits
    count = await sweep_missed_planned_visits(session)
    return {"status": "ok", "missed_planned_visits_swept": count}

