"""real client data integration: employee fields, location status, assignments, fos mappings, financial snapshots

Revision ID: e5f6a7b8c9d0
Revises: 27d98b38e3c6
Create Date: 2026-08-22 01:20:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "27d98b38e3c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update employees table
    op.add_column("employees", sa.Column("working_profile", sa.String(100), nullable=True))
    op.add_column("employees", sa.Column("cug", sa.String(30), nullable=True))
    op.add_column("employees", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("father_name", sa.String(150), nullable=True))
    op.add_column("employees", sa.Column("mother_name", sa.String(150), nullable=True))
    op.add_column("employees", sa.Column("aadhaar_no", sa.String(50), nullable=True))
    op.add_column("employees", sa.Column("pan_no", sa.String(50), nullable=True))
    op.add_column("employees", sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    # 2. Update customers table
    op.add_column("customers", sa.Column("location_status", sa.String(30), server_default="MISSING", nullable=False))
    # Make geography location column nullable for bulk imported rows
    op.alter_column("customers", "location", nullable=True)

    # 3. Create employee_customer_assignments table
    op.create_table(
        "employee_customer_assignments",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "customer_id", name="uq_employee_customer_assignment"),
    )

    # 4. Create fos_employee_mappings table
    op.create_table(
        "fos_employee_mappings",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("raw_fos_name", sa.String(150), nullable=False, unique=True, index=True),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 5. Create outlet_financial_snapshots table
    op.create_table(
        "outlet_financial_snapshots",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("brand", sa.String(100), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("sales", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("collection", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("market_outstanding", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_lt_15", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_15_30", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_30_45", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_45_60", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_60_75", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_75_90", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("bucket_gt_90", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("import_batch_id", sa.UUID(), sa.ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("customer_id", "brand", "snapshot_date", name="uq_customer_brand_snapshot_date"),
    )


def downgrade() -> None:
    op.drop_table("outlet_financial_snapshots")
    op.drop_table("fos_employee_mappings")
    op.drop_table("employee_customer_assignments")
    op.alter_column("customers", "location", nullable=False)
    op.drop_column("customers", "location_status")
    op.drop_column("employees", "must_change_password")
    op.drop_column("employees", "pan_no")
    op.drop_column("employees", "aadhaar_no")
    op.drop_column("employees", "mother_name")
    op.drop_column("employees", "father_name")
    op.drop_column("employees", "address")
    op.drop_column("employees", "date_of_birth")
    op.drop_column("employees", "cug")
    op.drop_column("employees", "working_profile")
