"""Business scope: Distribution-only (release 3.1).

Revision ID: s1c0p3d1st5r
Revises: r3c0n1d2x3y4
Create Date: 2026-11-22 20:00:00.000000

* tally_debtor_ledgers: business_scope (DISTRIBUTION / EXCLUDED / PENDING, NULL = not evaluated), scope_source
  (GROUP / MANUAL / DEFAULT), scope_reason, scope_decided_by, scope_decided_at.
* New table tally_scope_groups (group_name PK, scope, reason, decided_by, decided_at): the per-Tally-group rule.

Additive: every existing row keeps business_scope = NULL (in scope) and the table starts empty, so nothing changes
until rules are loaded (scripts/tally_business_scope.py). Downgrade drops the columns and the table only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s1c0p3d1st5r"
down_revision: Union[str, None] = "r3c0n1d2x3y4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tally_debtor_ledgers", sa.Column("business_scope", sa.String(12), nullable=True))
    op.add_column("tally_debtor_ledgers", sa.Column("scope_source", sa.String(10), nullable=True))
    op.add_column("tally_debtor_ledgers", sa.Column("scope_reason", sa.String(300), nullable=True))
    op.add_column("tally_debtor_ledgers", sa.Column("scope_decided_by", sa.UUID(), nullable=True))
    op.add_column("tally_debtor_ledgers", sa.Column("scope_decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_tally_debtor_ledgers_scope_decided_by", "tally_debtor_ledgers", "users",
                          ["scope_decided_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tally_debtor_ledgers_business_scope", "tally_debtor_ledgers", ["business_scope"])
    op.create_table(
        "tally_scope_groups",
        sa.Column("group_name", sa.String(150), primary_key=True),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("decided_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tally_scope_groups")
    op.drop_index("ix_tally_debtor_ledgers_business_scope", table_name="tally_debtor_ledgers")
    op.drop_constraint("fk_tally_debtor_ledgers_scope_decided_by", "tally_debtor_ledgers", type_="foreignkey")
    for col in ("scope_decided_at", "scope_decided_by", "scope_reason", "scope_source", "business_scope"):
        op.drop_column("tally_debtor_ledgers", col)
