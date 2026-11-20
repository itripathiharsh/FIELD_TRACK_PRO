"""
Every Tally voucher FieldTrack has processed, one row per voucher GUID (release 3.0, reconciliation).

The invoice / payment / adjustment tables only hold vouchers that move a customer balance; a purchase, a contra
or a cancelled voucher leaves no row there. Reconciliation must still know that FieldTrack has SEEN such a voucher
(and in which version), otherwise it would report it "missing" forever. This index records, for every voucher the
agent sent: its GUID, its latest AlterID, its date, and whether it still exists in Tally (state).

  ACTIVE   processed; the latest version FieldTrack holds is `alter_id`
  DELETED  absent from an accepted manifest (deleted in Tally or re-dated out of the window); its rows are retired

The index is written in the same savepoint as the voucher's rows, so it can never claim a version whose rows were
not written.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

STATE_ACTIVE = "ACTIVE"
STATE_DELETED = "DELETED"


class TallyVoucherIndex(Base):
    __tablename__ = "tally_voucher_index"

    guid: Mapped[str] = mapped_column(String(100), primary_key=True)
    alter_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False, default=STATE_ACTIVE)
    company_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_tally_voucher_index_state_date", "state", "voucher_date"),)
