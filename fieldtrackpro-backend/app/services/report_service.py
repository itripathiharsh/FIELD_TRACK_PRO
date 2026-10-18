"""
Report Service: High-performance business intelligence, operational analytics,
and monthly snapshot management.

Filter / date semantics are documented in app/services/report_filters.py:
  * all dates are IST calendar dates (timestamps are filtered on IST day windows);
  * snapshot reports: FLOWS (sales, collection) are summed across the snapshots
    in the window, STOCK (market outstanding, ageing buckets) is the LATEST
    snapshot in the window per outlet+brand and is never summed across dates.

Excel / PDF generation lives in app/services/report_exports.py.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, or_, and_, func, desc, case, exists, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.user import User, Role
from app.models.territory import Territory
from app.models.area import Area
from app.models.visit import Visit, VisitStatus
from app.models.geo_verification_log import GeoVerificationLog
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.employee_area_assignment import EmployeeAreaAssignment
from app.models.invoice import Invoice, InvoiceSource
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.monthly_reporting_period import MonthlyReportingPeriod, MonthlyPeriodStatus
from app.models.payment import Payment, PaymentBrandAllocation, PaymentSource, PaymentStatus
from app.services import payment_tally
from app.schemas.financial_snapshot import (
    BusinessBIDashboard,
    BusinessSummaryRow,
    MonthlyPeriodRead,
)
from app.schemas.reports import (
    OverviewReportData,
    EmployeeMasterReportRow,
    OutletReportRow,
    OutstandingAgeingReportRow,
    CollectionReportRow,
    VisitDetailedReportRow,
    GeoVerificationReportRow,
)
from app.services.brand_service import (
    resolve_canonical_brand_name,
    normalize_brand_name,
    BRAND_ALIASES,
)
from app.services.report_filters import (
    SnapshotWindow,
    ist_now,
    like_pattern,
    resolve_snapshot_window,
    validate_date_order,
    where_date_range,
    where_ist_range,
)

LIKE_ESCAPE = "\\"
_S = OutletFinancialSnapshot
_ECA = EmployeeCustomerAssignment


def _get_brand_filter_aliases(brand_query: str) -> list[str]:
    """Resolve brand query to canonical name and all alias strings (e.g. 'ZBR' -> ['zbr', 'zebronics'])."""
    canon = resolve_canonical_brand_name(brand_query)
    canon_norm = normalize_brand_name(canon)
    aliases = [k for k, v in BRAND_ALIASES.items() if v == canon_norm]
    if canon_norm not in aliases:
        aliases.append(canon_norm)
    raw_norm = normalize_brand_name(brand_query)
    if raw_norm and raw_norm not in aliases:
        aliases.append(raw_norm)
    return aliases


def _brand_aliases(brand: Optional[str]) -> Optional[list[str]]:
    if brand and brand != "ALL":
        return _get_brand_filter_aliases(brand)
    return None


def _snapshot_window_where(stmt, window: SnapshotWindow):
    if window.start is not None:
        stmt = stmt.where(_S.snapshot_date >= window.start)
    if window.end is not None:
        stmt = stmt.where(_S.snapshot_date <= window.end)
    return stmt


def effective_snapshots(window: SnapshotWindow, brand: Optional[str] = None):
    """
    One row per (outlet, brand) that has at least one snapshot in ``window``:

      * STOCK columns (market_outstanding, bucket_*, snapshot_date) come from the
        LATEST snapshot in the window - never summed across dates;
      * FLOW columns ``sales_sum`` / ``collection_sum`` are summed over every
        snapshot in the window.
    """
    part = (_S.customer_id, _S.brand)
    inner = select(
        _S.id.label("id"),
        _S.customer_id.label("customer_id"),
        _S.brand.label("brand"),
        _S.snapshot_date.label("snapshot_date"),
        _S.market_outstanding.label("market_outstanding"),
        _S.bucket_lt_15.label("bucket_lt_15"),
        _S.bucket_15_30.label("bucket_15_30"),
        _S.bucket_30_45.label("bucket_30_45"),
        _S.bucket_45_60.label("bucket_45_60"),
        _S.bucket_60_75.label("bucket_60_75"),
        _S.bucket_75_90.label("bucket_75_90"),
        _S.bucket_gt_90.label("bucket_gt_90"),
        func.sum(_S.sales).over(partition_by=part).label("sales_sum"),
        func.sum(_S.collection).over(partition_by=part).label("collection_sum"),
        func.count(_S.id).over(partition_by=part).label("snapshot_count"),
        func.min(_S.snapshot_date).over(partition_by=part).label("first_snapshot_date"),
        func.row_number().over(partition_by=part, order_by=(_S.snapshot_date.desc(), _S.id.desc())).label("rn"),
    )
    inner = _snapshot_window_where(inner, window)
    aliases = _brand_aliases(brand)
    if aliases:
        inner = inner.where(func.lower(_S.brand).in_(aliases))
    win = inner.subquery("snap_window")
    return select(win).where(win.c.rn == 1).subquery("eff")


def _employee_filter(employee_id: Optional[uuid.UUID]):
    """EXISTS (not a join) so an outlet with several employees is never fanned out."""
    return exists(
        select(literal(1))
        .select_from(_ECA)
        .where(_ECA.customer_id == Customer.id, _ECA.employee_id == employee_id)
        .correlate(Customer)
    )


def _outlet_search_clause(query: str, include_contact: bool = False):
    pattern = like_pattern(query)
    emp_match = exists(
        select(literal(1))
        .select_from(_ECA)
        .join(Employee, Employee.id == _ECA.employee_id)
        .where(_ECA.customer_id == Customer.id, func.lower(Employee.full_name).like(pattern, escape=LIKE_ESCAPE))
        .correlate(Customer)
    )
    parts = [
        func.lower(Customer.name).like(pattern, escape=LIKE_ESCAPE),
        func.lower(Customer.outlet_code).like(pattern, escape=LIKE_ESCAPE),
        func.lower(Territory.name).like(pattern, escape=LIKE_ESCAPE),
        func.lower(Area.name).like(pattern, escape=LIKE_ESCAPE),
        emp_match,
    ]
    if include_contact:
        parts += [
            func.lower(Customer.contact_person).like(pattern, escape=LIKE_ESCAPE),
            func.lower(Customer.contact_number).like(pattern, escape=LIKE_ESCAPE),
            func.lower(Customer.address).like(pattern, escape=LIKE_ESCAPE),
        ]
    return or_(*parts)


async def _load_fos_map(
    session: AsyncSession, only_employee: Optional[uuid.UUID] = None
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """customer_id -> [(employee_id, name)] assigned FOS list (sorted by name)."""
    stmt = (
        select(_ECA.customer_id, Employee.id, Employee.full_name)
        .join(Employee, Employee.id == _ECA.employee_id)
        .order_by(Employee.full_name.asc(), Employee.id.asc())
    )
    if only_employee:
        stmt = stmt.where(Employee.id == only_employee)
    out: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for cid, eid, name in (await session.execute(stmt)).all():
        out.setdefault(cid, []).append((eid, name))
    return out


def _fos_label(fos: list[tuple[uuid.UUID, str]]) -> str:
    return ", ".join(n for _, n in fos) if fos else "Unassigned"


def _highest_bucket_label(r) -> str:
    if r.bucket_gt_90 > 0:
        return "Critical (>90d)"
    if r.bucket_75_90 > 0:
        return "Severe (75-90d)"
    if r.bucket_60_75 > 0:
        return "High (60-75d)"
    if r.bucket_45_60 > 0:
        return "Medium (45-60d)"
    if r.bucket_30_45 > 0:
        return "Low (30-45d)"
    if r.bucket_15_30 > 0:
        return "Early (15-30d)"
    return "Normal (<15d)"


_BUCKET_FILTERS = {
    ">90": "bucket_gt_90", "gt_90": "bucket_gt_90",
    "75-90": "bucket_75_90", "75_90": "bucket_75_90",
    "60-75": "bucket_60_75", "60_75": "bucket_60_75",
    "45-60": "bucket_45_60", "45_60": "bucket_45_60",
    "30-45": "bucket_30_45", "30_45": "bucket_30_45",
    "15-30": "bucket_15_30", "15_30": "bucket_15_30",
    "<15": "bucket_lt_15", "lt_15": "bucket_lt_15",
}


@dataclass
class _BiEntry:
    """One outlet+brand figure set feeding the BI aggregation (snapshot or live-invoice sourced)."""

    key: Any
    customer_id: uuid.UUID
    brand: str
    outlet_name: str
    dms_code: str
    zone: str
    area: str
    fos: list
    sales: Decimal
    collection: Decimal
    market_os: Decimal
    buckets: list  # 7 Decimals: <15, 15-30, 30-45, 45-60, 60-75, 75-90, >90
    as_of: Optional[date] = None
class ReportService:

    @staticmethod
    async def get_overview_report(
        session: AsyncSession,
        brand: Optional[str] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        month: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> OverviewReportData:
        """
        Consolidated Overview KPIs based on real database records.
        """
        window = resolve_snapshot_window(month, start_date, end_date)
        # Get BI Dashboard aggregations for the filter
        bi_dash = await ReportService.get_business_bi_dashboard(
            session=session,
            brand=brand,
            zone_id=zone_id,
            area_id=area_id,
            employee_id=employee_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
        )

        # Count total active employees within filter scope
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

        # Operational visits metrics (IST day windows when a month / date range is given)
        visit_stmt = select(
            func.count(Visit.id).label("total_visits"),
            func.sum(case((Visit.status == VisitStatus.COMPLETED, 1), else_=0)).label("completed_visits"),
        )
        if employee_id:
            visit_stmt = visit_stmt.where(Visit.employee_id == employee_id)
        if zone_id or area_id:
            visit_stmt = visit_stmt.join(Customer, Visit.customer_id == Customer.id)
            if zone_id:
                visit_stmt = visit_stmt.where(Customer.territory_id == zone_id)
            if area_id:
                visit_stmt = visit_stmt.where(Customer.area_id == area_id)
        if not window.is_all:
            visit_stmt = where_ist_range(visit_stmt, Visit.scheduled_at, window.start, window.end)

        visit_res = await session.execute(visit_stmt)
        v_row = visit_res.one_or_none()
        total_visits = v_row.total_visits or 0 if v_row else 0
        completed_visits = v_row.completed_visits or 0 if v_row else 0
        completion_rate = round((completed_visits / total_visits * 100), 1) if total_visits > 0 else 0.0

        return OverviewReportData(
            total_employees=total_employees,
            total_outlets=bi_dash.total_outlets,
            total_sales=bi_dash.total_sales,
            total_collection=bi_dash.total_collection,
            total_market_outstanding=bi_dash.total_market_outstanding,
            total_overdue_gt_90=bi_dash.total_overdue_gt_90,
            total_visits=total_visits,
            completed_visits=completed_visits,
            completion_rate=completion_rate,
            brand_breakdown=bi_dash.brand_summaries,
            zone_breakdown=bi_dash.zone_summaries,
            fos_breakdown=bi_dash.fos_summaries,
            data_source=bi_dash.data_source,
            data_source_note=bi_dash.data_source_note,
            as_of_date=bi_dash.as_of_date,
        )

    @staticmethod
    async def get_employee_master_report(
        session: AsyncSession,
        working_profile: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        query: Optional[str] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[EmployeeMasterReportRow]:
        """
        Detailed employee master reporting with real working profile, CUG, and assigned outlet counts.
        """
        stmt = (
            select(
                Employee,
                User.role.label("app_role"),
                User.is_active.label("user_active"),
                User.email.label("user_email"),
                User.mobile_number.label("user_mobile"),
                func.count(EmployeeCustomerAssignment.customer_id).label("assigned_outlets_count"),
            )
            .join(User, Employee.user_id == User.id)
            .outerjoin(EmployeeCustomerAssignment, EmployeeCustomerAssignment.employee_id == Employee.id)
            .group_by(Employee.id, User.id)
            .order_by(Employee.employee_code.asc())
        )

        if working_profile and working_profile != "ALL":
            stmt = stmt.where(func.lower(Employee.working_profile) == func.lower(working_profile))
        if role and role != "ALL":
            stmt = stmt.where(User.role == Role(role))
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if query:
            q_str = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Employee.full_name).like(q_str),
                    func.lower(Employee.employee_code).like(q_str),
                    func.lower(User.mobile_number).like(q_str),
                    func.lower(Employee.cug).like(q_str),
                )
            )

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        res = await session.execute(stmt)
        rows = res.all()

        out = []
        for emp, app_role, user_act, u_email, u_mobile, outlet_cnt in rows:
            out.append(
                EmployeeMasterReportRow(
                    employee_id=emp.id,
                    employee_code=emp.employee_code,
                    full_name=emp.full_name,
                    email=u_email or "",
                    phone_number=u_mobile or emp.cug or "",
                    cug=emp.cug or "",
                    working_profile=emp.working_profile or "FOS",
                    role=app_role.value if hasattr(app_role, "value") else str(app_role),
                    is_active=user_act,
                    assigned_outlets_count=outlet_cnt or 0,
                    zone_names=[],
                )
            )
        return out

    @staticmethod
    async def get_outlet_report(
        session: AsyncSession,
        brand: Optional[str] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        location_status: Optional[str] = None,
        query: Optional[str] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        month: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[OutletReportRow]:
        """
        Outlet directory report: ONE row per outlet (employees are aggregated into
        ``fos_name``).  Financials follow the snapshot window semantics: sales /
        collection are summed across snapshots in the window, market outstanding
        and >90d are the latest snapshot per outlet+brand (summed over brands).
        Outlets with no snapshot in the window are still listed (zero financials)
        unless a brand filter is applied.
        """
        from app.services.customer_service import extract_coords

        window = resolve_snapshot_window(month, start_date, end_date)
        eff = effective_snapshots(window, brand)
        agg = (
            select(
                eff.c.customer_id.label("customer_id"),
                func.coalesce(func.sum(eff.c.sales_sum), Decimal("0.00")).label("tot_sales"),
                func.coalesce(func.sum(eff.c.collection_sum), Decimal("0.00")).label("tot_collection"),
                func.coalesce(func.sum(eff.c.market_outstanding), Decimal("0.00")).label("tot_os"),
                func.coalesce(func.sum(eff.c.bucket_gt_90), Decimal("0.00")).label("tot_gt_90"),
                func.max(eff.c.snapshot_date).label("as_of"),
            )
            .group_by(eff.c.customer_id)
            .subquery("agg")
        )

        stmt = (
            select(
                Customer.id,
                Customer.name,
                Customer.outlet_code,
                Customer.contact_person,
                Customer.contact_number,
                Customer.address,
                Customer.location,
                Customer.geofence_radius_m,
                Customer.location_status,
                Territory.name.label("zone_name"),
                Area.name.label("area_name"),
                func.coalesce(agg.c.tot_sales, Decimal("0.00")).label("tot_sales"),
                func.coalesce(agg.c.tot_collection, Decimal("0.00")).label("tot_collection"),
                func.coalesce(agg.c.tot_os, Decimal("0.00")).label("tot_os"),
                func.coalesce(agg.c.tot_gt_90, Decimal("0.00")).label("tot_gt_90"),
                agg.c.as_of.label("as_of"),
            )
            .outerjoin(Territory, Customer.territory_id == Territory.id)
            .outerjoin(Area, Customer.area_id == Area.id)
            .outerjoin(agg, agg.c.customer_id == Customer.id)
            .order_by(Customer.name.asc(), Customer.id.asc())
        )
        if zone_id:
            stmt = stmt.where(Customer.territory_id == zone_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if employee_id:
            stmt = stmt.where(_employee_filter(employee_id))
        if location_status and location_status != "ALL":
            stmt = stmt.where(Customer.location_status == location_status)
        if brand and brand != "ALL":
            stmt = stmt.where(agg.c.customer_id.is_not(None))
        if query:
            stmt = stmt.where(_outlet_search_clause(query, include_contact=True))

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = (await session.execute(stmt)).all()
        fos_map = await _load_fos_map(session)

        out = []
        for (
            c_id, c_name, c_dms, c_contact_person, c_contact_number, c_addr,
            c_loc, c_radius, c_loc_status, z_name, a_name, s, col, os_amt, gt90, as_of,
        ) in rows:
            lat, lng = None, None
            if c_loc is not None:
                lat_val, lng_val = extract_coords(c_loc)
                if lat_val != 0.0 or lng_val != 0.0:
                    lat, lng = lat_val, lng_val

            out.append(
                OutletReportRow(
                    customer_id=c_id,
                    dms_code=c_dms or "",
                    outlet_name=c_name,
                    contact_person=c_contact_person,
                    contact_number=c_contact_number,
                    address=c_addr,
                    zone_name=z_name or "Unassigned",
                    area_name=a_name or "Unassigned",
                    fos_name=_fos_label(fos_map.get(c_id, [])),
                    brand=brand or "Multi-Brand",
                    latitude=lat,
                    longitude=lng,
                    geofence_radius_m=c_radius or 75,
                    location_status=c_loc_status or "MISSING",
                    sales=s,
                    collection=col,
                    market_outstanding=os_amt,
                    overdue_gt_90=gt90,
                    as_of_date=as_of,
                )
            )
        return out

    @staticmethod
    async def get_outstanding_ageing_report(
        session: AsyncSession,
        brand: Optional[str] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        ageing_bucket: Optional[str] = None,
        month: Optional[str] = None,
        query: Optional[str] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[OutstandingAgeingReportRow]:
        """
        Market Outstanding & Ageing Buckets: STOCK figures from the LATEST snapshot
        in the window per outlet+brand (never summed across snapshot dates).
        """
        window = resolve_snapshot_window(month, start_date, end_date)
        eff = effective_snapshots(window, brand)
        stmt = (
            select(
                eff,
                Customer.name.label("customer_name"),
                Customer.outlet_code.label("dms_code"),
                Territory.name.label("zone_name"),
                Area.name.label("area_name"),
            )
            .join(Customer, eff.c.customer_id == Customer.id)
            .outerjoin(Territory, Customer.territory_id == Territory.id)
            .outerjoin(Area, Customer.area_id == Area.id)
            .where(eff.c.market_outstanding > 0)
            .order_by(eff.c.bucket_gt_90.desc(), eff.c.market_outstanding.desc(), eff.c.id.asc())
        )

        if zone_id:
            stmt = stmt.where(Customer.territory_id == zone_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if employee_id:
            stmt = stmt.where(_employee_filter(employee_id))
        if ageing_bucket and ageing_bucket != "ALL":
            col_name = _BUCKET_FILTERS.get(ageing_bucket)
            if col_name is None:
                raise BaseAPIException(
                    detail=f"Unknown ageing_bucket '{ageing_bucket}'",
                    status_code=422,
                    error_code="INVALID_AGEING_BUCKET",
                )
            stmt = stmt.where(eff.c[col_name] > 0)
        if query:
            stmt = stmt.where(_outlet_search_clause(query))

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        records = (await session.execute(stmt)).all()
        fos_map = await _load_fos_map(session)

        out = []
        for r in records:
            out.append(
                OutstandingAgeingReportRow(
                    customer_id=r.customer_id,
                    dms_code=r.dms_code or "",
                    outlet_name=r.customer_name,
                    brand=r.brand,
                    zone_name=r.zone_name or "Unassigned",
                    area_name=r.area_name or "Unassigned",
                    fos_name=_fos_label(fos_map.get(r.customer_id, [])),
                    market_outstanding=r.market_outstanding,
                    bucket_lt_15=r.bucket_lt_15,
                    bucket_15_30=r.bucket_15_30,
                    bucket_30_45=r.bucket_30_45,
                    bucket_45_60=r.bucket_45_60,
                    bucket_60_75=r.bucket_60_75,
                    bucket_75_90=r.bucket_75_90,
                    bucket_gt_90=r.bucket_gt_90,
                    highest_overdue_bucket=_highest_bucket_label(r),
                    as_of_date=r.snapshot_date,
                )
            )
        return out

    @staticmethod
    async def get_collection_report(
        session: AsyncSession,
        brand: Optional[str] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        month: Optional[str] = None,
        query: Optional[str] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[CollectionReportRow]:
        """
        Collections report: one row per outlet+brand with the collection / sales
        FLOWS summed across all snapshots in the window; ``snapshot_date`` is the
        latest snapshot date in the window ("as of").
        """
        window = resolve_snapshot_window(month, start_date, end_date)
        eff = effective_snapshots(window, brand)
        stmt = (
            select(
                eff,
                Customer.name.label("customer_name"),
                Customer.outlet_code.label("dms_code"),
                Territory.name.label("zone_name"),
                Area.name.label("area_name"),
            )
            .join(Customer, eff.c.customer_id == Customer.id)
            .outerjoin(Territory, Customer.territory_id == Territory.id)
            .outerjoin(Area, Customer.area_id == Area.id)
            .where(eff.c.collection_sum > 0)
            .order_by(eff.c.collection_sum.desc(), eff.c.id.asc())
        )
        if zone_id:
            stmt = stmt.where(Customer.territory_id == zone_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if employee_id:
            stmt = stmt.where(_employee_filter(employee_id))
        if query:
            stmt = stmt.where(_outlet_search_clause(query))

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        records = (await session.execute(stmt)).all()
        fos_map = await _load_fos_map(session)

        return [
            CollectionReportRow(
                customer_id=r.customer_id,
                dms_code=r.dms_code or "",
                outlet_name=r.customer_name,
                brand=r.brand,
                zone_name=r.zone_name or "Unassigned",
                area_name=r.area_name or "Unassigned",
                fos_name=_fos_label(fos_map.get(r.customer_id, [])),
                collection_amount=r.collection_sum,
                sales_amount=r.sales_sum,
                snapshot_date=r.snapshot_date,
                first_snapshot_date=r.first_snapshot_date,
                snapshot_count=r.snapshot_count,
            )
            for r in records
        ]

    @staticmethod
    async def get_visits_detailed_report(
        session: AsyncSession,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        employee_id: Optional[uuid.UUID] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        query: Optional[str] = None,
    ) -> list[VisitDetailedReportRow]:
        """
        Detailed operational visits report with GPS verification status.
        The date range is applied on IST calendar days of ``scheduled_at``.
        """
        stmt = (
            select(
                Visit,
                Employee.full_name.label("employee_name"),
                Customer.name.label("customer_name"),
                Customer.outlet_code.label("dms_code"),
                Territory.name.label("zone_name"),
                Area.name.label("area_name"),
            )
            .join(Employee, Visit.employee_id == Employee.id)
            .join(Customer, Visit.customer_id == Customer.id)
            .outerjoin(Territory, Customer.territory_id == Territory.id)
            .outerjoin(Area, Customer.area_id == Area.id)
            .order_by(Visit.scheduled_at.desc(), Visit.id.asc())
        )

        stmt = where_ist_range(stmt, Visit.scheduled_at, start_date, end_date)
        if employee_id:
            stmt = stmt.where(Visit.employee_id == employee_id)
        if zone_id:
            stmt = stmt.where(Customer.territory_id == zone_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if status and status != "ALL":
            try:
                stmt = stmt.where(Visit.status == VisitStatus(status))
            except ValueError:
                raise BaseAPIException(
                    detail=f"Unknown visit status '{status}'", status_code=422, error_code="INVALID_STATUS"
                )
        if query:
            pattern = like_pattern(query)
            stmt = stmt.where(
                or_(
                    func.lower(Employee.full_name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Employee.employee_code).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Customer.name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Customer.outlet_code).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Territory.name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Area.name).like(pattern, escape=LIKE_ESCAPE),
                )
            )

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        res = await session.execute(stmt)
        rows = res.all()

        out = []
        for v, e_name, c_name, dms, z_name, a_name in rows:
            dur = None
            if v.check_in_at and v.check_out_at:
                dur = max(1, int((v.check_out_at - v.check_in_at).total_seconds() // 60))

            out.append(
                VisitDetailedReportRow(
                    visit_id=v.id,
                    scheduled_at=v.scheduled_at.isoformat() if v.scheduled_at else "",
                    employee_name=e_name,
                    customer_name=c_name,
                    dms_code=dms or "",
                    zone_name=z_name or "Unassigned",
                    area_name=a_name or "Unassigned",
                    status=v.status.value if hasattr(v.status, "value") else str(v.status),
                    check_in_at=v.check_in_at.isoformat() if v.check_in_at else None,
                    check_out_at=v.check_out_at.isoformat() if v.check_out_at else None,
                    duration_minutes=dur,
                    is_gps_verified=bool(v.check_in_location is not None),
                )
            )
        return out

    @staticmethod
    def _staff_scope(stmt, employee_id, zone_id, area_id, query):
        """Employee-level filters shared by the Field Staff report and its exports."""
        if employee_id:
            stmt = stmt.where(Employee.id == employee_id)
        if zone_id:
            in_zone_area = exists(
                select(literal(1))
                .select_from(EmployeeAreaAssignment)
                .join(Area, Area.id == EmployeeAreaAssignment.area_id)
                .where(EmployeeAreaAssignment.employee_id == Employee.id, Area.territory_id == zone_id)
                .correlate(Employee)
            )
            stmt = stmt.where(or_(Employee.territory_id == zone_id, in_zone_area))
        if area_id:
            stmt = stmt.where(
                exists(
                    select(literal(1))
                    .select_from(EmployeeAreaAssignment)
                    .where(EmployeeAreaAssignment.employee_id == Employee.id, EmployeeAreaAssignment.area_id == area_id)
                    .correlate(Employee)
                )
            )
        if query:
            pattern = like_pattern(query)
            stmt = stmt.where(
                or_(
                    func.lower(Employee.full_name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Employee.employee_code).like(pattern, escape=LIKE_ESCAPE),
                )
            )
        return stmt

    @staticmethod
    async def get_employee_visit_report(
        session: AsyncSession,
        start_date: date | None = None,
        end_date: date | None = None,
        employee_id: Optional[uuid.UUID] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        query: Optional[str] = None,
    ) -> list[dict]:
        """Per-employee visit counts; the date range is applied on IST days of ``scheduled_at``."""
        from app.services.report_filters import ist_window

        validate_date_order(start_date, end_date)
        lo, hi = ist_window(start_date, end_date)
        join_conds = [Visit.employee_id == Employee.id]
        if lo is not None:
            join_conds.append(Visit.scheduled_at >= lo)
        if hi is not None:
            join_conds.append(Visit.scheduled_at < hi)
        stmt = (
            select(
                Employee.id.label("employee_id"),
                Employee.employee_code.label("employee_code"),
                Employee.full_name.label("employee_name"),
                func.count(Visit.id).label("total_visits"),
                func.sum(case((Visit.status == VisitStatus.COMPLETED, 1), else_=0)).label("completed_visits"),
                func.sum(case((Visit.status == VisitStatus.PENDING, 1), else_=0)).label("pending_visits"),
                func.sum(case((Visit.status == VisitStatus.MISSED, 1), else_=0)).label("missed_visits"),
                func.sum(case((Visit.status == VisitStatus.FLAGGED, 1), else_=0)).label("flagged_visits"),
            )
            .outerjoin(Visit, and_(*join_conds))
            .group_by(Employee.id, Employee.employee_code, Employee.full_name)
            .order_by(Employee.full_name.asc(), Employee.id.asc())
        )
        stmt = ReportService._staff_scope(stmt, employee_id, zone_id, area_id, query)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "employee_id": str(row.employee_id),
                "employee_code": row.employee_code,
                "employee_name": row.employee_name,
                "total_visits": row.total_visits or 0,
                "completed_visits": row.completed_visits or 0,
                "pending_visits": row.pending_visits or 0,
                "missed_visits": row.missed_visits or 0,
                "flagged_visits": row.flagged_visits or 0,
                "completion_rate": round(
                    ((row.completed_visits or 0) / float(row.total_visits) * 100), 1
                ) if row.total_visits and row.total_visits > 0 else 0.0,
            }
            for row in rows
        ]

    @staticmethod
    async def get_customer_visit_history(session: AsyncSession, customer_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(
                Visit.id.label("visit_id"),
                Visit.scheduled_at,
                Visit.status,
                Visit.check_in_at,
                Visit.check_out_at,
                Employee.full_name.label("employee_name"),
            )
            .join(Employee, Visit.employee_id == Employee.id)
            .where(Visit.customer_id == customer_id)
            .order_by(Visit.scheduled_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()
        return [
            {
                "visit_id": row.visit_id,
                "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else "",
                "status": row.status.value,
                "employee_name": row.employee_name,
                "check_in_at": row.check_in_at.isoformat() if row.check_in_at else None,
                "check_out_at": row.check_out_at.isoformat() if row.check_out_at else None,
            }
            for row in rows
        ]

    @staticmethod
    async def get_productivity_dashboard(session: AsyncSession) -> dict:
        today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
        today_end = datetime.combine(date.today(), datetime.max.time(), tzinfo=timezone.utc)

        total_emp_res = await session.execute(select(func.count(Employee.id)))
        total_emp = total_emp_res.scalar() or 0

        active_emp_res = await session.execute(
            select(func.count(Employee.id))
            .join(User, Employee.user_id == User.id)
            .where(User.is_active == True)
        )
        active_emp = active_emp_res.scalar() or 0

        stmt = select(
            func.count(Visit.id).label("total"),
            func.sum(case((Visit.status == VisitStatus.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((Visit.status == VisitStatus.PENDING, 1), else_=0)).label("pending"),
            func.sum(case((Visit.status == VisitStatus.MISSED, 1), else_=0)).label("missed"),
            func.sum(case((Visit.status == VisitStatus.FLAGGED, 1), else_=0)).label("flagged"),
        ).where(and_(Visit.scheduled_at >= today_start, Visit.scheduled_at <= today_end))

        result = await session.execute(stmt)
        row = result.one_or_none()

        tot = row.total if row and row.total else 0
        comp = row.completed if row and row.completed else 0
        pend = row.pending if row and row.pending else 0
        miss = row.missed if row and row.missed else 0
        flag = row.flagged if row and row.flagged else 0

        return {
            "total_employees": total_emp,
            "active_employees": active_emp,
            "total_visits_today": tot,
            "completed_visits_today": comp,
            "pending_visits_today": pend,
            "missed_visits_today": miss,
            "flagged_visits_today": flag,
            "avg_visits_per_employee": round(tot / active_emp, 1) if active_emp > 0 else 0.0,
        }

    @staticmethod
    async def get_geo_verification_report(
        session: AsyncSession,
        start_date: date | None = None,
        end_date: date | None = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        employee_id: Optional[uuid.UUID] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        query: Optional[str] = None,
    ) -> list[dict]:
        stmt = (
            select(
                GeoVerificationLog,
                Employee.full_name.label("employee_name"),
                Customer.name.label("customer_name"),
                Customer.outlet_code.label("dms_code"),
            )
            .join(Visit, GeoVerificationLog.visit_id == Visit.id)
            .join(Employee, Visit.employee_id == Employee.id)
            .join(Customer, Visit.customer_id == Customer.id)
            .order_by(GeoVerificationLog.attempted_at.desc(), GeoVerificationLog.id.asc())
        )

        stmt = where_ist_range(stmt, GeoVerificationLog.attempted_at, start_date, end_date)
        if employee_id:
            stmt = stmt.where(Visit.employee_id == employee_id)
        if zone_id:
            stmt = stmt.where(Customer.territory_id == zone_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if query:
            pattern = like_pattern(query)
            stmt = stmt.where(
                or_(
                    func.lower(Employee.full_name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Employee.employee_code).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Customer.name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Customer.outlet_code).like(pattern, escape=LIKE_ESCAPE),
                )
            )

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "visit_id": str(row.GeoVerificationLog.visit_id) if row.GeoVerificationLog.visit_id else "",
                "employee_name": row.employee_name,
                "customer_name": row.customer_name,
                "dms_code": row.dms_code or "",
                "attempted_at": row.GeoVerificationLog.attempted_at.isoformat(),
                "verification_type": row.GeoVerificationLog.verification_type.value,
                "is_valid": row.GeoVerificationLog.is_valid,
                "distance_m": round(float(row.GeoVerificationLog.distance_from_customer_m), 1) if row.GeoVerificationLog.distance_from_customer_m is not None else 0.0,
                "failure_reason": row.GeoVerificationLog.failure_reason,
            }
            for row in rows
        ]

    @staticmethod
    async def get_business_bi_dashboard(
        session: AsyncSession,
        brand: Optional[str] = None,
        zone_id: Optional[uuid.UUID] = None,
        area_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        month: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> BusinessBIDashboard:
        """
        Aggregated Business BI summaries.

        Data source (explicit in ``data_source``):
          * SNAPSHOT      - outlet financial snapshots in the window.  FLOWS (sales,
                            collection) are summed across the snapshots, STOCK
                            (market OS, ageing) is the latest snapshot per
                            outlet+brand.
          * LIVE_INVOICES - used ONLY when no snapshot exists at all in the window:
                            live Tally invoices (invoice_date in the window) and
                            verified payments (payment_date in the window); ageing
                            is as of today.
        """
        window = resolve_snapshot_window(month, start_date, end_date)
        today = ist_now().date()

        any_snapshot = (
            await session.execute(
                _snapshot_window_where(select(literal(1)).select_from(_S), window).limit(1)
            )
        ).first() is not None

        entries: list[_BiEntry] = []
        total_collection = Decimal("0.00")
        total_collection_posted = Decimal("0.00")
        total_collection_awaiting = Decimal("0.00")
        brand_collection_override: Optional[dict[str, Decimal]] = None
        data_source = "SNAPSHOT"
        as_of: Optional[date] = None

        fos_map = await _load_fos_map(session, only_employee=employee_id)

        if any_snapshot:
            eff = effective_snapshots(window, brand)
            stmt = (
                select(
                    eff,
                    Customer.name.label("customer_name"),
                    Customer.outlet_code.label("dms_code"),
                    Territory.name.label("zone_name"),
                    Area.name.label("area_name"),
                )
                .join(Customer, eff.c.customer_id == Customer.id)
                .outerjoin(Territory, Customer.territory_id == Territory.id)
                .outerjoin(Area, Customer.area_id == Area.id)
                .order_by(eff.c.id.asc())
            )
            if zone_id:
                stmt = stmt.where(Customer.territory_id == zone_id)
            if area_id:
                stmt = stmt.where(Customer.area_id == area_id)
            if employee_id:
                stmt = stmt.where(_employee_filter(employee_id))
            for r in (await session.execute(stmt)).all():
                entries.append(
                    _BiEntry(
                        key=r.id,
                        customer_id=r.customer_id,
                        brand=resolve_canonical_brand_name(r.brand) if r.brand else "General",
                        outlet_name=r.customer_name,
                        dms_code=r.dms_code or "",
                        zone=r.zone_name or "Unknown Zone",
                        area=r.area_name or "Unknown Area",
                        fos=fos_map.get(r.customer_id, []),
                        sales=r.sales_sum,
                        collection=r.collection_sum,
                        market_os=r.market_outstanding,
                        buckets=[r.bucket_lt_15, r.bucket_15_30, r.bucket_30_45, r.bucket_45_60,
                                 r.bucket_60_75, r.bucket_75_90, r.bucket_gt_90],
                        as_of=r.snapshot_date,
                    )
                )
            as_of = max((e.as_of for e in entries if e.as_of), default=None)
            total_collection = sum((e.collection for e in entries), Decimal("0.00"))
        else:
            data_source = "LIVE_INVOICES"
            aliases = _brand_aliases(brand)
            inv_stmt = (
                select(
                    Invoice,
                    Customer.name.label("customer_name"),
                    Customer.outlet_code.label("dms_code"),
                    Territory.name.label("zone_name"),
                    Area.name.label("area_name"),
                )
                .join(Customer, Invoice.customer_id == Customer.id)
                .outerjoin(Territory, Customer.territory_id == Territory.id)
                .outerjoin(Area, Customer.area_id == Area.id)
                .where(Invoice.source == InvoiceSource.TALLY)
                .order_by(Invoice.id.asc())
            )
            if aliases:
                inv_stmt = inv_stmt.where(func.lower(Invoice.brand).in_(aliases))
            if zone_id:
                inv_stmt = inv_stmt.where(Customer.territory_id == zone_id)
            if area_id:
                inv_stmt = inv_stmt.where(Customer.area_id == area_id)
            if employee_id:
                inv_stmt = inv_stmt.where(_employee_filter(employee_id))
            inv_stmt = where_date_range(inv_stmt, Invoice.invoice_date, window.start, window.end)

            for inv, c_name, dms, z_name, a_name in (await session.execute(inv_stmt)).all():
                inv_amt = inv.amount or Decimal("0.00")
                inv_os = inv.imported_outstanding_amount if inv.imported_outstanding_amount is not None else inv_amt
                age_days = (today - inv.invoice_date).days if inv.invoice_date else 0
                zero = Decimal("0.00")
                buckets = [
                    inv_os if age_days <= 15 else zero,
                    inv_os if 16 <= age_days <= 30 else zero,
                    inv_os if 31 <= age_days <= 45 else zero,
                    inv_os if 46 <= age_days <= 60 else zero,
                    inv_os if 61 <= age_days <= 75 else zero,
                    inv_os if 76 <= age_days <= 90 else zero,
                    inv_os if age_days > 90 else zero,
                ]
                entries.append(
                    _BiEntry(
                        key=inv.id,
                        customer_id=inv.customer_id,
                        brand=resolve_canonical_brand_name(inv.brand) if inv.brand else "General",
                        outlet_name=c_name,
                        dms_code=dms or "",
                        zone=z_name or "Unknown Zone",
                        area=a_name or "Unknown Area",
                        fos=fos_map.get(inv.customer_id, []),
                        sales=inv_amt,
                        collection=Decimal("0.00"),
                        market_os=inv_os,
                        buckets=buckets,
                        as_of=today,
                    )
                )
            as_of = today

            # Collections from VERIFIED payments, same window / brand / zone / area / employee filters.
            def _pay_filters(stmt):
                stmt = stmt.where(Payment.status == PaymentStatus.VERIFIED)
                stmt = where_date_range(stmt, Payment.payment_date, window.start, window.end)
                if employee_id:
                    stmt = stmt.where(Payment.employee_id == employee_id)
                if zone_id:
                    stmt = stmt.where(Customer.territory_id == zone_id)
                if area_id:
                    stmt = stmt.where(Customer.area_id == area_id)
                return stmt

            if aliases:
                pay_stmt = (
                    select(func.coalesce(func.sum(PaymentBrandAllocation.allocated_amount), Decimal("0.00")))
                    .select_from(Payment)
                    .join(Customer, Payment.customer_id == Customer.id)
                    .join(PaymentBrandAllocation, PaymentBrandAllocation.payment_id == Payment.id)
                    .where(func.lower(PaymentBrandAllocation.brand).in_(aliases))
                )
            else:
                pay_stmt = (
                    select(func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
                    .select_from(Payment)
                    .join(Customer, Payment.customer_id == Customer.id)
                )
            pay_stmt = _pay_filters(pay_stmt)
            total_collection = (await session.execute(pay_stmt)).scalar() or Decimal("0.00")
            # Split of the same VERIFIED collections: in Tally vs awaiting Tally.
            total_collection_posted = (
                await session.execute(pay_stmt.where(payment_tally.posted_clause()))
            ).scalar() or Decimal("0.00")
            total_collection_awaiting = (
                await session.execute(pay_stmt.where(payment_tally.awaiting_clause()))
            ).scalar() or Decimal("0.00")

            pay_brand_stmt = (
                select(
                    PaymentBrandAllocation.brand,
                    func.coalesce(func.sum(PaymentBrandAllocation.allocated_amount), Decimal("0.00")),
                )
                .select_from(Payment)
                .join(Customer, Payment.customer_id == Customer.id)
                .join(PaymentBrandAllocation, PaymentBrandAllocation.payment_id == Payment.id)
            )
            if aliases:
                pay_brand_stmt = pay_brand_stmt.where(func.lower(PaymentBrandAllocation.brand).in_(aliases))
            pay_brand_stmt = _pay_filters(pay_brand_stmt).group_by(PaymentBrandAllocation.brand)
            brand_collection_override = {}
            for b_raw, b_col in (await session.execute(pay_brand_stmt)).all():
                canon_b = resolve_canonical_brand_name(b_raw) if b_raw else "General"
                brand_collection_override[canon_b] = brand_collection_override.get(canon_b, Decimal("0.00")) + b_col

        # ---- aggregation (identical for both sources) ---------------------------------
        zero = Decimal("0.00")
        total_sales = sum((e.sales for e in entries), zero)
        total_market_os = sum((e.market_os for e in entries), zero)
        total_gt_90 = sum((e.buckets[6] for e in entries), zero)
        unique_outlets = {e.customer_id for e in entries}

        brand_map: dict[str, dict] = {}
        zone_map: dict[str, dict] = {}
        area_map: dict[str, dict] = {}
        fos_agg: dict[str, dict] = {}

        def _init_agg(name: str, b_name: str) -> dict:
            return {
                "dimension_name": name, "brand": b_name, "outlets": set(),
                "sales": zero, "collection": zero, "market_os": zero, "b": [zero] * 7,
            }

        def _add(agg: dict, e: _BiEntry):
            agg["outlets"].add(e.customer_id)
            agg["sales"] += e.sales
            agg["collection"] += e.collection
            agg["market_os"] += e.market_os
            agg["b"] = [x + y for x, y in zip(agg["b"], e.buckets)]

        raw_rows: list[BusinessSummaryRow] = []
        for e in entries:
            fos_label = _fos_label(e.fos)
            raw_rows.append(
                BusinessSummaryRow(
                    brand=e.brand,
                    dimension_name=e.outlet_name,
                    dms_code=e.dms_code,
                    outlet_name=e.outlet_name,
                    zone_name=e.zone,
                    area_name=e.area,
                    fos_name=fos_label,
                    outlets_count=1,
                    sales=e.sales,
                    collection=e.collection,
                    market_outstanding=e.market_os,
                    bucket_lt_15=e.buckets[0], bucket_15_30=e.buckets[1], bucket_30_45=e.buckets[2],
                    bucket_45_60=e.buckets[3], bucket_60_75=e.buckets[4], bucket_75_90=e.buckets[5],
                    bucket_gt_90=e.buckets[6],
                    as_of_date=e.as_of,
                )
            )
            _add(brand_map.setdefault(e.brand, _init_agg(e.brand, e.brand)), e)
            _add(zone_map.setdefault(f"{e.brand}::{e.zone}", _init_agg(e.zone, e.brand)), e)
            _add(area_map.setdefault(f"{e.brand}::{e.area}", _init_agg(e.area, e.brand)), e)
            # FOS aggregation: once per (entry, assigned FOS); unassigned outlets -> "Unassigned"
            for f_label in ([n for _, n in e.fos] or ["Unassigned"]):
                _add(fos_agg.setdefault(f"{e.brand}::{f_label}", _init_agg(f_label, e.brand)), e)

        if brand_collection_override is not None:
            for canon_b, b_col in brand_collection_override.items():
                if canon_b in brand_map:
                    brand_map[canon_b]["collection"] = b_col
                else:
                    agg_new = _init_agg(canon_b, canon_b)
                    agg_new["collection"] = b_col
                    brand_map[canon_b] = agg_new

        def _to_rows(d_map: dict) -> list[BusinessSummaryRow]:
            out = []
            for item in d_map.values():
                b = item["b"]
                out.append(
                    BusinessSummaryRow(
                        brand=item["brand"],
                        dimension_name=item["dimension_name"],
                        outlets_count=len(item["outlets"]),
                        sales=item["sales"],
                        collection=item["collection"],
                        market_outstanding=item["market_os"],
                        bucket_lt_15=b[0], bucket_15_30=b[1], bucket_30_45=b[2],
                        bucket_45_60=b[3], bucket_60_75=b[4], bucket_75_90=b[5], bucket_gt_90=b[6],
                    )
                )
            return sorted(out, key=lambda x: (-x.sales, x.brand, x.dimension_name))

        # Check finalization status if a calendar month (and not a date range) was selected
        is_fin = False
        if window.source == "MONTH" and month:
            y, m = [int(x) for x in month.split("-")]
            period_row = (
                await session.execute(
                    select(MonthlyReportingPeriod).where(
                        MonthlyReportingPeriod.period_year == y,
                        MonthlyReportingPeriod.period_month == m,
                    )
                )
            ).scalar_one_or_none()
            if period_row:
                status_val = period_row.status.value if hasattr(period_row.status, "value") else str(period_row.status)
                is_fin = status_val == MonthlyPeriodStatus.FINALIZED.value

        if data_source == "SNAPSHOT":
            note = (
                "Source: outlet financial snapshots. Sales and collection are summed across the snapshots in the "
                "selected period; market outstanding and ageing buckets are the latest snapshot per outlet and brand "
                "in the period"
                + (f" (as of {as_of.isoformat()})." if as_of else ".")
            )
        else:
            note = (
                "No snapshot exists for the selected period, so figures come from live Tally invoices "
                "(invoice date within the period) and verified payments (payment date within the period); "
                "outstanding and ageing are as of today."
            )

        return BusinessBIDashboard(
            snapshot_date=as_of or today,
            month_period=month if (month and month != "ALL" and not window.month_ignored) else None,
            is_finalized=is_fin,
            total_outlets=len(unique_outlets),
            total_sales=total_sales,
            total_collection=total_collection,
            total_collection_posted_in_tally=total_collection_posted,
            total_collection_verified_awaiting_tally=total_collection_awaiting,
            total_market_outstanding=total_market_os,
            total_overdue_gt_90=total_gt_90,
            brand_summaries=_to_rows(brand_map),
            zone_summaries=_to_rows(zone_map),
            area_summaries=_to_rows(area_map),
            fos_summaries=_to_rows(fos_agg),
            raw_outlet_rows=raw_rows,
            data_source=data_source,
            data_source_note=note,
            as_of_date=as_of,
            period_start=window.start,
            period_end=window.end,
            period_source=window.source,
            month_ignored=window.month_ignored,
        )

    # -----------------------------------------------------------------------
    # PHASE 4: Monthly Reporting Periods & Historical Snapshots
    # -----------------------------------------------------------------------
    @staticmethod
    async def get_monthly_periods(session: AsyncSession) -> list[MonthlyPeriodRead]:
        """
        Discovers snapshot months and invoice/payment months from database, computes and syncs monthly period records.
        """
        from app.services import period_service
        periods = await period_service.ensure_monthly_periods_synced(session)
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

    @staticmethod
    async def finalize_monthly_period(
        session: AsyncSession,
        period_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MonthlyPeriodRead:
        """
        Finalizes a monthly reporting period. Locks historical data.
        """
        stmt = select(MonthlyReportingPeriod).where(MonthlyReportingPeriod.id == period_id)
        res = await session.execute(stmt)
        period = res.scalar_one_or_none()
        if not period:
            raise BaseAPIException(status_code=404, detail="Monthly period not found", error_code="PERIOD_NOT_FOUND")

        now_dt = datetime.now(timezone.utc)
        period.status = MonthlyPeriodStatus.FINALIZED
        period.finalized_at = now_dt
        period.finalized_by = user_id
        period.updated_at = now_dt
        await session.flush()

        return MonthlyPeriodRead(
            id=period.id,
            period_year=period.period_year,
            period_month=period.period_month,
            period_name=period.period_name,
            status="FINALIZED",
            snapshot_count=period.snapshot_count,
            total_outlets=period.total_outlets,
            total_sales=period.total_sales,
            total_collection=period.total_collection,
            total_market_os=period.total_market_os,
            total_overdue_gt_90=period.total_overdue_gt_90,
            finalized_at=now_dt,
            finalized_by=user_id,
            created_at=period.created_at or now_dt,
            updated_at=now_dt,
        )

    @staticmethod
    async def reopen_monthly_period(
        session: AsyncSession,
        period_id: uuid.UUID,
    ) -> MonthlyPeriodRead:
        """
        Reopens a finalized monthly reporting period.
        """
        stmt = select(MonthlyReportingPeriod).where(MonthlyReportingPeriod.id == period_id)
        res = await session.execute(stmt)
        period = res.scalar_one_or_none()
        if not period:
            raise BaseAPIException(status_code=404, detail="Monthly period not found", error_code="PERIOD_NOT_FOUND")

        now_dt = datetime.now(timezone.utc)
        period.status = MonthlyPeriodStatus.OPEN
        period.finalized_at = None
        period.finalized_by = None
        period.updated_at = now_dt
        await session.flush()

        return MonthlyPeriodRead(
            id=period.id,
            period_year=period.period_year,
            period_month=period.period_month,
            period_name=period.period_name,
            status="OPEN",
            snapshot_count=period.snapshot_count,
            total_outlets=period.total_outlets,
            total_sales=period.total_sales,
            total_collection=period.total_collection,
            total_market_os=period.total_market_os,
            total_overdue_gt_90=period.total_overdue_gt_90,
            finalized_at=None,
            finalized_by=None,
            created_at=period.created_at or now_dt,
            updated_at=now_dt,
        )


report_service = ReportService()
