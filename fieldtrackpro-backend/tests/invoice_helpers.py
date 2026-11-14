"""
Test helper: create a sales invoice the way production gets one - from Tally.

There is no manual invoice entry (sales invoices come only from the Tally sync),
so tests that need an invoice insert a TALLY invoice attributed exactly like the
sync attributes it, and get back the same JSON shape as GET /invoices/{id}.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.database import AsyncSessionLocal
from app.models.invoice import Invoice, InvoiceSource
from app.services import invoice_service
from app.services.tally_sync_service import _get_system_user_id


async def create_tally_invoice(
    customer_id,
    invoice_number: str,
    invoice_date: date,
    amount,
    brand: str | None = None,
    created_invoices: list[str] | None = None,
) -> dict:
    async with AsyncSessionLocal() as session:
        invoice = Invoice(
            customer_id=uuid.UUID(str(customer_id)),
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=Decimal(str(amount)),
            brand=brand,
            source=InvoiceSource.TALLY,
            source_reference=f"TEST-TALLY-GUID-{uuid.uuid4()}",
            created_by=await _get_system_user_id(session),
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        body = (await invoice_service.to_invoice_read(invoice, session)).model_dump(mode="json")
    if created_invoices is not None:
        created_invoices.append(body["id"])
    return body
