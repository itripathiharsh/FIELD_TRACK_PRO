from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MonthlyPeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    FINALIZED = "FINALIZED"


class MonthlyReportingPeriod(Base):
    """
    Tracks monthly reporting periods and historical snapshot finalization state.
    Once finalized, historical snapshots for that month cannot be overwritten.
    """

    __tablename__ = "monthly_reporting_periods"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "August 2026"

    status: Mapped[MonthlyPeriodStatus] = mapped_column(
        Enum(MonthlyPeriodStatus, name="monthly_period_status_enum"),
        default=MonthlyPeriodStatus.OPEN,
        server_default=MonthlyPeriodStatus.OPEN.value,
        nullable=False,
    )

    snapshot_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_outlets: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_sales: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)
    total_collection: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)
    total_market_os: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)
    total_overdue_gt_90: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)

    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("period_year", "period_month", name="uq_monthly_reporting_period_year_month"),
    )
