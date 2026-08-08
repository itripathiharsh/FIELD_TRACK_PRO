"""media integrity: checksum, provenance, duplicate prevention, orphan removal

Repairs FT-036 and FT-047.

FT-036  visit_media recorded no content hash, no original filename and no
        uploader. The same photograph could therefore be attached repeatedly as
        "evidence" with nothing to detect it (adversarial audit VULN-03), and a
        stored object could be altered without the system noticing.

FT-047  The seed data contained a visit_media row whose storage_key
        (`uploads/visits/.../site_photo_01.jpg`) had no file behind it. The key
        format is one the current upload pipeline never produces, so the row was
        inserted directly by a seed script and no bytes were ever written.
        A media record that cannot be downloaded is indistinguishable from a
        real one until the user clicks it. Removed here with the reason recorded
        in docs/REPAIR_DECISIONS.md RD-005.

Revision ID: c3d81b6f4a52
Revises: b7f2a91c5e40
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d81b6f4a52"
down_revision: Union[str, Sequence[str], None] = "b7f2a91c5e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- FT-036: integrity and provenance ----------------------------------
    op.add_column("visit_media", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
    op.add_column("visit_media", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column("visit_media", sa.Column("uploaded_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_visit_media_uploaded_by",
        "visit_media",
        "users",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_visit_media_checksum", "visit_media", ["checksum_sha256"])

    # --- FT-047: remove media rows with no stored object --------------------
    # Scoped precisely: only rows using the legacy `uploads/` prefix, which the
    # current pipeline (`visits/{visit_id}/{media_id}_{name}`) never generates.
    # Real uploads are therefore untouched.
    op.execute("DELETE FROM visit_media WHERE storage_key LIKE 'uploads/%'")

    # --- Duplicate prevention ----------------------------------------------
    # Applied AFTER the cleanup so pre-existing duplicates cannot block it.
    op.create_unique_constraint(
        "uq_visit_media_content", "visit_media", ["visit_id", "checksum_sha256"]
    )
    # A storage key identifies exactly one object, so it must be unique.
    op.create_unique_constraint("uq_visit_media_storage_key", "visit_media", ["storage_key"])


def downgrade() -> None:
    op.drop_constraint("uq_visit_media_storage_key", "visit_media", type_="unique")
    op.drop_constraint("uq_visit_media_content", "visit_media", type_="unique")
    op.drop_index("ix_visit_media_checksum", table_name="visit_media")
    op.drop_constraint("fk_visit_media_uploaded_by", "visit_media", type_="foreignkey")
    op.drop_column("visit_media", "uploaded_by")
    op.drop_column("visit_media", "original_filename")
    op.drop_column("visit_media", "checksum_sha256")
