"""
Agent 2.2.0 - financial years, India time, and the per-FY state names.

* "Today" is always the INDIAN date (UTC+05:30). The client VM runs on UTC: with
  datetime.now().date() the agent still believed it was 17 Nov at 03:14 IST on 18 Nov (R10).
* A financial year runs 1 April .. 31 March.
* Exactly one FY - the one whose start is SYNC_FROM_DATE (FY 2026-27 today) - keeps the
  checkpoint / quarantine / retry / state-file names used by 2.0-2.1.x, so the production
  agent's existing state is used as it is. Every other FY gets disjoint names with an
  "@<label>" suffix, so a historical FY can never cap, advance or reset the live one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))
_LABEL = re.compile(r"^(\d{4})-(\d{2})$")


class FyConfigError(ValueError):
    """Financial-year configuration that the agent refuses to guess about."""


def ist_now() -> datetime:
    return datetime.now(IST)


def ist_today() -> date:
    return ist_now().date()


@dataclass(frozen=True)
class FinancialYear:
    label: str  # "2025-26"
    start: date  # 1 April
    end: date  # 31 March

    @property
    def previous(self) -> "FinancialYear":
        return fy_starting(self.start.year - 1)

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def clip(self, a: date, b: date) -> tuple:
        return max(a, self.start), min(b, self.end)


def fy_starting(year: int) -> FinancialYear:
    return FinancialYear(f"{year}-{str(year + 1)[-2:]}", date(year, 4, 1), date(year + 1, 3, 31))


def fy_containing(d: date) -> FinancialYear:
    return fy_starting(d.year if d.month >= 4 else d.year - 1)


def parse_fy(label: str) -> FinancialYear:
    m = _LABEL.match((label or "").strip())
    if not m:
        raise FyConfigError(f"financial year '{label}' is not in the form 2025-26")
    y = int(m.group(1))
    if m.group(2) != str(y + 1)[-2:]:
        raise FyConfigError(f"financial year '{label}' is not two consecutive years")
    return fy_starting(y)


def parse_fy_list(raw: str) -> List[FinancialYear]:
    out = [parse_fy(x) for x in (raw or "").split(",") if x.strip()]
    labels = [f.label for f in out]
    if len(set(labels)) != len(labels):
        raise FyConfigError(f"financial year listed twice in '{raw}'")
    return sorted(out, key=lambda f: f.start)


@dataclass(frozen=True)
class FyContext:
    """One FY's extraction scope and its own state names."""
    fy: FinancialYear
    legacy: bool  # True only for the FY of SYNC_FROM_DATE: 2.1.x names (production state preserved)
    historical: bool  # True for an FY that ended before today's FY

    @property
    def label(self) -> str:
        return self.fy.label

    @property
    def suffix(self) -> str:
        return "" if self.legacy else f"@{self.fy.label}"

    @property
    def cp_vouchers(self) -> str:
        return "vouchers_v2" + self.suffix

    @property
    def cp_manifest(self) -> str:
        return "manifest_v2" + self.suffix

    @property
    def cp_manifest_count(self) -> str:
        """last_alter_id of this row = GUID count of the last manifest the backend ACCEPTED (R7 floor)."""
        return "manifest_count_v2" + self.suffix

    @property
    def cp_balances(self) -> str:
        return "balances_v2" + self.suffix

    @property
    def cp_debtors(self) -> str:
        return "debtors_v2" + self.suffix

    @property
    def quarantine_entity(self) -> str:
        return "vouchers" + self.suffix

    @property
    def batch_type(self) -> str:
        return "vouchers" + self.suffix

    @property
    def state_file(self) -> str:
        return "initial_load_v2.json" if self.legacy else f"initial_load_fy{self.fy.label}.json"

    @property
    def validation_file(self) -> str:
        return f"validation_fy{self.fy.label}.json"


def legacy_context(sync_from_date: str) -> FyContext:
    fy = fy_containing(date.fromisoformat(sync_from_date))
    return FyContext(fy=fy, legacy=True, historical=False)


def build_contexts(financial_years: str, sync_from_date: str, history_upload: str,
                   today: Optional[date] = None) -> Dict[str, object]:
    """-> {"live": FyContext, "historical": [FyContext ...] (upload-enabled only, oldest first),
           "configured": [FinancialYear ...]}

    Refuses (FyConfigError) instead of guessing:
      * today's FY is not configured                (year-end procedure not done)
      * SYNC_FROM_DATE is not the start of today's FY (the opening-balance anchor would move)
      * a HISTORY_UPLOAD FY is not configured, or is not before today's FY
    """
    today = today or ist_today()
    configured = parse_fy_list(financial_years)
    live_fy = fy_containing(today)
    if live_fy.label not in {f.label for f in configured}:
        raise FyConfigError(f"today ({today}) is in FY {live_fy.label}, which is not in FINANCIAL_YEARS="
                            f"{financial_years}: the year-end procedure has not been done")
    sync_start = date.fromisoformat(sync_from_date)
    if sync_start != live_fy.start:
        raise FyConfigError(f"SYNC_FROM_DATE={sync_from_date} is not the start of today's FY {live_fy.label} "
                            f"({live_fy.start}); refusing to move the opening-balance anchor")
    live = FyContext(fy=live_fy, legacy=True, historical=False)
    hist: List[FyContext] = []
    for f in parse_fy_list(history_upload):
        if f.label not in {c.label for c in configured}:
            raise FyConfigError(f"HISTORY_UPLOAD lists FY {f.label}, which is not in FINANCIAL_YEARS")
        if f.start >= live_fy.start:
            raise FyConfigError(f"HISTORY_UPLOAD lists FY {f.label}, which is not before today's FY {live_fy.label}")
        hist.append(FyContext(fy=f, legacy=False, historical=True))
    return {"live": live, "historical": hist, "configured": configured}
