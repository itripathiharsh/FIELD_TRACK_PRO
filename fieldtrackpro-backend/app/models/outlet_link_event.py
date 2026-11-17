"""Audit trail of every outlet <-> Tally ledger mapping change (release 2.1.0). Reversible via `moved`/`before`."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ACTIONS = ("LINK", "UNLINK", "SET_PRIMARY", "BRAND_OVERRIDE", "OUTLET_CODE", "RENAME", "REVIEW", "BULK_APPLY", "BULK_REVERT")


class OutletLinkEvent(Base):
    __tablename__ = "outlet_link_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(20))
    ledger_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tally_debtor_ledgers.id", ondelete="SET NULL"), nullable=True, index=True)
    from_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    moved: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
