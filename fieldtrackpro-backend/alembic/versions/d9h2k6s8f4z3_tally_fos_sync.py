"""Tally FOS assignment synchronisation: group mapping, assignment source/provenance, audit, run log.

Revision ID: d9h2k6s8f4z3
Revises: c8e0g3p5d1x2
Create Date: 2026-11-23 18:00:00.000000

Additive only:
  * employee_customer_assignments: source (existing rows become 'LEGACY'), tally_group, tally_ledger_guid, synced_at
  * customers: fos_status, fos_synced_at (both NULL until the first synchronisation)
  * tally_fos_groups, fos_sync_runs, fos_assignment_audit (new tables)
No existing assignment is changed, added or removed by this migration; it only labels the existing rows LEGACY.
Downgrade drops exactly these objects.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9h2k6s8f4z3"
down_revision: Union[str, None] = "c8e0g3p5d1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employee_customer_assignments",
                  sa.Column("source", sa.String(10), nullable=False, server_default="LEGACY"))
    op.add_column("employee_customer_assignments", sa.Column("tally_group", sa.String(150), nullable=True))
    op.add_column("employee_customer_assignments", sa.Column("tally_ledger_guid", sa.String(255), nullable=True))
    op.add_column("employee_customer_assignments", sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("customers", sa.Column("fos_status", sa.String(16), nullable=True))
    op.add_column("customers", sa.Column("fos_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_customers_fos_status", "customers", ["fos_status"])

    op.create_table(
        "tally_fos_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_key", sa.String(150), nullable=False),
        sa.Column("group_name", sa.String(150), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="UNMAPPED"),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("suggested_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("suggestion_basis", sa.String(120), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tally_fos_groups_group_key", "tally_fos_groups", ["group_key"], unique=True)
    op.create_index("ix_tally_fos_groups_employee_id", "tally_fos_groups", ["employee_id"])

    op.create_table(
        "fos_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("legacy_policy", sa.String(12), nullable=False, server_default="REPORT_ONLY"),
        sa.Column("status", sa.String(10), nullable=False, server_default="RUNNING"),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "fos_assignment_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fos_sync_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name", sa.String(150), nullable=True),
        sa.Column("previous_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_fos", sa.String(300), nullable=True),
        sa.Column("new_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_fos", sa.String(300), nullable=True),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="TALLY"),
        sa.Column("tally_group", sa.String(150), nullable=True),
        sa.Column("tally_ledger_guid", sa.String(255), nullable=True),
        sa.Column("result", sa.String(16), nullable=False, server_default="APPLIED"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fos_assignment_audit_run_id", "fos_assignment_audit", ["run_id"])
    op.create_index("ix_fos_assignment_audit_customer_id", "fos_assignment_audit", ["customer_id"])
    op.create_index("ix_fos_assignment_audit_created_at", "fos_assignment_audit", ["created_at"])
    op.create_index("ix_fos_audit_customer_created", "fos_assignment_audit", ["customer_id", "created_at"])


def downgrade() -> None:
    op.drop_table("fos_assignment_audit")
    op.drop_table("fos_sync_runs")
    op.drop_table("tally_fos_groups")
    op.drop_index("ix_customers_fos_status", table_name="customers")
    op.drop_column("customers", "fos_synced_at")
    op.drop_column("customers", "fos_status")
    op.drop_column("employee_customer_assignments", "synced_at")
    op.drop_column("employee_customer_assignments", "tally_ledger_guid")
    op.drop_column("employee_customer_assignments", "tally_group")
    op.drop_column("employee_customer_assignments", "source")
