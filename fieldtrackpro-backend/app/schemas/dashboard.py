from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from app.schemas.financial_snapshot import BusinessSummaryRow
from app.schemas.field_exception import FieldExceptionRead


class DashboardExecutiveKPIs(BaseModel):
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    # Additive split of VERIFIED live collections (same filters as total_collection):
    # receipt confirmed in Tally vs verified but not yet in Tally. total_collection
    # itself keeps counting at VERIFIED (cash received).
    total_collection_posted_in_tally: Decimal = Decimal("0.00")
    total_collection_verified_awaiting_tally: Decimal = Decimal("0.00")
    total_market_outstanding: Decimal
    total_overdue_gt_90: Decimal
    total_employees: int
    total_visits: int
    completed_visits: int
    pending_visits: int
    in_progress_visits: int = 0
    flagged_visits: int
    gps_verified_visits: int
    total_exceptions: int
    pending_exceptions: int
    total_collections_count: int
    total_orders_count: int


class DashboardRecentVisit(BaseModel):
    """One row of the dashboard's "Recent Field Operations" list (same filters as every other widget)."""
    id: str
    customer_id: str
    customer_name: str
    employee_name: str
    scheduled_at: datetime
    status: str
    check_in_at: Optional[datetime] = None


class DashboardSummaryResponse(BaseModel):
    period: str  # e.g. "LIVE", "2026-08" or "FY2025-26"
    is_historical: bool
    # True when the period lies before the reporting floor (a past financial year): a read-only history view,
    # kept apart from Current Live Data and from the monthly close workflow.
    is_history: bool = False
    kpis: DashboardExecutiveKPIs
    brand_breakdown: list[BusinessSummaryRow]
    fos_breakdown: list[BusinessSummaryRow]
    zone_breakdown: list[BusinessSummaryRow]
    area_breakdown: list[BusinessSummaryRow]
    ageing_distribution: dict[str, Decimal]
    recent_exceptions: list[FieldExceptionRead]
    # What the figures are: LIVE_INVOICES (live from Tally, as of today) or SNAPSHOT (monthly snapshot).
    data_source: str = "LIVE_INVOICES"
    data_source_note: Optional[str] = None
    as_of_date: Optional[date] = None
    # Echo of the applied filters, so the page can show exactly what was applied.
    applied_brands: list[str] = []
    applied_periods: list[str] = []
    applied_employee_ids: list[str] = []
    ageing_bucket: Optional[str] = None
    ageing_basis: Optional[str] = None
    recent_visits: list[DashboardRecentVisit] = []


class EmployeeDayDashboardResponse(BaseModel):
    employee_id: str
    employee_name: str
    assigned_outlets_count: int
    today_visits_count: int
    completed_visits_count: int
    pending_visits_count: int
    in_progress_visits_count: int = 0
    collections_today_count: int
    collections_today_amount: Decimal
    orders_today_count: int


class HistoryMonth(BaseModel):
    value: str          # "2025-07"
    label: str          # "July 2025"
    invoices: int
    payments: int


class HistoryPeriod(BaseModel):
    value: str          # "FY2025-26"
    label: str          # "FY 2025-26"
    start: str
    end: str
    invoices: int
    payments: int
    months: list[HistoryMonth]


class HistoryPeriodsResponse(BaseModel):
    reporting_floor: str
    periods: list[HistoryPeriod]
