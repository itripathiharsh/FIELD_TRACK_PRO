from __future__ import annotations
import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_today_range
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.field_exception import FieldException, ExceptionStatus
from app.models.payment import Payment
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.models.visit_media import MediaType, VisitMedia
from app.schemas.dashboard import (
    DashboardExecutiveKPIs,
    DashboardSummaryResponse,
    EmployeeDayDashboardResponse,
)
from app.services import field_exception_service, report_service
from app.services.employee_service import get_employee_by_user_id


async def get_dashboard_summary(
    current_user: User,
    session: AsyncSession,
    brand: Optional[str] = None,
    zone_id: Optional[uuid.UUID] = None,
    area_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    ageing_bucket: Optional[str] = None,
    month: Optional[str] = None,
) -> DashboardSummaryResponse:
    """
    Unified Dashboard aggregation sharing 100% single source of truth with ReportService.
    Eliminates redundant execution of get_business_bi_dashboard.
    """
    # 1. Fetch Business BI multi-dimensional summaries (single execution)
    bi_data = await report_service.ReportService.get_business_bi_dashboard(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
    )

    # 2. Count total active employees within active filter scope (WEB-DASH-012)
    emp_stmt = select(func.count(func.distinct(Employee.id)))
    if employee_id:
        emp_stmt = emp_stmt.where(Employee.id == employee_id)
    if zone_id:
        emp_stmt = emp_stmt.where(Employee.territory_id == zone_id)
    if area_id:
        emp_stmt = emp_stmt.join(
            EmployeeCustomerAssignment,
            EmployeeCustomerAssignment.employee_id == Employee.id,
        ).join(
            Customer,
            Customer.id == EmployeeCustomerAssignment.customer_id,
        ).where(Customer.area_id == area_id)
    emp_res = await session.execute(emp_stmt)
    total_employees = emp_res.scalar() or 0

    # 3. Fetch Operational Visit Counts within active filter scope
    visit_q = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.PENDING).label("pending"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.IN_PROGRESS).label("in_progress"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.FLAGGED).label("flagged"),
        func.count(Visit.id).filter(Visit.check_in_location.isnot(None)).label("gps_verified"),
    )
    if employee_id:
        visit_q = visit_q.where(Visit.employee_id == employee_id)
    if zone_id or area_id:
        visit_q = visit_q.join(Customer, Visit.customer_id == Customer.id)
        if zone_id:
            visit_q = visit_q.where(Customer.territory_id == zone_id)
        if area_id:
            visit_q = visit_q.where(Customer.area_id == area_id)

    v_res = await session.execute(visit_q)
    v_row = v_res.one()

    # 4. Fetch Exceptions count
    exc_q = select(
        func.count(FieldException.id).label("total"),
        func.count(FieldException.id).filter(FieldException.status == ExceptionStatus.PENDING_REVIEW).label("pending"),
    )
    if employee_id:
        exc_q = exc_q.where(FieldException.employee_id == employee_id)
    exc_res = await session.execute(exc_q)
    exc_row = exc_res.one()

    # 5. Fetch Collections count
    col_q = select(func.count(Payment.id))
    if employee_id:
        col_q = col_q.where(Payment.employee_id == employee_id)
    col_count = (await session.execute(col_q)).scalar_one() or 0

    # 6. Fetch Orders count
    order_q = select(func.count(VisitMedia.id)).where(VisitMedia.media_type == MediaType.ORDER)
    if employee_id:
        emp_user_stmt = select(Employee.user_id).where(Employee.id == employee_id)
        emp_uid = (await session.execute(emp_user_stmt)).scalar_one_or_none()
        if emp_uid:
            order_q = order_q.where(VisitMedia.uploaded_by == emp_uid)
    order_count = (await session.execute(order_q)).scalar_one() or 0

    # 7. Recent Exceptions for preview
    recent_exceptions, _ = await field_exception_service.list_field_exceptions(
        current_user=current_user,
        session=session,
        employee_id=employee_id,
        limit=5,
    )

    # 8. 7 Ageing Buckets Distribution
    ageing_distribution = {
        "<15": Decimal("0.00"),
        "15-30": Decimal("0.00"),
        "30-45": Decimal("0.00"),
        "45-60": Decimal("0.00"),
        "60-75": Decimal("0.00"),
        "75-90": Decimal("0.00"),
        ">90": Decimal("0.00"),
    }
    for b in bi_data.brand_summaries:
        ageing_distribution["<15"] += b.bucket_lt_15
        ageing_distribution["15-30"] += b.bucket_15_30
        ageing_distribution["30-45"] += b.bucket_30_45
        ageing_distribution["45-60"] += b.bucket_45_60
        ageing_distribution["60-75"] += b.bucket_60_75
        ageing_distribution["75-90"] += b.bucket_75_90
        ageing_distribution[">90"] += b.bucket_gt_90

    kpis = DashboardExecutiveKPIs(
        total_outlets=bi_data.total_outlets,
        total_sales=bi_data.total_sales,
        total_collection=bi_data.total_collection,
        total_market_outstanding=bi_data.total_market_outstanding,
        total_overdue_gt_90=bi_data.total_overdue_gt_90,
        total_employees=total_employees,
        total_visits=v_row.total or 0,
        completed_visits=v_row.completed or 0,
        pending_visits=v_row.pending or 0,
        in_progress_visits=v_row.in_progress or 0,
        flagged_visits=v_row.flagged or 0,
        gps_verified_visits=v_row.gps_verified or 0,
        total_exceptions=exc_row.total or 0,
        pending_exceptions=exc_row.pending or 0,
        total_collections_count=col_count,
        total_orders_count=order_count,
    )

    return DashboardSummaryResponse(
        period=month if month and month != "ALL" else "LIVE",
        is_historical=bool(month and month != "ALL"),
        kpis=kpis,
        brand_breakdown=bi_data.brand_summaries,
        fos_breakdown=bi_data.fos_summaries,
        zone_breakdown=bi_data.zone_summaries,
        area_breakdown=bi_data.area_summaries,
        ageing_distribution=ageing_distribution,
        recent_exceptions=recent_exceptions,
    )


