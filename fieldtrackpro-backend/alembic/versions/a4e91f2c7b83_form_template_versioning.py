"""form template versioning: snapshot table + validation_config jsonb fix

Revision ID: a4e91f2c7b83
Revises: f8a2c1d9e3b4
Create Date: 2026-08-11 23:59:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a4e91f2c7b83"
down_revision: Union[str, Sequence[str], None] = "f8a2c1d9e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # form_questions.validation_config was created as TEXT but the ORM model
    # declares it JSONB - the two must agree or asyncpg rejects dict binds.
    op.alter_column(
        "form_questions",
        "validation_config",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="validation_config::jsonb",
        existing_nullable=True,
    )

    # --- form_template_versions -----------------------------------------
    # Immutable snapshot of a form's full section/question/option tree,
    # taken at publish time. FormSubmission.form_version resolves against
    # this table so a historical submission always renders the exact
    # structure it was answered against, never the live (possibly since
    # edited) template rows.
    op.create_table(
        "form_template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_by", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("form_id", "version", name="uq_form_template_versions_form_version"),
    )
    op.create_index("ix_form_template_versions_form", "form_template_versions", ["form_id"])


def downgrade() -> None:
    op.drop_index("ix_form_template_versions_form", table_name="form_template_versions")
    op.drop_table("form_template_versions")

    op.alter_column(
        "form_questions",
        "validation_config",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.Text(),
        existing_nullable=True,
    )
