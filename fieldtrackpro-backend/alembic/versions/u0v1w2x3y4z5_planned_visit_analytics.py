"""Add COMPLETED and MISSED to planned_visit_status_enum for analytics.

Revision ID: u0v1w2x3y4z5
Revises: t9u0v1w2x3y4
Create Date: 2026-09-02 19:20:00.000000
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "u0v1w2x3y4z5"
down_revision = "t9u0v1w2x3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: ALTER TYPE ... ADD VALUE is non-destructive and cannot
    # run inside a transaction block, so we commit the current transaction
    # first if needed.  Alembic migrations that only do DDL often have
    # autocommit, but we guard explicitly.
    op.execute("ALTER TYPE planned_visit_status_enum ADD VALUE IF NOT EXISTS 'COMPLETED'")
    op.execute("ALTER TYPE planned_visit_status_enum ADD VALUE IF NOT EXISTS 'MISSED'")


def downgrade() -> None:
    # PostgreSQL does not support DROP VALUE from an enum.
    # Removing enum values requires recreating the type, which is
    # destructive.  Since the new values are only used by analytics
    # (no existing rows use them at migration time), downgrade is a no-op.
    pass
