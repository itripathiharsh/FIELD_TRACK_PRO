from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FormStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class QuestionType(str, enum.Enum):
    SHORT_TEXT = "SHORT_TEXT"
    LONG_TEXT = "LONG_TEXT"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    CHECKBOXES = "CHECKBOXES"
    DROPDOWN = "DROPDOWN"
    YES_NO = "YES_NO"
    NUMBER = "NUMBER"
    DATE = "DATE"
    TIME = "TIME"
    DATE_TIME = "DATE_TIME"
    FILE_UPLOAD = "FILE_UPLOAD"
    PHOTO_UPLOAD = "PHOTO_UPLOAD"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    URL = "URL"
    RATING = "RATING"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("requirement_categories.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[FormStatus] = mapped_column(Enum(FormStatus, name="form_status_enum"), default=FormStatus.DRAFT, server_default=FormStatus.DRAFT.value)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped[Optional["RequirementCategory"]] = relationship(back_populates="form_templates")
    sections: Mapped[list["FormSection"]] = relationship(back_populates="form", cascade="all, delete-orphan", order_by="FormSection.display_order")
    questions: Mapped[list["FormQuestion"]] = relationship(back_populates="form", cascade="all, delete-orphan")
    submissions: Mapped[list["FormSubmission"]] = relationship(back_populates="form")
    versions: Mapped[list["FormTemplateVersion"]] = relationship(back_populates="form", cascade="all, delete-orphan")


class FormSection(Base):
    __tablename__ = "form_sections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_templates.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    form: Mapped["FormTemplate"] = relationship(back_populates="sections")
    questions: Mapped[list["FormQuestion"]] = relationship(back_populates="section", cascade="all, delete-orphan", order_by="FormQuestion.display_order")


class FormQuestion(Base):
    __tablename__ = "form_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_sections.id", ondelete="CASCADE"))
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_templates.id", ondelete="CASCADE"))
    question_text: Mapped[str] = mapped_column(Text)
    help_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_type: Mapped[QuestionType] = mapped_column(Enum(QuestionType, name="question_type_enum"))
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    placeholder: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    validation_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    section: Mapped["FormSection"] = relationship(back_populates="questions")
    form: Mapped["FormTemplate"] = relationship(back_populates="questions")
    options: Mapped[list["FormQuestionOption"]] = relationship(back_populates="question", cascade="all, delete-orphan", order_by="FormQuestionOption.display_order")
    answers: Mapped[list["FormAnswer"]] = relationship(back_populates="question")


class FormQuestionOption(Base):
    __tablename__ = "form_question_options"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_questions.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    question: Mapped["FormQuestion"] = relationship(back_populates="options")


class FormTemplateVersion(Base):
    """
    Immutable snapshot of a form's full section/question/option tree, taken
    at the moment it is published. FormSubmission.form_version points here
    (via form_id+version), so a submission always displays the exact
    structure it was answered against, even after the live template moves on
    to later, structurally different versions.
    """
    __tablename__ = "form_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_templates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    form: Mapped["FormTemplate"] = relationship(back_populates="versions")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_templates.id", ondelete="RESTRICT"))
    form_version: Mapped[int] = mapped_column(Integer, nullable=False)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus, name="submission_status_enum"), default=SubmissionStatus.DRAFT, server_default=SubmissionStatus.DRAFT.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    form: Mapped["FormTemplate"] = relationship(back_populates="submissions")
    answers: Mapped[list["FormAnswer"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class FormAnswer(Base):
    __tablename__ = "form_answers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_submissions.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form_questions.id", ondelete="RESTRICT"))
    answer_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    submission: Mapped["FormSubmission"] = relationship(back_populates="answers")
    question: Mapped["FormQuestion"] = relationship(back_populates="answers")
