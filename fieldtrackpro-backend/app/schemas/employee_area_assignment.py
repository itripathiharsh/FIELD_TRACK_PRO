"""
Employee <-> Area coverage schemas - many-to-many, brand-agnostic. See
app/models/employee_area_assignment.py for why this exists alongside (not
instead of) the older single-Zone Employee.territory_id model.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class EmployeeAreaAssignmentCreate(BaseModel):
    area_id: uuid.UUID


class EmployeeAreaAssignmentRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    area_id: uuid.UUID
    area_name: str
    territory_id: uuid.UUID
    territory_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
