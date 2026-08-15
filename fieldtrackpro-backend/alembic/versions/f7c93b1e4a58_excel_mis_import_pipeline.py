"""excel/mis import pipeline: import_batches, payment.source, payment.visit_id nullable, invoice.imported_outstanding_amount

Revision ID: f7c93b1e4a58
Revises: d4f8a92c1e67
Create Date: 2026-08-13 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f7c93b1e4a58"
down_revision: Union[str, Sequence[str], None] = "d4f8a92c1e67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- payments: historical-import support -------------------------------
    op.alter_column("payments", "visit_id", existing_type=sa.Uuid(), nullable=True)

    payment_source_enum = sa.Enum("MANUAL", "EXCEL_IMPORT", "TALLY", name="payment_source_enum")
    # Unlike create_table, add_column does NOT auto-create the enum type -
    # it must be created explicitly first.
    payment_source_enum.create(op.get_bind())
    op.add_column(
        "payments",
        sa.Column("source", payment_source_enum, nullable=False, server_default="MANUAL"),
    )
    # Mirrors invoices.source_reference: the originating row/id from the
    # external system, for import traceability and idempotency (re-importing
    # the same file must update the same payment row, not create a second one).
    op.add_column("payments", sa.Column("source_reference", sa.String(length=255), nullable=True))

    # --- invoices: preserve source-stated outstanding for reference --------
    op.add_column("invoices", sa.Column("imported_outstanding_amount", sa.Numeric(12, 2), nullable=True))

    # --- import_batches -------------------------------------------------------
    import_status_enum = sa.Enum("PENDING", "VALIDATED", "COMMITTED", "FAILED", name="import_status_enum")

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outlet_match_strategy", sa.String(length=50), nullable=False),
        sa.Column("status", import_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("parsed_rows", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_by", sa.Uuid(), nullable=True),
        sa.Column("failure_reason", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["committed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_batches_uploaded_at", "import_batches", ["uploaded_at"])


def downgrade() -> None:
    op.drop_index("ix_import_batches_uploaded_at", table_name="import_batches")
    op.drop_table("import_batches")
    sa.Enum(name="import_status_enum").drop(op.get_bind())

    op.drop_column("invoices", "imported_outstanding_amount")

    op.drop_column("payments", "source_reference")
    op.drop_column("payments", "source")
    sa.Enum(name="payment_source_enum").drop(op.get_bind())
    op.alter_column("payments", "visit_id", existing_type=sa.Uuid(), nullable=False)
