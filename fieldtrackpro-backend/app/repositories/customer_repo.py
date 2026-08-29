"""
Customer repository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.base import BaseRepository


def _escape_like_pattern(search: str) -> str:
    escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Customer, session)

    async def list_by_territory(
        self,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        area_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Customer], int]:
        filters = []
        if territory_id:
            filters.append(Customer.territory_id == territory_id)
        if area_id:
            filters.append(Customer.area_id == area_id)
        if search and search.strip():
            pattern = _escape_like_pattern(search)
            filters.append(
                or_(
                    Customer.name.ilike(pattern, escape="\\"),
                    Customer.outlet_code.ilike(pattern, escape="\\"),
                    Customer.address.ilike(pattern, escape="\\"),
                    Customer.contact_person.ilike(pattern, escape="\\"),
                    Customer.contact_number.ilike(pattern, escape="\\"),
                )
            )

        count_stmt = select(func.count(Customer.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Customer)
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.order_by(Customer.created_at.desc().nullslast(), Customer.name.asc()).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def list_visited_by_employee(
        self,
        employee_id: uuid.UUID,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        area_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Customer], int]:
        """
        P0-1: the outlets an EMPLOYEE is allowed to see - every customer they
        have at least one visit assigned to. `territory_id`/`area_id` further
        narrow this set; neither can ever widen it beyond the employee's own
        visits.
        """
        from app.models.visit import Visit

        filters = [
            Visit.employee_id == employee_id,
            Visit.customer_id == Customer.id,
        ]
        if territory_id:
            filters.append(Customer.territory_id == territory_id)
        if area_id:
            filters.append(Customer.area_id == area_id)
        if search and search.strip():
            pattern = _escape_like_pattern(search)
            filters.append(
                or_(
                    Customer.name.ilike(pattern, escape="\\"),
                    Customer.outlet_code.ilike(pattern, escape="\\"),
                    Customer.address.ilike(pattern, escape="\\"),
                    Customer.contact_person.ilike(pattern, escape="\\"),
                    Customer.contact_number.ilike(pattern, escape="\\"),
                )
            )

        count_stmt = select(func.count(func.distinct(Customer.id))).join(Visit, Visit.customer_id == Customer.id)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(Customer)
            .join(Visit, Visit.customer_id == Customer.id)
            .where(*filters)
            .distinct()
            .order_by(Customer.created_at.desc().nullslast(), Customer.name.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def get_by_outlet_code(
        self, outlet_code: str, exclude_id: uuid.UUID | None = None
    ) -> Customer | None:
        """Find a customer by outlet_code/DMS code case-insensitively, optionally excluding a specific ID."""
        clean_code = outlet_code.strip().upper()
        stmt = select(Customer).where(func.upper(Customer.outlet_code) == clean_code)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_map_locations(
        self, territory_id: uuid.UUID | None = None, area_id: uuid.UUID | None = None
    ) -> list[Customer]:
        """Fetch customer locations for map rendering without heavy join overhead."""
        stmt = select(Customer).where(Customer.location.isnot(None))
        if territory_id:
            stmt = stmt.where(Customer.territory_id == territory_id)
        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        stmt = stmt.order_by(Customer.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
