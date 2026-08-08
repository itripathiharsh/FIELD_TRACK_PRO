"""
Territory repository.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.territory import Territory
from app.repositories.base import BaseRepository


class TerritoryRepository(BaseRepository[Territory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Territory, session)

    async def list_all(self) -> list[Territory]:
        result = await self.session.execute(
            select(Territory).order_by(Territory.name)
        )
        return list(result.scalars().all())
