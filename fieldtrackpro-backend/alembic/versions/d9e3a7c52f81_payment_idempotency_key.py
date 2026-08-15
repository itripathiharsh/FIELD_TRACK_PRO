"""payment idempotency key (P0-2 duplicate-submission fix)

Revision ID: d9e3a7c52f81
Revises: c8f2a4d61e97
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9e3a7c52f81"
down_revision: Union[str, Sequence[str], None] = "c8f2a4d61e97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: every existing row (and every historical EXCEL_IMPORT/TALLY
    # row going forward) has no idempotency key. Postgres treats NULL as
    # distinct under a UniqueConstraint, so backfilling nothing is safe - no
    # existing row can collide with another existing row, or with a future
    # keyed row.
    op.add_column("payments", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_payments_visit_idempotency", "payments", ["visit_id", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_payments_visit_idempotency", "payments", type_="unique")
    op.drop_column("payments", "idempotency_key")
