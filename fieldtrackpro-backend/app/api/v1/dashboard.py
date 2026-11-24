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
from app.schemas.dashboard import DashboardSummaryResponse, EmployeeDayDashboardResponse, HistoryPeriodsResponse
from app.services import dashboard_service
from app.services.report_filters import as_list, as_uuid_list

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
EmployeeOnly = Depends(require_role(Role.EMPLOYEE))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))
FinanceRead = Depends(require_role(Role.ADMIN, Role.ACCOUNTANT))


@router.get("/summary", response_model=DashboardSummaryResponse, dependencies=[AnyAuth])
async def get_dashboard_summary(
    current_user: CurrentUser,
    session: DbSession,
    brand: Optional[list[str]] = Query(default=None, description="Brand(s); repeat or comma-separate. 'Unattributed' = no brand in Tally"),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[list[str]] = Query(default=None, description="FOS employee id(s); repeat or comma-separate"),
    ageing_bucket: Optional[str] = Query(default=None, description="'<15', '15-30', '30-45', '45-60', '60-75', '75-90' or '>90'"),
    month: Optional[list[str]] = Query(default=None, description="Period(s) YYYY-MM or FYyyyy-yy; repeat or comma-separate; none/'ALL' = Current Live Data"),
):
    """
    Unified Executive Dashboard BI summary.
    Role-aware: If user is EMPLOYEE, employee_id is automatically scoped to caller (any requested id is ignored).
    Brand, period and FOS accept several values (OR inside a filter, AND across filters).
    """
    scoped_emp_id = as_uuid_list(employee_id)
    if current_user.role == Role.EMPLOYEE:
        from app.services.employee_service import get_employee_by_user_id
        emp = await get_employee_by_user_id(current_user.id, session)
        scoped_emp_id = [emp.id]
    months = as_list(month)
    brands = as_list(brand)

    return await dashboard_service.get_dashboard_summary(
        current_user=current_user,
        session=session,
        brand=",".join(brands) if brands else None,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=scoped_emp_id,
        ageing_bucket=ageing_bucket,
        month=",".join(months) if months else None,
    )


@router.get("/history-periods", response_model=HistoryPeriodsResponse, dependencies=[FinanceRead])
async def get_history_periods(session: DbSession):
    """Read-only History periods for the dashboard filter: past financial years (before the reporting floor)
    that hold Tally data, with their months. Separate from the monthly reporting periods (no close workflow)."""
    return await dashboard_service.get_history_periods(session)


@router.get("/my-day", response_model=EmployeeDayDashboardResponse, dependencies=[EmployeeOnly])
async def get_my_day_dashboard(
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Employee Field Dashboard: My Day operational stats (Assigned Outlets, Today's Visits, Collections, Orders).
    """
    return await dashboard_service.get_employee_day_dashboard(current_user, session)
