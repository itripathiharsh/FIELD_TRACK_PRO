"""
Pydantic schemas for the form template builder.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.form_template import (
    FormStatus,
    QuestionType,
    SubmissionStatus,
)


# ---------------------------------------------------------------------------
# Question Options
# ---------------------------------------------------------------------------

class QuestionOptionCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=255)
    display_order: int = 0


class QuestionOptionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    value: Optional[str] = Field(default=None, min_length=1, max_length=255)
    display_order: Optional[int] = None


class QuestionOptionRead(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    label: str
    value: str
    display_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

class QuestionCreate(BaseModel):
    section_id: uuid.UUID
    question_text: str = Field(..., min_length=1)
    help_text: Optional[str] = None
    question_type: QuestionType
    required: bool = False
    display_order: int = 0
    placeholder: Optional[str] = None
    validation_config: Optional[dict[str, Any]] = None
    options: list[QuestionOptionCreate] = []


class QuestionUpdate(BaseModel):
    section_id: Optional[uuid.UUID] = None
    question_text: Optional[str] = Field(default=None, min_length=1)
    help_text: Optional[str] = None
    question_type: Optional[QuestionType] = None
    required: Optional[bool] = None
    display_order: Optional[int] = None
    placeholder: Optional[str] = None
    validation_config: Optional[dict[str, Any]] = None


class QuestionRead(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    form_id: uuid.UUID
    question_text: str
    help_text: Optional[str]
    question_type: QuestionType
    required: bool
    display_order: int
    placeholder: Optional[str]
    validation_config: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    options: list[QuestionOptionRead] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

class SectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: int = 0


class SectionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: Optional[int] = None


class SectionRead(BaseModel):
    id: uuid.UUID
    form_id: uuid.UUID
    title: str
    description: Optional[str]
    display_order: int
    created_at: datetime
    updated_at: datetime
    questions: list[QuestionRead] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Form Templates
# ---------------------------------------------------------------------------

class FormTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    sections: list[SectionCreate] = []


class FormTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None


class FormTemplateRead(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    category_id: Optional[uuid.UUID]
    status: FormStatus
    version: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    archived_at: Optional[datetime]
    sections: list[SectionRead] = []
    category_name: Optional[str] = None
    question_count: int = 0

    model_config = {"from_attributes": True}


class FormTemplateListRead(BaseModel):
    """Lightweight form template for list views."""
    id: uuid.UUID
    name: str
    description: Optional[str]
    category_id: Optional[uuid.UUID]
    status: FormStatus
    version: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    category_name: Optional[str] = None
    question_count: int = 0
    submission_count: int = 0
    # How many visits currently require this template - the "Used by N
    # visits" signal that tells an admin whether a form is actually wired
    # into real work before archiving/deleting it.
    visit_count: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Submissions & Answers
# ---------------------------------------------------------------------------

class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    answer_value: Optional[str] = None


class SubmissionCreate(BaseModel):
    form_id: uuid.UUID
    visit_id: uuid.UUID
    answers: list[AnswerSubmit] = []


class SubmissionUpdate(BaseModel):
    answers: list[AnswerSubmit] = []


class AnswerRead(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    question_id: uuid.UUID
    answer_value: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Enriched fields for display
    question_text: Optional[str] = None
    question_type: Optional[QuestionType] = None
    options: list[QuestionOptionRead] = []

    model_config = {"from_attributes": True}


class SubmissionRead(BaseModel):
    id: uuid.UUID
    form_id: uuid.UUID
    form_version: int
    visit_id: uuid.UUID
    submitted_by: uuid.UUID
    status: SubmissionStatus
    started_at: datetime
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Enriched fields - who filled it, for which outlet, during which visit.
    # "Obvious context" per the admin-review requirement: a submission is
    # never just a floating form_id/visit_id pair to the person reviewing it.
    form_name: Optional[str] = None
    employee_name: Optional[str] = None
    customer_name: Optional[str] = None
    outlet_code: Optional[str] = None
    visit_scheduled_at: Optional[datetime] = None
    answers: list[AnswerRead] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Employee-facing: form with answers for rendering
# ---------------------------------------------------------------------------

class FormRenderRead(BaseModel):
    """Complete form structure for employee rendering."""
    id: uuid.UUID
    name: str
    description: Optional[str]
    version: int
    status: FormStatus
    sections: list[SectionRead] = []


class SubmissionDetailRead(BaseModel):
    """Full submission with all answers for admin review."""
    id: uuid.UUID
    form_id: uuid.UUID
    form_name: str
    form_version: int
    visit_id: uuid.UUID
    submitted_by: uuid.UUID
    employee_name: Optional[str]
    customer_name: Optional[str] = None
    outlet_code: Optional[str] = None
    territory_name: Optional[str] = None
    visit_scheduled_at: Optional[datetime] = None
    status: SubmissionStatus
    started_at: datetime
    submitted_at: Optional[datetime]
    answers: list[AnswerRead] = []
    sections: list[SectionRead] = []
