"""
Tally v2 data that has no FieldTrack equivalent of its own:

* TallyLedgerAdjustment - every debtor-ledger line of a voucher that is neither a
  sales invoice nor a customer receipt (credit/debit notes, journals, payments to
  a debtor, purchases from a debtor, a receipt line that debits a debtor ...).
  Signed: amount > 0 increases what the customer owes (Tally Dr), < 0 reduces it.
* TallyOpenBill - Tally's own Bills Receivable report as on a date: the pending
  amount of every open bill, with Tally's due date and overdue days.
* TallySnapshotRun - one complete (possibly chunked) snapshot upload from the agent
  (ledger balances, open bills, voucher GUID manifest).
* TallyManifestGuid - staging rows of a voucher GUID manifest while it is uploaded.

Nothing here is ever hard-deleted by the sync except superseded open-bill
snapshot rows and manifest staging rows (both are re-derivable copies of Tally
reports, not financial records).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ADJUSTMENT_ACTIVE = "ACTIVE"
ADJUSTMENT_RETIRED = "RETIRED"


class TallyLedgerAdjustment(Base):
    __tablename__ = "tally_ledger_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    # Release 2.1.0: the original Tally ledger of this row (customer_id = its physical outlet).
    tally_debtor_ledger_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tally_debtor_ledgers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Line identity: the voucher GUID, or "<GUID>::<ledger name>" for a voucher that
    # touches several debtor ledgers.
    source_reference: Mapped[str] = mapped_column(String(255), unique=True)
    tally_voucher_guid: Mapped[str] = mapped_column(String(100), index=True)
    voucher_type: Mapped[str] = mapped_column(String(100))
    voucher_parent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    voucher_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    voucher_date: Mapped[date] = mapped_column(Date, index=True)
    financial_year: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    narration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bill_allocations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    tally_alter_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default=ADJUSTMENT_ACTIVE, server_default=ADJUSTMENT_ACTIVE, index=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TallyOpenBill(Base):
    __tablename__ = "tally_open_bills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    # Release 2.1.0: the original Tally ledger of this row (customer_id = its physical outlet).
    tally_debtor_ledger_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tally_debtor_ledgers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    bill_name: Mapped[str] = mapped_column(String(150))
    bill_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Positive = the customer owes this bill (Tally Dr); negative = an open credit bill.
    pending_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    overdue_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_tally_open_bills_customer_asof", "customer_id", "as_of_date"),
    )


class TallySnapshotRun(Base):
    __tablename__ = "tally_snapshot_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # agent-generated snapshot id
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sync_agents.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30), index=True)  # LEDGERS | BILLS | VOUCHER_MANIFEST
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    window_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    window_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVING")  # RECEIVING | COMPLETE | FAILED
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TallyManifestGuid(Base):
    __tablename__ = "tally_manifest_guids"

    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tally_snapshot_runs.id", ondelete="CASCADE"), primary_key=True
    )
    guid: Mapped[str] = mapped_column(String(100), primary_key=True)
