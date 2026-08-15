"""
Invoice Service: invoice CRUD plus aging annotation.

Aging is always computed here via aging_service - never stored, never
recomputed by a caller, so it can't drift from the one authoritative rule.
"""
from __future__ import annotations

import uuid
from datetime import date, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.repositories.invoice_repo import InvoiceRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas.invoice import InvoiceCreate, InvoiceRead
from app.services.aging_service import compute_invoice_aging


async def _verified_paid_amount(invoice_id: uuid.UUID, session: AsyncSession) -> Decimal:
    repo = PaymentRepository(session)
    payments = await repo.list_by_invoice(invoice_id, status=PaymentStatus.VERIFIED)
    return sum((p.amount for p in payments), Decimal("0"))


async def to_invoice_read(invoice: Invoice, session: AsyncSession, today: date | None = None) -> InvoiceRead:
    paid = await _verified_paid_amount(invoice.id, session)
    aging = compute_invoice_aging(
        invoice.invoice_date, invoice.amount, paid, today or date.today()
    )
    return InvoiceRead(
        id=invoice.id,
        customer_id=invoice.customer_id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        amount=invoice.amount,
        brand=invoice.brand,
        source=invoice.source,
        source_reference=invoice.source_reference,
        created_by=invoice.created_by,
        created_at=invoice.created_at,
        verified_paid_amount=paid,
        remaining_amount=aging.remaining_amount,
        days_outstanding=aging.days_outstanding,
        payment_status=aging.payment_status,
        aging_status=aging.aging_status,
        mis_bucket=aging.mis_bucket,
    )


async def create_invoice(data: InvoiceCreate, current_user: User, session: AsyncSession) -> Invoice:
    repo = InvoiceRepository(session)
    existing = await repo.find_by_number(data.customer_id, data.invoice_number)
    if existing is not None:
        raise BaseAPIException(
            status_code=409,
            detail=f"Invoice {data.invoice_number} already exists for this outlet",
            error_code="INVOICE_DUPLICATE",
        )
    invoice = Invoice(
        customer_id=data.customer_id,
        invoice_number=data.invoice_number,
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        amount=data.amount,
        brand=data.brand,
        source_reference=data.source_reference,
        created_by=current_user.id,
    )
    await repo.add(invoice)
    await repo.commit()
    return invoice


async def get_invoice(invoice_id: uuid.UUID, session: AsyncSession) -> Invoice:
    repo = InvoiceRepository(session)
    invoice = await repo.get_by_id(invoice_id)
    if invoice is None:
        raise BaseAPIException(status_code=404, detail="Invoice not found", error_code="INVOICE_NOT_FOUND")
    return invoice


async def list_invoices_for_customer(customer_id: uuid.UUID, session: AsyncSession) -> Sequence[Invoice]:
    repo = InvoiceRepository(session)
    return await repo.list_by_customer(customer_id)
