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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    ONLINE = "ONLINE"


class PaymentStatus(str, enum.Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class PaymentSource(str, enum.Enum):
    MANUAL = "MANUAL"
    EXCEL_IMPORT = "EXCEL_IMPORT"
    TALLY = "TALLY"


class Payment(Base):
    """
    A field collection recorded by an employee during a visit ("Collection" in
    the product spec). Never orphaned: always traces Employee -> Visit ->
    Outlet -> Payment -> Proof, per the P1 requirement. `invoice_id` is
    optional - an employee collecting cash/cheque/online payment in the field
    usually cannot (and should not have to) pick the exact invoice it settles;
    when unset, the amount is an unallocated/on-account payment against the
    outlet's total outstanding, which an accountant can later reconcile
    against a specific invoice.

    A payment captured by an employee is never auto-trusted: it starts
    PENDING_VERIFICATION and only counts toward the outlet's paid/outstanding
    totals once an admin/accountant marks it VERIFIED (see aging_service.py
    and payment_service.py) - this is deliberate, matching the client's
    explicit "similar retailer name" mistrust concern.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Nullable only for historical EXCEL_IMPORT/TALLY rows, which have no
    # associated field visit. Every live field collection (source=MANUAL)
    # still requires one - enforced in payment_service.create_payment, not
    # at the column level, since the column must accept both cases.
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("visits.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method_enum"))
    payment_date: Mapped[date] = mapped_column(Date)

    # CHEQUE-specific fields (nullable; required by schema validation only
    # when payment_method == CHEQUE).
    cheque_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cheque_bank_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # ONLINE-specific field (nullable; required by schema validation only
    # when payment_method == ONLINE).
    utr_reference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"), default=PaymentStatus.PENDING_VERIFICATION, index=True
    )
    # MANUAL = live field collection (default, unchanged behaviour).
    # EXCEL_IMPORT/TALLY = historical data brought in via the import
    # pipeline - these are created directly as VERIFIED (the source system
    # already treats them as settled/recorded) but are never confused with a
    # freshly-collected field payment because `source` says otherwise.
    source: Mapped[PaymentSource] = mapped_column(
        Enum(PaymentSource, name="payment_source_enum"), default=PaymentSource.MANUAL
    )
    # Mirrors Invoice.source_reference - the originating external row/id, for
    # import traceability and idempotency (re-import updates the same row).
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Client-generated key so a double-tap/retried submit cannot create two
    # collection rows for the same visit. Nullable (historical EXCEL_IMPORT/
    # TALLY rows never set one; those dedupe by source_reference instead) -
    # Postgres treats NULL as distinct under a UniqueConstraint, so any number
    # of rows without a key coexist safely. Mirrors the identical pattern
    # already used for GeoVerificationLog.idempotency_key.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    visit: Mapped["Visit"] = relationship(back_populates="payments")
    customer: Mapped["Customer"] = relationship()
    employee: Mapped["Employee"] = relationship()
    invoice: Mapped[Optional["Invoice"]] = relationship(back_populates="payments")
    proofs: Mapped[list["PaymentProof"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # A retried/double-tapped submission must not create a second
        # collection row for the same visit.
        UniqueConstraint("visit_id", "idempotency_key", name="uq_payments_visit_idempotency"),
    )
