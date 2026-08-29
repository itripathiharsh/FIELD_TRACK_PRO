"""
Missed-visit sweep.

Marks PENDING visits as MISSED once their ``scheduled_at`` is more than
``GRACE_PERIOD_HOURS`` in the past.

Scheduling lives in :mod:`app.jobs.scheduler`, which registers this coroutine on
an APScheduler cron trigger (every 15 minutes) from the FastAPI lifespan.

Product rationale, carried from `19_business_logic.md` section 4: the two-hour
grace window is deliberate. Field visits realistically run late, and flagging a
visit MISSED at the scheduled minute would generate constant false alarms and
erode trust in flagging generally.

APP-ATT-022: Atomic database update ensures concurrent employee check-in (moving
PENDING -> IN_PROGRESS) cannot be overwritten by the background sweep.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit, VisitStatus

logger = logging.getLogger("fieldtrackpro")

GRACE_PERIOD_HOURS = 2


async def mark_overdue_visits_as_missed(session: AsyncSession) -> int:
    """
    Query all PENDING visits older than GRACE_PERIOD_HOURS and atomically set them MISSED.

    Returns the number of visits updated.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)

    stmt = (
        update(Visit)
        .where(Visit.status == VisitStatus.PENDING)
        .where(Visit.scheduled_at < cutoff)
        .values(status=VisitStatus.MISSED)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    count = result.rowcount

    if count:
        await session.commit()
        logger.info(
            "[MissedVisitScheduler] Marked %s visit(s) as MISSED (cutoff=%s)",
            count,
            cutoff.isoformat(),
        )

    return count
