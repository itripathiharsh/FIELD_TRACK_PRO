"""Add sync_agents table for Tally bridge agent integration.

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-09-05 14:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("organization_id", sa.String(length=100), nullable=False, server_default="default"),
        sa.Column("api_key_hash", sa.String(length=255), nullable=False),
        sa.Column("tally_company_guid", sa.String(length=255), nullable=True),
        sa.Column("tally_company_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("agent_version", sa.String(length=50), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_agents_organization_id", "sync_agents", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_agents_organization_id", table_name="sync_agents")
    op.drop_table("sync_agents")
