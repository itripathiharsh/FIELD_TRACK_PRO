"""
Area repository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import Area
from app.repositories.base import BaseRepository


class AreaRepository(BaseRepository[Area]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Area, session)

    async def list_by_territory(self, territory_id: uuid.UUID | None = None) -> list[Area]:
        stmt = select(Area).order_by(Area.name)
        if territory_id:
            stmt = stmt.where(Area.territory_id == territory_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_name_ci(self, territory_id: uuid.UUID, name: str) -> Area | None:
        """Case-insensitive lookup within one Zone - used to reject an exact
        (modulo case) duplicate on create rather than silently allowing the
        same kind of "Kanpur nagar"/"Kanpur Nagar" duplication the client's
        own source data already shows."""
        result = await self.session.execute(
            select(Area).where(
                Area.territory_id == territory_id,
                func.lower(Area.name) == name.strip().lower(),
            )
        )
        return result.scalar_one_or_none()
