"""create field exceptions table

Revision ID: g2h3i4j5k6l7
Revises: f1b2c3d4e5f6
Create Date: 2026-08-22 02:25:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 2. Create field_exceptions table (create_type=False so it uses existing or created enum)
    op.create_table(
        "field_exceptions",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("visit_id", sa.UUID(), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column(
            "exception_type",
            sa.Enum(
                "VEHICLE_BREAKDOWN",
                "GPS_UNAVAILABLE",
                "OUTLET_CLOSED",
                "CUSTOMER_UNAVAILABLE",
                "OTHER",
                name="field_exception_type_enum",
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING_REVIEW",
                "APPROVED",
                "REJECTED",
                name="field_exception_status_enum",
                create_type=False,
            ),
            server_default="PENDING_REVIEW",
            nullable=False,
            index=True,
        ),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("field_exceptions")
