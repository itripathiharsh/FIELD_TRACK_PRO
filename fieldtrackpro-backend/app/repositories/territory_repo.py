"""
Territory repository.
"""
from __future__ import annotations

import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.territory import Territory
from app.repositories.base import BaseRepository


class TerritoryRepository(BaseRepository[Territory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Territory, session)

    async def get_by_name(
        self, name: str, exclude_id: uuid.UUID | None = None
    ) -> Territory | None:
        """Find a territory by name case-insensitively, optionally excluding a specific ID."""
        clean_name = name.strip().lower()
        stmt = select(Territory).where(func.lower(Territory.name) == clean_name)
        if exclude_id is not None:
            stmt = stmt.where(Territory.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, status: str | None = None) -> list[Territory]:
        stmt = select(Territory)
        if status:
            stmt = stmt.where(Territory.status == status)
        stmt = stmt.order_by(Territory.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
