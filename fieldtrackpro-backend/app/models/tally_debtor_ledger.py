"""
One Tally ledger (debtor or not) and the physical outlet it belongs to (release 2.1.0).

`customers` is the PHYSICAL OUTLET (one shop). Tally often keeps one ledger per brand
for the same shop; every such ledger is a row here, linked to its outlet by
`customer_id`, and keeps its own Tally identity (GUID), balances and records - linking
never changes Tally facts. A ledger is linked to another outlet only by an explicit,
audited action (`outlet_link_service`), never by name similarity.

`mapping_status`:
  AUTO_1TO1       migrated 1:1 from the customer that held the ledger, not reviewed
  NEW_UNREVIEWED  first seen in Tally after go-live; its own outlet until reviewed
  CONFIRMED       linked to its outlet by a confirmed mapping / admin action
  REVIEW          flagged for review
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

MAPPING_AUTO = "AUTO_1TO1"
MAPPING_NEW = "NEW_UNREVIEWED"
MAPPING_CONFIRMED = "CONFIRMED"
MAPPING_REVIEW = "REVIEW"

# Business scope (release 3.1): FieldTrack holds the SGRG Distribution business only.
#   DISTRIBUTION  in scope (also NULL: not evaluated, i.e. scope enforcement off)
#   EXCLUDED      another business vertical / staff / inter-company: hidden, its rows retired (never deleted)
#   PENDING       not decided yet (unknown group, ambiguous ledger): hidden until an admin decides
SCOPE_DISTRIBUTION = "DISTRIBUTION"
SCOPE_EXCLUDED = "EXCLUDED"
SCOPE_PENDING = "PENDING"
SCOPE_SOURCE_GROUP = "GROUP"
SCOPE_SOURCE_MANUAL = "MANUAL"
SCOPE_SOURCE_DEFAULT = "DEFAULT"


class TallyDebtorLedger(Base):
    __tablename__ = "tally_debtor_ledgers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    tally_guid: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    parent_group: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    aliases: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    tally_outlet_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    brand_tally: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    brand_override: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    brand_override_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    brand_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_debtor: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, index=True)
    is_bill_wise: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    credit_period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Signed exactly as Tally exports (Dr negative), like customers.tally_*_balance.
    opening_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    opening_balance_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    closing_balance_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    gst_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    mapping_status: Mapped[str] = mapped_column(String(20), nullable=False, default=MAPPING_AUTO,
                                                server_default=MAPPING_AUTO)
    linked_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    business_scope: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, index=True)
    scope_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    scope_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    scope_decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("uq_tally_debtor_ledgers_one_primary", "customer_id", unique=True,
              postgresql_where=text("is_primary")),
    )

    @property
    def in_scope(self) -> bool:
        """In the Distribution business scope (NULL = not evaluated: scope enforcement off)."""
        return self.business_scope in (None, SCOPE_DISTRIBUTION)

    @property
    def effective_brand(self) -> Optional[str]:
        return (self.brand_override or "").strip() or (self.brand_tally or "").strip() or None

    @property
    def brand_source(self) -> str:
        if (self.brand_override or "").strip():
            return "OVERRIDE"
        if (self.brand_tally or "").strip():
            return "TALLY"
        return "NONE"
