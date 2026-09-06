"""customer_requirement_admin_workflow

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-09-06 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "y4z5a6b7c8d9"
down_revision: Union[str, None] = "x3y4z5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add visit and photo linkages
    op.add_column(
        "customer_requirements",
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_customer_requirements_visit_id",
        "customer_requirements",
        ["visit_id"],
        unique=False,
    )

    op.add_column(
        "customer_requirements",
        sa.Column("photo_storage_key", sa.String(length=500), nullable=True),
    )

    op.add_column(
        "customer_requirements",
        sa.Column("photo_media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visit_media.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index(
        "ix_customer_requirements_photo_media_id",
        "customer_requirements",
        ["photo_media_id"],
        unique=False,
    )

    # 2. Add Admin Decision columns
    op.add_column(
        "customer_requirements",
        sa.Column("approved_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "customer_requirements",
        sa.Column("approved_value", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "customer_requirements",
        sa.Column("admin_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "customer_requirements",
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "customer_requirements",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. Update server default for status to PENDING
    op.alter_column(
        "customer_requirements",
        "status",
        server_default="PENDING",
        existing_type=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "customer_requirements",
        "status",
        server_default="OPEN",
        existing_type=sa.String(length=50),
        existing_nullable=False,
    )
    op.drop_column("customer_requirements", "decided_at")
    op.drop_column("customer_requirements", "decided_by")
    op.drop_column("customer_requirements", "admin_notes")
    op.drop_column("customer_requirements", "approved_value")
    op.drop_column("customer_requirements", "approved_quantity")
    op.drop_index("ix_customer_requirements_photo_media_id", table_name="customer_requirements")
    op.drop_column("customer_requirements", "photo_media_id")
    op.drop_column("customer_requirements", "photo_storage_key")
    op.drop_index("ix_customer_requirements_visit_id", table_name="customer_requirements")
    op.drop_column("customer_requirements", "visit_id")
