"""
GeoVerificationLog repository — insert-only, no updates.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo_verification_log import GeoVerificationLog
from app.repositories.base import BaseRepository


class GeoLogRepository(BaseRepository[GeoVerificationLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(GeoVerificationLog, session)

    async def list_by_visit(self, visit_id: uuid.UUID) -> list[GeoVerificationLog]:
        """
        Return every verification attempt for a visit, newest first.

        FT-005: ``visit_service.get_visit_geo_logs`` called this method but it
        was never implemented, so every read of the audit trail raised
        ``AttributeError`` and returned HTTP 500. The geo audit - the system's
        anti-fraud evidence - could not be viewed by anyone.

        Ordering is deterministic: ``attempted_at`` descending, with ``id`` as a
        tie-breaker so rows written inside the same transaction (identical
        ``now()``) always come back in a stable order.
        """
        result = await self.session.execute(
            select(GeoVerificationLog)
            .where(GeoVerificationLog.visit_id == visit_id)
            .order_by(
                GeoVerificationLog.attempted_at.desc(),
                GeoVerificationLog.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def count_failed_for_visit(self, visit_id: uuid.UUID) -> int:
        return await self.count(
            GeoVerificationLog.visit_id == visit_id,
            GeoVerificationLog.is_valid.is_(False),
        )

    async def idempotency_key_exists(self, visit_id: uuid.UUID, key: str) -> bool:
        result = await self.session.execute(
            select(GeoVerificationLog).where(
                GeoVerificationLog.visit_id == visit_id,
                GeoVerificationLog.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none() is not None
