"""
Add visit_type, adhoc_reason, and adhoc_notes to visits table for Ad-Hoc / Off-Beat visits.

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-08-30 19:35:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

visit_type_enum = ENUM("PLANNED", "AD_HOC", name="visit_type_enum", create_type=False)


def upgrade() -> None:
    # Create enum type if it does not already exist
    visit_type_enum_create = ENUM("PLANNED", "AD_HOC", name="visit_type_enum")
    visit_type_enum_create.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "visits",
        sa.Column(
            "visit_type",
            visit_type_enum,
            nullable=False,
            server_default="PLANNED",
        ),
    )
    op.add_column(
        "visits",
        sa.Column("adhoc_reason", sa.String(100), nullable=True),
    )
    op.add_column(
        "visits",
        sa.Column("adhoc_notes", sa.String(500), nullable=True),
    )
    op.create_index("ix_visits_visit_type", "visits", ["visit_type"])


def downgrade() -> None:
    op.drop_index("ix_visits_visit_type", table_name="visits")
    op.drop_column("visits", "adhoc_notes")
    op.drop_column("visits", "adhoc_reason")
    op.drop_column("visits", "visit_type")
    op.execute("DROP TYPE IF EXISTS visit_type_enum")
