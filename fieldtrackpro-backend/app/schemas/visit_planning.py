from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.monthly_visit_plan import MonthlyPlanStatus, PlannedVisitStatus
from app.models.requirement_form import Priority
from app.models.visit import VisitType


class PlannedVisitCreate(BaseModel):
    customer_id: uuid.UUID = Field(..., description="Target customer/outlet ID")
    planned_date: date = Field(..., description="Planned date of visit (YYYY-MM-DD)")
    visit_type: VisitType = Field(default=VisitType.PLANNED, description="Visit type (PLANNED, AD_HOC)")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority (LOW, MEDIUM, HIGH)")
    notes: Optional[str] = Field(default=None, max_length=1000, description="Planning remarks or objectives")
    employee_id: Optional[uuid.UUID] = Field(default=None, description="Admin-only: specify employee ID to plan for")


class PlannedVisitUpdate(BaseModel):
    priority: Optional[Priority] = Field(default=None, description="Updated priority")
    notes: Optional[str] = Field(default=None, max_length=1000, description="Updated notes")
    visit_type: Optional[VisitType] = Field(default=None, description="Updated visit type")


class PlannedVisitReschedule(BaseModel):
    new_date: date = Field(..., description="New target date for the planned visit")


class PlannedVisitReassign(BaseModel):
    new_employee_id: uuid.UUID = Field(..., description="Target employee to reassign this visit to")


class PlannedVisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monthly_plan_id: uuid.UUID
    employee_id: uuid.UUID
    customer_id: uuid.UUID
    planned_date: date
    visit_type: VisitType
    priority: Priority
    notes: Optional[str] = None
    status: PlannedVisitStatus
    created_at: datetime
    updated_at: datetime

    # Display properties
    customer_name: Optional[str] = ""
    customer_outlet_code: Optional[str] = None
    customer_address: Optional[str] = ""
    employee_name: Optional[str] = ""
    employee_code: Optional[str] = None
    area_name: Optional[str] = None
    territory_name: Optional[str] = None


class MonthlyVisitPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    year: int
    month: int
    status: MonthlyPlanStatus
    notes: Optional[str] = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    employee_name: Optional[str] = ""
    employee_code: Optional[str] = None

    planned_visits: list[PlannedVisitRead] = []
    total_planned_visits: int = 0
    active_days_count: int = 0


class MonthlyPlanSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_code: Optional[str] = None
    year: int
    month: int
    status: MonthlyPlanStatus
    total_planned_visits: int = 0
    active_days_count: int = 0


class TeamMonthlyPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    total_planned_visits: int = 0
    active_days_count: int = 0
    active_employees_count: int = 0
    planned_visits: list[PlannedVisitRead] = []
