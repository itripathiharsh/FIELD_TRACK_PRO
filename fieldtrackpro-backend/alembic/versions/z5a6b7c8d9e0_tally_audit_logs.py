"""Add tally_audit_logs table for Tally sync read/write audit logging.

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-09-21 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "z5a6b7c8d9e0"
down_revision: Union[str, None] = "y4z5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tally_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=150), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("company_guid", sa.String(length=255), nullable=True),
        sa.Column("tally_guid", sa.String(length=255), nullable=True),
        sa.Column("tally_voucher_number", sa.String(length=100), nullable=True),
        sa.Column("writeback_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_tally_audit_logs_timestamp", "tally_audit_logs", ["timestamp"])
    op.create_index("ix_tally_audit_logs_direction", "tally_audit_logs", ["direction"])
    op.create_index("ix_tally_audit_logs_operation", "tally_audit_logs", ["operation"])
    op.create_index("ix_tally_audit_logs_entity_type", "tally_audit_logs", ["entity_type"])
    op.create_index("ix_tally_audit_logs_status", "tally_audit_logs", ["status"])
    op.create_index("ix_tally_audit_logs_agent_id", "tally_audit_logs", ["agent_id"])
    op.create_index("ix_tally_audit_logs_tally_guid", "tally_audit_logs", ["tally_guid"])
    op.create_index("ix_tally_audit_logs_writeback_job_id", "tally_audit_logs", ["writeback_job_id"])
    op.create_index("ix_tally_audit_logs_direction_status", "tally_audit_logs", ["direction", "status"])


def downgrade() -> None:
    op.drop_index("ix_tally_audit_logs_direction_status", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_writeback_job_id", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_tally_guid", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_agent_id", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_status", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_entity_type", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_operation", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_direction", table_name="tally_audit_logs")
    op.drop_index("ix_tally_audit_logs_timestamp", table_name="tally_audit_logs")
    op.drop_table("tally_audit_logs")
