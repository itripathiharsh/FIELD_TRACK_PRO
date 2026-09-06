"""
Timezone and date boundary utilities.
Standardizes IST (UTC+05:30) date boundaries across the application.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_now() -> datetime:
    """Returns the current datetime in IST (UTC+05:30)."""
    return datetime.now(IST)


def get_ist_today_range(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """
    Returns (start_utc, end_utc) for the current day in IST (UTC+05:30).
    - start_utc: 00:00:00 IST of the day converted to UTC.
    - end_utc: 00:00:00 IST of the next day converted to UTC.

    All database queries comparing TIMESTAMP WITH TIME ZONE (scheduled_at, collected_at, created_at)
    against 'today in IST' should use:
        column >= start_utc AND column < end_utc
    """
    if now_utc is None:
        now_local = datetime.now(IST)
    else:
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        now_local = now_utc.astimezone(IST)

    start_local = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=IST)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc
