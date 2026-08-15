"""form template builder: templates, sections, questions, options, submissions, answers

Revision ID: f8a2c1d9e3b4
Revises: c3d81b6f4a52
Create Date: 2026-08-11 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
import geoalchemy2


revision: str = "f8a2c1d9e3b4"
down_revision: Union[str, Sequence[str], None] = "c3d81b6f4a52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- form_templates ------------------------------------------------------
    op.create_table(
        "form_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", "ARCHIVED", name="form_status_enum"), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["requirement_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_templates_category", "form_templates", ["category_id"])
    op.create_index("ix_form_templates_status", "form_templates", ["status"])

    # --- form_sections -------------------------------------------------------
    op.create_table(
        "form_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_sections_form", "form_sections", ["form_id"])

    # --- form_questions ------------------------------------------------------
    op.create_table(
        "form_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column(
            "question_type",
            sa.Enum(
                "SHORT_TEXT", "LONG_TEXT", "MULTIPLE_CHOICE", "CHECKBOXES",
                "DROPDOWN", "YES_NO", "NUMBER", "DATE", "TIME", "DATE_TIME",
                "FILE_UPLOAD", "PHOTO_UPLOAD", "EMAIL", "PHONE", "URL", "RATING",
                name="question_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("placeholder", sa.String(length=255), nullable=True),
        sa.Column("validation_config", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["form_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["form_id"], ["form_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_questions_section", "form_questions", ["section_id"])
    op.create_index("ix_form_questions_form", "form_questions", ["form_id"])

    # --- form_question_options -----------------------------------------------
    op.create_table(
        "form_question_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["question_id"], ["form_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_question_options_question", "form_question_options", ["question_id"])

    # --- form_submissions ----------------------------------------------------
    op.create_table(
        "form_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", name="submission_status_enum"), nullable=False, server_default="DRAFT"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_submissions_form", "form_submissions", ["form_id"])
    op.create_index("ix_form_submissions_visit", "form_submissions", ["visit_id"])
    op.create_index("ix_form_submissions_submitted_by", "form_submissions", ["submitted_by"])

    # --- form_answers --------------------------------------------------------
    op.create_table(
        "form_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["form_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["form_questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_form_answers_submission", "form_answers", ["submission_id"])
    op.create_index("ix_form_answers_question", "form_answers", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_form_answers_question", table_name="form_answers")
    op.drop_index("ix_form_answers_submission", table_name="form_answers")
    op.drop_table("form_answers")

    op.drop_index("ix_form_submissions_submitted_by", table_name="form_submissions")
    op.drop_index("ix_form_submissions_visit", table_name="form_submissions")
    op.drop_index("ix_form_submissions_form", table_name="form_submissions")
    op.drop_table("form_submissions")

    op.drop_index("ix_form_question_options_question", table_name="form_question_options")
    op.drop_table("form_question_options")

    op.drop_index("ix_form_questions_form", table_name="form_questions")
    op.drop_index("ix_form_questions_section", table_name="form_questions")
    op.drop_table("form_questions")

    op.drop_index("ix_form_sections_form", table_name="form_sections")
    op.drop_table("form_sections")

    op.drop_index("ix_form_templates_status", table_name="form_templates")
    op.drop_index("ix_form_templates_category", table_name="form_templates")
    op.drop_table("form_templates")
