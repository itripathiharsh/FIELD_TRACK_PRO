"""Payment bank-verification record (bank_reference, bank_verified_on, verified_note).

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-10-10 14:00:00.000000

Tally-is-final-truth flow: an admin verifies a collection against the bank and
may record the bank reference / date / note at that moment. All columns are
nullable (verify without a body keeps working). Guards are idempotent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp, "payments")
    if "bank_reference" not in cols:
        op.add_column("payments", sa.Column("bank_reference", sa.String(100), nullable=True))
    if "bank_verified_on" not in cols:
        op.add_column("payments", sa.Column("bank_verified_on", sa.Date(), nullable=True))
    if "verified_note" not in cols:
        op.add_column("payments", sa.Column("verified_note", sa.Text(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp, "payments")
    for name in ("verified_note", "bank_verified_on", "bank_reference"):
        if name in cols:
            op.drop_column("payments", name)
