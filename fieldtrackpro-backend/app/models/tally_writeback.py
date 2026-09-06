from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WritebackStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class TallyWritebackQueue(Base):
    """
    Durable transactional outbox queue for BE -> Tally write-back jobs.
    Created in the same DB transaction as a payment/collection.
    Guarantees idempotency and safe retries for creating Receipt vouchers in Tally.
    """
    __tablename__ = "tally_writeback_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Unique constraint prevents double-enqueuing for the same payment
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PAYMENT"
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(
        String(50), nullable=False, default="CREATE_RECEIPT"
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    status: Mapped[WritebackStatus] = mapped_column(
        String(50), nullable=False, default=WritebackStatus.PENDING, index=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # Identifiers returned upon successful Tally creation
    tally_guid: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    tally_master_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    tally_voucher_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tally_writeback_idempotency_key"),
    )
