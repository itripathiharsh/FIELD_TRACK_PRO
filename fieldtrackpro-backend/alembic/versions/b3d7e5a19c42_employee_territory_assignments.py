"""employee territory assignment history (P2-D)

Revision ID: b3d7e5a19c42
Revises: f7c93b1e4a58
Create Date: 2026-08-13 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b3d7e5a19c42"
down_revision: Union[str, Sequence[str], None] = "f7c93b1e4a58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # create_table auto-creates the enum type, unlike add_column.
    op.create_table(
        "employee_territory_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assignment_type",
            sa.Enum("PERMANENT", "TEMPORARY", name="assignment_type_enum"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_employee_territory_assignments_employee_start",
        "employee_territory_assignments",
        ["employee_id", "start_date"],
    )
    op.create_index(
        op.f("ix_employee_territory_assignments_employee_id"),
        "employee_territory_assignments",
        ["employee_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_employee_territory_assignments_employee_id"), table_name="employee_territory_assignments")
    op.drop_index("ix_employee_territory_assignments_employee_start", table_name="employee_territory_assignments")
    op.drop_table("employee_territory_assignments")
    sa.Enum(name="assignment_type_enum").drop(op.get_bind())
