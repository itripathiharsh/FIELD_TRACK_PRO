"""
Customer repository with enhanced support for employee directory search and assignments.
"""
from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.visit import Visit
from app.repositories.base import BaseRepository


def _escape_like_pattern(search: str) -> str:
    escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _build_customer_search_filter(search: str):
    """
    Tokenizes search query by whitespace and constructs an AND filter across all tokens,
    matching each token against name, outlet_code, address, contact_person, or contact_number.
    """
    tokens = [t.strip() for t in search.strip().split() if t.strip()]
    if not tokens:
        return None
    token_clauses = []
    for token in tokens:
        pattern = _escape_like_pattern(token)
        token_clauses.append(
            or_(
                Customer.name.ilike(pattern, escape="\\"),
                Customer.outlet_code.ilike(pattern, escape="\\"),
                Customer.address.ilike(pattern, escape="\\"),
                Customer.contact_person.ilike(pattern, escape="\\"),
                Customer.contact_number.ilike(pattern, escape="\\"),
            )
        )
    return and_(*token_clauses)


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
            search_clause = _build_customer_search_filter(search)
            if search_clause is not None:
                filters.append(search_clause)

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

    async def list_accessible_by_employee(
        self,
        employee_id: uuid.UUID,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        area_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Customer], int]:
        """
        Enables employee counter list and off-beat directory search.
        If a search term is provided, searches the counter directory matching the query.
        Otherwise, returns outlets assigned to the employee or visited by the employee.
        """
        filters = []
        if territory_id:
            filters.append(Customer.territory_id == territory_id)
        if area_id:
            filters.append(Customer.area_id == area_id)

        if search and search.strip():
            search_clause = _build_customer_search_filter(search)
            if search_clause is not None:
                filters.append(search_clause)
            # Off-beat search across the full customer directory
            count_stmt = select(func.count(Customer.id))
            if filters:
                count_stmt = count_stmt.where(*filters)
            total_count = (await self.session.execute(count_stmt)).scalar_one()

            stmt = select(Customer)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(Customer.name.asc()).offset(skip).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all()), total_count
        else:
            # Beat browsing: assigned in EmployeeCustomerAssignment OR visited in Visit
            assigned_or_visited = or_(
                Customer.id.in_(
                    select(EmployeeCustomerAssignment.customer_id).where(
                        EmployeeCustomerAssignment.employee_id == employee_id
                    )
                ),
                Customer.id.in_(
                    select(Visit.customer_id).where(
                        Visit.employee_id == employee_id
                    )
                )
            )
            filters.append(assigned_or_visited)

            count_stmt = select(func.count(Customer.id)).where(*filters)
            total_count = (await self.session.execute(count_stmt)).scalar_one()

            stmt = select(Customer).where(*filters).order_by(Customer.name.asc()).offset(skip).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all()), total_count

    # Backwards compatibility alias
    list_visited_by_employee = list_accessible_by_employee

    async def get_by_outlet_code(
        self, outlet_code: str, exclude_id: uuid.UUID | None = None
    ) -> Customer | None:
        clean_code = outlet_code.strip().upper()
        stmt = select(Customer).where(func.upper(Customer.outlet_code) == clean_code)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_map_locations(
        self,
        territory_id: uuid.UUID | None = None,
        area_id: uuid.UUID | None = None,
    ) -> list[Customer]:
        """
        Returns active customer records that possess non-null geographic locations
        for lightweight map rendering (WEB-CUST-002).
        """
        filters = [Customer.location.is_not(None)]
        if territory_id is not None:
            filters.append(Customer.territory_id == territory_id)
        if area_id is not None:
            filters.append(Customer.area_id == area_id)

        stmt = select(Customer).where(*filters).order_by(Customer.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

