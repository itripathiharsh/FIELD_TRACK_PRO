"""visit required_form_id (Forms-as-a-Visit-workflow fix)

Revision ID: c8f2a4d61e97
Revises: b3d7e5a19c42
Create Date: 2026-08-14 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8f2a4d61e97"
down_revision: Union[str, Sequence[str], None] = "b3d7e5a19c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("required_form_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_visits_required_form_id_form_templates",
        "visits",
        "form_templates",
        ["required_form_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_visits_required_form_id"), "visits", ["required_form_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_visits_required_form_id"), table_name="visits")
    op.drop_constraint("fk_visits_required_form_id_form_templates", "visits", type_="foreignkey")
    op.drop_column("visits", "required_form_id")
