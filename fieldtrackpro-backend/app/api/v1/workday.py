"""
Workday & Daily Field Activity API Router — /api/v1/workday
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.workday import (
    EmployeeWorkdayResponse,
    TodayFieldActivityOverview,
    WorkSessionEndRequest,
    WorkSessionStartRequest,
)
from app.services import workday_service

router = APIRouter(prefix="/workday", tags=["workday"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
EmployeeOnly = Depends(require_role(Role.EMPLOYEE))
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post(
    "/start",
    response_model=EmployeeWorkdayResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[EmployeeOnly],
)
async def start_workday(
    req: WorkSessionStartRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> EmployeeWorkdayResponse:
    """
    Start employee workday. Captures start GPS coordinates, timestamp, and creates a work session in STARTED state.
    """
    return await workday_service.start_workday(current_user, req, session)


@router.post(
    "/end",
    response_model=EmployeeWorkdayResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[EmployeeOnly],
)
async def end_workday(
    req: WorkSessionEndRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> EmployeeWorkdayResponse:
    """
    End employee workday. Captures end GPS coordinates, timestamp, and marks the work session as COMPLETED.
    """
    return await workday_service.end_workday(current_user, req, session)


@router.get(
    "/today",
    response_model=EmployeeWorkdayResponse,
    dependencies=[AnyAuth],
)
async def get_today_workday(
    current_user: CurrentUser,
    session: DbSession,
    work_date: Optional[date] = Query(default=None, description="Optional target date YYYY-MM-DD (defaults to today)"),
) -> EmployeeWorkdayResponse:
    """
    Returns the caller's workday state and live daily activity summary for the specified date.
    """
    return await workday_service.get_today_workday(current_user, work_date, session)


@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeWorkdayResponse,
    dependencies=[AdminOnly],
)
async def get_employee_workday(
    employee_id: uuid.UUID,
    session: DbSession,
    work_date: Optional[date] = Query(default=None, description="Target work date YYYY-MM-DD (defaults to today)"),
) -> EmployeeWorkdayResponse:
    """
    Admin lookup of an employee's workday session and field metrics by date.
    """
    return await workday_service.get_employee_workday_by_admin(employee_id, work_date, session)


@router.get(
    "/overview/today",
    response_model=TodayFieldActivityOverview,
    dependencies=[AdminOnly],
)
async def get_today_field_overview(
    session: DbSession,
    work_date: Optional[date] = Query(default=None, description="Target date YYYY-MM-DD (defaults to today)"),
) -> TodayFieldActivityOverview:
    """
    Admin overview of organization-wide field activity for today.
    """
    return await workday_service.get_today_field_overview(work_date, session)
