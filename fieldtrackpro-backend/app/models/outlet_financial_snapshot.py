from __future__ import annotations
import uuid
from typing import Optional
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OutletFinancialSnapshot(Base):
    """
    Periodic/monthly financial snapshot for an outlet per brand.
    Preserves historical sales, collections, market outstanding, and the 7
    standard ageing buckets (<15d, 15-30d, 30-45d, 45-60d, 60-75d, 75-90d, >90d)
    without mutating the outlet master record.
    """

    __tablename__ = "outlet_financial_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    brand: Mapped[str] = mapped_column(String(100), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)

    sales: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    collection: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    market_outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    bucket_lt_15: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_15_30: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_30_45: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_45_60: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_60_75: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_75_90: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    bucket_gt_90: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    import_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="financial_snapshots")

    __table_args__ = (
        UniqueConstraint("customer_id", "brand", "snapshot_date", name="uq_customer_brand_snapshot_date"),
    )
