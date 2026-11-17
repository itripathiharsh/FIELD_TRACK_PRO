"""Release 2.1.0: physical outlet <-> Tally ledgers, link audit, agent health.

Revision ID: h1b2c3d4e5f6
Revises: g1a2b3c4d5e6
Create Date: 2026-11-17 12:00:00.000000

* tally_debtor_ledgers: one row per Tally ledger, linked to its physical outlet (customers).
* outlet_link_events: audit + undo data of every mapping change.
* customers: merged_into_customer_id / merged_at / merged_by, outlet_name_source.
* invoices / payments / tally_ledger_adjustments / tally_open_bills: tally_debtor_ledger_id.
* sync_agents: health, health_reported_at, last_checkpoints.

Backfill is 1:1 and changes NO outlet: one primary ledger per customer that holds a
Tally GUID, and every Tally-sourced financial row points at its customer's ledger.

Downgrade refuses while any ledger is linked away from the customer it came from or any
customer is merged (links cannot be represented in the old schema): revert the mapping
batches first.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h1b2c3d4e5f6"
down_revision: Union[str, None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_LEDGERS_SQL = """
        INSERT INTO tally_debtor_ledgers (
            id, customer_id, tally_guid, name, parent_group, aliases, tally_outlet_code, brand_tally,
            is_debtor, is_bill_wise, credit_period, opening_balance, opening_balance_as_of,
            closing_balance, closing_balance_at, gst_number, mobile, address, is_primary, mapping_status,
            created_at, updated_at)
        SELECT gen_random_uuid(), c.id, c.tally_guid, left(c.name, 150), c.tally_parent_group, c.tally_aliases,
               c.outlet_code,
               (SELECT min(cb.brand) FROM customer_brands cb WHERE cb.customer_id = c.id AND cb.is_active
                 HAVING count(*) = 1),  -- only an unambiguous single brand; never guessed
               c.tally_is_debtor, c.tally_is_bill_wise, c.tally_credit_period, c.tally_opening_balance,
               c.tally_opening_balance_as_of, c.tally_closing_balance, c.tally_closing_balance_at,
               c.gst_number, NULLIF(c.mobile_number, ''), NULLIF(c.address, ''), true, 'AUTO_1TO1', now(), now()
          FROM customers c
         WHERE c.tally_guid IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM tally_debtor_ledgers l WHERE l.tally_guid = c.tally_guid)
"""

DOWNGRADE_GUARD_SQL = """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM customers WHERE merged_into_customer_id IS NOT NULL) THEN
            RAISE EXCEPTION 'downgrade refused: % customer(s) are merged into a physical outlet - revert the outlet mapping first',
              (SELECT count(*) FROM customers WHERE merged_into_customer_id IS NOT NULL);
          END IF;
          IF EXISTS (SELECT 1 FROM tally_debtor_ledgers l JOIN customers c ON c.tally_guid = l.tally_guid
                      WHERE c.id <> l.customer_id) THEN
            RAISE EXCEPTION 'downgrade refused: Tally ledgers are linked away from their original outlet - revert the outlet mapping first';
          END IF;
        END $$;
