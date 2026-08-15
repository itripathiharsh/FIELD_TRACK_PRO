"""add updated_at to customers and employees (P2-6)

Revision ID: b91e6c3a4d72
Revises: a7d43f8e2c19
Create Date: 2026-08-13 21:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b91e6c3a4d72"
down_revision: Union[str, Sequence[str], None] = "a7d43f8e2c19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing rows with the current time at
    # migration-apply time; onupdate keeps it current on every future edit
    # (the same created_at/updated_at convention already used by Visit,
    # Payment, Territory, FormTemplate, Invoice and User).
    op.add_column(
        "customers",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "employees",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("employees", "updated_at")
    op.drop_column("customers", "updated_at")
