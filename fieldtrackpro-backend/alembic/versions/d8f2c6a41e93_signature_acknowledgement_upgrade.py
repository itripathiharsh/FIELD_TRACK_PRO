"""signature acknowledgement upgrade: capture_method, integrity metadata, replace support

Revision ID: d8f2c6a41e93
Revises: c5e91a3f7b06
Create Date: 2026-08-16 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8f2c6a41e93"
down_revision: Union[str, Sequence[str], None] = "c5e91a3f7b06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    capture_method_enum = sa.Enum("SIGNATURE", "PHOTO_UPLOAD", name="signature_capture_method_enum")
    capture_method_enum.create(op.get_bind(), checkfirst=True)

    # Existing rows are all canvas-drawn signatures (photo-upload did not
    # exist before this migration) - server_default backfills them correctly,
    # not a guess.
    op.add_column(
        "visit_signatures",
        sa.Column(
            "capture_method", capture_method_enum,
            nullable=False, server_default="SIGNATURE",
        ),
    )
    # content_type/file_size_bytes/checksum_sha256 cannot be honestly
    # backfilled for existing rows without re-reading their stored bytes, so
    # they are added NULLable rather than guessed; the service layer always
    # populates them for every row created from here on.
    op.add_column("visit_signatures", sa.Column("content_type", sa.String(length=100), nullable=True))
    op.add_column("visit_signatures", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("visit_signatures", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_visit_signatures_checksum_sha256"), "visit_signatures", ["checksum_sha256"]
    )
    op.add_column(
        "visit_signatures",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_visit_signatures_created_by_users", "visit_signatures", "users",
        ["created_by"], ["id"], ondelete="SET NULL",
    )
    op.add_column(
        "visit_signatures",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Replace the old table-wide UniqueConstraint(visit_id, signature_type)
    # with a partial unique index that only applies to CURRENT
    # (superseded_at IS NULL) rows - existing rows are all superseded_at IS
    # NULL, so this is a like-for-like replacement for every row that exists
    # today, while allowing a replaced signature's history to stick around.
    op.drop_constraint("uq_visit_signature", "visit_signatures", type_="unique")
    op.create_index(
        "uq_visit_signature_current",
        "visit_signatures",
        ["visit_id", "signature_type"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_visit_signature_current", table_name="visit_signatures")
    op.create_unique_constraint(
        "uq_visit_signature", "visit_signatures", ["visit_id", "signature_type"]
    )

    op.drop_column("visit_signatures", "superseded_at")
    op.drop_constraint("fk_visit_signatures_created_by_users", "visit_signatures", type_="foreignkey")
    op.drop_column("visit_signatures", "created_by")
    op.drop_index(op.f("ix_visit_signatures_checksum_sha256"), table_name="visit_signatures")
    op.drop_column("visit_signatures", "checksum_sha256")
    op.drop_column("visit_signatures", "file_size_bytes")
    op.drop_column("visit_signatures", "content_type")
    op.drop_column("visit_signatures", "capture_method")

    sa.Enum(name="signature_capture_method_enum").drop(op.get_bind(), checkfirst=True)
