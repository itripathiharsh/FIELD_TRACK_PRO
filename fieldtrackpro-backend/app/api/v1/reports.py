"""
Reports router: REST endpoints for admin reports.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.reports import (
    EmployeeVisitReportRow,
    ProductivityDashboard,
    GeoVerificationReportRow,
)
from app.services import report_service

router = APIRouter(tags=["Reports"], dependencies=[Depends(require_role(Role.ADMIN))])


@router.get("/reports/employees", response_model=list[EmployeeVisitReportRow])
async def employee_visit_report(
    start_date: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[EmployeeVisitReportRow]:
    """Employee visit report: visits completed/missed per employee/period."""
    data = await report_service.get_employee_visit_report(session, start_date, end_date)
    return [EmployeeVisitReportRow(**row) for row in data]


@router.get("/reports/customers/{customer_id}/history")
async def customer_visit_history(
    customer_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[dict]:
    """Customer visit history: all visits for a specific customer."""
    return await report_service.get_customer_visit_history(session, customer_id)


@router.get("/reports/productivity", response_model=ProductivityDashboard)
async def productivity_dashboard(
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> ProductivityDashboard:
    """Productivity dashboard: visits/day, active employees, completion rates."""
    data = await report_service.get_productivity_dashboard(session)
    return ProductivityDashboard(**data)


@router.get("/reports/geo-verification", response_model=list[GeoVerificationReportRow])
async def geo_verification_report(
    start_date: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[GeoVerificationReportRow]:
    """Geo-verification report: flagged/failed check-ins with reason codes."""
    data = await report_service.get_geo_verification_report(session, start_date, end_date)
    return [GeoVerificationReportRow(**row) for row in data]
