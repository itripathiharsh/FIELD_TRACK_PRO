"""create monthly reporting periods table

Revision ID: f1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-08-22 02:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create monthly_reporting_periods table
    op.create_table(
        "monthly_reporting_periods",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("period_year", sa.Integer(), nullable=False, index=True),
        sa.Column("period_month", sa.Integer(), nullable=False, index=True),
        sa.Column("period_name", sa.String(50), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "FINALIZED", name="monthly_period_status_enum", create_type=False), server_default="OPEN", nullable=False),
        sa.Column("snapshot_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_outlets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_sales", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("total_collection", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("total_market_os", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("total_overdue_gt_90", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("period_year", "period_month", name="uq_monthly_reporting_period_year_month"),
    )


def downgrade() -> None:
    op.drop_table("monthly_reporting_periods")
    sa.Enum(name="monthly_period_status_enum").drop(op.get_bind(), checkfirst=True)
