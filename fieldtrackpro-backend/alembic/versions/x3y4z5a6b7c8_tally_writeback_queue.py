"""Add tally_writeback_queue table for BE -> Tally writeback.

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-09-06 14:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "x3y4z5a6b7c8"
down_revision = "w2x3y4z5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tally_writeback_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False, server_default="PAYMENT"),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False, server_default="CREATE_RECEIPT"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("tally_guid", sa.String(length=255), nullable=True),
        sa.Column("tally_master_id", sa.String(length=100), nullable=True),
        sa.Column("tally_voucher_number", sa.String(length=100), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tally_writeback_queue_idempotency_key", "tally_writeback_queue", ["idempotency_key"], unique=True)
    op.create_index("ix_tally_writeback_queue_entity_id", "tally_writeback_queue", ["entity_id"])
    op.create_index("ix_tally_writeback_queue_status", "tally_writeback_queue", ["status"])
    op.create_index("ix_tally_writeback_queue_next_retry_at", "tally_writeback_queue", ["next_retry_at"])
    op.create_index("ix_tally_writeback_queue_tally_guid", "tally_writeback_queue", ["tally_guid"])
    op.create_index("ix_tally_writeback_queue_status_retry", "tally_writeback_queue", ["status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_tally_writeback_queue_status_retry", table_name="tally_writeback_queue")
    op.drop_index("ix_tally_writeback_queue_tally_guid", table_name="tally_writeback_queue")
    op.drop_index("ix_tally_writeback_queue_next_retry_at", table_name="tally_writeback_queue")
    op.drop_index("ix_tally_writeback_queue_status", table_name="tally_writeback_queue")
    op.drop_index("ix_tally_writeback_queue_entity_id", table_name="tally_writeback_queue")
    op.drop_index("ix_tally_writeback_queue_idempotency_key", table_name="tally_writeback_queue")
    op.drop_table("tally_writeback_queue")
