"""
Reports router: REST endpoints for operational analytics, business intelligence,
and monthly historical snapshots.

Every report has a JSON endpoint and an export endpoint at ``<path>/export``.
The export takes EXACTLY the same filter / date parameters as its JSON
counterpart (no page/skip/limit - exports always contain the FULL filtered set)
plus ``format=xlsx|pdf`` (default xlsx).  Files are named
``<Report>_<YYYYMMDD>_<HHMM>[_filtered].<ext>`` (IST) via Content-Disposition.

Filter semantics (see app/services/report_filters.py):
  * dates are IST calendar days, ``start_date``/``end_date`` inclusive;
  * snapshot reports: ``month`` (YYYY-MM) OR a date range - the range wins when
    both are given; sales/collection are summed over the snapshots in range and
    market outstanding / ageing is the latest snapshot in range per outlet+brand.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.concurrency import run_in_threadpool

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.models.user import Role
from app.schemas.reports import (
    EmployeeVisitReportRow,
    ProductivityDashboard,
    GeoVerificationReportRow,
    OverviewReportData,
    EmployeeMasterReportRow,
    OutletReportRow,
    OutstandingAgeingReportRow,
    OutstandingSummary,
    CollectionReportRow,
    VisitDetailedReportRow,
)
from app.schemas.financial_snapshot import (
    BusinessBIDashboard,
    MonthlyPeriodRead,
    MonthlyPeriodReviewSummary,
    ReopenMonthlyPeriodRequest,
)
from app.services import period_service
from app.services import report_tables as rt
from app.services.report_exports import (
    PDF_MIME, XLSX_MIME, ReportTable, content_disposition, report_filename, to_pdf, to_xlsx,
)
from app.services.report_filters import as_list, as_uuid_list
from app.services.report_service import report_service

#: Financial reports are readable by ADMIN / SUPER_ADMIN and the read-only ACCOUNTANT. Every endpoint that is
#: not a financial read (staff, visits, GPS, productivity, closing / reopening a month) adds ``AdminOnly``.
FinanceRead = Depends(require_role(Role.ADMIN, Role.ACCOUNTANT))
AdminOnly = Depends(require_role(Role.ADMIN))

router = APIRouter(tags=["Reports"], dependencies=[FinanceRead])

ExportFormat = Literal["xlsx", "pdf"]

_DATE_DOC = "Inclusive IST calendar date (YYYY-MM-DD)"
_MONTH_DOC = "Calendar month YYYY-MM. Ignored when start_date/end_date is given (the date range wins)."


# ---------------------------------------------------------------------------
# Shared parameter sets (the JSON endpoint and its export use the SAME dependency)
# ---------------------------------------------------------------------------
_MULTI_DOC = " Several values: repeat the parameter or separate with commas (values OR together)."


def _multi(values: Optional[list[str]]) -> Optional[str]:
    """Repeated / comma-separated query values -> one comma-joined string (None when nothing is selected)."""
    items = as_list(values)
    return ",".join(items) if items else None


def _multi_ids(values: Optional[list[str]]) -> Optional[str]:
    ids = as_uuid_list(values)
    return ",".join(str(i) for i in ids) if ids else None


def bi_params(
    brand: Optional[list[str]] = Query(default=None, description="Brand (e.g. Oppo, USHA, Unattributed)." + _MULTI_DOC),
    zone_id: Optional[uuid.UUID] = Query(default=None, description="Zone / Territory ID"),
    area_id: Optional[uuid.UUID] = Query(default=None, description="Area ID"),
    employee_id: Optional[list[str]] = Query(default=None, description="Assigned FOS employee id." + _MULTI_DOC),
    month: Optional[list[str]] = Query(default=None, description=_MONTH_DOC + _MULTI_DOC),
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
) -> dict:
    return dict(brand=_multi(brand), zone_id=zone_id, area_id=area_id, employee_id=_multi_ids(employee_id),
                month=_multi(month), start_date=start_date, end_date=end_date)


def outstanding_params(
    brand: Optional[list[str]] = Query(default=None, description="Brand." + _MULTI_DOC),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[list[str]] = Query(default=None, description="Assigned FOS employee id." + _MULTI_DOC),
    ageing_bucket: Optional[str] = Query(default=None, description="'>90', '75-90', '60-75', '45-60', '30-45', '15-30', '<15'"),
    month: Optional[list[str]] = Query(default=None, description=_MONTH_DOC + _MULTI_DOC),
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    query: Optional[str] = Query(default=None, description="Outlet name/code, zone, area or employee"),
) -> dict:
    return dict(brand=_multi(brand), zone_id=zone_id, area_id=area_id, employee_id=_multi_ids(employee_id),
                ageing_bucket=ageing_bucket, month=_multi(month), start_date=start_date, end_date=end_date, query=query)


def outlets_params(
    brand: Optional[list[str]] = Query(default=None, description="Brand." + _MULTI_DOC),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[list[str]] = Query(default=None, description="Assigned FOS employee id." + _MULTI_DOC),
    location_status: Optional[str] = Query(default=None),
    month: Optional[list[str]] = Query(default=None, description=_MONTH_DOC + _MULTI_DOC),
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    query: Optional[str] = Query(default=None),
) -> dict:
    return dict(brand=_multi(brand), zone_id=zone_id, area_id=area_id, employee_id=_multi_ids(employee_id),
                location_status=location_status, month=_multi(month), start_date=start_date, end_date=end_date, query=query)


def collections_report_params(
    brand: Optional[list[str]] = Query(default=None, description="Brand." + _MULTI_DOC),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    employee_id: Optional[list[str]] = Query(default=None, description="Assigned FOS employee id." + _MULTI_DOC),
    month: Optional[list[str]] = Query(default=None, description=_MONTH_DOC + _MULTI_DOC),
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    query: Optional[str] = Query(default=None),
) -> dict:
    return dict(brand=_multi(brand), zone_id=zone_id, area_id=area_id, employee_id=_multi_ids(employee_id),
                month=_multi(month), start_date=start_date, end_date=end_date, query=query)


def visits_params(
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None, description="PENDING | IN_PROGRESS | COMPLETED | MISSED | FLAGGED"),
    query: Optional[str] = Query(default=None, description="Employee, outlet, DMS code, zone or area"),
) -> dict:
    return dict(start_date=start_date, end_date=end_date, employee_id=employee_id, zone_id=zone_id,
                area_id=area_id, status=status, query=query)


def geo_params(
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    query: Optional[str] = Query(default=None, description="Employee, outlet or DMS code"),
) -> dict:
    return dict(start_date=start_date, end_date=end_date, employee_id=employee_id, zone_id=zone_id,
                area_id=area_id, query=query)


def staff_params(
    start_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    end_date: Optional[date] = Query(default=None, description=_DATE_DOC),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    zone_id: Optional[uuid.UUID] = Query(default=None),
    area_id: Optional[uuid.UUID] = Query(default=None),
    query: Optional[str] = Query(default=None, description="Employee name or code"),
) -> dict:
    return dict(start_date=start_date, end_date=end_date, employee_id=employee_id, zone_id=zone_id,
                area_id=area_id, query=query)


async def _file_response(
    fmt: str, tables: list[ReportTable], prefix: str, filtered: bool, pdf_tables: Optional[list[ReportTable]] = None
) -> Response:
    """Render ``tables`` as xlsx (all tables = sheets) or pdf (``pdf_tables`` or all tables)."""
    if fmt == "pdf":
        data = await run_in_threadpool(to_pdf, pdf_tables or tables)
        mime, ext = PDF_MIME, "pdf"
    elif fmt == "xlsx":
        data = await run_in_threadpool(to_xlsx, tables)
        mime, ext = XLSX_MIME, "xlsx"
    else:  # pragma: no cover - guarded by the Literal type
        raise BaseAPIException(detail="format must be xlsx or pdf", status_code=422, error_code="INVALID_FORMAT")
    name = report_filename(prefix, ext, filtered)
    return Response(content=data, media_type=mime, headers={"Content-Disposition": content_disposition(name)})


# ---------------------------------------------------------------------------
# 1. OVERVIEW REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/overview", response_model=OverviewReportData)
async def get_overview_report(
    f: dict = Depends(bi_params),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> OverviewReportData:
    """Consolidated KPI overview and dimension summaries."""
    return await report_service.get_overview_report(session=session, **f)


@router.get("/reports/overview/export")
async def export_overview_report(
    f: dict = Depends(bi_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Overview Report (KPIs + dimension breakdown) to Excel / PDF."""
    overview = await report_service.get_overview_report(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "month", "brand", "zone", "area", "employee"], **f
    )
    table = rt.build_overview_table(overview, filters)
    return await _file_response(format, [table], "Overview", filtered)


