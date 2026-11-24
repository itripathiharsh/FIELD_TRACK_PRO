"""
Shared filter semantics for the Reports / Collections endpoints.

* Every user-facing date in FieldTrack is an Asia/Kolkata (IST) calendar date.
  A visit at 20:03 UTC on 30 Sep is 01:33 IST on 1 Oct and therefore belongs to
  1 Oct.  Timestamp columns are filtered with half-open IST day windows:
  ``[start 00:00 IST, end+1 00:00 IST)``.  India has no DST, so a fixed +05:30
  offset is exact (and avoids depending on the tzdata package at runtime).
* Snapshot based reports take either a calendar ``month`` (YYYY-MM) or an
  inclusive ``start_date``/``end_date`` range.  If both are given the date range
  wins.  See :class:`SnapshotWindow`.
* Snapshot figures are split into FLOWS (sales, collection - summed across the
  snapshots in the window) and STOCK (market outstanding, ageing buckets -
  the LATEST snapshot in the window per outlet+brand, never summed across dates).
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import Select

from app.exceptions.custom import BaseAPIException

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def ist_now() -> datetime:
    return datetime.now(IST)


def to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware (or assumed-UTC naive) datetime to IST."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def ist_date_of(dt: Optional[datetime]) -> Optional[date]:
    local = to_ist(dt)
    return local.date() if local else None


def ist_day_start(d: date) -> datetime:
    """00:00 IST of ``d`` as an aware datetime."""
    return datetime.combine(d, time.min, tzinfo=IST)


def ist_window(start: Optional[date], end: Optional[date]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Half-open [start, end_exclusive) window in aware datetimes (either bound may be None)."""
    lo = ist_day_start(start) if start else None
    hi = ist_day_start(end + timedelta(days=1)) if end else None
    return lo, hi


def validate_date_order(start: Optional[date], end: Optional[date]) -> None:
    if start and end and end < start:
        raise BaseAPIException(
            detail="end_date must be on or after start_date",
            status_code=422,
            error_code="INVALID_DATE_RANGE",
        )


def where_ist_range(stmt: Select, column: Any, start: Optional[date], end: Optional[date]) -> Select:
    """Constrain a timestamptz column to the IST calendar-day range (inclusive dates)."""
    validate_date_order(start, end)
    lo, hi = ist_window(start, end)
    if lo is not None:
        stmt = stmt.where(column >= lo)
    if hi is not None:
        stmt = stmt.where(column < hi)
    return stmt


def where_date_range(stmt: Select, column: Any, start: Optional[date], end: Optional[date]) -> Select:
    """Constrain a DATE column to the inclusive date range."""
    validate_date_order(start, end)
    if start is not None:
        stmt = stmt.where(column >= start)
    if end is not None:
        stmt = stmt.where(column <= end)
    return stmt


def parse_fy(month: Optional[str]) -> Optional[tuple[date, date]]:
    """'FY2025-26' -> (1 Apr 2025, 31 Mar 2026). Anything else -> None (not a financial-year period)."""
    m = re.fullmatch(r"FY(\d{4})-(\d{2})", (month or "").strip())
    if not m:
        return None
    y = int(m.group(1))
    if int(m.group(2)) != (y + 1) % 100:
        raise BaseAPIException(detail="financial year must be FYyyyy-yy with consecutive years (e.g. FY2025-26)",
                               status_code=422, error_code="INVALID_MONTH")
    return date(y, 4, 1), date(y + 1, 3, 31)


def parse_month(month: Optional[str]) -> Optional[tuple[date, date]]:
    """'YYYY-MM' -> (first_day, last_day); 'FYyyyy-yy' -> the whole financial year (1 Apr .. 31 Mar).
    Empty/'ALL' -> None. Malformed -> 422."""
    if not month or month == "ALL":
        return None
    fy = parse_fy(month)
    if fy:
        return fy
    try:
        y_s, m_s = month.split("-")
        y, m = int(y_s), int(m_s)
        if not (1 <= m <= 12 and 1900 <= y <= 9999):
            raise ValueError(month)
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    except Exception:
        raise BaseAPIException(
            detail="month must be in YYYY-MM format (or FYyyyy-yy for a financial year)",
            status_code=422,
            error_code="INVALID_MONTH",
        )


