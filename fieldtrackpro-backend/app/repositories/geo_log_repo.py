"""
GeoVerificationLog repository — insert-only, no updates.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo_verification_log import GeoVerificationLog
from app.repositories.base import BaseRepository


class GeoLogRepository(BaseRepository[GeoVerificationLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(GeoVerificationLog, session)

    async def list_by_visit(self, visit_id: uuid.UUID) -> list[GeoVerificationLog]:
        result = await self.session.execute(
            select(GeoVerificationLog)
            .where(GeoVerificationLog.visit_id == visit_id)
            .order_by(
                GeoVerificationLog.attempted_at.desc(),
                GeoVerificationLog.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def list_paginated(
        self,
        skip: int = 0,
        limit: int = 50,
        visit_id: uuid.UUID | None = None,
    ) -> tuple[list[tuple[GeoVerificationLog, uuid.UUID | None, str | None, uuid.UUID | None, str | None]], int]:
        from app.models.visit import Visit
        from app.models.customer import Customer
        from app.models.employee import Employee

        count_stmt = select(func.count(GeoVerificationLog.id))
        if visit_id is not None:
            count_stmt = count_stmt.where(GeoVerificationLog.visit_id == visit_id)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(
                GeoVerificationLog,
                Visit.customer_id,
                Customer.name.label("customer_name"),
                Visit.employee_id,
                Employee.full_name.label("employee_name"),
            )
            .join(Visit, Visit.id == GeoVerificationLog.visit_id)
            .outerjoin(Customer, Customer.id == Visit.customer_id)
            .outerjoin(Employee, Employee.id == Visit.employee_id)
            .order_by(GeoVerificationLog.attempted_at.desc(), GeoVerificationLog.id.desc())
            .offset(skip)
            .limit(limit)
        )
        if visit_id is not None:
            stmt = stmt.where(GeoVerificationLog.visit_id == visit_id)

        result = await self.session.execute(stmt)
        return list(result.all()), total_count

    async def count_failed_for_visit(self, visit_id: uuid.UUID) -> int:
        return await self.count(
            GeoVerificationLog.visit_id == visit_id,
            GeoVerificationLog.is_valid.is_(False),
        )

    async def count_failed_by_visit_ids(self, visit_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not visit_ids:
            return {}

        result = await self.session.execute(
            select(GeoVerificationLog.visit_id, func.count())
            .where(GeoVerificationLog.visit_id.in_(visit_ids), GeoVerificationLog.is_valid.is_(False))
            .group_by(GeoVerificationLog.visit_id)
        )
        return {vid: cnt for vid, cnt in result.all()}

    async def get_by_idempotency_key(self, visit_id: uuid.UUID, key: str) -> GeoVerificationLog | None:
        """Lookup any existing log for (visit_id, key) regardless of is_valid."""
        result = await self.session.execute(
            select(GeoVerificationLog).where(
                GeoVerificationLog.visit_id == visit_id,
                GeoVerificationLog.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def idempotency_key_exists(self, visit_id: uuid.UUID, key: str) -> bool:
        return (await self.get_by_idempotency_key(visit_id, key)) is not None
