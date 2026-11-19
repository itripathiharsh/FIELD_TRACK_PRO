"""
Builders that turn report rows + the applied filters into ReportTable objects
(consumed by report_exports.to_xlsx / to_pdf), plus the filter-echo helper that
lists EVERY filter the report supports - set or not - in the export header.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import Area
from app.models.employee import Employee
from app.models.territory import Territory
from app.services.report_exports import Col, ReportTable, fmt_date, parse_iso_dt
from app.services.report_filters import SnapshotWindow, ist_now, resolve_snapshot_window

ALL = "All"


def _month_label(month: str) -> str:
    if month.startswith("FY"):
        return f"Financial year {month[2:]} (history)"
    y, m = month.split("-")
    return f"{calendar.month_name[int(m)]} {y}"


async def describe_filters(
    session: AsyncSession,
    include: Sequence[str],
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    month: Optional[str] = None,
    brand: Optional[str] = None,
    zone_id: Optional[uuid.UUID] = None,
    area_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    ageing_bucket: Optional[str] = None,
    status: Optional[str] = None,
    query: Optional[str] = None,
    location_status: Optional[str] = None,
) -> tuple[list[tuple[str, str]], bool]:
    """Return ([(label, value)], any_filter_set) for the filters listed in ``include`` (in order)."""
    out: list[tuple[str, str]] = []
    filtered = False
    month_set = bool(month and month != "ALL")
    dates_set = bool(start_date or end_date)

    async def name_of(model, id_, col):
        if not id_:
            return None
        return (await session.execute(select(col).where(model.id == id_))).scalar_one_or_none()

    for key in include:
        if key == "date":
            if start_date and end_date:
                v = f"{fmt_date(start_date)} to {fmt_date(end_date)} (IST, inclusive)"
            elif start_date:
                v = f"from {fmt_date(start_date)} (IST)"
            elif end_date:
                v = f"up to {fmt_date(end_date)} (IST)"
            else:
                v = "All dates"
            out.append(("Date range", v))
            filtered |= dates_set
        elif key == "month":
            if month_set:
                v = _month_label(month) + (" (ignored - date range applied)" if dates_set else "")
                filtered |= not dates_set
            else:
                v = "All months"
            out.append(("Month", v))
        elif key == "brand":
            set_ = bool(brand and brand != "ALL")
            out.append(("Brand", brand if set_ else "All brands"))
            filtered |= set_
        elif key == "zone":
            nm = await name_of(Territory, zone_id, Territory.name)
            out.append(("Zone", (nm or str(zone_id)) if zone_id else "All zones"))
            filtered |= bool(zone_id)
        elif key == "area":
            nm = await name_of(Area, area_id, Area.name)
            out.append(("Area", (nm or str(area_id)) if area_id else "All areas"))
            filtered |= bool(area_id)
        elif key == "employee":
            if employee_id:
                row = (await session.execute(
                    select(Employee.full_name, Employee.employee_code).where(Employee.id == employee_id)
                )).first()
                v = f"{row[0]} ({row[1]})" if row and row[1] else (row[0] if row else str(employee_id))
            else:
                v = "All employees"
            out.append(("Employee", v))
            filtered |= bool(employee_id)
        elif key == "ageing":
            set_ = bool(ageing_bucket and ageing_bucket != "ALL")
            out.append(("Ageing bucket", ageing_bucket if set_ else "All buckets"))
            filtered |= set_
        elif key == "status":
            set_ = bool(status and status != "ALL")
            out.append(("Status", status if set_ else "All statuses"))
            filtered |= set_
        elif key == "location_status":
            set_ = bool(location_status and location_status != "ALL")
            out.append(("Location status", location_status if set_ else "All"))
            filtered |= set_
        elif key == "search":
            set_ = bool(query and query.strip())
            out.append(("Search", f'"{query.strip()}"' if set_ else "None"))
            filtered |= set_
    return out, filtered


def _money(h: str) -> Col:
    return Col(h, "money", total=True)


def _dec(v: Any) -> Decimal:
    return Decimal(str(v if v is not None else 0))


# ----------------------------------------------------------------------------- BI
BI_VIEWS = ("brand", "zone", "area", "fos", "raw")
_BI_TITLES = {
    "brand": "Brand Summary", "zone": "Zone Summary", "area": "Area Summary",
    "fos": "FOS Summary", "raw": "Outlet Data",
}
_BUCKET_HEADERS = ["<15d", "15-30d", "30-45d", "45-60d", "60-75d", "75-90d", ">90d"]


def _bi_kpis(d) -> list[tuple[str, str]]:
    from app.services.report_exports import fmt_inr
    return [
        ("Outlets", str(d.total_outlets)),
        ("Sales", f"₹{fmt_inr(d.total_sales)}"),
        ("Collection", f"₹{fmt_inr(d.total_collection)}"),
        ("Market OS", f"₹{fmt_inr(d.total_market_outstanding)}"),
        (">90d", f"₹{fmt_inr(d.total_overdue_gt_90)}"),
    ]


def build_bi_table(dashboard, view: str, filters: list[tuple[str, str]]) -> ReportTable:
    rows_src = {
        "brand": dashboard.brand_summaries, "zone": dashboard.zone_summaries,
        "area": dashboard.area_summaries, "fos": dashboard.fos_summaries, "raw": dashboard.raw_outlet_rows,
    }[view]
    bucket_cols = [_money(h + " (INR)") for h in _BUCKET_HEADERS]
    if view == "raw":
        cols = [
            Col("Brand", weight=0.8), Col("DMS Code", weight=0.9), Col("Outlet Name", weight=2.0),
            Col("Zone", weight=1.1), Col("Area", weight=1.1), Col("FOS", weight=1.3),
            _money("Sales (INR)"), _money("Collection (INR)"), _money("Market OS (INR)"), *bucket_cols,
        ]
        rows = [
            [r.brand, r.dms_code or "", r.outlet_name, r.zone_name or "", r.area_name or "", r.fos_name or "",
             r.sales, r.collection, r.market_outstanding, r.bucket_lt_15, r.bucket_15_30, r.bucket_30_45,
             r.bucket_45_60, r.bucket_60_75, r.bucket_75_90, r.bucket_gt_90]
            for r in rows_src
        ]
    else:
        dim = {"brand": "Brand", "zone": "Zone", "area": "Area", "fos": "FOS"}[view]
        cols = [
            Col("Brand", weight=1.0), Col(dim, weight=2.0), Col("Outlets", "int"),
            _money("Sales (INR)"), _money("Collection (INR)"), _money("Market OS (INR)"), *bucket_cols,
        ]
        rows = [
            [r.brand, r.dimension_name, r.outlets_count, r.sales, r.collection, r.market_outstanding,
             r.bucket_lt_15, r.bucket_15_30, r.bucket_30_45, r.bucket_45_60, r.bucket_60_75,
             r.bucket_75_90, r.bucket_gt_90]
            for r in rows_src
        ]
    note = dashboard.data_source_note or ""
    if view == "fos":
        note += " An outlet assigned to several FOS is counted under each of them, so this view has no grand total."
    elif view != "raw":
        note += " Outlets are counted once per row (an outlet with several brands appears in each brand row)."
    t = ReportTable(
        title=f"Financial & BI - {_BI_TITLES[view]}", sheet_name=_BI_TITLES[view], columns=cols, rows=rows,
        filters=filters, note=note.strip() or None, kpis=_bi_kpis(dashboard), totals=(view != "fos"),
    )
    return t


def build_bi_tables(dashboard, filters: list[tuple[str, str]]) -> list[ReportTable]:
    return [build_bi_table(dashboard, v, filters) for v in BI_VIEWS]


# ----------------------------------------------------------------------------- outstanding
def build_outstanding_table(records, filters, as_of: Optional[date]) -> ReportTable:
    cols = [
        Col("Brand", weight=0.8), Col("DMS Code", weight=0.9), Col("Outlet Name", weight=2.0),
        Col("Zone", weight=1.1), Col("Area", weight=1.1), Col("FOS", weight=1.3),
        _money("Market OS (INR)"), *[_money(h + " (INR)") for h in _BUCKET_HEADERS],
        Col("Severity", weight=1.1), Col("As of", "date"),
    ]
    rows = [
        [r.brand, r.dms_code or "", r.outlet_name, r.zone_name or "", r.area_name or "", r.fos_name or "",
         r.market_outstanding, r.bucket_lt_15, r.bucket_15_30, r.bucket_30_45, r.bucket_45_60,
         r.bucket_60_75, r.bucket_75_90, r.bucket_gt_90, r.highest_overdue_bucket, r.as_of_date]
        for r in records
    ]
    return ReportTable(
        title="Market Outstanding & Ageing Report", sheet_name="Outstanding", columns=cols, rows=rows,
        filters=filters,
        note="Stock figures: latest snapshot in the selected period per outlet and brand (never summed across dates).",
    )


# ----------------------------------------------------------------------------- outlets
def build_outlets_table(outlets, filters) -> ReportTable:
    cols = [
        Col("DMS Code", weight=0.9), Col("Outlet Name", weight=2.0), Col("Zone", weight=1.1), Col("Area", weight=1.1),
        Col("Assigned FOS", weight=1.3), Col("Contact Person", weight=1.2), Col("Phone", weight=1.0),
        Col("Location Status", weight=0.9), Col("Latitude", "text", 0.8), Col("Longitude", "text", 0.8),
        _money("Sales (INR)"), _money("Collection (INR)"), _money("Market OS (INR)"), _money(">90d (INR)"),
        Col("As of", "date"),
    ]
    rows = [
        [o.dms_code or "", o.outlet_name, o.zone_name or "", o.area_name or "", o.fos_name or "",
         o.contact_person or "", o.contact_number or "", o.location_status,
         f"{o.latitude:.6f}" if o.latitude is not None else "", f"{o.longitude:.6f}" if o.longitude is not None else "",
         o.sales, o.collection, o.market_outstanding, o.overdue_gt_90, o.as_of_date]
        for o in outlets
    ]
    return ReportTable(
        title="Outlet Directory Report", sheet_name="Outlets", columns=cols, rows=rows, filters=filters,
        note=("One row per outlet. Sales and collection are summed over the snapshots in the selected period; "
              "market OS and >90d are the latest snapshot per brand (as of the date shown)."),
    )


# ----------------------------------------------------------------------------- collections (snapshot)
def build_collections_report_table(records, filters) -> ReportTable:
    cols = [
        Col("Brand", weight=0.8), Col("DMS Code", weight=0.9), Col("Outlet Name", weight=2.0),
        Col("Zone", weight=1.1), Col("Area", weight=1.1), Col("FOS", weight=1.3),
        _money("Collection (INR)"), _money("Sales (INR)"), Col("As of", "date"), Col("Snapshots", "int"),
    ]
    rows = [
        [r.brand, r.dms_code or "", r.outlet_name, r.zone_name or "", r.area_name or "", r.fos_name or "",
         r.collection_amount, r.sales_amount, r.snapshot_date, r.snapshot_count]
        for r in records
    ]
    return ReportTable(
        title="Collections Report (snapshots)", sheet_name="Collections", columns=cols, rows=rows, filters=filters,
        note="Collection and sales are summed across the snapshots in the selected period; 'As of' is the latest snapshot date.",
    )


# ----------------------------------------------------------------------------- visits / geo / staff
def build_visits_table(visits, filters) -> ReportTable:
    cols = [
        Col("Scheduled Date (IST)", "date"), Col("Employee", weight=1.4), Col("Outlet", weight=2.0),
        Col("DMS Code", weight=0.9), Col("Zone", weight=1.1), Col("Area", weight=1.1), Col("Status", weight=0.9),
        Col("Check-in (IST)", "datetime"), Col("Check-out (IST)", "datetime"),
        Col("Duration (mins)", "int", total=False), Col("GPS Verified", weight=0.6),
    ]
    rows = []
    from app.services.report_filters import ist_date_of
    for v in visits:
        sched = parse_iso_dt(v.scheduled_at)
        rows.append([
            ist_date_of(sched), v.employee_name, v.customer_name, v.dms_code or "", v.zone_name or "",
            v.area_name or "", v.status, v.check_in_at, v.check_out_at, v.duration_minutes,
            "Yes" if v.is_gps_verified else "No",
        ])
    completed = sum(1 for v in visits if v.status == "COMPLETED")
    return ReportTable(
        title="Visits Operational Report", sheet_name="Visits", columns=cols, rows=rows, filters=filters,
        kpis=[("Total visits", str(len(visits))), ("Completed", str(completed))], totals=False,
        note="Dates and times are Asia/Kolkata (IST); the date range is applied on the IST day of the scheduled time.",
    )


def build_geo_table(rows_src: list[dict], filters) -> ReportTable:
    cols = [
        Col("Attempt Time (IST)", "datetime"), Col("Employee", weight=1.4), Col("Outlet", weight=2.0),
        Col("DMS Code", weight=0.9), Col("Verification Type", weight=1.1), Col("Valid", weight=0.5),
        Col("Distance (m)", "number"), Col("Failure Reason", weight=2.0),
    ]
    rows = [
        [r["attempted_at"], r["employee_name"], r["customer_name"], r["dms_code"], r["verification_type"],
         "Yes" if r["is_valid"] else "No", r["distance_m"], r["failure_reason"] or ""]
        for r in rows_src
    ]
    valid = sum(1 for r in rows_src if r["is_valid"])
    return ReportTable(
        title="Geo Verification Audit", sheet_name="Geo Audit", columns=cols, rows=rows, filters=filters,
        kpis=[("Attempts", str(len(rows_src))), ("Valid", str(valid))], totals=False,
        note="Times are Asia/Kolkata (IST); the date range is applied on the IST day of the attempt.",
    )


def build_staff_table(rows_src: list[dict], filters) -> ReportTable:
    cols = [
        Col("Employee Code", weight=1.0), Col("Employee Name", weight=2.5),
        Col("Total Visits", "int", total=True), Col("Completed", "int", total=True), Col("Pending", "int", total=True),
        Col("Missed", "int", total=True), Col("Flagged", "int", total=True), Col("Completion Rate", "pct"),
    ]
    rows = [
        [r.get("employee_code") or "", r["employee_name"], r["total_visits"], r["completed_visits"],
         r["pending_visits"], r["missed_visits"], r["flagged_visits"], r["completion_rate"]]
        for r in rows_src
    ]
    tot_visits = sum(r["total_visits"] for r in rows_src)
    tot_done = sum(r["completed_visits"] for r in rows_src)
    return ReportTable(
        title="Field Staff Performance", sheet_name="Field Staff", columns=cols, rows=rows, filters=filters,
        totals_override={7: round(tot_done / tot_visits * 100, 1) if tot_visits else 0.0},
        note="Visit counts for the selected date range (IST days of the scheduled time).",
    )


# ----------------------------------------------------------------------------- monthly periods
def build_periods_table(periods, filters) -> ReportTable:
    # Market OS / >90d are month-end balances: never totalled across months.
    cols = [
        Col("Period", weight=1.6), Col("Status", weight=1.0), Col("Snapshots", "int", total=True),
        Col("Outlets", "int"), _money("Sales (INR)"), _money("Collection (INR)"), Col("Market OS (INR)", "money"),
        Col(">90d (INR)", "money"), Col("Finalized On", "date"),
    ]
    rows = [
        [p.period_name, p.status, p.snapshot_count, p.total_outlets, p.total_sales, p.total_collection,
         p.total_market_os, p.total_overdue_gt_90, p.finalized_at]
        for p in periods
    ]
    return ReportTable(
        title="Monthly Snapshots - Accounting Periods", sheet_name="Monthly Periods", columns=cols, rows=rows,
        filters=filters,
        note=(
            "All monthly reporting periods that hold data. Market OS and >90d are that month's own balance-snapshot "
            "totals; they are blank for a month with no balance snapshot (not derivable from invoices alone)."
        ),
    )


# ----------------------------------------------------------------------------- employee master / overview
def build_employee_master_table(employees, filters) -> ReportTable:
    cols = [
        Col("Employee ID", weight=1.0), Col("Full Name", weight=2.0), Col("Email", weight=2.0), Col("Phone", weight=1.0),
        Col("CUG Number", weight=1.0), Col("Working Profile", weight=1.0), Col("Application Role", weight=1.0),
        Col("Assigned Outlets", "int", total=True), Col("Status", weight=0.7),
    ]
    rows = [
        [e.employee_code or "", e.full_name, e.email or "", e.phone_number or "", e.cug or "",
         e.working_profile or "", e.role, e.assigned_outlets_count, "Active" if e.is_active else "Inactive"]
        for e in employees
    ]
    return ReportTable(title="Employee Master Report", sheet_name="Employees", columns=cols, rows=rows, filters=filters)


def build_overview_table(overview, filters) -> ReportTable:
    from app.services.report_exports import fmt_inr
    cols = [
        Col("Category", weight=1.0), Col("Dimension", weight=2.0), Col("Brand", weight=1.0), Col("Outlets", "int"),
        _money("Sales (INR)"), _money("Collection (INR)"), _money("Market OS (INR)"), _money(">90d (INR)"),
    ]
    rows = []
    for label, src in (("Brand Summary", overview.brand_breakdown), ("Zone Summary", overview.zone_breakdown),
                       ("FOS Summary", overview.fos_breakdown)):
        for b in src:
            rows.append([label, b.dimension_name, b.brand, b.outlets_count, b.sales, b.collection,
                         b.market_outstanding, b.bucket_gt_90])
    return ReportTable(
        title="Overview Report", sheet_name="Overview", columns=cols, rows=rows, filters=filters, totals=False,
        note=overview.data_source_note,
        kpis=[("Employees", str(overview.total_employees)), ("Outlets", str(overview.total_outlets)),
              ("Sales", f"₹{fmt_inr(overview.total_sales)}"), ("Collection", f"₹{fmt_inr(overview.total_collection)}"),
              ("Market OS", f"₹{fmt_inr(overview.total_market_outstanding)}"),
              (">90d", f"₹{fmt_inr(overview.total_overdue_gt_90)}"),
              ("Visits", f"{overview.completed_visits}/{overview.total_visits}")],
    )


# ----------------------------------------------------------------------------- collections overview (live)
def build_collections_overview_table(resp, filters, has_period: bool, as_of: date) -> ReportTable:
    cols = [
        Col("Outlet Code", weight=0.9), Col("Outlet", weight=2.0), Col("Zone", weight=1.1), Col("Area", weight=1.1),
        Col("Assigned Employee(s)", weight=1.5),
        _money("Opening (INR)"), _money("Invoiced (INR)"), _money("Paid in Tally (INR)"),
        _money("Awaiting Tally (INR)"), _money("Outstanding (INR)"), _money("Overdue (INR)"),
        Col("Status", weight=0.8),
    ]
    if has_period:
        cols += [_money("Invoiced in period (INR)"), _money("Collected in period (INR)")]
    cols += [Col("Last payment", "date"), _money("Last payment (INR)")]
    cols[-1].total = False
    rows = []
    for r in resp.outlets:
        row = [
            r.outlet_code or "", r.customer_name, r.territory_name or "", r.area_name or "",
            ", ".join(e.name for e in r.assigned_employees),
            r.opening_balance, r.total_invoiced, r.paid_in_tally, r.verified_awaiting_tally_amount,
            r.total_outstanding, r.overdue_amount, r.collection_status.value if hasattr(r.collection_status, "value") else str(r.collection_status),
        ]
        if has_period:
            row += [r.invoiced_in_period, r.collected_in_period]
        row += [r.most_recent_payment_date, r.most_recent_payment_amount]
        rows.append(row)
    note = (f"Outstanding, Overdue and Opening are as of today ({fmt_date(as_of)}), not the date range. "
            "'Invoiced in period' / 'Collected in period (posted to Tally)' use invoice date / payment date.")
    return ReportTable(
        title="Collections Overview", sheet_name="Collections", columns=cols, rows=rows, filters=filters, note=note,
    )
