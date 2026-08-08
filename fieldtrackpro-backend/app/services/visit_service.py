"""
Visit service — refactored to use VisitRepository and GeoLogRepository.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.geo_verification_log import GeoVerificationLog, GeoVerificationType
from app.models.user import Role
from app.models.visit import Visit, VisitStatus
from app.repositories.geo_log_repo import GeoLogRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.visit import CheckInRequest, CheckOutRequest, VisitCreate
from app.services.customer_service import get_customer, verify_geo_proximity
from app.services.employee_service import get_employee_by_user_id
from app.services.visit_state_machine import assert_valid_transition
from app.models.user import User

# Number of geo-verification failures before auto-flagging
GEO_FAILURE_THRESHOLD = 3


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


async def create_visit(data: VisitCreate, created_by: uuid.UUID, session: AsyncSession) -> Visit:
    """
    Admin: schedule a visit.

    FT-006: the customer and employee are validated up front. Previously an
    unknown id reached the database and surfaced as an unhandled
    ForeignKeyViolation (HTTP 500) instead of a meaningful 404.
    """
    from app.services.employee_service import get_employee

    await get_customer(data.customer_id, session)
    await get_employee(data.employee_id, session)

    repo = VisitRepository(session)
    visit = Visit(
        customer_id=data.customer_id,
        employee_id=data.employee_id,
        scheduled_at=data.scheduled_at,
        created_by=created_by,
        status=VisitStatus.PENDING,
    )
    await repo.add(visit)
    await repo.commit()
    return visit


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
    status: VisitStatus | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Visit]:
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
    return await repo.list_filtered(employee_id, status, skip, limit)


async def get_my_today_visits(current_user: User, session: AsyncSession) -> list[Visit]:
    """Employee: returns today's scheduled visits for the authenticated employee."""
    employee = await get_employee_by_user_id(current_user.id, session)
    repo = VisitRepository(session)
    today = date.today()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return await repo.get_employee_today_visits(employee.id, start, end)


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
        raise BaseAPIException(
            status_code=422,
            detail=f"Check-in failed: {geo_res.failure_reason}",
            error_code="GEO_VERIFICATION_FAILED",
        )

    visit.status = VisitStatus.IN_PROGRESS
    visit.check_in_at = datetime.now(tz=timezone.utc)
    visit.check_in_location = f"SRID=4326;POINT({data.longitude} {data.latitude})"
    session.add(visit)
    await geo_repo.commit()
    await session.refresh(visit)
    return visit


async def check_out(
    visit_id: uuid.UUID,
    data: CheckOutRequest,
    current_user: User,
    session: AsyncSession,
) -> Visit:
    from app.services.customer_service import verify_device_against_customer

    visit = await get_visit_for_user(visit_id, current_user, session)

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
    )

    geo_repo = GeoLogRepository(session)
    log = GeoVerificationLog(
        visit_id=visit.id,
        verification_type=GeoVerificationType.CHECK_OUT,
        device_location=f"SRID=4326;POINT({data.longitude} {data.latitude})",
        distance_from_customer_m=geo_res.distance_m,
        is_valid=geo_res.is_valid,
        failure_reason=geo_res.failure_reason,
        idempotency_key=None,
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
    visit.check_out_at = datetime.now(tz=timezone.utc)
    visit.check_out_location = f"SRID=4326;POINT({data.longitude} {data.latitude})"
    session.add(visit)
    await session.commit()
    await session.refresh(visit)
    return visit


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
    """Admin-only: override visit status without normal state machine guard."""
    visit = await get_visit(visit_id, session)
    visit.status = target_status
    session.add(visit)
    await session.commit()
    await session.refresh(visit)
    return visit

