"""
Invoice Service: invoice reads plus aging annotation.

Invoices are created only by the Tally sync (tally_sync_service); there is no
manual entry. Aging is always computed here via aging_service - never stored,
never recomputed by a caller, so it can't drift from the one authoritative rule.
"""
from __future__ import annotations

import uuid
from datetime import date, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_now
from app.exceptions.custom import BaseAPIException
from app.models.invoice import Invoice
from app.repositories.invoice_repo import InvoiceRepository
from app.schemas.invoice import InvoiceRead
from app.services.aging_service import compute_invoice_aging


async def _verified_paid_amount(invoice_id: uuid.UUID, session: AsyncSession) -> Decimal:
    """
    Money that has actually SETTLED this invoice = payments whose receipt is in
    Tally (VERIFIED and write-back CONFIRMED, or sourced from Tally). The name
    is historical; a VERIFIED MANUAL payment still awaiting Tally does NOT count
    (see app/services/payment_tally.py). Use `_awaiting_tally_amount` for the
    verified-but-not-yet-posted money.
    """
    from app.services import payment_tally

    return (await payment_tally.posted_paid_by_invoice(session, [invoice_id]))[invoice_id]


async def _awaiting_tally_amount(invoice_id: uuid.UUID, session: AsyncSession) -> Decimal:
    from app.services import payment_tally

    return (await payment_tally.awaiting_by_invoice(session, [invoice_id]))[invoice_id]


async def to_invoice_read(invoice: Invoice, session: AsyncSession, today: date | None = None) -> InvoiceRead:
    paid = await _verified_paid_amount(invoice.id, session)
    awaiting = await _awaiting_tally_amount(invoice.id, session)
    aging = compute_invoice_aging(
        invoice.invoice_date, invoice.amount, paid, today or get_ist_now().date()
    )
    ledger_name = None
    lid = getattr(invoice, "tally_debtor_ledger_id", None)
    if lid is not None:
        from app.models.tally_debtor_ledger import TallyDebtorLedger
        led = await session.get(TallyDebtorLedger, lid)
        ledger_name = led.name if led is not None else None
    return InvoiceRead(
        id=invoice.id,
        customer_id=invoice.customer_id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        financial_year=invoice.financial_year,
        due_date=invoice.due_date,
        amount=invoice.amount,
        brand=invoice.brand,
        source=invoice.source,
        source_reference=invoice.source_reference,
        tally_bill_name=invoice.tally_bill_name,
        tally_voucher_type=invoice.tally_voucher_type,
        tally_debtor_ledger_id=lid,
        tally_ledger_name=ledger_name,
        created_by=invoice.created_by,
        created_at=invoice.created_at,
        verified_paid_amount=paid,
        verified_awaiting_tally_amount=awaiting,
        remaining_amount=aging.remaining_amount,
        days_outstanding=aging.days_outstanding,
        payment_status=aging.payment_status,
        aging_status=aging.aging_status,
        mis_bucket=aging.mis_bucket,
    )


async def get_invoice(invoice_id: uuid.UUID, session: AsyncSession) -> Invoice:
    repo = InvoiceRepository(session)
    invoice = await repo.get_by_id(invoice_id)
    if invoice is None:
        raise BaseAPIException(status_code=404, detail="Invoice not found", error_code="INVOICE_NOT_FOUND")
    return invoice


async def list_invoices_for_customer(customer_id: uuid.UUID, session: AsyncSession) -> Sequence[Invoice]:
    repo = InvoiceRepository(session)
    return await repo.list_by_customer(customer_id)
