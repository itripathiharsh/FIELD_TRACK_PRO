from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, model_validator

OUTSTANDING_UNAVAILABLE_NOTE = (
    "Outstanding and ageing are not available for this month: no Tally balance snapshot exists for it, "
    "and they cannot be derived from invoices alone without the balances brought forward."
)


class OutletFinancialSnapshotRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    brand: str
    snapshot_date: date
    sales: Decimal
    collection: Decimal
    market_outstanding: Decimal
    bucket_lt_15: Decimal
    bucket_15_30: Decimal
    bucket_30_45: Decimal
    bucket_45_60: Decimal
    bucket_60_75: Decimal
    bucket_75_90: Decimal
    bucket_gt_90: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessSummaryRow(BaseModel):
    brand: str
    dimension_name: str  # e.g. Zone name, Area name, FOS name, or Outlet name
    dms_code: Optional[str] = None
    outlet_name: Optional[str] = None
    zone_name: Optional[str] = None
    area_name: Optional[str] = None
    fos_name: Optional[str] = None
    outlets_count: int = 1
    sales: Decimal = Decimal("0.00")
    collection: Decimal = Decimal("0.00")
    market_outstanding: Decimal = Decimal("0.00")
    bucket_lt_15: Decimal = Decimal("0.00")
    bucket_15_30: Decimal = Decimal("0.00")
    bucket_30_45: Decimal = Decimal("0.00")
    bucket_45_60: Decimal = Decimal("0.00")
    bucket_60_75: Decimal = Decimal("0.00")
    bucket_75_90: Decimal = Decimal("0.00")
    bucket_gt_90: Decimal = Decimal("0.00")
    # Latest snapshot date of the stock figures on a raw outlet row.
    as_of_date: Optional[date] = None


class BusinessBIDashboard(BaseModel):
    snapshot_date: Optional[date] = None
    month_period: Optional[str] = None
    is_finalized: bool = False
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    # Additive split of live VERIFIED collections (0 on the snapshot path).
    total_collection_posted_in_tally: Decimal = Decimal("0.00")
    total_collection_verified_awaiting_tally: Decimal = Decimal("0.00")
    total_market_outstanding: Decimal
    total_overdue_gt_90: Decimal
    brand_summaries: list[BusinessSummaryRow]
    zone_summaries: list[BusinessSummaryRow]
    area_summaries: list[BusinessSummaryRow]
    fos_summaries: list[BusinessSummaryRow]
    raw_outlet_rows: list[BusinessSummaryRow]
    # SNAPSHOT (outlet financial snapshots) or LIVE_INVOICES (fallback when no snapshot exists in the period).
    data_source: str = "SNAPSHOT"
    data_source_note: Optional[str] = None
    # Latest snapshot date backing the stock figures (market OS / ageing); today for LIVE_INVOICES.
    as_of_date: Optional[date] = None
    # Resolved period: inclusive IST dates, source DATES | MONTH | ALL.
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_source: str = "ALL"
    # True when a month was supplied but ignored because an explicit date range won.
    month_ignored: bool = False
    # Selected ageing bucket ('<15' ... '>90') when the figures are restricted to one bucket, else None.
    ageing_bucket: Optional[str] = None
    # Plain-language rule used to place money in an ageing bucket.
    ageing_basis: Optional[str] = None


class MonthlyPeriodRead(BaseModel):
    id: uuid.UUID
    period_year: int
    period_month: int
    period_name: str
    status: str
    snapshot_count: int
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    # None when the month has no balance snapshot (see outstanding_available).
    total_market_os: Optional[Decimal] = None
    total_overdue_gt_90: Optional[Decimal] = None
    outstanding_available: bool = False
    outstanding_note: Optional[str] = None
    opened_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[uuid.UUID] = None
    reopened_at: Optional[datetime] = None
    reopened_by: Optional[uuid.UUID] = None
    reopen_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _outstanding_only_from_snapshots(self) -> "MonthlyPeriodRead":
        # A month's closing outstanding is known only from a balance snapshot;
        # without one the stored 0 must not be shown as "nothing outstanding".
        self.outstanding_available = self.snapshot_count > 0
        if not self.outstanding_available:
            self.total_market_os = None
            self.total_overdue_gt_90 = None
            self.outstanding_note = OUTSTANDING_UNAVAILABLE_NOTE
        return self


class ReopenMonthlyPeriodRequest(BaseModel):
    reason: str


class MonthlyPeriodReviewSummary(BaseModel):
    period_id: uuid.UUID
    period_year: int
    period_month: int
    period_name: str
    status: str
    visits_completed: int
    visits_adhoc: int
    visits_total: int
    collections_submitted_amount: Decimal
    collections_verified_amount: Decimal
    collections_pending_amount: Decimal
    collections_count: int
    # None when the month has no balance snapshot.
    total_outstanding: Optional[Decimal] = None
    outstanding_available: bool = False
    total_invoices_count: int
    total_outlets_count: int
    can_finalize: bool