@dataclass(frozen=True)
class SnapshotWindow:
    """Resolved snapshot window. start/end are inclusive dates; None = open."""

    start: Optional[date] = None
    end: Optional[date] = None
    # DATES (explicit range), MONTH (calendar month) or ALL (every snapshot)
    source: str = "ALL"
    # True when a month was supplied but ignored because a date range won
    month_ignored: bool = False
    # Several selected periods (multi-select): snapshot_date must fall in one of these inclusive ranges.
    # start/end then span the whole selection. None = the single start..end window above.
    ranges: Optional[tuple] = None

    @property
    def is_all(self) -> bool:
        return self.start is None and self.end is None


def resolve_snapshot_window(
    month: Optional[str], start_date: Optional[date], end_date: Optional[date]
) -> SnapshotWindow:
    validate_date_order(start_date, end_date)
    ranges = month_ranges(month)  # validates every period even when dates win
    if start_date or end_date:
        return SnapshotWindow(start_date, end_date, "DATES", month_ignored=ranges is not None)
    if ranges and len(ranges) == 1:
        return SnapshotWindow(ranges[0][0], ranges[0][1], "MONTH")
    if ranges:
        return SnapshotWindow(min(r[0] for r in ranges), max(r[1] for r in ranges), "MONTHS", ranges=tuple(ranges))
    return SnapshotWindow()


def like_pattern(query: str) -> str:
    """Case-insensitive contains pattern with LIKE wildcards in the input escaped."""
    q = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


# ---------------------------------------------------------------------------
# Multi-value BI filters (Dashboard + Reports): brand, period/month and FOS may
# each carry several values. They arrive either as a repeated query parameter
# (?brand=Oppo&brand=Samsung) or comma separated (?brand=Oppo,Samsung); both
# are accepted. Values OR together inside one filter and AND across filters.
# ---------------------------------------------------------------------------
#: Brand filter value that selects records Tally gives no brand for (shown as "Unattributed").
UNATTRIBUTED_BRAND = "Unattributed"
_ALL_TOKENS = {"", "ALL", "LIVE"}


def as_list(value: Any) -> Optional[list[str]]:
    """None / 'ALL' / [] -> None (no filter); 'a,b' or ['a', 'b,c'] -> de-duplicated list in input order."""
    if value is None:
        return None
    raw = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[str] = []
    for item in raw:
        if item is None:
            continue
        for part in str(item).split(","):
            p = part.strip()
            if p and p.upper() not in _ALL_TOKENS and p not in out:
                out.append(p)
    return out or None


def as_uuid_list(value: Any) -> Optional[list]:
    """Like :func:`as_list` for ids; a malformed id is a 422 (never silently dropped)."""
    import uuid as _uuid
    items = as_list(value)
    if not items:
        return None
    try:
        return [v if isinstance(v, _uuid.UUID) else _uuid.UUID(str(v)) for v in items]
    except ValueError:
        raise BaseAPIException(detail="employee_id must be one or more valid ids", status_code=422,
                               error_code="INVALID_EMPLOYEE_ID")


def month_ranges(months: Any) -> Optional[list[tuple[date, date]]]:
    """Several periods ('2026-10', '2026-11', 'FY2025-26') -> their (start, end) ranges, sorted. None = no period."""
    items = as_list(months)
    if not items:
        return None
    return sorted({parse_month(m) for m in items})


def in_ranges(column: Any, ranges: list[tuple[date, date]]):
    """column BETWEEN start AND end for any of the ranges (inclusive calendar dates)."""
    return or_(*[column.between(s, e) for s, e in ranges])


def single_or_none(values: Optional[list]) -> Any:
    """The one value of a one-element filter, else None (for code paths that only take one value)."""
    return values[0] if values and len(values) == 1 else None


def where_ist_window(stmt: Select, column: Any, window: "SnapshotWindow") -> Select:
    """Timestamp column inside the window's IST day range(s): one range, or any of several selected periods."""
    if window.ranges:
        parts = []
        for s, e in window.ranges:
            lo, hi = ist_window(s, e)
            parts.append(and_(column >= lo, column < hi))
        return stmt.where(or_(*parts))
    if window.is_all:
        return stmt
    return where_ist_range(stmt, column, window.start, window.end)
