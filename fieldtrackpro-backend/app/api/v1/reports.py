"""
Reports router: REST endpoints for operational analytics, business intelligence,
and monthly historical snapshots.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.reports import (
    EmployeeVisitReportRow,
    ProductivityDashboard,
    GeoVerificationReportRow,
    OverviewReportData,
    EmployeeMasterReportRow,
    OutletReportRow,
    OutstandingAgeingReportRow,
    CollectionReportRow,
    VisitDetailedReportRow,
)
from app.schemas.financial_snapshot import BusinessBIDashboard, MonthlyPeriodRead
from app.services.report_service import report_service

router = APIRouter(tags=["Reports"], dependencies=[Depends(require_role(Role.ADMIN))])


# ---------------------------------------------------------------------------
# 1. OVERVIEW REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/overview", response_model=OverviewReportData)
async def get_overview_report(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    month: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> OverviewReportData:
    """Consolidated KPI overview and dimension summaries."""
    return await report_service.get_overview_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
    )


@router.get("/reports/overview/export")
async def export_overview_report_excel(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    month: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Overview Report with KPIs and dimension breakdown to Excel."""
    overview = await report_service.get_overview_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
    )
    headers = ["Category", "Dimension", "Brand", "Outlets", "Sales (INR)", "Collection (INR)", "Market OS (INR)", ">90d (INR)"]
    rows = []
    for b in overview.brand_breakdown:
        rows.append(["Brand Summary", b.dimension_name, b.brand, b.outlets_count, float(b.sales), float(b.collection), float(b.market_outstanding), float(b.bucket_gt_90)])
    for z in overview.zone_breakdown:
        rows.append(["Zone Summary", z.dimension_name, z.brand, z.outlets_count, float(z.sales), float(z.collection), float(z.market_outstanding), float(z.bucket_gt_90)])
    for f in overview.fos_breakdown:
        rows.append(["FOS Summary", f.dimension_name, f.brand, f.outlets_count, float(f.sales), float(f.collection), float(f.market_outstanding), float(f.bucket_gt_90)])

    kpis = [
        ("Total Outlets", str(overview.total_outlets)),
        ("Total Sales", f"₹{overview.total_sales:,.2f}"),
        ("Total Collection", f"₹{overview.total_collection:,.2f}"),
        ("Market OS", f"₹{overview.total_market_outstanding:,.2f}"),
        ("Overdue >90d", f"₹{overview.total_overdue_gt_90:,.2f}"),
    ]
    filters = {"Brand": brand, "Month": month}

    excel_bytes = report_service.export_report_excel(
        report_title="Overview Report",
        sheet_name="Overview",
        headers=headers,
        data_rows=rows,
        filters_applied=filters,
        summary_kpis=kpis,
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Overview_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 2. EMPLOYEE MASTER REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/employees-master", response_model=list[EmployeeMasterReportRow])
async def get_employees_master_report(
    working_profile: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[EmployeeMasterReportRow]:
    """Employee master directory report with profiles and assigned outlets."""
    return await report_service.get_employee_master_report(
        session=session,
        working_profile=working_profile,
        role=role,
        is_active=is_active,
        query=query,
    )


@router.get("/reports/employees-master/export")
async def export_employees_master_excel(
    working_profile: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports employee master directory to Excel."""
    employees = await report_service.get_employee_master_report(
        session=session,
        working_profile=working_profile,
        role=role,
        is_active=is_active,
        query=query,
    )
    headers = ["Employee ID", "Full Name", "Email", "Phone", "CUG Number", "Working Profile", "Application Role", "Assigned Outlets", "Status"]
    rows = [
        [
            e.employee_code, e.full_name, e.email or "", e.phone_number or "",
            e.cug or "", e.working_profile or "", e.role, e.assigned_outlets_count,
            "Active" if e.is_active else "Inactive",
        ]
        for e in employees
    ]
    excel_bytes = report_service.export_report_excel(
        report_title="Employee Master Report",
        sheet_name="Employees",
        headers=headers,
        data_rows=rows,
        filters_applied={"Profile": working_profile, "Role": role},
        summary_kpis=[("Total Employees", str(len(employees)))],
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Employees_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 3. OUTLETS / CUSTOMERS REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/outlets", response_model=list[OutletReportRow])
async def get_outlets_report(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    location_status: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[OutletReportRow]:
    """Outlet master report with GPS, zones, areas, FOS, and financial aggregates."""
    return await report_service.get_outlet_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        location_status=location_status,
        query=query,
    )


@router.get("/reports/outlets/export")
async def export_outlets_excel(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    location_status: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Outlets Master Report to Excel."""
    outlets = await report_service.get_outlet_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        location_status=location_status,
        query=query,
    )
    headers = ["DMS Code", "Outlet Name", "Zone", "Area", "Assigned FOS", "Contact Person", "Phone", "Location Status", "Latitude", "Longitude", "Sales (INR)", "Collection (INR)", "Market OS (INR)", ">90d (INR)"]
    rows = [
        [
            o.dms_code or "", o.outlet_name, o.zone_name or "", o.area_name or "",
            o.fos_name or "", o.contact_person or "", o.contact_number or "",
            o.location_status, o.latitude or "", o.longitude or "",
            float(o.sales), float(o.collection), float(o.market_outstanding), float(o.overdue_gt_90),
        ]
        for o in outlets
    ]
    tot_s = sum(o.sales for o in outlets)
    tot_c = sum(o.collection for o in outlets)
    tot_os = sum(o.market_outstanding for o in outlets)
    excel_bytes = report_service.export_report_excel(
        report_title="Outlet Directory Report",
        sheet_name="Outlets",
        headers=headers,
        data_rows=rows,
        filters_applied={"Location Status": location_status},
        summary_kpis=[
            ("Total Outlets", str(len(outlets))),
            ("Total Sales", f"₹{tot_s:,.2f}"),
            ("Total Collection", f"₹{tot_c:,.2f}"),
            ("Market OS", f"₹{tot_os:,.2f}"),
        ],
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Outlets_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 4. OUTSTANDING & AGEING REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/outstanding", response_model=list[OutstandingAgeingReportRow])
async def get_outstanding_report(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    ageing_bucket: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[OutstandingAgeingReportRow]:
    """Dedicated Market Outstanding and 7 Ageing Buckets report."""
    return await report_service.get_outstanding_ageing_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        ageing_bucket=ageing_bucket,
        month=month,
        query=query,
    )


@router.get("/reports/outstanding/export")
async def export_outstanding_excel(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    ageing_bucket: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Outstanding & Ageing report to Excel."""
    records = await report_service.get_outstanding_ageing_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        ageing_bucket=ageing_bucket,
        month=month,
        query=query,
    )
    headers = ["Brand", "DMS Code", "Outlet Name", "Zone", "Area", "FOS", "Market OS", "<15d", "15-30d", "30-45d", "45-60d", "60-75d", "75-90d", ">90d", "Severity"]
    rows = [
        [
            r.brand, r.dms_code or "", r.outlet_name, r.zone_name or "", r.area_name or "",
            r.fos_name or "", float(r.market_outstanding), float(r.bucket_lt_15),
            float(r.bucket_15_30), float(r.bucket_30_45), float(r.bucket_45_60),
            float(r.bucket_60_75), float(r.bucket_75_90), float(r.bucket_gt_90),
            r.highest_overdue_bucket,
        ]
        for r in records
    ]
    tot_os = sum(r.market_outstanding for r in records)
    tot_gt90 = sum(r.bucket_gt_90 for r in records)
    excel_bytes = report_service.export_report_excel(
        report_title="Market Outstanding & Ageing Report",
        sheet_name="Outstanding",
        headers=headers,
        data_rows=rows,
        filters_applied={"Brand": brand, "Ageing Bucket": ageing_bucket, "Month": month},
        summary_kpis=[
            ("Overdue Outlets", str(len(records))),
            ("Total Market OS", f"₹{tot_os:,.2f}"),
            ("Total >90 Days Overdue", f"₹{tot_gt90:,.2f}"),
        ],
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Outstanding_Ageing_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 5. COLLECTIONS REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/collections", response_model=list[CollectionReportRow])
async def get_collections_report(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    month: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[CollectionReportRow]:
    """Collections report per outlet and brand."""
    return await report_service.get_collection_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
        query=query,
    )


@router.get("/reports/collections/export")
async def export_collections_excel(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    month: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Collections report to Excel."""
    records = await report_service.get_collection_report(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
        query=query,
    )
    headers = ["Brand", "DMS Code", "Outlet Name", "Zone", "Area", "FOS", "Collection (INR)", "Sales (INR)", "Date"]
    rows = [
        [
            r.brand, r.dms_code or "", r.outlet_name, r.zone_name or "", r.area_name or "",
            r.fos_name or "", float(r.collection_amount), float(r.sales_amount),
            r.snapshot_date.isoformat(),
        ]
        for r in records
    ]
    tot_c = sum(r.collection_amount for r in records)
    excel_bytes = report_service.export_report_excel(
        report_title="Collections Report",
        sheet_name="Collections",
        headers=headers,
        data_rows=rows,
        filters_applied={"Brand": brand, "Month": month},
        summary_kpis=[("Total Collections", f"₹{tot_c:,.2f}")],
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Collections_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 6. OPERATIONAL VISITS DETAILED REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/visits-detailed", response_model=list[VisitDetailedReportRow])
async def get_visits_detailed_report(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[VisitDetailedReportRow]:
    """Detailed operational visits report."""
    return await report_service.get_visits_detailed_report(
        session=session,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        zone_id=zone_id,
        area_id=area_id,
        status=status,
    )


@router.get("/reports/visits-detailed/export")
async def export_visits_detailed_excel(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports detailed operational visits report to Excel."""
    visits = await report_service.get_visits_detailed_report(
        session=session,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        zone_id=zone_id,
        area_id=area_id,
        status=status,
    )
    headers = ["Scheduled Date", "Employee", "Outlet", "DMS Code", "Zone", "Area", "Status", "Check-in", "Check-out", "Duration (mins)", "GPS Verified"]
    rows = [
        [
            v.scheduled_at, v.employee_name, v.customer_name, v.dms_code or "",
            v.zone_name or "", v.area_name or "", v.status, v.check_in_at or "",
            v.check_out_at or "", v.duration_minutes or "", "Yes" if v.is_gps_verified else "No",
        ]
        for v in visits
    ]
    comp = sum(1 for v in visits if v.status == "COMPLETED")
    excel_bytes = report_service.export_report_excel(
        report_title="Visits Operational Report",
        sheet_name="Visits",
        headers=headers,
        data_rows=rows,
        filters_applied={"Status": status},
        summary_kpis=[("Total Visits", str(len(visits))), ("Completed", str(comp))],
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Visits_Report.xlsx"'},
    )


# ---------------------------------------------------------------------------
# 7. PHASE 4: MONTHLY REPORTING PERIODS & HISTORICAL SNAPSHOTS
# ---------------------------------------------------------------------------
@router.get("/reports/monthly-periods", response_model=list[MonthlyPeriodRead])
async def get_monthly_periods(
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[MonthlyPeriodRead]:
    """Lists all historical and current monthly reporting periods."""
    return await report_service.get_monthly_periods(session)


@router.post("/reports/monthly-periods/{period_id}/finalize", response_model=MonthlyPeriodRead)
async def finalize_monthly_period(
    period_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> MonthlyPeriodRead:
    """Finalizes a monthly reporting period and locks historical data."""
    return await report_service.finalize_monthly_period(session, period_id, current_user.id)


@router.post("/reports/monthly-periods/{period_id}/reopen", response_model=MonthlyPeriodRead)
async def reopen_monthly_period(
    period_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> MonthlyPeriodRead:
    """Reopens a finalized monthly reporting period."""
    return await report_service.reopen_monthly_period(session, period_id)


# ---------------------------------------------------------------------------
# 8. LEGACY / PRESERVED ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/reports/employees", response_model=list[EmployeeVisitReportRow])
async def employee_visit_report(
    start_date: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[EmployeeVisitReportRow]:
    data = await report_service.get_employee_visit_report(session, start_date, end_date)
    return [EmployeeVisitReportRow(**row) for row in data]


@router.get("/reports/customers/{customer_id}/history")
async def customer_visit_history(
    customer_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[dict]:
    return await report_service.get_customer_visit_history(session, customer_id)


@router.get("/reports/productivity", response_model=ProductivityDashboard)
async def productivity_dashboard(
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> ProductivityDashboard:
    data = await report_service.get_productivity_dashboard(session)
    return ProductivityDashboard(**data)


@router.get("/reports/geo-verification", response_model=list[GeoVerificationReportRow])
async def geo_verification_report(
    start_date: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[GeoVerificationReportRow]:
    data = await report_service.get_geo_verification_report(session, start_date, end_date)
    return [GeoVerificationReportRow(**row) for row in data]


@router.get("/reports/business-summary", response_model=BusinessBIDashboard)
async def get_business_summary_report(
    brand: Optional[str] = Query(default=None, description="Filter by brand (e.g., Usha, VU, ZBR)"),
    zone_id: Optional[uuid.UUID] = Query(default=None, description="Filter by Zone / Territory ID"),
    area_id: Optional[uuid.UUID] = Query(default=None, description="Filter by Area ID"),
    employee_id: Optional[uuid.UUID] = Query(default=None, description="Filter by assigned Employee ID"),
    month: Optional[str] = Query(default=None, description="Filter by month (YYYY-MM)"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> BusinessBIDashboard:
    return await report_service.get_business_bi_dashboard(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
    )


@router.get("/reports/business-summary/export")
async def export_business_summary_excel(
    brand: Optional[str] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    month: Optional[str] = Query(default=None),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    dashboard = await report_service.get_business_bi_dashboard(
        session=session,
        brand=brand,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=employee_id,
        month=month,
    )
    excel_bytes = report_service.export_business_bi_excel(dashboard)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Business_BI_Report.xlsx"'},
    )
