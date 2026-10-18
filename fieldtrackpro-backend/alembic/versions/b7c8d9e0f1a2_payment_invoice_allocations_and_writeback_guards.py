"""Create payment_invoice_allocations (model/migration drift fix) and cancel
Tally write-back jobs that belong to unverified payments.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-10-10 10:00:00.000000

The PaymentInvoiceAllocation model existed with no migration, so a database
built purely from `alembic upgrade head` lacked the table (POST /invoices
raised UndefinedTableError).

Data step: old code enqueued a Tally write-back at payment CREATION. Payments
that are still PENDING_VERIFICATION or REJECTED must never reach Tally, so any
PENDING/PROCESSING job whose payment is not VERIFIED is moved to FAILED with an
explanatory last_error (never deleted - kept for audit). Verified payments and
already CONFIRMED jobs are untouched. The statement is idempotent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "payment_invoice_allocations" not in insp.get_table_names():
        op.create_table(
            "payment_invoice_allocations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("bill_name", sa.String(150), nullable=True),
            sa.Column("bill_type", sa.String(50), nullable=True),
            sa.Column("allocated_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocations_payment_invoice"),
        )
        op.create_index("ix_payment_invoice_allocations_payment_id", "payment_invoice_allocations", ["payment_id"])
        op.create_index("ix_payment_invoice_allocations_invoice_id", "payment_invoice_allocations", ["invoice_id"])

    # Second drift: SyncAgent.tally_status had no column.
    sync_cols = {c["name"] for c in insp.get_columns("sync_agents")}
    if "tally_status" not in sync_cols:
        op.add_column("sync_agents", sa.Column("tally_status", sa.String(50), nullable=True))

    # Third drift: Payment.employee_id is Optional in the model (historical
    # TALLY / EXCEL_IMPORT receipts have no field employee) but the column was
    # NOT NULL, so POST /integrations/tally/sync/payments crashed.
    op.alter_column("payments", "employee_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    # Cancel write-back jobs of payments that were never verified (old behaviour
    # enqueued at creation). Not deleted; marked FAILED with a reason.
    op.execute(
        """
        UPDATE tally_writeback_queue q
           SET status = 'FAILED',
               next_retry_at = NULL,
               last_error = 'Cancelled by migration: payment is not VERIFIED (write-back is enqueued only on verification)'
          FROM payments p
         WHERE q.entity_type = 'PAYMENT'
           AND q.entity_id = p.id
           AND q.status IN ('PENDING', 'PROCESSING')
           AND p.status::text <> 'VERIFIED'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sync_agents DROP COLUMN IF EXISTS tally_status")
    # employee_id is intentionally left nullable on downgrade: re-adding NOT NULL
    # would fail as soon as a TALLY-sourced payment without an employee exists.
    op.drop_index("ix_payment_invoice_allocations_invoice_id", table_name="payment_invoice_allocations")
    op.drop_index("ix_payment_invoice_allocations_payment_id", table_name="payment_invoice_allocations")
    op.drop_table("payment_invoice_allocations")
