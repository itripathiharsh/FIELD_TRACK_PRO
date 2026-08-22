from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


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


class BusinessBIDashboard(BaseModel):
    snapshot_date: Optional[date] = None
    month_period: Optional[str] = None
    is_finalized: bool = False
    total_outlets: int
    total_sales: Decimal
    total_collection: Decimal
    total_market_outstanding: Decimal
    total_overdue_gt_90: Decimal
    brand_summaries: list[BusinessSummaryRow]
    zone_summaries: list[BusinessSummaryRow]
    area_summaries: list[BusinessSummaryRow]
    fos_summaries: list[BusinessSummaryRow]
    raw_outlet_rows: list[BusinessSummaryRow]


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
    total_market_os: Decimal
    total_overdue_gt_90: Decimal
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
