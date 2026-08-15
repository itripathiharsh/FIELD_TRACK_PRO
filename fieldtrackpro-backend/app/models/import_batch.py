from __future__ import annotations
import enum
import uuid
from typing import Any, Optional
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class ImportBatch(Base):
    """
    Audit trail for one Excel/MIS import run, and the durable staging area
    between /imports/validate (parses + resolves + validates the full file,
    writes nothing to the business tables) and /imports/{id}/commit (reads
    `parsed_rows` back and performs the actual transactional write).

    Storing the fully-resolved rows here means the browser only has to
    upload the source file once (at validate time) - commit never needs it
    again, and a past batch remains fully inspectable (mapping used, what
    would happen, what errors were found) even if never committed.
    """

    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    sheet_name: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # {excel_column_name: target_field_key} - see import_service.TARGET_FIELDS.
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The outlet-resolution strategy chosen for this batch: "outlet_code" or
    # "name_and_territory" (see import_service.py).
    outlet_match_strategy: Mapped[str] = mapped_column(String(50))

    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus, name="import_status_enum"), default=ImportStatus.PENDING)

    # Fully resolved, ready-to-commit row data (list of dicts) - see
    # import_service.ParsedRow.to_dict(). Populated at validate time.
    parsed_rows: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{row, column, value, error, suggested_fix}, ...]
    error_report: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # {territories_created, employees_matched, customers_created,
    #  customers_updated, invoices_created, invoices_updated,
    #  payments_created, ...}
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    rows_error: Mapped[int] = mapped_column(Integer, default=0)

    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
