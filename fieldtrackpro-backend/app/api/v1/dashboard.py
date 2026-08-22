"""
Dashboard API Router — /api/v1/dashboard
"""
from __future__ import annotations
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.dashboard import DashboardSummaryResponse, EmployeeDayDashboardResponse
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("/summary", response_model=DashboardSummaryResponse, dependencies=[AnyAuth])
async def get_dashboard_summary(
    current_user: CurrentUser,
    session: DbSession,
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    ageing_bucket: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None, description="Month format YYYY-MM or 'ALL'/'LIVE'"),
):
    """
    Unified Executive Dashboard BI summary.
    Role-aware: If user is EMPLOYEE, employee_id is automatically scoped to caller.
    """
    scoped_emp_id = employee_id
    if current_user.role == Role.EMPLOYEE:
        from app.services.employee_service import get_employee_by_user_id
        emp = await get_employee_by_user_id(current_user.id, session)
        scoped_emp_id = emp.id

    return await dashboard_service.get_dashboard_summary(
        current_user=current_user,
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=scoped_emp_id,
        ageing_bucket=ageing_bucket,
        month=month,
    )


@router.get("/my-day", response_model=EmployeeDayDashboardResponse, dependencies=[AnyAuth])
async def get_my_day_dashboard(
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Employee Field Dashboard: My Day operational stats (Assigned Outlets, Today's Visits, Collections, Orders).
    """
    return await dashboard_service.get_employee_day_dashboard(current_user, session)
