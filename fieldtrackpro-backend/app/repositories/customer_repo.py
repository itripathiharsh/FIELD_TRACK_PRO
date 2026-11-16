"""
Customer repository with enhanced support for employee directory search and assignments.
"""
from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.employee_area_assignment import EmployeeAreaAssignment
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.core.datetime_utils import get_ist_today_range
from app.models.visit import Visit, VisitStatus, VisitType
from app.repositories.base import BaseRepository


def _escape_like_pattern(search: str) -> str:
    escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


AD_HOC_MIN_SEARCH_LEN = 3
AD_HOC_MAX_RESULTS = 50


def _build_customer_search_filter(search: str, scope_clause=None):
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
        contact_match = or_(
            Customer.contact_person.ilike(pattern, escape="\\"),
            Customer.contact_number.ilike(pattern, escape="\\"),
        )
        if scope_clause is not None:
            # Contact fields are only searchable for outlets the caller may see.
            contact_match = and_(scope_clause, contact_match)
        token_clauses.append(
            or_(
                Customer.name.ilike(pattern, escape="\\"),
                Customer.outlet_code.ilike(pattern, escape="\\"),
                Customer.address.ilike(pattern, escape="\\"),
                contact_match,
            )
        )
    return and_(*token_clauses)


# Outlet lists exclude customers whose Tally ledger is not a debtor (bank, supplier,
# expense ledgers the old sync imported). They are kept, never deleted, and still
# open by id; NULL (never seen in a Tally ledger snapshot / created in FieldTrack) shows.
OUTLET_CLAUSE = Customer.tally_is_debtor.is_not(False)


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
        filters = [OUTLET_CLAUSE]
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

    @staticmethod
    def employee_scope_clause(employee_id: uuid.UUID, territory_id: uuid.UUID | None = None):
        """
        The set of outlets an EMPLOYEE is entitled to see:
          * directly assigned (employee_customer_assignments),
          * on any PLANNED visit (past or future) assigned to them,
          * on an AD_HOC visit ONLY while it is PENDING/IN_PROGRESS and was created today
            (IST) - enough to do the visit/collection that day, but an ad-hoc visit must
            never leave lasting read access to an arbitrary outlet (it is a self-service
            action; the outlet id can come from the redacted directory search). Mirrors
            visit_repo.visit_in_scope_clause, where ad-hoc visits never legitimise an outlet.
          * inside an Area they are assigned to cover (employee_area_assignments),
          * inside their own home territory (employees.territory_id).
        """
        today_start, today_end = get_ist_today_range()
        own_visit = or_(
            Visit.visit_type != VisitType.AD_HOC,
            and_(
                Visit.status.in_((VisitStatus.PENDING, VisitStatus.IN_PROGRESS)),
                Visit.created_at >= today_start,
                Visit.created_at < today_end,
            ),
        )
        clauses = [
            Customer.id.in_(
                select(EmployeeCustomerAssignment.customer_id).where(
                    EmployeeCustomerAssignment.employee_id == employee_id
                )
            ),
            Customer.id.in_(select(Visit.customer_id).where(Visit.employee_id == employee_id, own_visit)),
            Customer.area_id.in_(
                select(EmployeeAreaAssignment.area_id).where(
                    EmployeeAreaAssignment.employee_id == employee_id
                )
            ),
        ]
        if territory_id is not None:
            clauses.append(Customer.territory_id == territory_id)
        return or_(*clauses)

    async def list_accessible_by_employee(
        self,
        employee_id: uuid.UUID,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        area_id: uuid.UUID | None = None,
        search: str | None = None,
        home_territory_id: uuid.UUID | None = None,
    ) -> tuple[list[Customer], int]:
        """
        Employee outlet list. Without a search term: only in-scope outlets.

        With a search term of at least AD_HOC_MIN_SEARCH_LEN characters the
        lookup extends to the whole directory (needed to pick an outlet for an
        off-beat / ad-hoc visit) but matches ONLY name / outlet code / address
        outside scope; phone and contact-person matching is limited to in-scope
        outlets so the search cannot be used to enumerate contact data. The
        caller redacts contact/financial fields for out-of-scope rows.
        """
        scope = self.employee_scope_clause(employee_id, home_territory_id)
        filters = [OUTLET_CLAUSE]
        if territory_id:
            filters.append(Customer.territory_id == territory_id)
        if area_id:
            filters.append(Customer.area_id == area_id)

        term = (search or "").strip()
        if term:
            directory_wide = len(term) >= AD_HOC_MIN_SEARCH_LEN
            clause = _build_customer_search_filter(term, scope_clause=scope)
            if clause is not None:
                filters.append(clause)
            if not directory_wide:
                filters.append(scope)
            limit = min(limit, AD_HOC_MAX_RESULTS)
        else:
            filters.append(scope)

        count_stmt = select(func.count(Customer.id)).where(*filters)
        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            select(Customer).where(*filters).order_by(Customer.name.asc()).offset(skip).limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def in_scope_ids(
        self,
        employee_id: uuid.UUID,
        customer_ids: list[uuid.UUID],
        home_territory_id: uuid.UUID | None = None,
    ) -> set[uuid.UUID]:
        if not customer_ids:
            return set()
        scope = self.employee_scope_clause(employee_id, home_territory_id)
        res = await self.session.execute(
            select(Customer.id).where(Customer.id.in_(customer_ids), scope)
        )
        return set(res.scalars().all())

    async def list_map_locations_for_employee(
        self,
        employee_id: uuid.UUID,
        territory_id: uuid.UUID | None = None,
        area_id: uuid.UUID | None = None,
        home_territory_id: uuid.UUID | None = None,
    ) -> list[Customer]:
        filters = [Customer.location.is_not(None), OUTLET_CLAUSE, self.employee_scope_clause(employee_id, home_territory_id)]
        if territory_id is not None:
            filters.append(Customer.territory_id == territory_id)
        if area_id is not None:
            filters.append(Customer.area_id == area_id)
        res = await self.session.execute(
            select(Customer).where(*filters).order_by(Customer.name.asc())
        )
        return list(res.scalars().all())

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
        filters = [Customer.location.is_not(None), OUTLET_CLAUSE]
        if territory_id is not None:
            filters.append(Customer.territory_id == territory_id)
        if area_id is not None:
            filters.append(Customer.area_id == area_id)

        stmt = select(Customer).where(*filters).order_by(Customer.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