# ---------------------------------------------------------------------------
# 2. EMPLOYEE MASTER REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/employees-master", dependencies=[AdminOnly], response_model=list[EmployeeMasterReportRow])
async def get_employees_master_report(
    working_profile: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    query: Optional[str] = Query(default=None),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
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
        skip=skip,
        limit=limit,
    )


@router.get("/reports/employees-master/export", dependencies=[AdminOnly])
async def export_employees_master(
    working_profile: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    query: Optional[str] = Query(default=None),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports employee master directory to Excel / PDF."""
    employees = await report_service.get_employee_master_report(
        session=session, working_profile=working_profile, role=role, is_active=is_active, query=query,
    )
    filters = [
        ("Working profile", working_profile if working_profile and working_profile != "ALL" else "All"),
        ("Role", role if role and role != "ALL" else "All"),
        ("Active", "All" if is_active is None else ("Active only" if is_active else "Inactive only")),
        ("Search", f'"{query.strip()}"' if query and query.strip() else "None"),
    ]
    filtered = any(v not in ("All", "None") for _, v in filters)
    table = rt.build_employee_master_table(employees, filters)
    return await _file_response(format, [table], "Employee_Master", filtered)


# ---------------------------------------------------------------------------
# 3. OUTLETS / CUSTOMERS REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/outlets", response_model=list[OutletReportRow])
async def get_outlets_report(
    f: dict = Depends(outlets_params),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[OutletReportRow]:
    """Outlet master report (one row per outlet) with GPS, zones, areas, FOS, and financial aggregates."""
    return await report_service.get_outlet_report(session=session, skip=skip, limit=limit, **f)


@router.get("/reports/outlets/export")
async def export_outlets(
    f: dict = Depends(outlets_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the Outlets report (ALL filtered rows) to Excel / PDF."""
    outlets = await report_service.get_outlet_report(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "month", "brand", "zone", "area", "employee", "location_status", "search"], **f
    )
    table = rt.build_outlets_table(outlets, filters)
    return await _file_response(format, [table], "Outlets", filtered)


