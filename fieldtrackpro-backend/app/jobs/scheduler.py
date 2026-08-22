"""
Background job scheduler.

Handles:
1. Overdue visit sweep (every 15 minutes) -> transitions to MISSED.
2. Expired security records cleanup (daily at 03:00 UTC) -> purges expired tokens & old login attempts.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import AsyncSessionLocal
from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed
from app.services.security_cleanup_service import security_cleanup_service

logger = logging.getLogger("fieldtrackpro")

#: Stable ids so jobs can never be registered twice.
MISSED_VISIT_JOB_ID = "missed_visit_sweep"
SECURITY_CLEANUP_JOB_ID = "security_records_cleanup"

_scheduler: AsyncIOScheduler | None = None


async def _run_missed_visit_sweep() -> None:
    """Open a dedicated session and sweep overdue visits."""
    async with AsyncSessionLocal() as session:
        try:
            updated = await mark_overdue_visits_as_missed(session)
            if updated:
                logger.info("[scheduler] marked %s visit(s) as MISSED", updated)
        except Exception:
            await session.rollback()
            logger.exception("[scheduler] missed-visit sweep failed")


async def _run_security_cleanup_sweep() -> None:
    """Open a dedicated session and purge expired security records."""
    async with AsyncSessionLocal() as session:
        try:
            counts = await security_cleanup_service.cleanup_expired_records(session)
            logger.info(f"[scheduler] security cleanup sweep finished: {counts}")
        except Exception:
            await session.rollback()
            logger.exception("[scheduler] security cleanup sweep failed")


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

    # 1. Overdue visit sweep - every 15 minutes
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

    # 2. Expired security records cleanup - daily at 03:00 UTC
    _scheduler.add_job(
        _run_security_cleanup_sweep,
        trigger="cron",
        hour=3,
        minute=0,
        id=SECURITY_CLEANUP_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )

    _scheduler.start()
    logger.info("[scheduler] started; missed-visit sweep (*/15 min) and security cleanup (daily 03:00 UTC) active")
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
