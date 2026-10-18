"""Live outlet proof (photo + GPS bundle) table.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-10-13 12:00:00.000000

outlet_proofs holds a live outlet photo and the GPS fix taken at the same
click, for new outlets (linked to a customer_prospects row, or UNATTACHED for
up to 48h before the prospect is submitted) and for existing outlets whose
location is missing/unverified/being changed. Idempotent / inspector-guarded.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "outlet_proofs" in set(insp.get_table_names()):
        return

    uuid_t = postgresql.UUID(as_uuid=True)
    op.create_table(
        "outlet_proofs",
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("customer_id", uuid_t, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("prospect_id", uuid_t, sa.ForeignKey("customer_prospects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="INITIAL"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("storage_provider", sa.String(length=20), nullable=False, server_default="LOCAL"),
        sa.Column("content_type", sa.String(length=100), nullable=False, server_default="image/jpeg"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_mock_location", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("device_info", sa.String(length=200), nullable=True),
        sa.Column("submitted_by", uuid_t, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_employee_id", uuid_t, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by", uuid_t, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("distance_from_verified_m", sa.Float(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status = 'UNATTACHED' OR customer_id IS NOT NULL OR prospect_id IS NOT NULL",
            name="ck_outlet_proofs_has_target",
        ),
        sa.UniqueConstraint("submitted_by", "idempotency_key", name="uq_outlet_proofs_submitter_idem"),
    )
    op.create_index("ix_outlet_proofs_customer_id", "outlet_proofs", ["customer_id"])
    op.create_index("ix_outlet_proofs_prospect_id", "outlet_proofs", ["prospect_id"])
    op.create_index("ix_outlet_proofs_status", "outlet_proofs", ["status"])
    op.create_index("ix_outlet_proofs_checksum_sha256", "outlet_proofs", ["checksum_sha256"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "outlet_proofs" not in set(insp.get_table_names()):
        return
    for ix in (
        "ix_outlet_proofs_checksum_sha256",
        "ix_outlet_proofs_status",
        "ix_outlet_proofs_prospect_id",
        "ix_outlet_proofs_customer_id",
    ):
        op.drop_index(ix, table_name="outlet_proofs")
    op.drop_table("outlet_proofs")