# ---------------------------------------------------------------------------
# 4. OUTSTANDING & AGEING REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/outstanding", response_model=list[OutstandingAgeingReportRow])
async def get_outstanding_report(
    f: dict = Depends(outstanding_params),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[OutstandingAgeingReportRow]:
    """Market Outstanding and 7 Ageing Buckets, one row per outlet+brand. Same source and filters as the
    dashboard (snapshots when the period has any, otherwise live Tally invoices). Pages with skip/limit; the
    totals of the whole filtered set are at /reports/outstanding/summary."""
    return await report_service.get_outstanding_ageing_report(session=session, skip=skip, limit=limit, **f)


@router.get("/reports/outstanding/summary", response_model=OutstandingSummary)
async def get_outstanding_summary(
    f: dict = Depends(outstanding_params),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> OutstandingSummary:
    """Totals of the whole filtered outstanding report (accounts, outlets, zones, areas, market OS, buckets)."""
    return await report_service.get_outstanding_summary(session=session, **f)


@router.get("/reports/outstanding/export")
async def export_outstanding(
    f: dict = Depends(outstanding_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Outstanding & Ageing report (ALL filtered rows) to Excel / PDF."""
    records = await report_service.get_outstanding_ageing_report(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "month", "brand", "zone", "area", "employee", "ageing", "search"], **f
    )
    as_of = max((r.as_of_date for r in records if r.as_of_date), default=None)
    table = rt.build_outstanding_table(records, filters, as_of)
    tot_os = sum((r.market_outstanding for r in records), 0)
    from app.services.report_exports import fmt_inr
    table.kpis = [("Accounts", str(len(records))), ("Market OS", f"₹{fmt_inr(tot_os)}")]
    return await _file_response(format, [table], "Outstanding", filtered)


# ---------------------------------------------------------------------------
# 5. COLLECTIONS REPORT (snapshot based)
# ---------------------------------------------------------------------------
@router.get("/reports/collections", response_model=list[CollectionReportRow])
async def get_collections_report(
    f: dict = Depends(collections_report_params),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[CollectionReportRow]:
    """Collections report per outlet and brand (summed across the snapshots in the period)."""
    return await report_service.get_collection_report(session=session, skip=skip, limit=limit, **f)


@router.get("/reports/collections/export")
async def export_collections_report(
    f: dict = Depends(collections_report_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the snapshot Collections report (ALL filtered rows) to Excel / PDF."""
    records = await report_service.get_collection_report(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "month", "brand", "zone", "area", "employee", "search"], **f
    )
    table = rt.build_collections_report_table(records, filters)
    return await _file_response(format, [table], "Collections_Report", filtered)


# ---------------------------------------------------------------------------
# 6. OPERATIONAL VISITS DETAILED REPORT
# ---------------------------------------------------------------------------
@router.get("/reports/visits-detailed", dependencies=[AdminOnly], response_model=list[VisitDetailedReportRow])
async def get_visits_detailed_report(
    f: dict = Depends(visits_params),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[VisitDetailedReportRow]:
    """Detailed operational visits report (date range = IST calendar days of the scheduled time)."""
    return await report_service.get_visits_detailed_report(session=session, skip=skip, limit=limit, **f)


@router.get("/reports/visits-detailed/export", dependencies=[AdminOnly])
async def export_visits_detailed(
    f: dict = Depends(visits_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the detailed visits report (ALL filtered rows) to Excel / PDF."""
    visits = await report_service.get_visits_detailed_report(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "zone", "area", "employee", "status", "search"], **f
    )
    table = rt.build_visits_table(visits, filters)
    return await _file_response(format, [table], "Visits", filtered)


# ---------------------------------------------------------------------------
# 7. PHASE 4: MONTHLY REPORTING PERIODS & HISTORICAL SNAPSHOTS
# ---------------------------------------------------------------------------
async def _periods_read(session, only_with_data: bool) -> list[MonthlyPeriodRead]:
    periods = await period_service.ensure_monthly_periods_synced(session, only_with_data=only_with_data)
    return [
        MonthlyPeriodRead(
            id=p.id,
            period_year=p.period_year,
            period_month=p.period_month,
            period_name=p.period_name,
            status=p.status.value if hasattr(p.status, "value") else str(p.status),
            snapshot_count=p.snapshot_count,
            total_outlets=p.total_outlets,
            total_sales=p.total_sales,
            total_collection=p.total_collection,
            total_market_os=p.total_market_os,
            total_overdue_gt_90=p.total_overdue_gt_90,
            opened_at=p.opened_at,
            finalized_at=p.finalized_at,
            finalized_by=p.finalized_by,
            reopened_at=p.reopened_at,
            reopened_by=p.reopened_by,
            reopen_reason=p.reopen_reason,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in periods
    ]


@router.get("/reports/monthly-periods", response_model=list[MonthlyPeriodRead])
async def get_monthly_periods(
    only_with_data: bool = Query(default=False, description="Filter for periods that contain real imported transaction data"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[MonthlyPeriodRead]:
    """Lists all historical and current monthly reporting periods with automatic month rollover."""
    return await _periods_read(session, only_with_data)


@router.get("/reports/monthly-periods/export")
async def export_monthly_periods(
    only_with_data: bool = Query(default=True, description="Only periods that contain imported data (as shown in the UI)"),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the Monthly Snapshots (accounting periods) table to Excel / PDF."""
    periods = await _periods_read(session, only_with_data)
    if only_with_data:
        periods = [
            p for p in periods
            if float(p.total_sales or 0) > 0 or float(p.total_collection or 0) > 0
            or (p.snapshot_count or 0) > 0 or (p.total_outlets or 0) > 0
        ]
    filters = [("Periods", "Periods with data" if only_with_data else "All periods")]
    table = rt.build_periods_table(periods, filters)
    return await _file_response(format, [table], "Monthly_Snapshots", False)


@router.get("/reports/monthly-periods/{period_id}/review", response_model=MonthlyPeriodReviewSummary)
async def get_monthly_period_review(
    period_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> MonthlyPeriodReviewSummary:
    """Pre-closing operational and financial summary for Admin review."""
    return await period_service.get_monthly_period_review(period_id, session)


@router.post("/reports/monthly-periods/{period_id}/finalize", dependencies=[AdminOnly], response_model=MonthlyPeriodRead)
async def finalize_monthly_period(
    period_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> MonthlyPeriodRead:
    """Finalizes a monthly reporting period and locks financial transactions."""
    return await period_service.finalize_monthly_period(period_id, current_user.id, session)


@router.post("/reports/monthly-periods/{period_id}/reopen", dependencies=[AdminOnly], response_model=MonthlyPeriodRead)
async def reopen_monthly_period(
    period_id: uuid.UUID,
    payload: Optional[ReopenMonthlyPeriodRequest] = None,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> MonthlyPeriodRead:
    """Reopens a finalized monthly reporting period with mandatory reason tracking."""
    reason = payload.reason if payload else "Administrative adjustment"
    return await period_service.reopen_monthly_period(period_id, current_user.id, reason, session)


# ---------------------------------------------------------------------------
# 8. FIELD STAFF / GEO / PRESERVED ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/reports/employees", dependencies=[AdminOnly], response_model=list[EmployeeVisitReportRow])
async def employee_visit_report(
    f: dict = Depends(staff_params),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[EmployeeVisitReportRow]:
    """Field staff visit counts (date range = IST days of the scheduled time)."""
    data = await report_service.get_employee_visit_report(session, **f)
    return [EmployeeVisitReportRow(**row) for row in data]


@router.get("/reports/employees/export", dependencies=[AdminOnly])
async def export_employee_visit_report(
    f: dict = Depends(staff_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the Field Staff table (ALL filtered rows) to Excel / PDF."""
    data = await report_service.get_employee_visit_report(session, **f)
    filters, filtered = await rt.describe_filters(session, ["date", "zone", "area", "employee", "search"], **f)
    table = rt.build_staff_table(data, filters)
    return await _file_response(format, [table], "Field_Staff", filtered)


@router.get("/reports/customers/{customer_id}/history", dependencies=[AdminOnly])
async def customer_visit_history(
    customer_id: uuid.UUID,
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[dict]:
    return await report_service.get_customer_visit_history(session, customer_id)


@router.get("/reports/productivity", dependencies=[AdminOnly], response_model=ProductivityDashboard)
async def productivity_dashboard(
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> ProductivityDashboard:
    data = await report_service.get_productivity_dashboard(session)
    return ProductivityDashboard(**data)


@router.get("/reports/geo-verification", dependencies=[AdminOnly], response_model=list[GeoVerificationReportRow])
async def geo_verification_report(
    f: dict = Depends(geo_params),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> list[GeoVerificationReportRow]:
    data = await report_service.get_geo_verification_report(session, skip=skip, limit=limit, **f)
    return [GeoVerificationReportRow(**row) for row in data]


@router.get("/reports/geo-verification/export", dependencies=[AdminOnly])
async def export_geo_verification(
    f: dict = Depends(geo_params),
    format: ExportFormat = Query(default="xlsx"),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports the Geo Verification audit (ALL filtered rows) to Excel / PDF."""
    data = await report_service.get_geo_verification_report(session, **f)
    filters, filtered = await rt.describe_filters(session, ["date", "zone", "area", "employee", "search"], **f)
    table = rt.build_geo_table(data, filters)
    return await _file_response(format, [table], "Geo_Verification", filtered)


# ---------------------------------------------------------------------------
# 9. FINANCIAL & BUSINESS INTELLIGENCE
# ---------------------------------------------------------------------------
@router.get("/reports/business-summary", response_model=BusinessBIDashboard)
async def get_business_summary_report(
    f: dict = Depends(bi_params),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
) -> BusinessBIDashboard:
    return await report_service.get_business_bi_dashboard(session=session, **f)


@router.get("/reports/business-summary/export")
async def export_business_summary(
    f: dict = Depends(bi_params),
    format: ExportFormat = Query(default="xlsx"),
    view: Literal["brand", "zone", "area", "fos", "raw"] = Query(
        default="brand", description="PDF only: which summary view to print (Excel always has every sheet)"
    ),
    current_user: CurrentUser = None,
    session=Depends(get_async_session),
):
    """Exports Financial & BI: Excel = one sheet per view; PDF = the requested ``view``."""
    dashboard = await report_service.get_business_bi_dashboard(session=session, **f)
    filters, filtered = await rt.describe_filters(
        session, ["date", "month", "brand", "zone", "area", "employee"], **f
    )
    tables = rt.build_bi_tables(dashboard, filters)
    pdf_tables = [tables[rt.BI_VIEWS.index(view)]]
    return await _file_response(format, tables, "Financial_BI", filtered, pdf_tables=pdf_tables)
