from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_now
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.visit_analytics import (
    DailyAnalytics,
    EmployeeMonthlyAnalytics,
    TeamMonthlyAnalytics,
)
from app.schemas.visit_planning import (
    MonthlyPlanSummaryRead,
    MonthlyVisitPlanRead,
    PlannedVisitCreate,
    PlannedVisitRead,
    PlannedVisitReassign,
    PlannedVisitReschedule,
    PlannedVisitUpdate,
    TeamMonthlyPlanRead,
)
from app.services import visit_analytics_service, visit_planning_service

router = APIRouter(prefix="/visit-planning", tags=["visit-planning"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


def _default_year_month(year: Optional[int], month: Optional[int]) -> tuple[int, int]:
    ist_now = get_ist_now()
    y = year if year is not None else ist_now.year
    m = month if month is not None else ist_now.month
    return y, m


@router.get(
    "/my-plan",
    response_model=MonthlyVisitPlanRead,
    dependencies=[AnyAuth],
    summary="Get authenticated employee's monthly visit plan",
)
async def get_my_plan(
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100, description="Calendar year"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Calendar month (1-12)"),
) -> MonthlyVisitPlanRead:
    """
    Returns the authenticated employee's monthly plan and planned visits.
    Automatically initializes the plan if it does not already exist.
    """
    y, m = _default_year_month(year, month)
    return await visit_planning_service.get_my_plan(current_user, y, m, session)


@router.get(
    "/plans/{employee_id}",
    response_model=MonthlyVisitPlanRead,
    dependencies=[AnyAuth],
    summary="Get specified employee's monthly visit plan",
)
async def get_employee_plan(
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100, description="Calendar year"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Calendar month (1-12)"),
) -> MonthlyVisitPlanRead:
    """
    Admin (or the owner employee): view any employee's monthly plan.
    """
    y, m = _default_year_month(year, month)
    return await visit_planning_service.get_employee_plan(employee_id, y, m, current_user, session)


@router.get(
    "/plans",
    response_model=list[MonthlyPlanSummaryRead],
    dependencies=[AdminOnly],
    summary="Admin: list all employees' monthly planning summaries",
)
async def list_monthly_plans(
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100, description="Calendar year"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Calendar month (1-12)"),
) -> list[MonthlyPlanSummaryRead]:
    """
    Admin: view an overview of all employees' monthly plans for the specified month.
    """
    y, m = _default_year_month(year, month)
    return await visit_planning_service.list_monthly_plans(y, m, current_user, session)


@router.get(
    "/team-plan",
    response_model=TeamMonthlyPlanRead,
    dependencies=[AdminOnly],
    summary="Admin: get team monthly plan with visits across all employees or filtered by employee",
)
async def get_team_plan(
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100, description="Calendar year"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Calendar month (1-12)"),
    employee_id: Optional[uuid.UUID] = Query(default=None, description="Optional filter by employee ID"),
) -> TeamMonthlyPlanRead:
    """
    Admin: returns the combined team plan with planned visits across all employees (or filtered by employee).
    """
    y, m = _default_year_month(year, month)
    return await visit_planning_service.get_team_plan(y, m, current_user, session, employee_id=employee_id)


@router.post(
    "/visits",
    response_model=PlannedVisitRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AnyAuth],
    summary="Create a planned visit for a future date",
)
async def create_planned_visit(
    data: PlannedVisitCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> PlannedVisitRead:
    """
    Schedule a planned visit. Employees can schedule for themselves; admins can schedule for any employee.
    Multiple visits per day and zero visits on any day are fully supported.
    """
    return await visit_planning_service.create_planned_visit(data, current_user, session)


@router.patch(
    "/visits/{id}",
    response_model=PlannedVisitRead,
    dependencies=[AnyAuth],
    summary="Update planned visit details",
)
async def update_planned_visit(
    id: uuid.UUID,
    data: PlannedVisitUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> PlannedVisitRead:
    """
    Update priority, visit type, or notes of an existing planned visit.
    """
    return await visit_planning_service.update_planned_visit(id, data, current_user, session)


@router.post(
    "/visits/{id}/reschedule",
    response_model=PlannedVisitRead,
    dependencies=[AnyAuth],
    summary="Reschedule planned visit to a different date",
)
async def reschedule_planned_visit(
    id: uuid.UUID,
    data: PlannedVisitReschedule,
    current_user: CurrentUser,
    session: DbSession,
) -> PlannedVisitRead:
    """
    Change the target date of a planned visit.
    """
    return await visit_planning_service.reschedule_planned_visit(id, data.new_date, current_user, session)


@router.post(
    "/visits/{id}/reassign",
    response_model=PlannedVisitRead,
    dependencies=[AdminOnly],
    summary="Admin: reassign planned visit to another employee",
)
async def reassign_planned_visit(
    id: uuid.UUID,
    data: PlannedVisitReassign,
    current_user: CurrentUser,
    session: DbSession,
) -> PlannedVisitRead:
    """
    Admin: reassign a planned visit to a different employee.
    """
    return await visit_planning_service.reassign_planned_visit(id, data.new_employee_id, current_user, session)


@router.delete(
    "/visits/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[AnyAuth],
    summary="Delete / cancel a planned visit",
)
async def delete_planned_visit(
    id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> None:
    """
    Remove/cancel a planned visit.
    """
    await visit_planning_service.delete_planned_visit(id, current_user, session)


# ── Analytics Endpoints ──


@router.get(
    "/analytics/my-month",
    response_model=EmployeeMonthlyAnalytics,
    dependencies=[AnyAuth],
    summary="Employee: get own monthly planned vs actual analytics",
)
async def get_my_month_analytics(
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
) -> EmployeeMonthlyAnalytics:
    """Returns the authenticated employee's planned vs actual metrics for the month."""
    from app.services.employee_service import get_employee_by_user_id

    y, m = _default_year_month(year, month)
    employee = await get_employee_by_user_id(current_user.id, session)
    return await visit_analytics_service.get_employee_monthly_analytics(employee.id, y, m, session)


@router.get(
    "/analytics/employee/{employee_id}",
    response_model=EmployeeMonthlyAnalytics,
    dependencies=[AdminOnly],
    summary="Admin: get specific employee monthly analytics",
)
async def get_employee_analytics(
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
) -> EmployeeMonthlyAnalytics:
    """Admin: view a specific employee's planned vs actual metrics."""
    y, m = _default_year_month(year, month)
    return await visit_analytics_service.get_employee_monthly_analytics(employee_id, y, m, session)


@router.get(
    "/analytics/team",
    response_model=TeamMonthlyAnalytics,
    dependencies=[AdminOnly],
    summary="Admin: get team-wide monthly analytics",
)
async def get_team_analytics(
    current_user: CurrentUser,
    session: DbSession,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    employee_id: Optional[uuid.UUID] = Query(default=None, description="Optional filter by employee"),
) -> TeamMonthlyAnalytics:
    """Admin: team-wide or filtered planned vs actual analytics."""
    y, m = _default_year_month(year, month)
    return await visit_analytics_service.get_team_monthly_analytics(y, m, session, employee_id=employee_id)


@router.get(
    "/analytics/daily",
    response_model=DailyAnalytics,
    dependencies=[AnyAuth],
    summary="Get daily planned vs actual analytics for an employee",
)
async def get_daily_analytics(
    current_user: CurrentUser,
    session: DbSession,
    employee_id: uuid.UUID = Query(..., description="Employee ID"),
    target_date: date = Query(..., alias="date", description="Calendar date (YYYY-MM-DD)"),
) -> DailyAnalytics:
    """Daily planned vs actual breakdown. Employees can only query their own data."""
    if current_user.role != Role.ADMIN:
        from app.services.employee_service import get_employee_by_user_id
        caller_emp = await get_employee_by_user_id(current_user.id, session)
        if caller_emp.id != employee_id:
            from app.exceptions.custom import ForbiddenException
            raise ForbiddenException("Access denied to another employee's analytics")
    return await visit_analytics_service.get_daily_analytics(employee_id, target_date, session)
