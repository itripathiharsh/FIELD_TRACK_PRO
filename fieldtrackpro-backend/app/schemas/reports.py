"""
Report schemas.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel


class DateRangeFilter(BaseModel):
    """Date range filter for reports."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None


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
    attempted_at: str
    verification_type: str
    is_valid: bool
    distance_m: float
    failure_reason: Optional[str] = None


class ExportRequest(BaseModel):
    """Export request payload."""
    report_type: str
    format: str = "csv"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
