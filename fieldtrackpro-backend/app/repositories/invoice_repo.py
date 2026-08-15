"""
Invoice repository: data access operations for the Invoice entity.
Follows: Router -> Service -> Repository -> DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.repositories.base import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Invoice, session)

    async def list_by_customer(self, customer_id: uuid.UUID) -> Sequence[Invoice]:
        result = await self.session.execute(
            select(Invoice)
            .where(Invoice.customer_id == customer_id)
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        )
        return result.scalars().all()

    async def find_by_number(self, customer_id: uuid.UUID, invoice_number: str) -> Invoice | None:
        result = await self.session.execute(
            select(Invoice).where(
                Invoice.customer_id == customer_id,
                Invoice.invoice_number == invoice_number,
            )
        )
        return result.scalar_one_or_none()
