"""add notes column to visits table

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9
Create Date: 2026-08-27 01:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l5m6n7o8p9q0"
down_revision: Union[str, Sequence[str], None] = "k4l5m6n7o8p9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("notes", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "notes")
