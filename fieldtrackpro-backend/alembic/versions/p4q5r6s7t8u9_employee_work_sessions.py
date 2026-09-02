"""
Employee work sessions for Start Day / End Day and Daily Field Activity.

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-08-30 20:20:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None

work_session_status_enum = ENUM(
    "NOT_STARTED", "STARTED", "COMPLETED",
    name="work_session_status_enum",
    create_type=False
)


def upgrade() -> None:
    # 1. Create work session status enum
    work_session_status_enum_create = ENUM(
        "NOT_STARTED", "STARTED", "COMPLETED",
        name="work_session_status_enum"
    )
    work_session_status_enum_create.create(op.get_bind(), checkfirst=True)

    # 2. Create employee_work_sessions table
    op.create_table(
        "employee_work_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("status", work_session_status_enum, nullable=False, server_default="STARTED"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_latitude", sa.Float(), nullable=True),
        sa.Column("start_longitude", sa.Float(), nullable=True),
        sa.Column("start_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_latitude", sa.Float(), nullable=True),
        sa.Column("end_longitude", sa.Float(), nullable=True),
        sa.Column("end_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("start_notes", sa.Text(), nullable=True),
        sa.Column("end_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_employee_work_date"),
    )
    op.create_index("ix_employee_work_sessions_employee_id", "employee_work_sessions", ["employee_id"])
    op.create_index("ix_employee_work_sessions_work_date", "employee_work_sessions", ["work_date"])
    op.create_index("ix_employee_work_sessions_status", "employee_work_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_employee_work_sessions_status", table_name="employee_work_sessions")
    op.drop_index("ix_employee_work_sessions_work_date", table_name="employee_work_sessions")
    op.drop_index("ix_employee_work_sessions_employee_id", table_name="employee_work_sessions")
    op.drop_table("employee_work_sessions")
    work_session_status_enum.drop(op.get_bind(), checkfirst=True)
