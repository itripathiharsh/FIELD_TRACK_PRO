"""
Missed-visit scheduler job.

Marks PENDING visits as MISSED if their scheduled_at time is
more than 2 hours in the past.

Runs every 15 minutes via APScheduler (configured in main.py lifespan).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import VisitStatus
from app.repositories.visit_repo import VisitRepository

logger = logging.getLogger("fieldtrackpro")

GRACE_PERIOD_HOURS = 2


async def mark_overdue_visits_as_missed(session: AsyncSession) -> int:
    """
    Query all PENDING visits older than GRACE_PERIOD_HOURS and set them MISSED.

    Returns the number of visits updated.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)
    repo = VisitRepository(session)
    overdue = await repo.get_overdue_pending(cutoff)

    count = 0
    for visit in overdue:
        visit.status = VisitStatus.MISSED
        session.add(visit)
        count += 1

    if count:
        await session.commit()
        logger.info(f"[MissedVisitScheduler] Marked {count} visit(s) as MISSED (cutoff={cutoff.isoformat()})")

    return count
