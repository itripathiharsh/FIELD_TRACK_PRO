"""
Payment ("Collection") schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentProofRead(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    storage_key: str
    file_size_bytes: int
    original_filename: str | None = None
    uploaded_by: uuid.UUID | None = None
    uploaded_at: datetime


class PaymentCreate(BaseModel):
    """
    Submitted by an employee during a visit. `visit_id` determines the
    outlet/employee automatically server-side (see payment_service.py) - the
    client never supplies customer_id/employee_id directly, so a collection
    can never be misattributed to a similarly-named outlet by typing/selecting
    the wrong one.
    """

    visit_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    payment_method: PaymentMethod
    payment_date: date
    cheque_number: str | None = Field(default=None, max_length=50)
    cheque_bank_name: str | None = Field(default=None, max_length=150)
    utr_reference: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    # Client-generated key (e.g. a UUID minted once per submit attempt) so a
    # double-tap or a retried request after a dropped response cannot create
    # two collection rows for the same visit. Optional for backward
    # compatibility with any caller that doesn't send one - those requests
    # simply get no duplicate protection, matching pre-existing behaviour.
    idempotency_key: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_method_specific_fields(self) -> "PaymentCreate":
        if self.payment_method == PaymentMethod.CHEQUE and not self.cheque_number:
            raise ValueError("cheque_number is required for CHEQUE payments")
        if self.payment_method == PaymentMethod.ONLINE and not self.utr_reference:
            raise ValueError("utr_reference is required for ONLINE payments")
        return self


class PaymentReviewAction(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_reason_for_rejection(self) -> "PaymentReviewAction":
        # Router distinguishes verify/reject; this model is reused for both,
        # so the reason requirement is enforced at the service layer for the
        # reject action specifically (see payment_service.reject_payment).
        return self


class PaymentRead(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    customer_id: uuid.UUID
    employee_id: uuid.UUID
    invoice_id: uuid.UUID | None
    amount: Decimal
    payment_method: PaymentMethod
    payment_date: date
    cheque_number: str | None
    cheque_bank_name: str | None
    utr_reference: str | None
    notes: str | None
    status: PaymentStatus
    rejection_reason: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    proofs: list[PaymentProofRead] = []

    # Denormalized display fields, populated by the service layer for the
    # accountant queue (avoids N+1 joins on the frontend).
    customer_name: str | None = None
    outlet_code: str | None = None
    employee_name: str | None = None
    territory_name: str | None = None
