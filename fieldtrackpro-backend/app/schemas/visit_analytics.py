"""Analytics schemas for planned vs actual visit metrics."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EmployeeMonthlyAnalytics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_name: str
    employee_code: Optional[str] = None
    year: int
    month: int
    total_planned: int
    completed: int
    missed: int
    cancelled: int
    extra_unplanned: int
    completion_rate: Optional[float] = None  # None when total_planned = 0
    active_planned_days: int
    active_execution_days: int
    avg_planned_per_active_day: Optional[float] = None
    avg_completed_per_execution_day: Optional[float] = None
    behind_schedule: bool


class DailyAnalytics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    employee_id: uuid.UUID
    employee_name: str
    planned: int
    completed: int
    missed: int
    extra_unplanned: int


class TeamMonthlyAnalytics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    employees: list[EmployeeMonthlyAnalytics] = []
    team_total_planned: int = 0
    team_completed: int = 0
    team_missed: int = 0
    team_cancelled: int = 0
    team_extra: int = 0
    team_completion_rate: Optional[float] = None
