"""
Visit service â€” refactored to use VisitRepository and GeoLogRepository.
Follows: Router â†’ Service â†’ Repository â†’ DB
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import os

from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException, DuplicateVisitException
from app.models.form_template import FormStatus, FormTemplate
from app.models.geo_verification_log import GeoVerificationLog, GeoVerificationType
from app.models.notification import NotificationType
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus, VisitType
from app.repositories.geo_log_repo import GeoLogRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.visit import AdHocVisitCreate, CheckInRequest, CheckOutRequest, VisitCreate
from app.services import notification_service
from app.services.customer_service import get_customer, verify_geo_proximity
from app.services.employee_service import get_employee, get_employee_by_user_id
from app.services.visit_state_machine import assert_valid_transition, is_terminal

logger = logging.getLogger("fieldtrackpro")


async def _validate_required_form(required_form_id: uuid.UUID | None, session: AsyncSession) -> None:
    """
    A visit may only require a PUBLISHED template - a DRAFT isn't ready for
    an employee to see, and an archived one is no longer meant for new work
    (existing visits/submissions against an archived form are unaffected;
    this only gates assigning one to a visit going forward).
    """
    if required_form_id is None:
        return
    result = await session.execute(select(FormTemplate).where(FormTemplate.id == required_form_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise BaseAPIException(status_code=404, detail="Form template not found", error_code="FORM_NOT_FOUND")
    if template.status != FormStatus.PUBLISHED:
        raise BaseAPIException(
            status_code=400,
            detail="Only a published form template can be required for a visit",
            error_code="FORM_NOT_PUBLISHED",
        )

# Number of geo-verification failures before auto-flagging
GEO_FAILURE_THRESHOLD = 3

# Minimum gap (in minutes) required between two active visits for the same employee.
# Configurable via environment variable VISIT_CONFLICT_WINDOW_MINUTES (default 60).
VISIT_CONFLICT_WINDOW_MINUTES: int = int(os.environ.get("VISIT_CONFLICT_WINDOW_MINUTES", "60"))


async def _resolve_employee_scope(
    current_user: User, session: AsyncSession
) -> uuid.UUID | None:
    """
    Return the employee id a caller is restricted to, or None for unrestricted.

    FT-002: ADMIN sees everything; EMPLOYEE is confined to their own records.
    Centralised here so every visit-scoped operation shares one rule instead of
    re-implementing it (the audit found the same check copy-pasted four times,
    and absent entirely from the two read paths).
    """
    if current_user.role == Role.ADMIN:
        return None
    employee = await get_employee_by_user_id(current_user.id, session)
    return employee.id


async def assert_visit_access(
    visit: Visit, current_user: User, session: AsyncSession
) -> Visit:
    """
    Enforce object-level ownership on a visit (Security Design section 2).

    A valid EMPLOYEE token is not sufficient authorisation: the visit must also
    belong to that employee.
    """
    scope = await _resolve_employee_scope(current_user, session)
    if scope is not None and visit.employee_id != scope:
        raise BaseAPIException(
            status_code=403,
            detail="You are not assigned to this visit",
            error_code="VISIT_NOT_ASSIGNED",
        )
    return visit


async def _check_duplicate_visit(
    employee_id: uuid.UUID,
    scheduled_at: "datetime",
    session: AsyncSession,
    *,
    exclude_visit_id: uuid.UUID | None = None,
) -> None:
    """
    Raise DuplicateVisitException when *employee_id* already has a
    non-terminal visit within VISIT_CONFLICT_WINDOW_MINUTES of *scheduled_at*.

    This is called inside the same unit-of-work as the INSERT so that the
    check and the write are effectively atomic at the application layer.
    The database-level partial unique index (h1i2j3k4l5m6 migration) catches
    any race condition that slips through concurrent requests.
    """
    repo = VisitRepository(session)
    conflict = await repo.find_conflicting_visit(
        employee_id=employee_id,
        scheduled_at=scheduled_at,
        window_minutes=VISIT_CONFLICT_WINDOW_MINUTES,
        exclude_visit_id=exclude_visit_id,
    )
    if conflict is not None:
        # Build a human-readable message that tells the admin exactly which
        # existing visit causes the conflict.
        conflict_time = conflict.scheduled_at.strftime("%Y-%m-%d %H:%M UTC")
        conflict_customer = conflict.customer_name if conflict.customer_name else str(conflict.customer_id)
        employee_name = conflict.employee_name if conflict.employee_name else str(employee_id)
        raise DuplicateVisitException(
            detail=(
                f"Scheduling conflict: {employee_name} already has a "
                f"{conflict.status.value} visit to '{conflict_customer}' at "
                f"{conflict_time} (visit {conflict.id}). "
                f"Visits must be at least {VISIT_CONFLICT_WINDOW_MINUTES} minutes apart."
            )
        )


async def create_visit(data: VisitCreate, created_by: uuid.UUID, session: AsyncSession) -> Visit:
    """
    Admin: schedule a visit.

    FT-006: the customer and employee are validated up front. Previously an
    unknown id reached the database and surfaced as an unhandled
    ForeignKeyViolation (HTTP 500) instead of a meaningful 404.
    """
    from app.services.employee_service import get_employee
    from app.services.notification_service import notification_service
    from app.models.notification import NotificationType

    customer = await get_customer(data.customer_id, session)
    employee = await get_employee(data.employee_id, session)
    await _validate_required_form(data.required_form_id, session)

    # Duplicate visit guard — must run before repo.add() inside the same
    # unit-of-work so the check-then-insert is effectively atomic.
    await _check_duplicate_visit(data.employee_id, data.scheduled_at, session)

    repo = VisitRepository(session)
    visit = Visit(
        customer_id=data.customer_id,
        employee_id=data.employee_id,
        scheduled_at=data.scheduled_at,
        created_by=created_by,
        status=VisitStatus.PENDING,
        visit_type=data.visit_type or VisitType.PLANNED,
        adhoc_reason=data.adhoc_reason,
        adhoc_notes=data.adhoc_notes,
        required_form_id=data.required_form_id,
    )
    await repo.add(visit)
    await repo.commit()
    full_visit = await repo.get_full(visit.id)

    req_id = get_current_request_id()
    logger.info(
        "event=visit_create result=success request_id=%s visit_id=%s employee_id=%s customer_id=%s visit_type=%s",
        req_id,
        visit.id,
        visit.employee_id,
        visit.customer_id,
        visit.visit_type.value if hasattr(visit.visit_type, "value") else str(visit.visit_type),
    )

    # Notify employee of newly assigned visit
    try:
        if employee and employee.user_id:
            time_str = data.scheduled_at.strftime("%I:%M %p")
            await notification_service.create_notification(
                user_id=employee.user_id,
                notification_type=NotificationType.NEW_VISIT,
                message=f"New Visit Assigned: {customer.name} at {time_str}",
                visit_id=visit.id,
                session=session,
            )
    except Exception as e:
        logger.warning(f"Failed to create new visit notification: {e}")

    return full_visit


async def create_adhoc_visit(
    data: AdHocVisitCreate,
    current_user: User,
    session: AsyncSession,
) -> Visit:
    """
    Employee / Admin: Initiate an off-beat / ad-hoc visit to a customer.
    If the customer already has a pending planned visit for today with this employee,
    that planned visit is returned.
    Otherwise, a new visit is created with visit_type = AD_HOC, adhoc_reason, and adhoc_notes.
    """
    customer = await get_customer(data.customer_id, session)

    if current_user.role == Role.ADMIN:
        try:
            employee = await get_employee_by_user_id(current_user.id, session)
        except BaseAPIException:
            from app.models.employee import Employee
            first_emp = (await session.execute(select(Employee).limit(1))).scalar_one_or_none()
            if not first_emp:
                raise BaseAPIException(status_code=400, detail="No employee profile available to assign ad-hoc visit")
            employee = first_emp
    else:
        employee = await get_employee_by_user_id(current_user.id, session)

    scheduled_at = data.scheduled_at or datetime.now(timezone.utc)
    await _validate_required_form(data.required_form_id, session)

    repo = VisitRepository(session)
    from app.core.datetime_utils import get_ist_today_range
    start_utc, end_utc = get_ist_today_range()

    req_id = get_current_request_id()

    # Check if there is already a pending planned visit for today for this customer and employee
    existing_visits_stmt = (
        select(Visit)
        .where(
            Visit.employee_id == employee.id,
            Visit.customer_id == customer.id,
            Visit.scheduled_at >= start_utc,
            Visit.scheduled_at <= end_utc,
            Visit.status == VisitStatus.PENDING,
        )
        .order_by(Visit.scheduled_at.asc())
        .limit(1)
    )
    existing_pending = (await session.execute(existing_visits_stmt)).scalar_one_or_none()
    if existing_pending is not None:
        logger.info(
            "event=visit_adhoc_matched_planned request_id=%s customer_id=%s planned_visit_id=%s employee_id=%s",
            req_id,
            customer.id,
            existing_pending.id,
            employee.id,
        )
        return await repo.get_full(existing_pending.id)

    # Create new ad-hoc visit
    visit = Visit(
        customer_id=customer.id,
        employee_id=employee.id,
        scheduled_at=scheduled_at,
        created_by=current_user.id,
        status=VisitStatus.PENDING,
        visit_type=VisitType.AD_HOC,
        adhoc_reason=data.adhoc_reason.strip(),
        adhoc_notes=data.adhoc_notes.strip() if data.adhoc_notes else None,
        required_form_id=data.required_form_id,
    )
    await repo.add(visit)
    await repo.commit()
    logger.info(
        "event=visit_adhoc_created request_id=%s visit_id=%s employee_id=%s customer_id=%s reason=%s",
        req_id,
        visit.id,
        employee.id,
        customer.id,
        data.adhoc_reason,
    )
    return await repo.get_full(visit.id)


async def get_visit(visit_id: uuid.UUID, session: AsyncSession) -> Visit:
    """Load a visit without authorisation. Callers must enforce access."""
    repo = VisitRepository(session)
    visit = await repo.get_full(visit_id)
    if visit is None:
        raise BaseAPIException(status_code=404, detail="Visit not found", error_code="VISIT_NOT_FOUND")
    return visit


async def get_visit_for_user(
    visit_id: uuid.UUID, current_user: User, session: AsyncSession
) -> Visit:
    """FT-002: load a visit and enforce object-level ownership."""
    visit = await get_visit(visit_id, session)
    return await assert_visit_access(visit, current_user, session)


async def list_visits(
    session: AsyncSession,
    current_user: User,
    employee_id: uuid.UUID | None = None,
    status: list[VisitStatus] | VisitStatus | None = None,
    territory_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    search: str | None = None,
    sort_order: str = "desc",
    visit_type: VisitType | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Visit], int]:
    """
    List visits, scoped to the caller.

    FT-002: an EMPLOYEE is confined to their own visits regardless of the
    `employee_id` filter they supply, so the filter cannot be used to enumerate
    colleagues' schedules and customer coordinates.
    """
    scope = await _resolve_employee_scope(current_user, session)
    if scope is not None:
        employee_id = scope

    repo = VisitRepository(session)
    return await repo.list_filtered_paginated(
        employee_id=employee_id,
        status=status,
        territory_id=territory_id,
        area_id=area_id,
        from_date=from_date,
        to_date=to_date,
        search=search,
        sort_order=sort_order,
        visit_type=visit_type,
        skip=skip,
        limit=limit,
    )


async def get_my_today_visits(
    current_user: User,
    session: AsyncSession,
    status: list[VisitStatus] | VisitStatus | None = None,
    search: str | None = None,
    visit_type: VisitType | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Visit], int]:
    """
    Employee: returns today's scheduled visits for the authenticated employee in IST / local timezone (+05:30)
    with optional status filtering, search, and pagination.
    """
    employee = await get_employee_by_user_id(current_user.id, session)
    repo = VisitRepository(session)

    from app.core.datetime_utils import get_ist_today_range
    start_utc, end_utc = get_ist_today_range()

    return await repo.list_filtered_paginated(
        employee_id=employee.id,
        status=status,
        from_date=start_utc,
        to_date=end_utc,
        search=search,
        sort_order="asc",
        visit_type=visit_type,
        skip=skip,
        limit=limit,
    )


async def check_in(
    visit_id: uuid.UUID,
    data: CheckInRequest,
    current_user: User,
    session: AsyncSession,
) -> Visit:
    from app.services.customer_service import verify_device_against_customer

    req_id = get_current_request_id()
    visit = await get_visit_for_user(visit_id, current_user, session)

    # Idempotency: if key matches any previous check-in attempt, replay the exact outcome
    if data.idempotency_key:
        geo_repo = GeoLogRepository(session)
        existing_log = await geo_repo.get_by_idempotency_key(visit.id, data.idempotency_key)
        if existing_log is not None:
            if not existing_log.is_valid:
                logger.warning(
                    "event=visit_checkin result=rejected reason=%s idempotency_replay=true request_id=%s visit_id=%s",
                    existing_log.failure_reason,
                    req_id,
                    visit.id,
                )
                raise BaseAPIException(
                    status_code=422,
                    detail=f"Check-in failed: {existing_log.failure_reason}",
                    error_code="GEO_VERIFICATION_FAILED",
                )
            logger.info("event=visit_checkin result=success idempotency_replay=true request_id=%s visit_id=%s", req_id, visit.id)
            return visit

    assert_valid_transition(visit.status, VisitStatus.IN_PROGRESS)

    customer = await get_customer(visit.customer_id, session)
    if customer.location is None:
        logger.warning(
            "event=visit_checkin result=rejected reason=OUTLET_LOCATION_NOT_CONFIGURED request_id=%s visit_id=%s customer_id=%s",
            req_id,
            visit.id,
            visit.customer_id,
        )
        raise BaseAPIException(
            status_code=422,
            detail="Outlet location is not configured.",
            error_code="OUTLET_LOCATION_NOT_CONFIGURED",
        )

    # FT-004: PostGIS measures the distance from the stored geography.
    geo_res = await verify_device_against_customer(
        customer,
        session,
        device_lat=data.latitude,
        device_lng=data.longitude,
        accuracy_m=data.accuracy_m,
        is_mock_location=data.is_mock_location,
        captured_at=data.captured_at,
    )

    # Log the verification attempt (success or failure) - insert-only audit.
    geo_repo = GeoLogRepository(session)
    log = GeoVerificationLog(
        visit_id=visit.id,
        verification_type=GeoVerificationType.CHECK_IN,
        device_location=f"SRID=4326;POINT({data.longitude} {data.latitude})",
        distance_from_customer_m=geo_res.distance_m,
        is_valid=geo_res.is_valid,
        failure_reason=geo_res.failure_reason,
        idempotency_key=data.idempotency_key,
    )
    await geo_repo.add(log)

    if not geo_res.is_valid:
        # Check if failure threshold reached — auto-flag visit
        fail_count = await geo_repo.count_failed_for_visit(visit.id)
        if fail_count >= GEO_FAILURE_THRESHOLD and visit.status in (VisitStatus.PENDING, VisitStatus.IN_PROGRESS):
            visit.status = VisitStatus.FLAGGED
            session.add(visit)
        await geo_repo.commit()
        logger.warning(
            "event=visit_checkin result=rejected reason=%s request_id=%s visit_id=%s employee_id=%s customer_id=%s distance_m=%s accuracy_m=%s allowed_radius_m=%s is_mock=%s",
            geo_res.failure_reason,
            req_id,
            visit.id,
            visit.employee_id,
            visit.customer_id,
            geo_res.distance_m,
            data.accuracy_m,
            customer.geofence_radius_m,
            data.is_mock_location,
        )
        raise BaseAPIException(
            status_code=422,
            detail=f"Check-in failed: {geo_res.failure_reason}",
            error_code="GEO_VERIFICATION_FAILED",
        )

    visit.status = VisitStatus.IN_PROGRESS
    visit.check_in_at = data.captured_at if data.captured_at else datetime.now(tz=timezone.utc)
    visit.check_in_received_at = datetime.now(tz=timezone.utc)
    visit.check_in_location = f"SRID=4326;POINT({data.longitude} {data.latitude})"
    session.add(visit)
    await geo_repo.commit()

    logger.info(
        "event=visit_checkin result=success request_id=%s visit_id=%s employee_id=%s customer_id=%s distance_m=%s accuracy_m=%s visit_type=%s",
        req_id,
        visit.id,
        visit.employee_id,
        visit.customer_id,
        geo_res.distance_m,
        data.accuracy_m,
        visit.visit_type.value if hasattr(visit.visit_type, "value") else str(visit.visit_type),
    )

    repo = VisitRepository(session)
    return await repo.get_full(visit.id)


async def check_out(
    visit_id: uuid.UUID,
    data: CheckOutRequest,
    current_user: User,
    session: AsyncSession,
) -> Visit:
    from app.services.customer_service import verify_device_against_customer

    req_id = get_current_request_id()
    visit = await get_visit_for_user(visit_id, current_user, session)

    # Idempotency: if key matches any previous check-out attempt, replay the exact outcome
    if data.idempotency_key:
        geo_repo = GeoLogRepository(session)
        existing_log = await geo_repo.get_by_idempotency_key(visit.id, data.idempotency_key)
        if existing_log is not None:
            if not existing_log.is_valid:
                logger.warning(
                    "event=visit_checkout result=rejected reason=%s idempotency_replay=true request_id=%s visit_id=%s",
                    existing_log.failure_reason,
                    req_id,
                    visit.id,
                )
                raise BaseAPIException(
                    status_code=422,
                    detail=f"Check-out failed: {existing_log.failure_reason}",
                    error_code="GEO_VERIFICATION_FAILED",
                )
            logger.info("event=visit_checkout result=success idempotency_replay=true request_id=%s visit_id=%s", req_id, visit.id)
            return visit

    if visit.status == VisitStatus.COMPLETED:
        return visit

    if visit.status != VisitStatus.IN_PROGRESS:
        logger.warning(
            "event=visit_checkout result=rejected reason=CHECKIN_REQUIRED request_id=%s visit_id=%s current_status=%s",
            req_id,
            visit.id,
            visit.status.value if hasattr(visit.status, "value") else str(visit.status),
        )
        raise BaseAPIException(
            status_code=400,
            detail="Check-in is required before checking out",
            error_code="CHECKIN_REQUIRED",
        )

    assert_valid_transition(visit.status, VisitStatus.COMPLETED)

    check_out_time = data.captured_at if data.captured_at else datetime.now(tz=timezone.utc)
    if visit.check_in_at is not None:
        cin = visit.check_in_at if visit.check_in_at.tzinfo else visit.check_in_at.replace(tzinfo=timezone.utc)
        cout = check_out_time if check_out_time.tzinfo else check_out_time.replace(tzinfo=timezone.utc)
        if cout < cin:
            logger.warning(
                "event=visit_checkout result=rejected reason=INVALID_VISIT_DURATION request_id=%s visit_id=%s",
                req_id,
                visit.id,
            )
            raise BaseAPIException(
                status_code=422,
                detail="Check-out time cannot be earlier than check-in time",
                error_code="INVALID_VISIT_DURATION",
            )

    customer = await get_customer(visit.customer_id, session)
    if customer.location is None:
        logger.warning(
            "event=visit_checkout result=rejected reason=OUTLET_LOCATION_NOT_CONFIGURED request_id=%s visit_id=%s customer_id=%s",
            req_id,
            visit.id,
            visit.customer_id,
        )
        raise BaseAPIException(
            status_code=422,
            detail="Outlet location is not configured.",
            error_code="OUTLET_LOCATION_NOT_CONFIGURED",
        )

    # FT-004: identical geofence rules as check-in, same PostGIS distance.
    geo_res = await verify_device_against_customer(
        customer,
        session,
        device_lat=data.latitude,
        device_lng=data.longitude,
        accuracy_m=data.accuracy_m,
        is_mock_location=data.is_mock_location,
        captured_at=data.captured_at,
    )

    geo_repo = GeoLogRepository(session)
    log = GeoVerificationLog(
        visit_id=visit.id,
        verification_type=GeoVerificationType.CHECK_OUT,
        device_location=f"SRID=4326;POINT({data.longitude} {data.latitude})",
        distance_from_customer_m=geo_res.distance_m,
        is_valid=geo_res.is_valid,
        failure_reason=geo_res.failure_reason,
        idempotency_key=data.idempotency_key,
    )
    await geo_repo.add(log)

    if not geo_res.is_valid:
        fail_count = await geo_repo.count_failed_for_visit(visit.id)
        if fail_count >= GEO_FAILURE_THRESHOLD:
            visit.status = VisitStatus.FLAGGED
            session.add(visit)
        await geo_repo.commit()
        logger.warning(
            "event=visit_checkout result=rejected reason=%s request_id=%s visit_id=%s employee_id=%s customer_id=%s distance_m=%s accuracy_m=%s",
            geo_res.failure_reason,
            req_id,
            visit.id,
            visit.employee_id,
            visit.customer_id,
            geo_res.distance_m,
            data.accuracy_m,
        )
        raise BaseAPIException(
            status_code=422,
            detail=f"Check-out failed: {geo_res.failure_reason}",
            error_code="GEO_VERIFICATION_FAILED",
        )

    visit.status = VisitStatus.COMPLETED
    visit.check_out_at = data.captured_at if data.captured_at else datetime.now(tz=timezone.utc)
    visit.check_out_received_at = datetime.now(tz=timezone.utc)
    visit.check_out_location = f"SRID=4326;POINT({data.longitude} {data.latitude})"
    if data.notes is not None:
        visit.notes = data.notes
    session.add(visit)
    await session.commit()

    logger.info(
        "event=visit_checkout result=success request_id=%s visit_id=%s employee_id=%s customer_id=%s",
        req_id,
        visit.id,
        visit.employee_id,
        visit.customer_id,
    )

    repo = VisitRepository(session)
    return await repo.get_full(visit.id)


async def get_visit_geo_logs(
    visit_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> list[GeoVerificationLog]:
    """Retrieve immutable geo verification audit logs for a visit."""
    await get_visit_for_user(visit_id, current_user, session)

    geo_repo = GeoLogRepository(session)
    return await geo_repo.list_by_visit(visit_id)


async def admin_force_status(
    visit_id: uuid.UUID,
    target_status: VisitStatus,
    session: AsyncSession,
) -> Visit:
    """
    Admin-only status override.

    This deliberately relaxes the ordinary state machine - the API design lists
    "manual status override (e.g. mark MISSED)" as an administrative power, and
    resolving a FLAGGED visit requires moving it to a state the normal flow
    would not allow.

    FT-074: what it must NOT do is resurrect a terminal visit. Previously it
    assigned `status` unconditionally, so a COMPLETED visit could be forced
    back to PENDING and persisted as::

        status = PENDING, check_in_at = <set>, check_out_at = <set>

    That record is incoherent: it reappears as outstanding work while carrying
    evidence it was finished, and the employee's "today" list would offer a
    check-in on a visit that already has a check-out.

    `19_business_logic.md` section 1 defines COMPLETED and MISSED as terminal.
    Reopening one is refused; correcting a wrong outcome is a new visit, not a
    rewrite of the audited one.
    """
    visit = await get_visit(visit_id, session)

    if visit.status == target_status:
        return visit  # no-op

    if is_terminal(visit.status):
        raise BaseAPIException(
            status_code=409,
            detail=(
                f"Visit is {visit.status.value} and cannot be reopened. "
                "Schedule a new visit instead."
            ),
            error_code="VISIT_TERMINAL_STATE",
        )

    visit.status = target_status
    session.add(visit)
    await session.commit()
    repo = VisitRepository(session)
    full_visit = await repo.get_full(visit.id)

    # Notify employee of visit status update
    try:
        from app.services.notification_service import notification_service
        from app.models.notification import NotificationType
        from app.services.employee_service import get_employee
        employee = await get_employee(visit.employee_id, session)
        if employee and employee.user_id:
            notif_type = NotificationType.GEO_FAILURE_ALERT if target_status in [VisitStatus.MISSED, VisitStatus.FLAGGED] else NotificationType.REMINDER
            msg = f"Visit status updated to {target_status.value} for {full_visit.customer_name}"
            await notification_service.create_notification(
                user_id=employee.user_id,
                notification_type=notif_type,
                message=msg,
                visit_id=visit.id,
                session=session,
            )
    except Exception as e:
        logger.warning(f"Failed to create visit status notification: {e}")

    return full_visit


async def bulk_create_visits(
    data: "BulkVisitCreate",
    created_by: uuid.UUID,
    session: AsyncSession,
) -> list[Visit]:
    """
    Admin: bulk schedule visits for multiple customers.

    Creates one visit per customer with the same employee and scheduled time.
    Validates all customers exist and are unique.
    """
    from app.schemas.visit import BulkVisitCreate

    if not data.customer_ids:
        raise BaseAPIException(
            status_code=400,
            detail="At least one customer is required",
            error_code="BULK_NO_CUSTOMERS",
        )

    # Check for duplicates
    if len(data.customer_ids) != len(set(data.customer_ids)):
        raise BaseAPIException(
            status_code=400,
            detail="Duplicate customer IDs are not allowed",
            error_code="BULK_DUPLICATE_CUSTOMERS",
        )

    # Validate employee exists
    from app.models.employee import Employee
    from sqlalchemy import select

    employee = await session.execute(
        select(Employee).where(Employee.id == data.employee_id)
    )
    emp_record = employee.scalar_one_or_none()
    if emp_record is None:
        raise BaseAPIException(
            status_code=404,
            detail=f"Employee {data.employee_id} not found",
            error_code="EMPLOYEE_NOT_FOUND",
        )
    await _validate_required_form(data.required_form_id, session)

    # Duplicate visit guard for bulk — checked ONCE before writing any rows.
    # A single pre-existing conflict blocks the entire batch (all-or-nothing).
    await _check_duplicate_visit(data.employee_id, data.scheduled_at, session)

    visits = []
    for i, customer_id in enumerate(data.customer_ids):
        # Validate customer exists
        from app.models.customer import Customer
        customer = await session.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        if customer.scalar_one_or_none() is None:
            raise BaseAPIException(
                status_code=404,
                detail=f"Customer {customer_id} not found",
                error_code="CUSTOMER_NOT_FOUND",
            )

        slot_time = data.scheduled_at + timedelta(minutes=i * VISIT_CONFLICT_WINDOW_MINUTES)
        visit = Visit(
            customer_id=customer_id,
            employee_id=data.employee_id,
            scheduled_at=slot_time,
            status=VisitStatus.PENDING,
            created_by=created_by,
            visit_type=VisitType.PLANNED,
            required_form_id=data.required_form_id,
        )
        session.add(visit)
        await session.flush()
        visits.append(visit)

    await session.commit()
    repo = VisitRepository(session)
    full_visits = []
    for visit in visits:
        fv = await repo.get_full(visit.id)
        full_visits.append(fv)

    # Bulk notification
    try:
        from app.services.notification_service import notification_service
        from app.models.notification import NotificationType
        if emp_record and emp_record.user_id:
            await notification_service.create_notification(
                user_id=emp_record.user_id,
                notification_type=NotificationType.NEW_VISIT,
                message=f"{len(visits)} new visits have been assigned to your schedule.",
                visit_id=visits[0].id if visits else None,
                session=session,
            )
    except Exception as e:
        logger.warning(f"Failed to create bulk visit notification: {e}")

    return full_visits


async def update_visit_required_form(
    visit_id: uuid.UUID,
    required_form_id: uuid.UUID | None,
    session: AsyncSession,
) -> Visit:
    """Admin: assign, change, or clear ("no form required") the form a visit requires."""
    visit = await get_visit(visit_id, session)
    await _validate_required_form(required_form_id, session)
    visit.required_form_id = required_form_id
    session.add(visit)
    await session.commit()
    repo = VisitRepository(session)
    return await repo.get_full(visit.id)


async def find_stale_in_progress_visits(
    session: AsyncSession, threshold_hours: int = 24
) -> list[Visit]:
    """
    WEB-EMP-026: Identify IN_PROGRESS visits that have remained in progress beyond threshold_hours.
    Provides the isolated query/service helper needed to identify stale visits without prematurely
    deciding terminal state.
    """
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=threshold_hours)
    result = await session.execute(
        select(Visit).where(
            Visit.status == VisitStatus.IN_PROGRESS,
            Visit.check_in_at < cutoff,
        )
    )
    return list(result.scalars().all())



