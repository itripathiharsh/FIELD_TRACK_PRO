"""
Customer repository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Customer, session)

    async def list_by_territory(
        self,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Customer]:
        stmt = select(Customer).offset(skip).limit(limit)
        if territory_id:
            stmt = stmt.where(Customer.territory_id == territory_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