async def get_employee_day_dashboard(
    current_user: User,
    session: AsyncSession,
) -> EmployeeDayDashboardResponse:
    """
    Mobile / Employee scoped operational "My Day" summary.
    Restricts visits, collections, and orders strictly to IST Today boundaries.
    """
    emp = await get_employee_by_user_id(current_user.id, session)
    start_utc, end_utc = get_ist_today_range()

    # Assigned outlets
    outlets_count = (
        await session.execute(
            select(func.count(EmployeeCustomerAssignment.customer_id)).where(
                EmployeeCustomerAssignment.employee_id == emp.id,
            )
        )
    ).scalar_one() or 0

    # Today's visits in IST (WEB-DASH-005)
    v_q = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.PENDING).label("pending"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.IN_PROGRESS).label("in_progress"),
    ).where(
        Visit.employee_id == emp.id,
        Visit.scheduled_at >= start_utc,
        Visit.scheduled_at < end_utc,
    )
    v_row = (await session.execute(v_q)).one()

    # Today's Collections in IST (WEB-DASH-006)
    col_q = select(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
    ).where(
        Payment.employee_id == emp.id,
        Payment.created_at >= start_utc,
        Payment.created_at < end_utc,
    )
    col_count, col_sum = (await session.execute(col_q)).one()

    # Today's Orders in IST (WEB-DASH-006)
    order_q = select(func.count(VisitMedia.id)).where(
        VisitMedia.media_type == MediaType.ORDER,
        VisitMedia.uploaded_by == current_user.id,
        VisitMedia.uploaded_at >= start_utc,
        VisitMedia.uploaded_at < end_utc,
    )
    orders_count = (await session.execute(order_q)).scalar_one() or 0

    return EmployeeDayDashboardResponse(
        employee_id=str(emp.id),
        employee_name=emp.full_name,
        assigned_outlets_count=outlets_count,
        today_visits_count=v_row.total or 0,
        completed_visits_count=v_row.completed or 0,
        pending_visits_count=v_row.pending or 0,
        in_progress_visits_count=v_row.in_progress or 0,
        collections_today_count=col_count or 0,
        collections_today_amount=col_sum or Decimal("0.00"),
        orders_today_count=orders_count or 0,
    )
