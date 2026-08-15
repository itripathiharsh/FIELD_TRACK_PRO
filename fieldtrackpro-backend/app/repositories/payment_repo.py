"""
Payment repository: data access operations for the Payment ("Collection")
and PaymentProof entities. Follows: Router -> Service -> Repository -> DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import Payment, PaymentStatus
from app.models.payment_proof import PaymentProof
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Payment, session)

    async def get_by_id(self, record_id: uuid.UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment).options(selectinload(Payment.proofs)).where(Payment.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_by_customer(self, customer_id: uuid.UUID) -> Sequence[Payment]:
        result = await self.session.execute(
            select(Payment)
            .options(selectinload(Payment.proofs))
            .where(Payment.customer_id == customer_id)
            .order_by(Payment.payment_date.desc(), Payment.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_invoice(self, invoice_id: uuid.UUID, status: PaymentStatus | None = None) -> Sequence[Payment]:
        stmt = select(Payment).where(Payment.invoice_id == invoice_id)
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_queue(
        self,
        status: PaymentStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Payment]:
        """The accountant review queue - newest pending first by default."""
        stmt = select(Payment).options(selectinload(Payment.proofs))
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        stmt = stmt.order_by(Payment.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_employee(self, employee_id: uuid.UUID) -> Sequence[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.employee_id == employee_id)
            .order_by(Payment.payment_date.desc())
        )
        return result.scalars().all()

    async def find_by_visit_and_idempotency_key(
        self, visit_id: uuid.UUID, idempotency_key: str
    ) -> Payment | None:
        result = await self.session.execute(
            select(Payment)
            .options(selectinload(Payment.proofs))
            .where(Payment.visit_id == visit_id, Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()


class PaymentProofRepository(BaseRepository[PaymentProof]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PaymentProof, session)

    async def list_by_payment(self, payment_id: uuid.UUID) -> Sequence[PaymentProof]:
        result = await self.session.execute(
            select(PaymentProof).where(PaymentProof.payment_id == payment_id)
        )
        return result.scalars().all()

    async def find_by_checksum_for_payment(
        self, payment_id: uuid.UUID, checksum: str
    ) -> PaymentProof | None:
        result = await self.session.execute(
            select(PaymentProof).where(
                PaymentProof.payment_id == payment_id,
                PaymentProof.checksum_sha256 == checksum,
            )
        )
        return result.scalar_one_or_none()