"""

_LEDGER_FK_TABLES = ("invoices", "payments", "tally_ledger_adjustments", "tally_open_bills")


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have_tables = _tables()
    if "tally_debtor_ledgers" not in have_tables:
        op.create_table(
            "tally_debtor_ledgers",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("tally_guid", sa.String(255), nullable=False, unique=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("parent_group", sa.String(150)),
            sa.Column("aliases", postgresql.JSONB()),
            sa.Column("tally_outlet_code", sa.String(50)),
            sa.Column("brand_tally", sa.String(100)),
            sa.Column("brand_override", sa.String(100)),
            sa.Column("brand_override_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("brand_override_at", sa.DateTime(timezone=True)),
            sa.Column("is_debtor", sa.Boolean()),
            sa.Column("is_bill_wise", sa.Boolean()),
            sa.Column("credit_period", sa.String(50)),
            sa.Column("opening_balance", sa.Numeric(14, 2)),
            sa.Column("opening_balance_as_of", sa.Date()),
            sa.Column("closing_balance", sa.Numeric(14, 2)),
            sa.Column("closing_balance_at", sa.DateTime(timezone=True)),
            sa.Column("gst_number", sa.String(20)),
            sa.Column("mobile", sa.String(50)),
            sa.Column("address", sa.Text()),
            sa.Column("pincode", sa.String(20)),
            sa.Column("state", sa.String(100)),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("mapping_status", sa.String(20), nullable=False, server_default="AUTO_1TO1"),
            sa.Column("linked_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("linked_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    op.create_index("ix_tally_debtor_ledgers_customer_id", "tally_debtor_ledgers", ["customer_id"], if_not_exists=True)
    op.create_index("ix_tally_debtor_ledgers_tally_outlet_code", "tally_debtor_ledgers", ["tally_outlet_code"],
                    if_not_exists=True)
    op.create_index("ix_tally_debtor_ledgers_is_debtor", "tally_debtor_ledgers", ["is_debtor"], if_not_exists=True)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tally_debtor_ledgers_one_primary "
               "ON tally_debtor_ledgers (customer_id) WHERE is_primary")

    if "outlet_link_events" not in have_tables:
        op.create_table(
            "outlet_link_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("action", sa.String(20), nullable=False),
            sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("tally_debtor_ledgers.id", ondelete="SET NULL")),
            sa.Column("from_customer_id", sa.Uuid()),
            sa.Column("to_customer_id", sa.Uuid()),
            sa.Column("moved", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("before", postgresql.JSONB()),
            sa.Column("batch_id", sa.Uuid()),
            sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    op.create_index("ix_outlet_link_events_ledger_id", "outlet_link_events", ["ledger_id"], if_not_exists=True)
    op.create_index("ix_outlet_link_events_batch_id", "outlet_link_events", ["batch_id"], if_not_exists=True)

    have = _cols("customers")
    if "merged_into_customer_id" not in have:
        op.add_column("customers", sa.Column("merged_into_customer_id", sa.Uuid(),
                                             sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True))
    if "merged_at" not in have:
        op.add_column("customers", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    if "merged_by" not in have:
        op.add_column("customers", sa.Column("merged_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"),
                                             nullable=True))
    if "outlet_name_source" not in have:
        op.add_column("customers", sa.Column("outlet_name_source", sa.String(20), nullable=False,
                                             server_default="TALLY_PRIMARY"))
    op.create_index("ix_customers_merged_into_customer_id", "customers", ["merged_into_customer_id"], if_not_exists=True)

    for table in _LEDGER_FK_TABLES:
        if "tally_debtor_ledger_id" not in _cols(table):
            op.add_column(table, sa.Column("tally_debtor_ledger_id", sa.Uuid(),
                                           sa.ForeignKey("tally_debtor_ledgers.id", ondelete="RESTRICT"), nullable=True))
        op.create_index(f"ix_{table}_tally_debtor_ledger_id", table, ["tally_debtor_ledger_id"], if_not_exists=True)

    have = _cols("sync_agents")
    for name, type_ in (("health", postgresql.JSONB()), ("health_reported_at", sa.DateTime(timezone=True)),
                        ("last_checkpoints", postgresql.JSONB())):
        if name not in have:
            op.add_column("sync_agents", sa.Column(name, type_, nullable=True))

    # ---- 1:1 backfill (idempotent) ---------------------------------------------------------------
    op.execute(BACKFILL_LEDGERS_SQL)
    op.execute("""
        UPDATE invoices i SET tally_debtor_ledger_id = l.id
          FROM tally_debtor_ledgers l
         WHERE l.customer_id = i.customer_id AND l.is_primary AND i.tally_debtor_ledger_id IS NULL
           AND i.source IN ('TALLY', 'TALLY_RETIRED')
    """)
    op.execute("""
        UPDATE payments p SET tally_debtor_ledger_id = l.id
          FROM tally_debtor_ledgers l
         WHERE l.customer_id = p.customer_id AND l.is_primary AND p.tally_debtor_ledger_id IS NULL
           AND p.source IN ('TALLY', 'TALLY_RETIRED')
    """)
    for table in ("tally_ledger_adjustments", "tally_open_bills"):
        op.execute(f"""
            UPDATE {table} t SET tally_debtor_ledger_id = l.id
              FROM tally_debtor_ledgers l
             WHERE l.customer_id = t.customer_id AND l.is_primary AND t.tally_debtor_ledger_id IS NULL
        """)


def downgrade() -> None:
    op.execute(DOWNGRADE_GUARD_SQL)
    op.drop_column("sync_agents", "last_checkpoints")
    op.drop_column("sync_agents", "health_reported_at")
    op.drop_column("sync_agents", "health")
    for table in _LEDGER_FK_TABLES:
        op.drop_index(f"ix_{table}_tally_debtor_ledger_id", table_name=table, if_exists=True)
        op.drop_column(table, "tally_debtor_ledger_id")
    op.drop_index("ix_customers_merged_into_customer_id", table_name="customers", if_exists=True)
    for col in ("outlet_name_source", "merged_by", "merged_at", "merged_into_customer_id"):
        op.drop_column("customers", col)
    op.drop_table("outlet_link_events")
    op.drop_table("tally_debtor_ledgers")
