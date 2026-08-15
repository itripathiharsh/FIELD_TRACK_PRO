from __future__ import annotations
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaymentProof(Base):
    """
    A cheque photo or online-payment screenshot attached to a Payment.
    Mirrors VisitMedia's exact pattern (storage_key + checksum + size +
    original_filename + uploaded_by) rather than a new media abstraction -
    per the P1 requirement, proof belongs to the payment/collection entity,
    not a generic Media Vault.
    """

    __tablename__ = "payment_proofs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    payment: Mapped["Payment"] = relationship(back_populates="proofs")

    __table_args__ = (
        UniqueConstraint("payment_id", "checksum_sha256", name="uq_payment_proof_content"),
    )
