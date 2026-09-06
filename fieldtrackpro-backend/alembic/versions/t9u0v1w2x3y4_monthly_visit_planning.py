"""Monthly visit planning foundation: monthly_visit_plans and planned_visits tables.

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
Create Date: 2026-09-02 17:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

# revision identifiers, used by Alembic.
revision = "t9u0v1w2x3y4"
down_revision = "s8t9u0v1w2x3"
branch_labels = None
depends_on = None

monthly_plan_status_enum = ENUM("ACTIVE", "LOCKED", name="monthly_plan_status_enum", create_type=False)
planned_visit_status_enum = ENUM("PLANNED", "CANCELLED", name="planned_visit_status_enum", create_type=False)
visit_type_enum = ENUM("PLANNED", "AD_HOC", name="visit_type_enum", create_type=False)
priority_enum = ENUM("LOW", "MEDIUM", "HIGH", name="priority_enum", create_type=False)


def upgrade() -> None:
    # 1. Create enum types if not existing
    monthly_plan_status_create = ENUM("ACTIVE", "LOCKED", name="monthly_plan_status_enum")
    monthly_plan_status_create.create(op.get_bind(), checkfirst=True)

    planned_visit_status_create = ENUM("PLANNED", "CANCELLED", name="planned_visit_status_enum")
    planned_visit_status_create.create(op.get_bind(), checkfirst=True)

    # 2. Create monthly_visit_plans table
    op.create_table(
        "monthly_visit_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", monthly_plan_status_enum, server_default="ACTIVE", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "year", "month", name="uq_monthly_visit_plan_employee_year_month"),
    )
    op.create_index("ix_monthly_visit_plans_employee_id", "monthly_visit_plans", ["employee_id"])
    op.create_index("ix_monthly_visit_plans_year_month", "monthly_visit_plans", ["year", "month"])

    # 3. Create planned_visits table
    op.create_table(
        "planned_visits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("monthly_plan_id", UUID(as_uuid=True), sa.ForeignKey("monthly_visit_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("visit_type", visit_type_enum, server_default="PLANNED", nullable=False),
        sa.Column("priority", priority_enum, server_default="MEDIUM", nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("status", planned_visit_status_enum, server_default="PLANNED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_planned_visits_monthly_plan_id", "planned_visits", ["monthly_plan_id"])
    op.create_index("ix_planned_visits_employee_date", "planned_visits", ["employee_id", "planned_date"])
    op.create_index("ix_planned_visits_customer_id", "planned_visits", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_planned_visits_customer_id", table_name="planned_visits")
    op.drop_index("ix_planned_visits_employee_date", table_name="planned_visits")
    op.drop_index("ix_planned_visits_monthly_plan_id", table_name="planned_visits")
    op.drop_table("planned_visits")

    op.drop_index("ix_monthly_visit_plans_year_month", table_name="monthly_visit_plans")
    op.drop_index("ix_monthly_visit_plans_employee_id", table_name="monthly_visit_plans")
    op.drop_table("monthly_visit_plans")

    op.execute("DROP TYPE IF EXISTS planned_visit_status_enum")
    op.execute("DROP TYPE IF EXISTS monthly_plan_status_enum")
