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
            .order_by(VisitMedia.uploaded_at.desc())
        )
        return result.scalars().all()
