"""
Business-scope rule for one Tally debtor group (release 3.1).

FieldTrack holds the SGRG Distribution business only. A debtor ledger's scope follows its Tally group:
  DISTRIBUTION  every ledger of the group is in scope (new outlets of the group sync automatically)
  EXCLUDED      every ledger of the group is out of scope (e.g. "Other Debtor": staff / personal / related)
A ledger whose group has no rule is PENDING (hidden) until an admin decides it. A ledger-level MANUAL decision
(tally_debtor_ledgers.scope_source = MANUAL) always wins over the group rule.

Scope enforcement is ON as soon as this table holds at least one rule; with no rule every ledger is in scope
(the pre-3.1 behaviour).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TallyScopeGroup(Base):
    __tablename__ = "tally_scope_groups"

    group_name: Mapped[str] = mapped_column(String(150), primary_key=True)
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
