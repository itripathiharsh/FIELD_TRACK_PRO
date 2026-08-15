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
from app.services.aging_service import AgingStatus


class BrandSummary(BaseModel):
    """Aggregated, brand-level account info (never SKU/product-level)."""

    brand: str
    total_invoiced: Decimal
    total_paid: Decimal
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


class AccountSummary(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    outlet_code: str | None

    total_invoiced: Decimal
    total_paid: Decimal
    total_outstanding: Decimal
    overdue_amount: Decimal
    # Days outstanding of the single oldest unpaid/partially-paid invoice -
    # the headline "how old is the oldest thing they owe" number.
    max_days_outstanding: int
    # Worst aging status across all outstanding invoices, for a single
    # at-a-glance badge (NORMAL if fully paid / no invoices).
    collection_status: AgingStatus

    most_recent_payment: PaymentRead | None
    recent_invoices: list[InvoiceRead]
    recent_payments: list[PaymentRead]
    brand_summary: list[BrandSummary]
