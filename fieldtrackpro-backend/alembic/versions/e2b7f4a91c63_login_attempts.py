"""login_attempts table (P1-3 distributed rate limiting)

Revision ID: e2b7f4a91c63
Revises: d9e3a7c52f81
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2b7f4a91c63"
down_revision: Union[str, Sequence[str], None] = "d9e3a7c52f81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_login_attempts_identifier_attempted_at", "login_attempts", ["identifier", "attempted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_identifier_attempted_at", table_name="login_attempts")
    op.drop_table("login_attempts")
