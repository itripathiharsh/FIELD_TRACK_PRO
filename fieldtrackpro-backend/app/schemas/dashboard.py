from __future__ import annotations
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from app.schemas.financial_snapshot import BusinessSummaryRow
from app.schemas.field_exception import FieldExceptionRead


class DashboardExecutiveKPIs(BaseModel):
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    total_market_outstanding: Decimal
    total_overdue_gt_90: Decimal
    total_employees: int
    total_visits: int
    completed_visits: int
    pending_visits: int
    flagged_visits: int
    gps_verified_visits: int
    total_exceptions: int
    pending_exceptions: int
    total_collections_count: int
    total_orders_count: int


class DashboardSummaryResponse(BaseModel):
    period: str  # e.g. "LIVE" or "2026-08"
    is_historical: bool
    kpis: DashboardExecutiveKPIs
    brand_breakdown: list[BusinessSummaryRow]
    fos_breakdown: list[BusinessSummaryRow]
    zone_breakdown: list[BusinessSummaryRow]
    area_breakdown: list[BusinessSummaryRow]
    ageing_distribution: dict[str, Decimal]
    recent_exceptions: list[FieldExceptionRead]


class EmployeeDayDashboardResponse(BaseModel):
    employee_id: str
    employee_name: str
    assigned_outlets_count: int
    today_visits_count: int
    completed_visits_count: int
    pending_visits_count: int
    collections_today_count: int
    collections_today_amount: Decimal
    orders_today_count: int
