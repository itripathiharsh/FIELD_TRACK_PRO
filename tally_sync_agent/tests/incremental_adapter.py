"""Test helper (2.2.1): in-memory sources written for 2.2.0 answered one FY-wide `changed_vouchers(m, min_alter)`.
The 2.2.1 engine asks month-scoped `changed_headers(a, b, min_alter)` and then `changed_vouchers_on(m, day, min_alter)`.
This mixin derives both from the source's own changed_vouchers answer (one answer per cycle), so the test data
stays the same. A rejected record without a date is placed on the earliest date of the cycle."""
from __future__ import annotations

from datetime import date


class IncrementalFromChanged:
    _incr = None  # (min_alter, cycle_start_ymd, good, bad)

    def _ymd(self, r) -> str:
        if "guid" in r and r.get("date"):
            return r["date"].replace("-", "")
        raw = (r.get("raw") or {}).get("date") or ""
        if raw:
            return raw.replace("-", "")[:8]
        good = self._incr[2]
        return min([v["date"].replace("-", "") for v in good] or [self._incr[1]])

    def changed_headers(self, a: date, b: date, min_alter: int):
        self.__dict__.setdefault("incr_calls", []).append(("headers", a, b, min_alter))
        lo, hi = a.strftime("%Y%m%d"), b.strftime("%Y%m%d")
        if self._incr is None or self._incr[0] != min_alter or lo <= self._incr[1]:  # a new cycle starts
            good, bad = self.changed_vouchers(getattr(self, "m", None), min_alter)
            self._incr = (min_alter, lo, good, bad)
        _, _, good, bad = self._incr
        out = [(v["guid"], self._ymd(v), v.get("alter_id") or 0) for v in good if lo <= self._ymd(v) <= hi]
        out += [(r["source_reference"], self._ymd(r), r.get("alter_id") or 0) for r in bad
                if r.get("source_reference") and lo <= self._ymd(r) <= hi]
        return out

    def changed_vouchers_on(self, m, day: date, min_alter: int):
        self.__dict__.setdefault("incr_calls", []).append(("day", day, min_alter))
        ymd = day.strftime("%Y%m%d")
        _, _, good, bad = self._incr
        return [v for v in good if self._ymd(v) == ymd], [r for r in bad if self._ymd(r) == ymd]
