"""
Invoice schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.invoice import InvoiceSource
from app.services.aging_service import AgingStatus, MisBucket, PaymentStatusLabel


class InvoiceRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str
    invoice_date: date
    financial_year: str | None = None
    due_date: date | None
    amount: Decimal
    brand: str | None
    source: InvoiceSource
    source_reference: str | None
    tally_bill_name: str | None = None
    tally_voucher_type: str | None = None
    created_by: uuid.UUID
    created_at: datetime

    # Computed aging fields (from aging_service - never recomputed elsewhere).
    # Settled money only: VERIFIED payments whose receipt is in Tally
    # (write-back CONFIRMED, or sourced from Tally). remaining_amount = amount - this.
    verified_paid_amount: Decimal
    # Additive: verified (cash received) but receipt not yet confirmed in Tally.
    # Does NOT reduce remaining_amount until Tally confirms.
    verified_awaiting_tally_amount: Decimal = Decimal("0.00")
    remaining_amount: Decimal
    days_outstanding: int
    payment_status: PaymentStatusLabel
    aging_status: AgingStatus
    mis_bucket: MisBucket
