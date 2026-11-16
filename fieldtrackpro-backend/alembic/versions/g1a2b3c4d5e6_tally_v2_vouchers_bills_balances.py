"""Tally v2: every debtor voucher, bills, balances, retirement.

Revision ID: g1a2b3c4d5e6
Revises: f3a4b5c6d7e8
Create Date: 2026-11-16 18:00:00.000000

Schema only - no financial row is changed, deleted or re-derived here (the
cut-over data steps live in scripts/tally_v2_cutover.py, dry-run by default).

* enum values: invoice_source_enum / payment_source_enum += TALLY_RETIRED,
  payment_method_enum += UNSPECIFIED;
* customers: Tally ledger master facts (debtor flag, parent group, aliases,
  bill-wise flag, credit period, opening balance + its as-of date);
* invoices / payments: voucher GUID, voucher type, AlterID, narration,
  retirement time + reason; payments also the raw transaction type and bank
  allocation details;
* new tables: tally_ledger_adjustments, tally_open_bills, tally_snapshot_runs,
  tally_manifest_guids.

Downgrade drops the new columns and tables. PostgreSQL cannot drop enum values,
so downgrade refuses (in its transaction, changing nothing) while any row uses a
new value: the rollback for a database that has run the v2 sync is the
pre-deployment backup, not a downgrade.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VOUCHER_COLS = (
    ("tally_voucher_guid", sa.String(100)),
    ("tally_voucher_type", sa.String(100)),
    ("tally_alter_id", sa.BigInteger()),
    ("narration", sa.Text()),
    ("tally_retired_at", sa.DateTime(timezone=True)),
    ("tally_retired_reason", sa.String(50)),
)
_CUSTOMER_COLS = (
    ("tally_is_debtor", sa.Boolean()),
    ("tally_parent_group", sa.String(150)),
    ("tally_aliases", postgresql.JSONB()),
    ("tally_is_bill_wise", sa.Boolean()),
    ("tally_credit_period", sa.String(50)),
    ("tally_opening_balance", sa.Numeric(14, 2)),
    ("tally_opening_balance_as_of", sa.Date()),
)
_PAYMENT_EXTRA = (
    ("tally_transaction_type", sa.String(50)),
    ("tally_bank_details", postgresql.JSONB()),
)


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    op.execute("ALTER TYPE invoice_source_enum ADD VALUE IF NOT EXISTS 'TALLY_RETIRED'")
    op.execute("ALTER TYPE payment_source_enum ADD VALUE IF NOT EXISTS 'TALLY_RETIRED'")
    op.execute("ALTER TYPE payment_method_enum ADD VALUE IF NOT EXISTS 'UNSPECIFIED'")

    have = _cols("customers")
    for name, type_ in _CUSTOMER_COLS:
        if name not in have:
            op.add_column("customers", sa.Column(name, type_, nullable=True))
    op.create_index("ix_customers_tally_is_debtor", "customers", ["tally_is_debtor"], if_not_exists=True)

    for table, cols in (("invoices", _VOUCHER_COLS), ("payments", _VOUCHER_COLS + _PAYMENT_EXTRA)):
        have = _cols(table)
        for name, type_ in cols:
            if name not in have:
                op.add_column(table, sa.Column(name, type_, nullable=True))
        op.create_index(f"ix_{table}_tally_voucher_guid", table, ["tally_voucher_guid"], if_not_exists=True)

    op.create_table(
        "tally_ledger_adjustments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False, unique=True),
        sa.Column("tally_voucher_guid", sa.String(100), nullable=False),
        sa.Column("voucher_type", sa.String(100), nullable=False),
        sa.Column("voucher_parent", sa.String(100)),
        sa.Column("voucher_number", sa.String(100)),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("financial_year", sa.String(7)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("narration", sa.Text()),
        sa.Column("bill_allocations", postgresql.JSONB()),
        sa.Column("tally_alter_id", sa.BigInteger()),
        sa.Column("state", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("retired_reason", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )
    for col in ("customer_id", "tally_voucher_guid", "voucher_date", "financial_year", "state"):
        op.create_index(f"ix_tally_ledger_adjustments_{col}", "tally_ledger_adjustments", [col], if_not_exists=True)

    op.create_table(
        "tally_snapshot_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("sync_agents.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("as_of_date", sa.Date()),
        sa.Column("window_from", sa.Date()),
        sa.Column("window_to", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="RECEIVING"),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        if_not_exists=True,
    )
    op.create_index("ix_tally_snapshot_runs_kind", "tally_snapshot_runs", ["kind"], if_not_exists=True)

    op.create_table(
        "tally_open_bills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("bill_name", sa.String(150), nullable=False),
        sa.Column("bill_date", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("pending_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("overdue_days", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )
    for col in ("customer_id", "as_of_date", "snapshot_id"):
        op.create_index(f"ix_tally_open_bills_{col}", "tally_open_bills", [col], if_not_exists=True)
    op.create_index("ix_tally_open_bills_customer_asof", "tally_open_bills", ["customer_id", "as_of_date"],
                    if_not_exists=True)

    op.create_table(
        "tally_manifest_guids",
        sa.Column("snapshot_id", sa.String(64),
                  sa.ForeignKey("tally_snapshot_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("guid", sa.String(100), primary_key=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM invoices WHERE source::text = 'TALLY_RETIRED')"
        " + (SELECT count(*) FROM payments WHERE source::text = 'TALLY_RETIRED')"
        " + (SELECT count(*) FROM payments WHERE payment_method::text = 'UNSPECIFIED')"
    )).scalar()
    if in_use:
        raise RuntimeError(
            f"{in_use} rows use TALLY_RETIRED / UNSPECIFIED; restore the pre-deployment backup instead of downgrading."
        )
    op.drop_table("tally_manifest_guids", if_exists=True)
    op.drop_table("tally_open_bills", if_exists=True)
    op.drop_table("tally_snapshot_runs", if_exists=True)
    op.drop_table("tally_ledger_adjustments", if_exists=True)
    for table, cols in (("payments", _VOUCHER_COLS + _PAYMENT_EXTRA), ("invoices", _VOUCHER_COLS)):
        op.drop_index(f"ix_{table}_tally_voucher_guid", table_name=table, if_exists=True)
        have = _cols(table)
        for name, _ in cols:
            if name in have:
                op.drop_column(table, name)
    op.drop_index("ix_customers_tally_is_debtor", table_name="customers", if_exists=True)
    have = _cols("customers")
    for name, _ in _CUSTOMER_COLS:
        if name in have:
            op.drop_column("customers", name)
