"""zone/area/outlet hierarchy: areas table, customers.area_id, employee_area_assignments

Revision ID: e1a4c9f27b58
Revises: d8f2c6a41e93
Create Date: 2026-08-17 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1a4c9f27b58"
down_revision: Union[str, Sequence[str], None] = "d8f2c6a41e93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Zone (Territory) -> Area -> Outlet (Customer). Territory itself is
    # unchanged - it already represents the Zone level; Area is the new
    # layer the client's real data showed was missing (Meeting 3 audit).
    op.create_table(
        "areas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("territory_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_areas_territory_id", "areas", ["territory_id"])

    # Nullable: no existing outlet can be safely auto-assigned an Area - the
    # client's real Zone/Area/Outlet export could not be matched to existing
    # Customer rows without guessing (see the pre-migration audit: outlet
    # identity across the brand-specific DMS codes is ambiguous). Every
    # existing outlet keeps working exactly as it did via its unchanged
    # territory_id; area_id is populated going forward by an admin.
    op.add_column("customers", sa.Column("area_id", sa.Uuid(), nullable=True))
    op.create_index("ix_customers_area_id", "customers", ["area_id"])
    op.create_foreign_key(
        "fk_customers_area_id_areas", "customers", "areas", ["area_id"], ["id"], ondelete="SET NULL"
    )

    # Employee <-> Area coverage, many-to-many, brand-agnostic (confirmed:
    # one employee legitimately covers many Areas across many Zones - the
    # existing Employee.territory_id/EmployeeTerritoryAssignment single-zone
    # model is left completely untouched for backward compatibility; this is
    # purely additive).
    op.create_table(
        "employee_area_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("employee_id", "area_id", name="uq_employee_area_assignment"),
    )
    op.create_index("ix_employee_area_assignments_employee_id", "employee_area_assignments", ["employee_id"])
    op.create_index("ix_employee_area_assignments_area_id", "employee_area_assignments", ["area_id"])


def downgrade() -> None:
    op.drop_index("ix_employee_area_assignments_area_id", table_name="employee_area_assignments")
    op.drop_index("ix_employee_area_assignments_employee_id", table_name="employee_area_assignments")
    op.drop_table("employee_area_assignments")

    op.drop_constraint("fk_customers_area_id_areas", "customers", type_="foreignkey")
    op.drop_index("ix_customers_area_id", table_name="customers")
    op.drop_column("customers", "area_id")

    op.drop_index("ix_areas_territory_id", table_name="areas")
    op.drop_table("areas")
