"""add indexes for security cleanup on refresh_tokens and password_reset_tokens

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
Create Date: 2026-08-22 13:10:00.000000

Adds B-Tree indexes on refresh_tokens(expires_at) and password_reset_tokens(expires_at)
to accelerate automated expiration cleanup sweeps.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "j3k4l5m6n7o8"
down_revision: Union[str, Sequence[str], None] = "i2j3k4l5m6n7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
