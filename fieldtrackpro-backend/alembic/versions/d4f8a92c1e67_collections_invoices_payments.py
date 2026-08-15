"""collections: outlet_code, order media type, invoices, payments, payment_proofs

Revision ID: d4f8a92c1e67
Revises: e9821f8a7c34
Create Date: 2026-08-13 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4f8a92c1e67"
down_revision: Union[str, Sequence[str], None] = "e9821f8a7c34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- customers.outlet_code ----------------------------------------------
    # Stable, human-readable identity for cross-referencing an outlet against
    # external systems (Tally ledger code, Excel/MIS imports) - never the
    # outlet name, which can collide (e.g. "Balaji Enterprises" vs "Balaji
    # Electrical"). The internal `id` remains the canonical in-app FK.
    op.add_column("customers", sa.Column("outlet_code", sa.String(length=50), nullable=True))
    op.create_unique_constraint("uq_customers_outlet_code", "customers", ["outlet_code"])

    # --- visit_media: order-capture reuse -----------------------------------
    # Reuses the existing media table for the P1 "photograph a diary order"
    # requirement instead of a new table (per the explicit reuse mandate).
    op.execute("ALTER TYPE media_type_enum ADD VALUE 'ORDER'")
    op.add_column("visit_media", sa.Column("note", sa.Text(), nullable=True))

    # --- invoices ------------------------------------------------------------
    # Enum types are created automatically by create_table's column
    # definition below - do not also call .create() explicitly, or Postgres
    # raises DuplicateObjectError on the second attempt.
    invoice_source_enum = sa.Enum("MANUAL", "EXCEL_IMPORT", "TALLY", name="invoice_source_enum")

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("source", invoice_source_enum, nullable=False, server_default="MANUAL"),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "invoice_number", name="uq_invoice_customer_number"),
    )
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])

    # --- payments (the "Collection") ----------------------------------------
    payment_method_enum = sa.Enum("CASH", "CHEQUE", "ONLINE", name="payment_method_enum")
    payment_status_enum = sa.Enum(
        "PENDING_VERIFICATION", "VERIFIED", "REJECTED", name="payment_status_enum"
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", payment_method_enum, nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("cheque_number", sa.String(length=50), nullable=True),
        sa.Column("cheque_bank_name", sa.String(length=150), nullable=True),
        sa.Column("utr_reference", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", payment_status_enum, nullable=False, server_default="PENDING_VERIFICATION"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_visit_id", "payments", ["visit_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_employee_id", "payments", ["employee_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    # --- payment_proofs -------------------------------------------------------
    op.create_table(
        "payment_proofs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_payment_proofs_storage_key"),
        sa.UniqueConstraint("payment_id", "checksum_sha256", name="uq_payment_proof_content"),
    )
    op.create_index("ix_payment_proofs_payment_id", "payment_proofs", ["payment_id"])
    op.create_index("ix_payment_proofs_checksum", "payment_proofs", ["checksum_sha256"])


def downgrade() -> None:
    op.drop_index("ix_payment_proofs_checksum", table_name="payment_proofs")
    op.drop_index("ix_payment_proofs_payment_id", table_name="payment_proofs")
    op.drop_table("payment_proofs")

    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_employee_id", table_name="payments")
    op.drop_index("ix_payments_customer_id", table_name="payments")
    op.drop_index("ix_payments_visit_id", table_name="payments")
    op.drop_table("payments")
    sa.Enum(name="payment_status_enum").drop(op.get_bind())
    sa.Enum(name="payment_method_enum").drop(op.get_bind())

    op.drop_index("ix_invoices_customer_id", table_name="invoices")
    op.drop_table("invoices")
    sa.Enum(name="invoice_source_enum").drop(op.get_bind())

    op.drop_column("visit_media", "note")
    # Postgres cannot remove an enum value; ORDER stays defined on downgrade
    # (harmless - matches how other enum-widening migrations in this repo
    # behave, since Postgres has no DROP VALUE).

    op.drop_constraint("uq_customers_outlet_code", "customers", type_="unique")
    op.drop_column("customers", "outlet_code")
