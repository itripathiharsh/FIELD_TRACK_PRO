"""
Invoice schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.invoice import InvoiceSource
from app.services.aging_service import AgingStatus, MisBucket, PaymentStatusLabel


class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    amount: Decimal = Field(gt=0)
    brand: str | None = Field(default=None, max_length=100)
    source_reference: str | None = Field(default=None, max_length=255)


class InvoiceRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str
    invoice_date: date
    due_date: date | None
    amount: Decimal
    brand: str | None
    source: InvoiceSource
    source_reference: str | None
    created_by: uuid.UUID
    created_at: datetime

    # Computed aging fields (from aging_service - never recomputed elsewhere).
    verified_paid_amount: Decimal
    remaining_amount: Decimal
    days_outstanding: int
    payment_status: PaymentStatusLabel
    aging_status: AgingStatus
    mis_bucket: MisBucket
