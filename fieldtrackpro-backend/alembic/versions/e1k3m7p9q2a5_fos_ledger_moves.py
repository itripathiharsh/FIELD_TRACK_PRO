"""Per-outlet FOS changes made in FieldTrack, awaiting the matching ledger move in Tally.

Revision ID: e1k3m7p9q2a5
Revises: d9h2k6s8f4z3
Create Date: 2026-11-24 10:00:00.000000

Additive only: one new table, fos_ledger_moves. No existing row is changed.
Downgrade drops exactly this table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1k3m7p9q2a5"
down_revision: Union[str, None] = "d9h2k6s8f4z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fos_ledger_moves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tally_debtor_ledgers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tally_ledger_guid", sa.String(255), nullable=True),
        sa.Column("ledger_name", sa.String(150), nullable=True),
        sa.Column("from_group", sa.String(150), nullable=True),
        sa.Column("to_group", sa.String(150), nullable=True),
        sa.Column("previous_employee_ids", postgresql.JSONB(), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING_TALLY"),
        sa.Column("writeback_status", sa.String(16), nullable=False, server_default="NOT_SENT"),
        sa.Column("writeback_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("writeback_error", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fos_ledger_moves_customer_id", "fos_ledger_moves", ["customer_id"])
    op.create_index("ix_fos_ledger_moves_status", "fos_ledger_moves", ["status"])
    op.create_index("ix_fos_ledger_moves_idempotency_key", "fos_ledger_moves", ["idempotency_key"], unique=True)
    # At most one open move per outlet (a new change supersedes the open one explicitly, in the service).
    op.create_index("uq_fos_ledger_moves_open_customer", "fos_ledger_moves", ["customer_id"], unique=True,
                    postgresql_where=sa.text("status IN ('PENDING_TALLY', 'CONFLICT')"))


def downgrade() -> None:
    op.drop_index("uq_fos_ledger_moves_open_customer", table_name="fos_ledger_moves")
    op.drop_index("ix_fos_ledger_moves_idempotency_key", table_name="fos_ledger_moves")
    op.drop_index("ix_fos_ledger_moves_status", table_name="fos_ledger_moves")
    op.drop_index("ix_fos_ledger_moves_customer_id", table_name="fos_ledger_moves")
    op.drop_table("fos_ledger_moves")
