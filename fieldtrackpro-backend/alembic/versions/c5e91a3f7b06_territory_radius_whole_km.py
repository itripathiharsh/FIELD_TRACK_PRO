"""territory radius_km must be a whole number of km

Revision ID: c5e91a3f7b06
Revises: b91e6c3a4d72
Create Date: 2026-08-14 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c5e91a3f7b06"
down_revision: Union[str, Sequence[str], None] = "b91e6c3a4d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Non-destructive: rounds any existing fractional value to the nearest
    # whole km rather than truncating/discarding data. Going forward, the
    # Pydantic schema layer (app/schemas/territory.py) rejects any fractional
    # input before it ever reaches this column.
    op.execute(
        "ALTER TABLE territories "
        "ALTER COLUMN radius_km TYPE INTEGER "
        "USING (CASE WHEN radius_km IS NULL THEN NULL ELSE ROUND(radius_km)::INTEGER END)"
    )


def downgrade() -> None:
    op.alter_column(
        "territories",
        "radius_km",
        type_=sa.Float(),
        existing_type=sa.Integer(),
    )
