"""create user_devices table for FCM push notifications

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-08-22 13:00:00.000000

Creates user_devices table to track active FCM device tokens for mobile/web
clients, supporting real-time push notifications, token refresh, and logout unregistration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "i2j3k4l5m6n7"
down_revision: Union[str, Sequence[str], None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fcm_token", sa.String(length=512), nullable=False),
        sa.Column("device_type", sa.String(length=50), nullable=False, server_default="ANDROID"),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])
    op.create_index("ix_user_devices_fcm_token", "user_devices", ["fcm_token"], unique=True)
    op.create_index("ix_user_devices_is_active", "user_devices", ["is_active"])
    op.create_index("ix_user_devices_user_active", "user_devices", ["user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_user_devices_user_active", table_name="user_devices")
    op.drop_index("ix_user_devices_is_active", table_name="user_devices")
    op.drop_index("ix_user_devices_fcm_token", table_name="user_devices")
    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")
