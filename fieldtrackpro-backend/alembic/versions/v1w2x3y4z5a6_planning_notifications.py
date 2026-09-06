"""Add planning notification types and link notifications to planned_visits.

Revision ID: v1w2x3y4z5a6
Revises: u0v1w2x3y4z5
Create Date: 2026-09-02 19:38:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "v1w2x3y4z5a6"
down_revision = "u0v1w2x3y4z5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend notification_type_enum with planning notification types
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'PLANNED_VISIT_MISSED'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'EMPLOYEE_SCHEDULE_CHANGED'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'PLANNED_VISIT_CANCELLED'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'RESCHEDULED'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'CANCELLED'")

    # 2. Add planned_visit_id column to notifications table
    op.add_column(
        "notifications",
        sa.Column(
            "planned_visit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("planned_visits.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 3. Add title column to notifications table
    op.add_column(
        "notifications",
        sa.Column("title", sa.String(200), nullable=True),
    )

    # 4. Indexes for performance and duplicate checks
    op.create_index(
        "ix_notifications_planned_visit_id",
        "notifications",
        ["planned_visit_id"],
    )
    op.create_index(
        "ix_notifications_user_id_is_read",
        "notifications",
        ["user_id", "is_read"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id_is_read", table_name="notifications")
    op.drop_index("ix_notifications_planned_visit_id", table_name="notifications")
    op.drop_column("notifications", "title")
    op.drop_column("notifications", "planned_visit_id")
