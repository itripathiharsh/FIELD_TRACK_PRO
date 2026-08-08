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
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import VisitStatus
from app.repositories.visit_repo import VisitRepository
from app.services.visit_state_machine import assert_valid_transition

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
        # Route through the state machine rather than assigning directly, so
        # the sweep cannot perform a transition the domain forbids. Only
        # PENDING visits are selected, and PENDING -> MISSED is valid, but the
        # guard keeps this job honest if the query is ever widened.
        assert_valid_transition(visit.status, VisitStatus.MISSED)
        visit.status = VisitStatus.MISSED
        session.add(visit)
        count += 1

    if count:
        await session.commit()
        logger.info(
            "[MissedVisitScheduler] Marked %s visit(s) as MISSED (cutoff=%s)",
            count,
            cutoff.isoformat(),
        )

    return count
