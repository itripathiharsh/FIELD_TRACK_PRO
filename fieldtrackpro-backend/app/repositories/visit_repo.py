"""
Visit repository.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit, VisitStatus
from app.repositories.base import BaseRepository


class VisitRepository(BaseRepository[Visit]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Visit, session)

    async def get_full(self, visit_id: uuid.UUID) -> Visit | None:
        result = await self.session.execute(
            select(Visit)
            .options(selectinload(Visit.employee), selectinload(Visit.customer))
            .where(Visit.id == visit_id)
        )
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        employee_id: uuid.UUID | None = None,
        status: VisitStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Visit]:
        stmt = (
            select(Visit)
            .options(selectinload(Visit.employee), selectinload(Visit.customer))
            .offset(skip)
            .limit(limit)
            .order_by(Visit.scheduled_at)
        )
        if employee_id:
            stmt = stmt.where(Visit.employee_id == employee_id)
        if status:
            stmt = stmt.where(Visit.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_employee_today_visits(
        self, employee_id: uuid.UUID, date_start: datetime, date_end: datetime
    ) -> list[Visit]:
        stmt = (
            select(Visit)
            .options(selectinload(Visit.customer))
            .where(Visit.employee_id == employee_id)
            .where(Visit.scheduled_at >= date_start)
            .where(Visit.scheduled_at < date_end)
            .order_by(Visit.scheduled_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue_pending(self, cutoff: datetime) -> list[Visit]:
        """Used by the missed-visit scheduler job."""
        stmt = (
            select(Visit)
            .where(Visit.status == VisitStatus.PENDING)
            .where(Visit.scheduled_at < cutoff)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
