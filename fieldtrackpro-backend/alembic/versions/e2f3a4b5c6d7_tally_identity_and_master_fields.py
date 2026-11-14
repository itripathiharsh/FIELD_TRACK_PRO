"""Tally identity and master fields: customer ledger GUID, mobile/email, closing
balance (reference), and the invoice's Tally bill name.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-15 10:00:00.000000

The ledger GUID becomes the outlet's stable Tally identity (a renamed ledger no
longer creates a second outlet). The bill name is what Tally receipts reference
("Agst Ref") and may differ from the voucher number. Additive and nullable;
guards are idempotent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ_GUID = "uq_customers_tally_guid"
_IX_BILL = "ix_invoices_tally_bill_name"


def _cols(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp, "customers")
    if "tally_guid" not in cols:
        op.add_column("customers", sa.Column("tally_guid", sa.String(255), nullable=True))
        op.create_unique_constraint(_UQ_GUID, "customers", ["tally_guid"])
    if "email" not in cols:
        op.add_column("customers", sa.Column("email", sa.String(255), nullable=True))
    if "mobile_number" not in cols:
        op.add_column("customers", sa.Column("mobile_number", sa.String(50), nullable=True))
    if "tally_closing_balance" not in cols:
        op.add_column("customers", sa.Column("tally_closing_balance", sa.Numeric(14, 2), nullable=True))
    if "tally_closing_balance_at" not in cols:
        op.add_column("customers", sa.Column("tally_closing_balance_at", sa.DateTime(timezone=True), nullable=True))
    if "tally_bill_name" not in _cols(insp, "invoices"):
        op.add_column("invoices", sa.Column("tally_bill_name", sa.String(150), nullable=True))
        op.create_index(_IX_BILL, "invoices", ["tally_bill_name"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "tally_bill_name" in _cols(insp, "invoices"):
        op.drop_index(_IX_BILL, table_name="invoices")
        op.drop_column("invoices", "tally_bill_name")
    cols = _cols(insp, "customers")
    for name in ("tally_closing_balance_at", "tally_closing_balance", "mobile_number", "email"):
        if name in cols:
            op.drop_column("customers", name)
    if "tally_guid" in cols:
        op.drop_constraint(_UQ_GUID, "customers", type_="unique")
        op.drop_column("customers", "tally_guid")
