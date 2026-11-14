"""
Invoice repository: data access operations for the Invoice entity.
Follows: Router -> Service -> Repository -> DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceSource
from app.repositories.base import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Invoice, session)

    async def list_by_customer(self, customer_id: uuid.UUID) -> Sequence[Invoice]:
        """The outlet's sales invoices in Tally - the only invoices that are part of the books."""
        result = await self.session.execute(
            select(Invoice)
            .where(Invoice.customer_id == customer_id, Invoice.source == InvoiceSource.TALLY)
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        )
        return result.scalars().all()
