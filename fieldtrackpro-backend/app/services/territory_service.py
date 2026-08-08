"""
Territory service — refactored to use TerritoryRepository.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.territory import Territory
from app.repositories.territory_repo import TerritoryRepository
from app.schemas.territory import TerritoryCreate, TerritoryUpdate


async def create_territory(data: TerritoryCreate, session: AsyncSession) -> Territory:
    repo = TerritoryRepository(session)
    territory = Territory(name=data.name)
    await repo.add(territory)
    await repo.commit()
    return territory


async def get_territory(territory_id: uuid.UUID, session: AsyncSession) -> Territory:
    repo = TerritoryRepository(session)
    t = await repo.get_by_id(territory_id)
    if t is None:
        raise BaseAPIException(status_code=404, detail="Territory not found", error_code="TERRITORY_NOT_FOUND")
    return t


async def list_territories(session: AsyncSession) -> list[Territory]:
    repo = TerritoryRepository(session)
    return await repo.list_all()


async def update_territory(territory_id: uuid.UUID, data: TerritoryUpdate, session: AsyncSession) -> Territory:
    t = await get_territory(territory_id, session)
    if data.name is not None:
        t.name = data.name
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def delete_territory(territory_id: uuid.UUID, session: AsyncSession) -> None:
    t = await get_territory(territory_id, session)
    await session.delete(t)
    await session.commit()
