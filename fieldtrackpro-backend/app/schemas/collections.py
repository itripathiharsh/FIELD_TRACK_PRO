"""
Collections Overview schemas - the outlet-list-level "who owes what, how
old, whose outlet is it" view (Meeting 2's "Excel screenshot" ask).

Reuses the exact same aging/status vocabulary as the per-outlet Account
Summary (schemas/account.py, services/aging_service.py) rather than
inventing a second status system - see services/collections_service.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.services.aging_service import AgingStatus, MisBucket


class AssignedEmployeeSummary(BaseModel):
    id: uuid.UUID
    name: str


class OutletCollectionRow(BaseModel):
    customer_id: uuid.UUID
    outlet_code: str | None
    customer_name: str
    territory_id: uuid.UUID | None
    territory_name: str | None
    area_id: uuid.UUID | None
    area_name: str | None
    # Every employee currently assigned to cover this outlet's Area
    # (EmployeeAreaAssignment - brand-agnostic, many-to-many: coverage can
    # genuinely be zero, one, or several employees, never assumed to be
    # exactly one). Falls back to the legacy single-Zone
    # Employee.territory_id derivation only for an outlet that has no Area
    # assigned yet, so pre-migration outlets don't regress to "unassigned".
    assigned_employees: list[AssignedEmployeeSummary]

    total_invoiced: Decimal
    total_paid: Decimal
    total_outstanding: Decimal
    overdue_amount: Decimal
    max_days_outstanding: int
    collection_status: AgingStatus

    # The single MIS bucket the outlet's oldest outstanding invoice falls
    # into, and how much of its outstanding money sits specifically in that
    # bucket - not the whole total_outstanding, since an outlet's invoices
    # can straddle several buckets at once.
    relevant_mis_bucket: MisBucket | None
    relevant_bucket_amount: Decimal

    most_recent_payment_date: date | None
    most_recent_payment_amount: Decimal | None
    most_recent_payment_employee_name: str | None
    # The most recent visit that actually happened (has a check_in_at) -
    # never a future-scheduled visit.
    most_recent_visit_date: datetime | None
    most_recent_visit_employee_name: str | None


class CollectionsOverviewTotals(BaseModel):
    """Reflects every outlet matching the current filters, not just the
    current page - so the summary tiles never silently disagree with what a
    filter claims to show."""

    total_outlets: int
    total_invoiced: Decimal
    total_paid: Decimal
    total_outstanding: Decimal
    # Outstanding money not yet even in the warning window (AgingStatus.NORMAL).
    current_amount: Decimal
    bucket_0_15: Decimal
    bucket_16_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal


class CollectionsOverviewResponse(BaseModel):
    totals: CollectionsOverviewTotals
    outlets: list[OutletCollectionRow]
    total_count: int
    skip: int
    limit: int
