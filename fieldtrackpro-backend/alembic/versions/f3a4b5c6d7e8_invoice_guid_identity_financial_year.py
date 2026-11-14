"""Invoice identity is the Tally voucher GUID; invoice numbers may repeat across
financial years.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-15 14:00:00.000000

* adds invoices.financial_year ("2026-27", April-March) as a business field and
  backfills it from invoice_date;
* drops the (customer_id, invoice_number) uniqueness, which made a number reused in
  a later financial year impossible to store, and keeps a plain lookup index;
* makes source_reference (the Tally voucher GUID) unique where present, so one
  voucher can never become two invoices and a different voucher can never take
  over an existing invoice.

Pre-checked on 2026-11-15: production and development hold no duplicate invoice
source_reference and production has none NULL. Downgrade restores the old
uniqueness and fails (safely, in a transaction) if a reused number now exists.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_UQ = "uq_invoice_customer_number"
_IX_NUMBER = "ix_invoices_customer_number"
_UQ_GUID = "uq_invoices_source_reference"
_IX_FY = "ix_invoices_financial_year"

_BACKFILL = """
UPDATE invoices SET financial_year =
  CASE WHEN EXTRACT(MONTH FROM invoice_date) >= 4
       THEN EXTRACT(YEAR FROM invoice_date)::int || '-' || LPAD(((EXTRACT(YEAR FROM invoice_date)::int + 1) % 100)::text, 2, '0')
       ELSE (EXTRACT(YEAR FROM invoice_date)::int - 1) || '-' || LPAD((EXTRACT(YEAR FROM invoice_date)::int % 100)::text, 2, '0')
  END
WHERE financial_year IS NULL AND invoice_date IS NOT NULL
"""


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "financial_year" not in {c["name"] for c in insp.get_columns("invoices")}:
        op.add_column("invoices", sa.Column("financial_year", sa.String(7), nullable=True))
        op.create_index(_IX_FY, "invoices", ["financial_year"])
    op.execute(_BACKFILL)

    if _OLD_UQ in {u["name"] for u in insp.get_unique_constraints("invoices")}:
        op.drop_constraint(_OLD_UQ, "invoices", type_="unique")
    indexes = {i["name"] for i in insp.get_indexes("invoices")}
    if _IX_NUMBER not in indexes:
        op.create_index(_IX_NUMBER, "invoices", ["customer_id", "invoice_number"])
    if _UQ_GUID not in indexes:
        op.create_index(_UQ_GUID, "invoices", ["source_reference"], unique=True,
                        postgresql_where=sa.text("source_reference IS NOT NULL"))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    indexes = {i["name"] for i in insp.get_indexes("invoices")}
    if _UQ_GUID in indexes:
        op.drop_index(_UQ_GUID, table_name="invoices")
    if _IX_NUMBER in indexes:
        op.drop_index(_IX_NUMBER, table_name="invoices")
    op.create_unique_constraint(_OLD_UQ, "invoices", ["customer_id", "invoice_number"])
    if "financial_year" in {c["name"] for c in insp.get_columns("invoices")}:
        op.drop_index(_IX_FY, table_name="invoices")
        op.drop_column("invoices", "financial_year")
