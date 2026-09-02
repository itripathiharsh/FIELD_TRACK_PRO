"""
Monthly period lifecycle lock and reopen tracking.

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-08-31 16:15:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add PENDING_CLOSE to monthly_period_status_enum if PostgreSQL
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        op.execute("ALTER TYPE monthly_period_status_enum ADD VALUE IF NOT EXISTS 'PENDING_CLOSE'")

    # 2. Add columns to monthly_reporting_periods
    with op.batch_alter_table("monthly_reporting_periods") as batch_op:
        batch_op.add_column(sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("reopened_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
        )
        batch_op.add_column(sa.Column("reopen_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("monthly_reporting_periods") as batch_op:
        batch_op.drop_column("reopen_reason")
        batch_op.drop_column("reopened_by")
        batch_op.drop_column("reopened_at")
        batch_op.drop_column("opened_at")
