"""
Media repository: data access operations for VisitMedia entity.
Follows: Router → Service → Repository → DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit_media import VisitMedia
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
