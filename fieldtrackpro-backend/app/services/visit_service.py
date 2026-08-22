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

from app.exceptions.custom import BaseAPIException, DuplicateVisitException
from app.models.form_template import FormStatus, FormTemplate
from app.models.geo_verification_log import GeoVerificationLog, GeoVerificationType
from app.models.notification import NotificationType
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.repositories.geo_log_repo import GeoLogRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.visit import CheckInRequest, CheckOutRequest, VisitCreate
from app.services import notification_service
from app.services.customer_service import get_customer, verify_geo_proximity
from app.services.employee_service import get_employee, get_employee_by_user_id
from app.services.visit_state_machine import assert_valid_transition, is_terminal

logger = logging.getLogger(__name__)


async def _validate_required_form(required_form_id: uuid.UUID | None, session: AsyncSession) -> None:
    """
    A visit may only require a PUBLISHED template - a DRAFT isn't ready for
    an employee to see, and an ARCHIVED one is no longer meant for new work
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
        required_form_id=data.required_form_id,
    )
    await repo.add(visit)
    await repo.commit()
    full_visit = await repo.get_full(visit.id)

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
        skip=skip,
        limit=limit,
    )


async def get_my_today_visits(
    current_user: User,
    session: AsyncSession,
    status: list[VisitStatus] | VisitStatus | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Visit], int]:
    """
    Employee: returns today's scheduled visits for the authenticated employee in IST / local timezone (+05:30)
    with optional status filtering, search, and pagination.
    """
    employee = await get_employee_by_user_id(current_user.id, session)
    repo = VisitRepository(session)

    # Calculate Today's boundaries in IST (+05:30)
    tz_offset = timezone(timedelta(hours=5, minutes=30))
    now_local = datetime.now(tz_offset)
    start_local = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=tz_offset)
    end_local = start_local + timedelta(days=1)

    # Convert to UTC for database comparison
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    return await repo.list_filtered_paginated(
        employee_id=employee.id,
        status=status,
        from_date=start_utc,
        to_date=end_utc,
        search=search,
        sort_order="asc",
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

    visit = await get_visit_for_user(visit_id, current_user, session)

    # Idempotency: if key matches a previous successful check-in, return current visit
    if data.idempotency_key:
        geo_repo = GeoLogRepository(session)
        if await geo_repo.idempotency_key_exists(visit.id, data.idempotency_key):
            return visit

    assert_valid_transition(visit.status, VisitStatus.IN_PROGRESS)

    customer = await get_customer(visit.customer_id, session)

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
        # Check if failure threshold reached â€” auto-flag visit
        fail_count = await geo_repo.count_failed_for_visit(visit.id)
        if fail_count >= GEO_FAILURE_THRESHOLD and visit.status in (VisitStatus.PENDING, VisitStatus.IN_PROGRESS):
            visit.status = VisitStatus.FLAGGED
            session.add(visit)
        await geo_repo.commit()
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
    repo = VisitRepository(session)
    return await repo.get_full(visit.id)


async def check_out(
    visit_id: uuid.UUID,
    data: CheckOutRequest,
    current_user: User,
    session: AsyncSession,
) -> Visit:
    from app.services.customer_service import verify_device_against_customer

    visit = await get_visit_for_user(visit_id, current_user, session)

    # Idempotency: if key matches a previous successful check-out, return current visit
    if data.idempotency_key:
        geo_repo = GeoLogRepository(session)
        if await geo_repo.idempotency_key_exists(visit.id, data.idempotency_key):
            return visit

    assert_valid_transition(visit.status, VisitStatus.COMPLETED)

    customer = await get_customer(visit.customer_id, session)

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
        raise BaseAPIException(
            status_code=422,
            detail=f"Check-out failed: {geo_res.failure_reason}",
            error_code="GEO_VERIFICATION_FAILED",
        )

    visit.status = VisitStatus.COMPLETED
    visit.check_out_at = data.captured_at if data.captured_at else datetime.now(tz=timezone.utc)
    visit.check_out_received_at = datetime.now(tz=timezone.utc)
    visit.check_out_location = f"SRID=4326;POINT({data.longitude} {data.latitude})"
    session.add(visit)
    await session.commit()
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
    for customer_id in data.customer_ids:
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

        visit = Visit(
            customer_id=customer_id,
            employee_id=data.employee_id,
            scheduled_at=data.scheduled_at,
            status=VisitStatus.PENDING,
            created_by=created_by,
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


