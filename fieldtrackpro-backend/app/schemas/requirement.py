"""
Requirement form request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RequirementCategoryCreate(BaseModel):
    """Create a new requirement category."""
    name: str = Field(..., min_length=1, max_length=100, description="Category name")


class RequirementCategoryRead(BaseModel):
    """Requirement category metadata."""
    id: uuid.UUID
    name: str
    is_active: bool = True

    model_config = {"from_attributes": True}


class RequirementFormCreate(BaseModel):
    """Submit a requirement form for a visit."""
    category_id: uuid.UUID
    description: str = Field(..., min_length=1, description="Requirement description")
    priority: str = Field(..., pattern="^(LOW|MEDIUM|HIGH)$", description="Priority level")
    expected_timeline: str = Field(..., min_length=1, max_length=100, description="Expected timeline")
    budget_range: Optional[str] = Field(default=None, max_length=100, description="Optional budget range")
    notes: Optional[str] = Field(default=None, description="Optional additional notes")


class RequirementFormRead(BaseModel):
    """Requirement form response."""
    id: uuid.UUID
    visit_id: uuid.UUID
    category_id: uuid.UUID
    category_name: Optional[str] = None
    description: str
    priority: str
    expected_timeline: str
    budget_range: Optional[str] = None
    notes: Optional[str] = None
    submitted_at: datetime

    model_config = {"from_attributes": True}
