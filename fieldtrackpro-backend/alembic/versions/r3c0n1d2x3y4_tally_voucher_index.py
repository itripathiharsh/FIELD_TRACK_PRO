"""Tally voucher index for reconciliation (release 3.0).

Revision ID: r3c0n1d2x3y4
Revises: j3d4e5f6a7b8
Create Date: 2026-11-20 03:00:00.000000

* New table tally_voucher_index (guid PK, alter_id, voucher_date, state, company_guid, updated_at): every Tally
  voucher FieldTrack has processed, including those that leave no invoice / payment / adjustment row.
* Backfill from the rows FieldTrack already holds (invoices, payments, ledger adjustments with a Tally voucher GUID):
  one index row per voucher GUID with its highest stored AlterID and its earliest row date; ACTIVE when any of its
  rows is active, DELETED when every row is retired. Vouchers that left no row (purchases, contras, cancelled ...)
  are not known yet: the first reconciliation reports them missing once, the agent re-sends them once, and the
  index is complete from then on.

Additive. No existing row is changed. Downgrade drops the table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r3c0n1d2x3y4"
down_revision: Union[str, None] = "j3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tally_voucher_index",
        sa.Column("guid", sa.String(100), primary_key=True),
        sa.Column("alter_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.Column("company_guid", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tally_voucher_index_state_date", "tally_voucher_index", ["state", "voucher_date"])
    op.execute(
        """
        INSERT INTO tally_voucher_index (guid, alter_id, voucher_date, state)
        SELECT guid, MAX(alter_id), MIN(d), CASE WHEN BOOL_OR(active) THEN 'ACTIVE' ELSE 'DELETED' END
        FROM (
            SELECT tally_voucher_guid AS guid, COALESCE(tally_alter_id, 0) AS alter_id, invoice_date AS d,
                   (source <> 'TALLY_RETIRED') AS active
            FROM invoices WHERE tally_voucher_guid IS NOT NULL
            UNION ALL
            SELECT tally_voucher_guid, COALESCE(tally_alter_id, 0), payment_date, (source <> 'TALLY_RETIRED')
            FROM payments WHERE tally_voucher_guid IS NOT NULL
            UNION ALL
            SELECT tally_voucher_guid, COALESCE(tally_alter_id, 0), voucher_date, (state <> 'RETIRED')
            FROM tally_ledger_adjustments WHERE tally_voucher_guid IS NOT NULL
        ) rows
        GROUP BY guid
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tally_voucher_index_state_date", table_name="tally_voucher_index")
    op.drop_table("tally_voucher_index")
