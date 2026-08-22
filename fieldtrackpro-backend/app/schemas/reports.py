"""
Report schemas for operational, business intelligence, and monthly reports.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict
from app.schemas.financial_snapshot import BusinessSummaryRow


class DateRangeFilter(BaseModel):
    """Date range filter for reports."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    month: Optional[str] = None  # e.g. "2026-08"
    brand: Optional[str] = None
    zone_id: Optional[uuid.UUID] = None
    area_id: Optional[uuid.UUID] = None
    employee_id: Optional[uuid.UUID] = None
    ageing_bucket: Optional[str] = None
    query: Optional[str] = None


class EmployeeVisitReportRow(BaseModel):
    """Single row in the employee visit report."""
    employee_id: uuid.UUID
    employee_name: str
    total_visits: int
    completed_visits: int
    pending_visits: int
    missed_visits: int
    flagged_visits: int
    completion_rate: float


class EmployeeMasterReportRow(BaseModel):
    """Full employee master row for management reporting."""
    employee_id: uuid.UUID
    employee_code: str
    full_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    cug: Optional[str] = None
    working_profile: Optional[str] = None
    role: str
    is_active: bool
    assigned_outlets_count: int = 0
    zone_names: list[str] = []


class OutletReportRow(BaseModel):
    """Outlet directory reporting row with location and financial snapshot summary."""
    customer_id: uuid.UUID
    dms_code: Optional[str] = None
    outlet_name: str
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    address: Optional[str] = None
    zone_name: Optional[str] = None
    area_name: Optional[str] = None
    fos_name: Optional[str] = None
    brand: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geofence_radius_m: int = 75
    location_status: str = "MISSING"
    sales: Decimal = Decimal("0.00")
    collection: Decimal = Decimal("0.00")
    market_outstanding: Decimal = Decimal("0.00")
    overdue_gt_90: Decimal = Decimal("0.00")


class OutstandingAgeingReportRow(BaseModel):
    """Dedicated outstanding and ageing bucket report row."""
    customer_id: uuid.UUID
    dms_code: Optional[str] = None
    outlet_name: str
    brand: str
    zone_name: Optional[str] = None
    area_name: Optional[str] = None
    fos_name: Optional[str] = None
    market_outstanding: Decimal = Decimal("0.00")
    bucket_lt_15: Decimal = Decimal("0.00")
    bucket_15_30: Decimal = Decimal("0.00")
    bucket_30_45: Decimal = Decimal("0.00")
    bucket_45_60: Decimal = Decimal("0.00")
    bucket_60_75: Decimal = Decimal("0.00")
    bucket_75_90: Decimal = Decimal("0.00")
    bucket_gt_90: Decimal = Decimal("0.00")
    highest_overdue_bucket: str = "Normal"


class CollectionReportRow(BaseModel):
    """Collections report row."""
    customer_id: uuid.UUID
    dms_code: Optional[str] = None
    outlet_name: str
    brand: str
    zone_name: Optional[str] = None
    area_name: Optional[str] = None
    fos_name: Optional[str] = None
    collection_amount: Decimal = Decimal("0.00")
    sales_amount: Decimal = Decimal("0.00")
    snapshot_date: date


class VisitDetailedReportRow(BaseModel):
    """Detailed operational visit reporting row."""
    visit_id: uuid.UUID
    scheduled_at: str
    employee_name: str
    customer_name: str
    dms_code: Optional[str] = None
    zone_name: Optional[str] = None
    area_name: Optional[str] = None
    status: str
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_gps_verified: bool = False
    distance_m: Optional[float] = None


class CustomerVisitHistoryRow(BaseModel):
    """Single row in the customer visit history report."""
    visit_id: uuid.UUID
    scheduled_at: str
    status: str
    employee_name: str
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None


class ProductivityDashboard(BaseModel):
    """Productivity dashboard data."""
    total_employees: int
    active_employees: int
    total_visits_today: int
    completed_visits_today: int
    pending_visits_today: int
    missed_visits_today: int
    flagged_visits_today: int
    avg_visits_per_employee: float


class GeoVerificationReportRow(BaseModel):
    """Single row in the geo-verification report."""
    visit_id: uuid.UUID
    employee_name: str
    customer_name: str
    dms_code: Optional[str] = None
    attempted_at: str
    verification_type: str
    is_valid: bool
    distance_m: float
    failure_reason: Optional[str] = None


class OverviewReportData(BaseModel):
    """Consolidated high-level Overview KPI & breakdown report."""
    total_employees: int
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    total_market_outstanding: Decimal
    total_overdue_gt_90: Decimal
    total_visits: int
    completed_visits: int
    completion_rate: float
    brand_breakdown: list[BusinessSummaryRow]
    zone_breakdown: list[BusinessSummaryRow]
    fos_breakdown: list[BusinessSummaryRow]


class OrderReportRow(BaseModel):
    """Order activity reporting row."""
    order_id: uuid.UUID
    order_date: str
    employee_name: str
    outlet_name: str
    dms_code: Optional[str] = None
    brand: Optional[str] = None
    order_value: Decimal = Decimal("0.00")
    status: str = "COMPLETED"


class ExportRequest(BaseModel):
    """Export request payload."""
    report_type: str
    format: str = "xlsx"  # xlsx, pdf, csv
    month: Optional[str] = None
    brand: Optional[str] = None
    zone_id: Optional[uuid.UUID] = None
    area_id: Optional[uuid.UUID] = None
    employee_id: Optional[uuid.UUID] = None
    ageing_bucket: Optional[str] = None
