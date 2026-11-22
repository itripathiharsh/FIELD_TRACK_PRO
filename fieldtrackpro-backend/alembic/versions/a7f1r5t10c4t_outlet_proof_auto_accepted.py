"""Outlet proof: auto_accepted flag (first-location auto-acceptance audit).

Revision ID: a7f1r5t10c4t
Revises: s1c0p3d1st5r
Create Date: 2026-11-23 10:00:00.000000

Adds outlet_proofs.auto_accepted (boolean, default false). Existing rows keep false. Downgrade drops the column only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7f1r5t10c4t"
down_revision: Union[str, None] = "s1c0p3d1st5r"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlet_proofs", sa.Column("auto_accepted", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("outlet_proofs", "auto_accepted")
