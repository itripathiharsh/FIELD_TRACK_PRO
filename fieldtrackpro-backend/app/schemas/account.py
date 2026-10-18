"""
Outlet account summary schemas - the "Account / Collections" panel the
employee sees on an outlet/visit, and the admin sees on a customer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.invoice import InvoiceRead
from app.schemas.payment import PaymentRead
from app.schemas.position import PositionFields
from app.services.aging_service import AgingStatus


class BrandSummary(PositionFields):
    """Aggregated, brand-level account info (never SKU/product-level)."""

    brand: str
    total_invoiced: Decimal
    # Paid = verified AND posted to Tally (or Tally-sourced). Only this reduces outstanding.
    total_paid: Decimal
    # Additive: verified (cash received) but receipt not yet confirmed in Tally.
    verified_awaiting_tally_amount: Decimal = Decimal("0.00")
    total_outstanding: Decimal
    overdue_amount: Decimal
    invoice_count: int
    # Only VERIFIED payments allocated to one of this brand's invoices are
    # counted - an unallocated payment (invoice_id is None) has no brand to
    # attribute it to and is intentionally excluded here, not guessed into
    # a bucket.
    payment_count: int
    latest_invoice_date: date | None
    latest_payment_date: date | None


class AccountSummary(PositionFields):
    customer_id: uuid.UUID
    customer_name: str
    outlet_code: str | None

    # Snapshot sales (Tally baseline) + live invoices.
    total_invoiced: Decimal
    # Paid = payments POSTED to Tally (or Tally-sourced) only; the snapshot
    # baseline collection is in `paid_in_tally` (= baseline_collected + total_paid).
    total_paid: Decimal
    # Additive: "Verified, not yet in Tally" - does NOT reduce total_outstanding.
    verified_awaiting_tally_amount: Decimal = Decimal("0.00")
    total_outstanding: Decimal
    advance_amount: Decimal = Decimal("0.00")
    overdue_amount: Decimal
    # Days outstanding of the single oldest unpaid/partially-paid invoice -
    # the headline "how old is the oldest thing they owe" number.
    max_days_outstanding: int
    # Worst aging status across all outstanding invoices, for a single
    # at-a-glance badge (NORMAL if fully paid / no invoices).
    collection_status: AgingStatus

    most_recent_payment: PaymentRead | None
    # The most recent visit that actually happened (has a check_in_at), and
    # who made it - never a future-scheduled visit. None if this outlet has
    # never had a checked-in visit.
    most_recent_visit_date: datetime | None = None
    most_recent_visit_employee_name: str | None = None
    recent_invoices: list[InvoiceRead]
    recent_payments: list[PaymentRead]
    brand_summary: list[BrandSummary]
    # Legacy gross view (snapshot columns + invoice remaining by 0-30/31-60/...),
    # NOT netted for on-account credit. The authoritative split is `ageing`.
    aging_buckets: dict[str, Decimal] = {}
