"""create payment_brand_allocations table

Revision ID: m1n2o3p4q5r6
Revises: l5m6n7o8p9q0
Create Date: 2026-08-30 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "l5m6n7o8p9q0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_brand_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("payment_id", "brand", name="uq_payment_brand_allocations_payment_brand"),
    )
    op.create_index("ix_payment_brand_allocations_payment_id", "payment_brand_allocations", ["payment_id"])
    op.create_index("ix_payment_brand_allocations_brand", "payment_brand_allocations", ["brand"])


def downgrade() -> None:
    op.drop_index("ix_payment_brand_allocations_brand", table_name="payment_brand_allocations")
    op.drop_index("ix_payment_brand_allocations_payment_id", table_name="payment_brand_allocations")
    op.drop_table("payment_brand_allocations")
