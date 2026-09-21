"""Add multi-item requirement support and confirmed orders pipeline.

Revision ID: a6b7c8d9e0f1
Revises: z5a6b7c8d9e0
Create Date: 2026-09-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "z5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enhance customer_requirements with aggregated total columns
    op.add_column("customer_requirements", sa.Column("total_requested_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("customer_requirements", sa.Column("total_approved_value", sa.Numeric(14, 2), nullable=True))

    # 2. Create requirement_items table
    op.create_table(
        "requirement_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customer_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="SET NULL"), nullable=True),
        sa.Column("brand_name", sa.String(100), nullable=False),
        sa.Column("product_model", sa.String(200), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expected_rate", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("requested_amount", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("approved_quantity", sa.Integer(), nullable=True),
        sa.Column("approved_rate", sa.Numeric(14, 2), nullable=True),
        sa.Column("approved_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("tally_stock_item_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_requirement_items_requirement_id", "requirement_items", ["requirement_id"])
    op.create_index("ix_requirement_items_brand_id", "requirement_items", ["brand_id"])

    # 3. Create orders table
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("order_number", sa.String(100), unique=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customer_requirements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING_TALLY"),
        sa.Column("tally_guid", sa.String(255), nullable=True),
        sa.Column("tally_master_id", sa.String(100), nullable=True),
        sa.Column("tally_voucher_number", sa.String(100), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_requirement_id", "orders", ["requirement_id"])
    op.create_index("ix_orders_visit_id", "orders", ["visit_id"])
    op.create_index("ix_orders_employee_id", "orders", ["employee_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_tally_guid", "orders", ["tally_guid"])

    # 4. Create order_items table
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_name", sa.String(100), nullable=False),
        sa.Column("product_model", sa.String(200), nullable=False),
        sa.Column("stock_item_name", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False, server_default="PCS"),
        sa.Column("rate", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_tally_guid", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_employee_id", table_name="orders")
    op.drop_index("ix_orders_visit_id", table_name="orders")
    op.drop_index("ix_orders_requirement_id", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_requirement_items_brand_id", table_name="requirement_items")
    op.drop_index("ix_requirement_items_requirement_id", table_name="requirement_items")
    op.drop_table("requirement_items")

    op.drop_column("customer_requirements", "total_approved_value")
    op.drop_column("customer_requirements", "total_requested_value")
