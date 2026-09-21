from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TallyAuditLog(Base):
    """
    Persistent audit log table for Tally Prime <-> FieldTrack Pro integration.
    Records every READ (sync from Tally) and standalone WRITE/audit event.
    Writeback operations in tally_writeback_queue are unified with this log in audit views.
    """
    __tablename__ = "tally_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Direction: "READ" (Tally -> FieldTrack) or "WRITE" (FieldTrack -> Tally)
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )
    # Operation: e.g. "SYNC_CUSTOMERS", "SYNC_INVOICES", "SYNC_PAYMENTS", "CREATE_RECEIPT"
    operation: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # Entity Type: "CUSTOMERS", "INVOICES", "PAYMENTS"
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # Number of records processed / included in the batch
    record_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # Status: "SUCCESS", "FAILED", "PARTIAL", "PROCESSING", "PENDING"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    # Execution duration in milliseconds
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # Failure or warning details
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # Agent & Company Context
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    agent_name: Mapped[Optional[str]] = mapped_column(
        String(150), nullable=True
    )
    company_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    company_guid: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Identifiers when applicable (e.g. for writeback or specific voucher sync)
    tally_guid: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    tally_voucher_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    writeback_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )

    # Structured metadata (batch_id, created/updated counts, sample items)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
