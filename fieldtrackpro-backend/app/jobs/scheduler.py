"""
Background job scheduler.

FT-021: `missed_visit_scheduler.py` documented itself as "runs every 15 minutes
via APScheduler (configured in main.py lifespan)" - but no such wiring existed
anywhere in the codebase. Overdue visits were therefore never transitioned to
MISSED, so the MISSED status was unreachable in normal operation.

Implemented to the locked design in `19_business_logic.md` section 4:
APScheduler, `cron` trigger at `minute="*/15"`, two-hour grace window.

A single module-level scheduler instance is created lazily and guarded, so
repeated calls to `start_scheduler()` (multiple workers importing the module,
or tests) cannot register duplicate jobs.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import AsyncSessionLocal
from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed

logger = logging.getLogger("fieldtrackpro")

#: Stable id so the job can never be registered twice.
MISSED_VISIT_JOB_ID = "missed_visit_sweep"

_scheduler: AsyncIOScheduler | None = None


async def _run_missed_visit_sweep() -> None:
    """Open a dedicated session and sweep overdue visits."""
    async with AsyncSessionLocal() as session:
        try:
            updated = await mark_overdue_visits_as_missed(session)
            if updated:
                logger.info("[scheduler] marked %s visit(s) as MISSED", updated)
        except Exception:
            # A failed sweep must never kill the scheduler thread; the next
            # run (15 minutes later) retries. The traceback is recorded.
            await session.rollback()
            logger.exception("[scheduler] missed-visit sweep failed")


def start_scheduler() -> AsyncIOScheduler | None:
    """
    Start the background scheduler if it is not already running.

    Returns the scheduler, or None when scheduling is disabled (tests set
    ``ENABLE_SCHEDULER=false`` so a background job cannot mutate fixture data
    mid-assertion).
    """
    global _scheduler

    from app.config import settings

    if not settings.enable_scheduler:
        logger.info("[scheduler] disabled by configuration; not starting")
        return None

    if _scheduler is not None and _scheduler.running:
        logger.debug("[scheduler] already running; not starting a second instance")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_missed_visit_sweep,
        trigger="cron",
        minute="*/15",
        id=MISSED_VISIT_JOB_ID,
        replace_existing=True,
        max_instances=1,          # never overlap two sweeps
        coalesce=True,            # a backlog collapses into one run
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info("[scheduler] started; missed-visit sweep runs every 15 minutes")
    return _scheduler


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly on application shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")
    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Expose the active scheduler for diagnostics and tests."""
    return _scheduler
