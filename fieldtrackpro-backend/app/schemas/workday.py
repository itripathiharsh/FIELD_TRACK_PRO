from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.employee_work_session import WorkSessionStatus


class WorkSessionStartRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Start day GPS latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Start day GPS longitude")
    accuracy_meters: Optional[float] = Field(default=None, ge=0.0, description="GPS accuracy in meters")
    client_timestamp: Optional[datetime] = Field(default=None, description="Client captured timestamp")
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional start day field note")


class WorkSessionEndRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="End day GPS latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="End day GPS longitude")
    accuracy_meters: Optional[float] = Field(default=None, ge=0.0, description="GPS accuracy in meters")
    client_timestamp: Optional[datetime] = Field(default=None, description="Client captured timestamp")
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional end day summary note")


class WorkSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    status: WorkSessionStatus
    start_time: Optional[datetime] = None
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    start_accuracy_meters: Optional[float] = None
    end_time: Optional[datetime] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    end_accuracy_meters: Optional[float] = None
    start_notes: Optional[str] = None
    end_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DailyFieldActivitySummary(BaseModel):
    work_date: date
    total_visits: int = 0
    planned_visits: int = 0
    adhoc_visits: int = 0
    completed_visits: int = 0
    missed_visits: int = 0
    flagged_visits: int = 0
    collections_count: int = 0
    collections_total_amount: Decimal = Decimal(0)
    collections_verified_amount: Decimal = Decimal(0)


class EmployeeWorkdayResponse(BaseModel):
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    work_date: date
    session: Optional[WorkSessionRead] = None
    summary: DailyFieldActivitySummary


class EmployeeWorkdaySessionItem(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_code: Optional[str] = None
    work_date: date
    status: WorkSessionStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    start_accuracy_meters: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    end_accuracy_meters: Optional[float] = None
    visits_total: int = 0
    visits_planned: int = 0
    visits_adhoc: int = 0
    visits_completed: int = 0
    collections_amount: Decimal = Decimal(0)


class RequirementFollowUpItem(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    brand: Optional[str] = None
    product_details: Optional[str] = None
    expected_value: Optional[Decimal] = None
    follow_up_date: Optional[date] = None


class TodayFieldActivityOverview(BaseModel):
    work_date: date
    total_employees: int = 0
    employees_started: int = 0
    employees_completed: int = 0
    employees_active: int = 0
    employees_not_started: int = 0
    total_visits: int = 0
    planned_visits: int = 0
    adhoc_visits: int = 0
    completed_visits: int = 0
    total_collections_amount: Decimal = Decimal(0)
    collections_pending_verification: Decimal = Decimal(0)
    collections_verified: Decimal = Decimal(0)
    pending_location_proposals_count: int = 0
    pending_payments_count: int = 0
    recent_prospects_count: int = 0
    upcoming_follow_ups: list[RequirementFollowUpItem] = Field(default_factory=list)
    sessions: list[EmployeeWorkdaySessionItem] = Field(default_factory=list)
