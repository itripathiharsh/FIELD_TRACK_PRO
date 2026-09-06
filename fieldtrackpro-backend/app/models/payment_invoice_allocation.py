from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaymentInvoiceAllocation(Base):
    """
    Explicit allocation of a payment (or Tally receipt) to a specific invoice.
    Tracks Tally bill reference (bill_name, bill_type) and the allocated amount.
    Guarantees:
    - An invoice's remaining balance is always derived from: invoice.amount - sum(allocations)
    - Full idempotency: (payment_id, invoice_id) is unique.
    - Preserves audit trail for both explicit Agst Ref and deterministic FIFO on-account allocations.
    """

    __tablename__ = "payment_invoice_allocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bill_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    bill_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payment: Mapped["Payment"] = relationship("Payment", back_populates="invoice_allocations")
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="payment_allocations")

    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocations_payment_invoice"),
    )
