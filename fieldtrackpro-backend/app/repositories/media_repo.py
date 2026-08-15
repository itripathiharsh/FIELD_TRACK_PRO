"""
Media repository: data access operations for VisitMedia entity.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.visit_media import MediaType, VisitMedia
from app.repositories.base import BaseRepository


class MediaRepository(BaseRepository[VisitMedia]):
    """Repository handling database operations for VisitMedia."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(VisitMedia, session)

    async def list_by_visit(self, visit_id: uuid.UUID) -> Sequence[VisitMedia]:
        """Fetch all media items attached to a specific visit."""
        result = await self.session.execute(
            select(VisitMedia)
            .where(VisitMedia.visit_id == visit_id)
            .order_by(VisitMedia.uploaded_at.desc(), VisitMedia.id.desc())
        )
        return result.scalars().all()

    async def find_by_checksum_for_visit(
        self, visit_id: uuid.UUID, checksum: str
    ) -> VisitMedia | None:
        """
        Return an existing attachment on this visit with identical content.

        FT-036: used to reject a duplicate upload before any bytes are written,
        so identical "evidence" cannot be attached to the same visit twice.
        """
        result = await self.session.execute(
            select(VisitMedia).where(
                VisitMedia.visit_id == visit_id,
                VisitMedia.checksum_sha256 == checksum,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[VisitMedia]:
        """Every media row, used by the storage-integrity check."""
        result = await self.session.execute(select(VisitMedia).order_by(VisitMedia.uploaded_at))
        return result.scalars().all()

    async def list_orders_by_customer(self, customer_id: uuid.UUID) -> Sequence[VisitMedia]:
        """
        Every ORDER-type media row captured across ALL of this outlet's
        visits (not just one) - joins through Visit since VisitMedia has no
        customer_id of its own, by design (an order is always reached
        through the visit it was captured on, never a standalone entity).
        """
        result = await self.session.execute(
            select(VisitMedia)
            .join(Visit, Visit.id == VisitMedia.visit_id)
            .where(Visit.customer_id == customer_id, VisitMedia.media_type == MediaType.ORDER)
            .order_by(VisitMedia.uploaded_at.desc())
        )
        return result.scalars().all()

    async def list_orders_by_employee(self, employee_id: uuid.UUID, limit: int = 100) -> Sequence[VisitMedia]:
        """Every order this employee has captured, across all their visits (Employee Activity view)."""
        result = await self.session.execute(
            select(VisitMedia)
            .join(Visit, Visit.id == VisitMedia.visit_id)
            .where(Visit.employee_id == employee_id, VisitMedia.media_type == MediaType.ORDER)
            .order_by(VisitMedia.uploaded_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_orders_by_employee(self, employee_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(VisitMedia)
            .join(Visit, Visit.id == VisitMedia.visit_id)
            .where(Visit.employee_id == employee_id, VisitMedia.media_type == MediaType.ORDER)
        )
        return result.scalar_one()
