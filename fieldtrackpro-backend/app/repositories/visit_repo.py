"""
Visit repository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, func, or_, cast, String, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import Area
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.form_template import FormTemplate
from app.models.territory import Territory
from app.models.visit import Visit, VisitStatus
from app.repositories.base import BaseRepository


class VisitRepository(BaseRepository[Visit]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Visit, session)

    async def get_full(self, visit_id: uuid.UUID) -> Visit | None:
        result = await self.session.execute(
            select(Visit)
            .options(
                selectinload(Visit.employee), 
                selectinload(Visit.customer).selectinload(Customer.territory),
                selectinload(Visit.customer).selectinload(Customer.area),
                selectinload(Visit.required_form),
            )
            .where(Visit.id == visit_id)
        )
        return result.scalar_one_or_none()

    async def list_filtered_paginated(
        self,
        employee_id: uuid.UUID | None = None,
        status: list[VisitStatus] | VisitStatus | None = None,
        territory_id: uuid.UUID | None = None,
        area_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        search: str | None = None,
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Visit], int]:
        """
        Scalable backend querying with full search, combinable filters,
        and deterministic most-recent-first sorting (scheduled_at DESC, id DESC).
        """
        stmt = (
            select(Visit)
            .outerjoin(Customer, Customer.id == Visit.customer_id)
            .outerjoin(Employee, Employee.id == Visit.employee_id)
            .options(
                selectinload(Visit.employee),
                selectinload(Visit.customer).selectinload(Customer.territory),
                selectinload(Visit.customer).selectinload(Customer.area),
                selectinload(Visit.required_form),
            )
        )
        count_stmt = (
            select(func.count(Visit.id))
            .outerjoin(Customer, Customer.id == Visit.customer_id)
            .outerjoin(Employee, Employee.id == Visit.employee_id)
        )

        if employee_id:
            stmt = stmt.where(Visit.employee_id == employee_id)
            count_stmt = count_stmt.where(Visit.employee_id == employee_id)

        if status:
            if isinstance(status, (list, tuple, set)):
                if len(status) > 0:
                    stmt = stmt.where(Visit.status.in_(status))
                    count_stmt = count_stmt.where(Visit.status.in_(status))
            else:
                stmt = stmt.where(Visit.status == status)
                count_stmt = count_stmt.where(Visit.status == status)

        if territory_id:
            stmt = stmt.where(Customer.territory_id == territory_id)
            count_stmt = count_stmt.where(Customer.territory_id == territory_id)

        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
            count_stmt = count_stmt.where(Customer.area_id == area_id)

        if from_date:
            stmt = stmt.where(Visit.scheduled_at >= from_date)
            count_stmt = count_stmt.where(Visit.scheduled_at >= from_date)

        if to_date:
            stmt = stmt.where(Visit.scheduled_at <= to_date)
            count_stmt = count_stmt.where(Visit.scheduled_at <= to_date)

        if search and search.strip():
            term = f"%{search.strip()}%"
            cond = or_(
                Customer.name.ilike(term),
                Customer.outlet_code.ilike(term),
                Employee.full_name.ilike(term),
                cast(Visit.id, String).ilike(term),
                cast(Customer.id, String).ilike(term),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total_count = (await self.session.execute(count_stmt)).scalar_one()

        if sort_order.lower() == "asc":
            stmt = stmt.order_by(Visit.scheduled_at.asc(), Visit.id.asc())
        else:
            stmt = stmt.order_by(Visit.scheduled_at.desc(), Visit.id.desc())

        stmt = stmt.offset(skip).limit(limit)
        items = (await self.session.execute(stmt)).scalars().all()
        return list(items), total_count

    async def list_filtered(
        self,
        employee_id: uuid.UUID | None = None,
        status: VisitStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Visit]:
        items, _ = await self.list_filtered_paginated(
            employee_id=employee_id,
            status=status,
            skip=skip,
            limit=limit,
        )
        return items

    async def get_employee_today_visits(
        self, employee_id: uuid.UUID, date_start: datetime, date_end: datetime
    ) -> list[Visit]:
        stmt = (
            select(Visit)
            .options(
                selectinload(Visit.employee),
                selectinload(Visit.customer).selectinload(Customer.territory),
                selectinload(Visit.customer).selectinload(Customer.area)
            )
            .where(Visit.employee_id == employee_id)
            .where(Visit.scheduled_at >= date_start)
            .where(Visit.scheduled_at < date_end)
            .order_by(Visit.scheduled_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_most_recent_checked_in(self, customer_id: uuid.UUID) -> Visit | None:
        """
        The most recent visit that actually happened (has a check_in_at) for
        this outlet - used for the outlet detail's/collections overview's
        "Last Visit" figure. Deliberately not just the most recently
        *scheduled* visit, which could be a future, not-yet-happened one.
        """
        stmt = (
            select(Visit)
            .options(selectinload(Visit.employee))
            .where(Visit.customer_id == customer_id, Visit.check_in_at.is_not(None))
            .order_by(Visit.check_in_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_overdue_pending(self, cutoff: datetime) -> list[Visit]:
        """Used by the missed-visit scheduler job."""
        stmt = (
            select(Visit)
            .where(Visit.status == VisitStatus.PENDING)
            .where(Visit.scheduled_at < cutoff)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Non-terminal statuses that participate in the conflict check. ---
    # Terminal visits (COMPLETED, MISSED) are finished and must NOT block
    # future scheduling for the same employee at the same time slot.
    _ACTIVE_STATUSES: tuple[VisitStatus, ...] = (
        VisitStatus.PENDING,
        VisitStatus.IN_PROGRESS,
        VisitStatus.FLAGGED,
    )

    async def find_conflicting_visit(
        self,
        employee_id: uuid.UUID,
        scheduled_at: datetime,
        window_minutes: int = 60,
        exclude_visit_id: uuid.UUID | None = None,
    ) -> Visit | None:
        """
        Return the first non-terminal visit for *employee_id* whose
        ``scheduled_at`` falls within ±*window_minutes* of the requested
        time, or ``None`` when no conflict exists.

        Only PENDING, IN_PROGRESS, and FLAGGED visits count.
        COMPLETED and MISSED are deliberately excluded so that rescheduling
        after a missed/completed visit for the same slot is allowed.

        *exclude_visit_id* lets rescheduling flows avoid a self-collision
        (the visit being updated should not conflict with itself).

        The query hits the existing ``ix_visits_employee_id`` index and
        filters *status* through the existing ``ix_visits_status`` index.
        The new partial unique index (h1i2j3k4l5m6 migration) gives O(1)
        exact-duplicate detection at the DB level.
        """
        window = timedelta(minutes=window_minutes)
        lower = scheduled_at - window
        upper = scheduled_at + window

        stmt = (
            select(Visit)
            .options(
                selectinload(Visit.employee),
                selectinload(Visit.customer),
            )
            .where(
                and_(
                    Visit.employee_id == employee_id,
                    Visit.status.in_(self._ACTIVE_STATUSES),
                    Visit.scheduled_at >= lower,
                    Visit.scheduled_at <= upper,
                )
            )
            .order_by(Visit.scheduled_at.asc())
            .limit(1)
        )

        if exclude_visit_id is not None:
            stmt = stmt.where(Visit.id != exclude_visit_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

