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

    async def list_visited_by_employee(
        self,
        employee_id: uuid.UUID,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Customer]:
        """
        P0-1: the outlets an EMPLOYEE is allowed to see - every customer they
        have at least one visit assigned to. `territory_id` further narrows
        this set; it can never widen it beyond the employee's own visits.
        """
        from app.models.visit import Visit

        stmt = (
            select(Customer)
            .join(Visit, Visit.customer_id == Customer.id)
            .where(Visit.employee_id == employee_id)
            .distinct()
            .order_by(Customer.name)
            .offset(skip)
            .limit(limit)
        )
        if territory_id:
            stmt = stmt.where(Customer.territory_id == territory_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
