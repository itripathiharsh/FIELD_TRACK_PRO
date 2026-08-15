"""
Employee-Territory assignment schemas (P2-D).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.employee_territory_assignment import AssignmentType


class TerritoryAssignmentCreate(BaseModel):
    territory_id: uuid.UUID
    assignment_type: AssignmentType
    start_date: date
    # Required for TEMPORARY, must be omitted/null for PERMANENT - validated
    # in the service layer since the rule depends on assignment_type.
    end_date: date | None = None


class TerritoryAssignmentRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    territory_id: uuid.UUID
    territory_name: str
    assignment_type: AssignmentType
    start_date: date
    end_date: date | None
    created_by: uuid.UUID
    created_by_email: str | None
    created_at: datetime
    # Whether THIS row is the one currently in effect (today), per the same
    # resolution rule as get_effective_territory_id - lets the admin UI
    # highlight "current" without re-deriving the rule client-side.
    is_current: bool


class TerritoryAssignmentHistory(BaseModel):
    employee_id: uuid.UUID
    effective_territory_id: uuid.UUID | None
    effective_territory_name: str | None
    assignments: list[TerritoryAssignmentRead]
