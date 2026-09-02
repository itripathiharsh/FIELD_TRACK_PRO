"""
Customer location proposals, customer brands, customer requirements, and customer gst_number.

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-08-30 20:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None

location_proposal_status_enum = ENUM("PENDING", "APPROVED", "REJECTED", name="location_proposal_status_enum", create_type=False)


def upgrade() -> None:
    # 1. Create Enum for location proposal status
    location_proposal_status_enum_create = ENUM("PENDING", "APPROVED", "REJECTED", name="location_proposal_status_enum")
    location_proposal_status_enum_create.create(op.get_bind(), checkfirst=True)

    # 2. Add gst_number to customers
    op.add_column(
        "customers",
        sa.Column("gst_number", sa.String(20), nullable=True),
    )
    op.create_index("ix_customers_gst_number", "customers", ["gst_number"])

    # 3. Create customer_location_proposals table
    op.create_table(
        "customer_location_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposed_latitude", sa.Float(), nullable=False),
        sa.Column("proposed_longitude", sa.Float(), nullable=False),
        sa.Column("gps_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("submitted_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", location_proposal_status_enum, server_default="PENDING", nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_location_proposals_customer_id", "customer_location_proposals", ["customer_id"])
    op.create_index("ix_customer_location_proposals_status", "customer_location_proposals", ["status"])

    # 4. Create customer_brands table
    op.create_table(
        "customer_brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("customer_id", "brand", name="uq_customer_brands_customer_brand"),
    )
    op.create_index("ix_customer_brands_customer_id", "customer_brands", ["customer_id"])
    op.create_index("ix_customer_brands_brand", "customer_brands", ["brand"])

    # 5. Create customer_requirements table
    op.create_table(
        "customer_requirements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("requirement_type", sa.String(100), nullable=True),
        sa.Column("product_details", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("expected_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="OPEN", nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_requirements_customer_id", "customer_requirements", ["customer_id"])
    op.create_index("ix_customer_requirements_status", "customer_requirements", ["status"])
    op.create_index("ix_customer_requirements_follow_up_date", "customer_requirements", ["follow_up_date"])


def downgrade() -> None:
    op.drop_index("ix_customer_requirements_follow_up_date", table_name="customer_requirements")
    op.drop_index("ix_customer_requirements_status", table_name="customer_requirements")
    op.drop_index("ix_customer_requirements_customer_id", table_name="customer_requirements")
    op.drop_table("customer_requirements")

    op.drop_index("ix_customer_brands_brand", table_name="customer_brands")
    op.drop_index("ix_customer_brands_customer_id", table_name="customer_brands")
    op.drop_table("customer_brands")

    op.drop_index("ix_customer_location_proposals_status", table_name="customer_location_proposals")
    op.drop_index("ix_customer_location_proposals_customer_id", table_name="customer_location_proposals")
    op.drop_table("customer_location_proposals")

    op.drop_index("ix_customers_gst_number", table_name="customers")
    op.drop_column("customers", "gst_number")

    location_proposal_status_enum_drop = ENUM("PENDING", "APPROVED", "REJECTED", name="location_proposal_status_enum")
    location_proposal_status_enum_drop.drop(op.get_bind(), checkfirst=True)
