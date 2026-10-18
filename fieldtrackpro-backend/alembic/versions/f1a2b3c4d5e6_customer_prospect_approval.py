"""Customer prospect approval workflow + needs_tally_entry flag on customers.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-10-11 20:00:00.000000

A new outlet submitted by an employee no longer becomes a live Customer row
immediately - it's held in customer_prospects (PENDING/APPROVED/REJECTED)
until an admin reviews and approves it. On approval the real Customer row is
created with needs_tally_entry=True, since there is no Tally writeback for
customers (Tally sync is import-only) - an admin must add it to Tally by hand
and later mark it done.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing_tables = set(insp.get_table_names())

    if "customer_prospects" not in existing_tables:
        op.create_table(
            "customer_prospects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("contact_number", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("contact_person", sa.String(length=150), nullable=True),
            sa.Column("gst_number", sa.String(length=20), nullable=True),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("outlet_code", sa.String(length=50), nullable=True),
            sa.Column("territory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("territories.id", ondelete="SET NULL"), nullable=True),
            sa.Column("area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("areas.id", ondelete="SET NULL"), nullable=True),
            sa.Column("brand_names", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("proposed_latitude", sa.Float(), nullable=True),
            sa.Column("proposed_longitude", sa.Float(), nullable=True),
            sa.Column("gps_accuracy_meters", sa.Float(), nullable=True),
            sa.Column("location_notes", sa.String(length=500), nullable=True),
            sa.Column("requirement_payload", sa.JSON(), nullable=True),
            sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("submitted_by_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.String(length=255), nullable=True),
            sa.Column("resulting_customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_customer_prospects_status", "customer_prospects", ["status"])

    cust_cols = {c["name"] for c in insp.get_columns("customers")}
    if "needs_tally_entry" not in cust_cols:
        op.add_column(
            "customers",
            sa.Column("needs_tally_entry", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "tally_entry_marked_by" not in cust_cols:
        op.add_column(
            "customers",
            sa.Column("tally_entry_marked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
    if "tally_entry_marked_at" not in cust_cols:
        op.add_column("customers", sa.Column("tally_entry_marked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cust_cols = {c["name"] for c in insp.get_columns("customers")}
    if "tally_entry_marked_at" in cust_cols:
        op.drop_column("customers", "tally_entry_marked_at")
    if "tally_entry_marked_by" in cust_cols:
        op.drop_column("customers", "tally_entry_marked_by")
    if "needs_tally_entry" in cust_cols:
        op.drop_column("customers", "needs_tally_entry")

    existing_tables = set(insp.get_table_names())
    if "customer_prospects" in existing_tables:
        op.drop_index("ix_customer_prospects_status", table_name="customer_prospects")
        op.drop_table("customer_prospects")
