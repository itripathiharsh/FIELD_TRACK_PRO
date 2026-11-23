"""Accuracy-aware check-in: decision audit columns, visit confidence, admin review queue.

Revision ID: c8e0g3p5d1x2
Revises: a7f1r5t10c4t
Create Date: 2026-11-23 12:00:00.000000

Additive only:
  * geo_verification_logs: accuracy_m, pin_accuracy_m, decision, device_captured_at, is_offline
  * visits: check_in_confidence
  * checkin_reviews (new table) with a partial unique index (one PENDING review per visit and kind)
Downgrade drops exactly these objects. No existing row is modified.
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8e0g3p5d1x2"
down_revision: Union[str, None] = "a7f1r5t10c4t"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("geo_verification_logs", sa.Column("accuracy_m", sa.Numeric(8, 2), nullable=True))
    op.add_column("geo_verification_logs", sa.Column("pin_accuracy_m", sa.Numeric(8, 2), nullable=True))
    op.add_column("geo_verification_logs", sa.Column("decision", sa.String(16), nullable=True))
    op.add_column("geo_verification_logs", sa.Column("device_captured_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("geo_verification_logs", sa.Column("is_offline", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("visits", sa.Column("check_in_confidence", sa.String(16), nullable=True))

    op.create_table(
        "checkin_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("distance_m", sa.Numeric(10, 2), nullable=True),
        sa.Column("accuracy_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("pin_accuracy_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("device_location", geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("device_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checkin_reviews_visit_id", "checkin_reviews", ["visit_id"])
    op.create_index("ix_checkin_reviews_customer_id", "checkin_reviews", ["customer_id"])
    op.create_index("ix_checkin_reviews_status_created", "checkin_reviews", ["status", "created_at"])
    op.create_index(
        "uq_checkin_review_pending", "checkin_reviews", ["visit_id", "kind"], unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_checkin_review_pending", table_name="checkin_reviews")
    op.drop_index("ix_checkin_reviews_status_created", table_name="checkin_reviews")
    op.drop_index("ix_checkin_reviews_customer_id", table_name="checkin_reviews")
    op.drop_index("ix_checkin_reviews_visit_id", table_name="checkin_reviews")
    op.drop_table("checkin_reviews")
    op.drop_column("visits", "check_in_confidence")
    for col in ("is_offline", "device_captured_at", "decision", "pin_accuracy_m", "accuracy_m"):
        op.drop_column("geo_verification_logs", col)
