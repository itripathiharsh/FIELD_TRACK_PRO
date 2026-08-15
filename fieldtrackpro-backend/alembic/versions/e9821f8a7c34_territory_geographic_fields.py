"""add geographic center, radius_km, and status to territories

Revision ID: e9821f8a7c34
Revises: a4e91f2c7b83
Create Date: 2026-08-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e9821f8a7c34"
down_revision: Union[str, Sequence[str], None] = "a4e91f2c7b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("territories", sa.Column("center_latitude", sa.Float(), nullable=True))
    op.add_column("territories", sa.Column("center_longitude", sa.Float(), nullable=True))
    op.add_column("territories", sa.Column("radius_km", sa.Float(), nullable=True))
    op.add_column(
        "territories",
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
    )
    op.add_column(
        "territories",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("territories", "updated_at")
    op.drop_column("territories", "status")
    op.drop_column("territories", "radius_km")
    op.drop_column("territories", "center_longitude")
    op.drop_column("territories", "center_latitude")
