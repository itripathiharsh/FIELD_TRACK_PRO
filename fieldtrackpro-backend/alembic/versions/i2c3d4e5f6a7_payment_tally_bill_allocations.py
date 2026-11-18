"""Tally receipts keep their bill allocations (signed, as in Tally).

Revision ID: i2c3d4e5f6a7
Revises: h1b2c3d4e5f6
Create Date: 2026-11-19 03:00:00.000000

* payments.tally_bill_allocations (JSONB, nullable): the receipt's Tally bill allocations exactly as the
  agent sent them. Lets a receipt be linked to an invoice that reaches FieldTrack AFTER the receipt (a
  historical year loaded after the live year, or an advance received before its invoice), and lets
  links be rebuilt without re-reading Tally.

Additive and nullable: no backfill (existing receipts fill it the next time the agent sends them).
Downgrade drops the column; links already created stay valid.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i2c3d4e5f6a7"
down_revision: Union[str, None] = "h1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("tally_bill_allocations", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "tally_bill_allocations")
