"""
Admin review of check-ins whose location could not be confirmed automatically, and the employee's request for
admin verification. Nothing here ever touches the outlet's coordinates.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.checkin_review import CheckInReview, CheckInReviewKind, CheckInReviewStatus
from app.models.customer import Customer
from app.models.notification import NotificationType
from app.models.user import User
from app.models.visit import Visit, VisitStatus
from app.schemas.checkin_review import VerificationRequestCreate
from app.services import visit_service
from app.services.checkin_geo import evaluate_checkin_fix
from app.services.customer_service import get_customer

logger = logging.getLogger("fieldtrackpro")

MAX_REQUESTS_PER_VISIT = 3
MAX_REQUESTS_PER_EMPLOYEE_PER_HOUR = 5
MIN_SECONDS_BETWEEN_REQUESTS = 60


def _err(status: int, code: str, detail: str) -> BaseAPIException:
    return BaseAPIException(status_code=status, detail=detail, error_code=code)


async def _notify(session: AsyncSession, user_id: uuid.UUID, title: str, message: str) -> None:
    try:
        from app.services.notification_service import notification_service

        await notification_service.create_notification(
            user_id=user_id, notification_type=NotificationType.REMINDER, title=title, message=message, session=session
        )
    except Exception as exc:  # pragma: no cover - best effort, never undoes a decision
        logger.warning("event=checkin_review_notify_failed error=%s", type(exc).__name__)


async def create_verification_request(
    session: AsyncSession, current_user: User, data: VerificationRequestCreate
) -> CheckInReview:
    visit = await visit_service.get_visit_for_user(data.visit_id, current_user, session)
    if visit.status not in (VisitStatus.PENDING, VisitStatus.FLAGGED):
        raise _err(409, "VISIT_NOT_CHECKABLE", "This visit is not waiting for a check-in.")
    customer: Customer = await get_customer(visit.customer_id, session)
    if customer.location is None:
        raise _err(422, "OUTLET_LOCATION_NOT_CONFIGURED", "Outlet location is not configured.")

    now = datetime.now(timezone.utc)

    # --- rate limits (cheap checks first) ---
    total_for_visit = (await session.execute(
        select(func.count(CheckInReview.id)).where(
            CheckInReview.visit_id == visit.id, CheckInReview.kind == CheckInReviewKind.VERIFICATION_REQUEST)
    )).scalar_one()
    if total_for_visit >= MAX_REQUESTS_PER_VISIT:
        raise _err(429, "VERIFICATION_REQUEST_LIMIT", "Too many verification requests for this visit. Please contact your administrator.")
    pending = (await session.execute(
        select(CheckInReview.id).where(
            CheckInReview.visit_id == visit.id, CheckInReview.kind == CheckInReviewKind.VERIFICATION_REQUEST,
            CheckInReview.status == CheckInReviewStatus.PENDING).limit(1)
    )).scalar_one_or_none()
    if pending is not None:
        raise _err(409, "VERIFICATION_ALREADY_PENDING", "A verification request for this visit is already waiting for an administrator.")
    recent = (await session.execute(
        select(CheckInReview.received_at).where(
            CheckInReview.requested_by == current_user.id, CheckInReview.kind == CheckInReviewKind.VERIFICATION_REQUEST,
            CheckInReview.received_at >= now - timedelta(hours=1)).order_by(CheckInReview.received_at.desc())
    )).scalars().all()
    if len(recent) >= MAX_REQUESTS_PER_EMPLOYEE_PER_HOUR:
        raise _err(429, "VERIFICATION_REQUEST_LIMIT", "Too many verification requests in the last hour. Please try again later.")
    if recent and (now - recent[0]).total_seconds() < MIN_SECONDS_BETWEEN_REQUESTS:
        raise _err(429, "VERIFICATION_REQUEST_TOO_SOON", "Please wait a minute before requesting verification again.")

    # --- the same decision as check-in, live fixes only ---
    ev = await evaluate_checkin_fix(
        session, customer, latitude=data.latitude, longitude=data.longitude, accuracy_m=data.accuracy_m,
        is_mock=data.is_mock_location, captured_at=data.captured_at, allow_offline=False, now=now,
    )
    if not ev.needs_verification:
        if ev.accepted:
            raise _err(409, "CHECKIN_ALLOWED", "Your location is good enough: check in normally.")
        raise _err(422, ev.error_code or "GEO_VERIFICATION_FAILED", f"Verification cannot be requested: {ev.reason}")

    review = CheckInReview(
        visit_id=visit.id, customer_id=customer.id, employee_id=visit.employee_id, requested_by=current_user.id,
        kind=CheckInReviewKind.VERIFICATION_REQUEST, decision=ev.label, distance_m=ev.distance_m,
        accuracy_m=ev.accuracy_m, pin_accuracy_m=ev.pin_accuracy_m,
        device_location=f"SRID=4326;POINT({data.longitude} {data.latitude})",
        device_captured_at=data.captured_at, received_at=now, note=(data.note or None),
    )
    try:
        async with session.begin_nested():
            session.add(review)
    except IntegrityError:
        raise _err(409, "VERIFICATION_ALREADY_PENDING", "A verification request for this visit is already waiting for an administrator.")
    await session.commit()
    logger.info("event=checkin_verification_requested visit_id=%s review_id=%s distance_m=%s accuracy_m=%s",
                visit.id, review.id, ev.distance_m, ev.accuracy_m)
    return review


async def list_reviews(session: AsyncSession, status: str | None, limit: int = 100, offset: int = 0):
    stmt = select(CheckInReview).order_by(CheckInReview.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(CheckInReview.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def _load_pending(session: AsyncSession, review_id: uuid.UUID) -> CheckInReview:
    review = (await session.execute(
        select(CheckInReview).where(CheckInReview.id == review_id).with_for_update()
    )).scalar_one_or_none()
    if review is None:
        raise _err(404, "CHECKIN_REVIEW_NOT_FOUND", "Review not found.")
    if review.status != CheckInReviewStatus.PENDING:
        raise _err(409, "CHECKIN_REVIEW_NOT_PENDING", "This review has already been decided.")
    return review


async def approve(session: AsyncSession, admin: User, review_id: uuid.UUID, note: str | None) -> CheckInReview:
    review = await _load_pending(session, review_id)
    visit = (await session.execute(select(Visit).where(Visit.id == review.visit_id).with_for_update(of=Visit))).scalar_one()
    if review.kind == CheckInReviewKind.VERIFICATION_REQUEST:
        if visit.status not in (VisitStatus.PENDING, VisitStatus.FLAGGED):
            raise _err(409, "VISIT_NOT_CHECKABLE", "The visit has already moved on; the request can no longer be approved.")
        visit.status = VisitStatus.IN_PROGRESS
        visit.check_in_at = review.device_captured_at or review.received_at
        visit.check_in_received_at = review.received_at
        visit.check_in_location = review.device_location
        visit.check_in_confidence = "ADMIN_VERIFIED"
    else:
        visit.check_in_confidence = "ADMIN_CONFIRMED"
    review.status = CheckInReviewStatus.APPROVED
    review.reviewed_by = admin.id
    review.reviewed_at = datetime.now(timezone.utc)
    review.review_note = note
    session.add_all([visit, review])
    await session.commit()
    await _notify(session, review.requested_by, "Check-in approved", "An administrator verified your check-in location.")
    return review


async def reject(session: AsyncSession, admin: User, review_id: uuid.UUID, reason: str) -> CheckInReview:
    review = await _load_pending(session, review_id)
    visit = (await session.execute(select(Visit).where(Visit.id == review.visit_id).with_for_update(of=Visit))).scalar_one()
    if review.kind != CheckInReviewKind.VERIFICATION_REQUEST and visit.status in (VisitStatus.IN_PROGRESS, VisitStatus.COMPLETED):
        # A conditional/offline check-in that an admin does not accept: keep the record, mark the visit for follow-up.
        visit.status = VisitStatus.FLAGGED
        session.add(visit)
    review.status = CheckInReviewStatus.REJECTED
    review.reviewed_by = admin.id
    review.reviewed_at = datetime.now(timezone.utc)
    review.review_note = reason
    session.add(review)
    await session.commit()
    await _notify(session, review.requested_by, "Check-in not verified", f"An administrator did not verify your check-in: {reason}")
    return review
