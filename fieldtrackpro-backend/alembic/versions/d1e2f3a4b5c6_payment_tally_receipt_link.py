"""Link a field collection to the Tally receipt that confirms it.

Revision ID: d1e2f3a4b5c6
Revises: b9c0d1e2f3a4
Create Date: 2026-11-14 18:00:00.000000

With Tally write-back disabled the accountant keys receipts into Tally by hand
and the sync agent imports them as separate TALLY payments. An admin confirms
that a MANUAL field collection is the same money as such a receipt by linking
the two. Additive and nullable; guards are idempotent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_RECEIPT = "fk_payments_tally_receipt_payment_id"
_FK_LINKED_BY = "fk_payments_tally_linked_by"
_IX_RECEIPT = "ix_payments_tally_receipt_payment_id"


def _cols(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp, "payments")
    if "tally_receipt_payment_id" not in cols:
        op.add_column("payments", sa.Column("tally_receipt_payment_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(_FK_RECEIPT, "payments", "payments", ["tally_receipt_payment_id"], ["id"], ondelete="RESTRICT")
        op.create_index(_IX_RECEIPT, "payments", ["tally_receipt_payment_id"])
    if "tally_linked_at" not in cols:
        op.add_column("payments", sa.Column("tally_linked_at", sa.DateTime(timezone=True), nullable=True))
    if "tally_linked_by" not in cols:
        op.add_column("payments", sa.Column("tally_linked_by", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(_FK_LINKED_BY, "payments", "users", ["tally_linked_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp, "payments")
    if "tally_linked_by" in cols:
        op.drop_constraint(_FK_LINKED_BY, "payments", type_="foreignkey")
        op.drop_column("payments", "tally_linked_by")
    if "tally_linked_at" in cols:
        op.drop_column("payments", "tally_linked_at")
    if "tally_receipt_payment_id" in cols:
        op.drop_index(_IX_RECEIPT, table_name="payments")
        op.drop_constraint(_FK_RECEIPT, "payments", type_="foreignkey")
        op.drop_column("payments", "tally_receipt_payment_id")
