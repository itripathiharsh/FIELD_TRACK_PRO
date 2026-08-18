"""add visit check_in_received_at and check_out_received_at timestamps

Revision ID: f9b1c2d3e4a5
Revises: e1a4c9f27b58
Create Date: 2026-08-17 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f9b1c2d3e4a5"
down_revision: Union[str, Sequence[str], None] = "e1a4c9f27b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "visits",
        sa.Column("check_in_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "visits",
        sa.Column("check_out_received_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("visits", "check_out_received_at")
    op.drop_column("visits", "check_in_received_at")
