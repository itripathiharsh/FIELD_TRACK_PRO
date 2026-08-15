from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class InvoiceSource(str, enum.Enum):
    MANUAL = "MANUAL"
    EXCEL_IMPORT = "EXCEL_IMPORT"
    TALLY = "TALLY"


class Invoice(Base):
    """
    A single outlet invoice. Historical invoices are first-class rows, never
    overwritten by later payments - `Payment` rows reference an invoice and
    the outstanding/remaining amount is always derived at query time
    (invoice.amount - sum of its VERIFIED payments), so history stays intact
    as more payments are recorded (P1 requirement: history over a single
    running balance).
    """

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(100))
    # Authoritative source for aging calculations (never due_date - see
    # aging_service.py). due_date is informational/display-only.
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Brand-level aggregation (P1: brand info, not SKU/product-level detail).
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[InvoiceSource] = mapped_column(
        Enum(InvoiceSource, name="invoice_source_enum"), default=InvoiceSource.MANUAL
    )
    # Original external row/reference id (Tally voucher id, Excel row), for
    # import traceability and de-duplication. Not a FieldTrack identity.
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # If the source file states its own outstanding/remaining figure for this
    # invoice, it's preserved here for reference/cross-checking - it never
    # drives `remaining_amount` (still always amount - verified payments, the
    # one authoritative computation). Kept only so source information isn't
    # silently discarded when it doesn't reconcile with our own math.
    imported_outstanding_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")

    __table_args__ = (
        # The same invoice cannot be imported/entered twice for one outlet.
        UniqueConstraint("customer_id", "invoice_number", name="uq_invoice_customer_number"),
    )
