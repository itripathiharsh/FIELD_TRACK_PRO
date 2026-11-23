"""
Agent 2.x sync engine for ONE financial year (read-only towards Tally; no write-back).

2.2.0: an engine is bound to an FyContext (config/fiscal.py). The live FY (today's, the FY of
SYNC_FROM_DATE) keeps the 2.0-2.1.x state names, so the production agent's checkpoints are used
as they are; a historical FY has disjoint "@<fy>" names and never touches the live state.
engine/multi_fy.py runs the live FY every cycle and, only when explicitly enabled, historical FYs.

Live FY, every cycle (SYNC_INTERVAL_SECONDS):
  1. retry queue; 2. company (by GUID) + heartbeat; 3. masters (groups, all ledgers, voucher types,
  changed debtors by AlterID, debtor balances in the FY scope); 4. changed vouchers (AlterID >
  checkpoint, FY scope) -> /sync/vouchers.
Hourly: ledger snapshot with balances -> /sync/ledgers, ONLY after the per-ledger sums equal Tally's
  Group Summary (closing) and the previous FY's Group Summary (opening); Bills Receivable as on
  today (IST) -> /sync/bills.
Daily: voucher GUID manifest of the FY window -> /sync/manifest (retires vouchers deleted in Tally),
  never empty, never below half of the last accepted manifest.
First run: ledger + bills snapshot, a resumable header pre-scan (manifest + AlterID high-water mark
  M0), every day's vouchers one day per request (resumable), the manifest, the checkpoint = M0.
  An empty window or a rejected manifest never completes the load and writes no checkpoint.
Historical FY (only when HISTORY_UPLOAD lists it and the backend reports history_safe): the same
  first load, HISTORY_DAYS_PER_CYCLE days per cycle, no ledger / bills snapshot upload (they would
  move the live opening anchor); then an AlterID incremental and a weekly manifest in its own window.

Checkpoints only advance after the backend accepted (or the durable retry queue holds) the data; a
voucher the backend rejects stays quarantined (per FY) and caps that FY's checkpoint.

2.2.1 (release_v2/agent_2.2.1/RELEASE_PLAN_2.2.1.md):
  * every Tally request goes through core/tally_guard.py: circuit breaker with cool-down, machine-wide
    request lock, duty-cycle pacing, per-request telemetry (B2, B5, B8, items 10-12);
  * voucher requests are scoped to the day / month they ask for and use the lean fetch (B1, B11);
  * the incremental reads month-scoped headers (AlterID > checkpoint), then the changed vouchers one
    day-scoped request per date (B4, B10). It needs a positive, integer checkpoint: zero / missing /
    invalid -> CHECKPOINT_ZERO / CHECKPOINT_INVALID, nothing is requested (item 1). A first load runs
    only after `approve-first-load <fy>` (explicit, logged), and still never asks Tally for a whole FY;
  * balances (debtors, creditors) are read to the WINDOW END - the same date as Group Summary and
    the bills as-of date (A5, item 18);
  * Bills Receivable uses the typed report form and a bills answer containing a bill dated after the
    as-of date is rejected (A3, items 13-16); bills sanity checks (C12, item 23).
"""
from __future__ import annotations

import json
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tally_sync_agent.config.fiscal import FyContext, ist_today, legacy_context
from tally_sync_agent.config.settings import AGENT_VERSION, DATA_DIR, settings
from tally_sync_agent.core.backend_client import BackendAuthError, BackendClient, BackendServerError
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.deferred_store import DeferredStore
from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.core.tally_guard import TallyBusy, TallyCoolingDown, TallyGuard, guard_for
from tally_sync_agent.engine.sync_engine import _safe_checkpoint_alter_id
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X

# Live-FY state names (unchanged since 2.0; the FY of SYNC_FROM_DATE keeps them).
CP_VOUCHERS = "vouchers_v2"
CP_DEBTORS = "debtors_v2"
CP_BALANCES = "balances_v2"
CP_MANIFEST = "manifest_v2"
Q_VOUCHERS = "vouchers"

TOLERANCE = Decimal("0.01")
# Voucher parents that never post to ledgers (same list as the backend's NON_ACCOUNTING_PARENTS).
NON_ACCOUNTING_PARENTS = {p.lower() for p in (
    "Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Rejections In", "Rejections Out",
    "Stock Journal", "Physical Stock", "Material In", "Material Out", "Job Work In Order", "Job Work Out Order",
    "Memorandum", "Reversing Journal", "Attendance")}


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def month_chunks(start: date, end: date) -> List[tuple]:
    """Inclusive (first, last) date pairs per calendar month covering start..end."""
    out = []
    a = start
    while a <= end:
        nxt = date(a.year + (a.month == 12), a.month % 12 + 1, 1)
        b = min(nxt - timedelta(days=1), end)
        out.append((a, b))
        a = nxt
    return out


def posts_to_ledgers(v: Dict[str, Any], voucher_parent: Optional[str] = None) -> bool:
    """A voucher that changes ledger balances: not cancelled, not optional, an accounting type."""
    if v.get("is_cancelled") or v.get("is_optional"):
        return False
    parent = (voucher_parent or v.get("voucher_parent") or v.get("voucher_type") or "").lower()
    return parent not in NON_ACCOUNTING_PARENTS


class ManifestRangeUntrusted(Exception):
    """A month's range answer failed validation; that month is re-read one day per request."""


class InitialLoadEmpty(Exception):
    """The whole first-load window returned no voucher. Not marked complete, no checkpoint, progress
    discarded so the next attempt reads every day again (R3)."""


class ManifestRejected(Exception):
    """The manifest was refused - by the backend (details.error) or locally (empty / below half of the
    last accepted one). The manifest checkpoint does not move; a first load is not completed (R4, R7)."""


class CheckpointZero(Exception):
    """The FY's voucher checkpoint is zero / missing (no completed first load). Nothing is requested:
    the agent stops and reports. A first load runs only after `approve-first-load <fy>` (item 1)."""


class CheckpointInvalid(Exception):
    """The FY's voucher checkpoint is not a usable positive integer (negative, text, AlterID 0 with records
    counted ...). Nothing is requested; the checkpoint is NOT modified (items 1, 2)."""


class BillsDateInvalid(Exception):
    """A bills report contained a bill dated after the requested as-of date: the answer is not for that
    date (A3) - rejected, nothing uploaded (item 15)."""


class BillsSanityFailed(Exception):
    """The bills answer is implausible (empty while debtors owe money, duplicate bills): not uploaded (item 23)."""


class BalanceCheckFailed(Exception):
    """The per-ledger balances do not equal Tally's own Group Summary (closing at the FY window end,
    opening = previous FY closing). Nothing is uploaded: this is how a wrong scope (zero balances,
    opening overwritten by closing) is caught before it reaches the backend (R2)."""


class TallyV2Source:
    """Fetches and parses for ONE FY scope. Every request goes through the TallyGuard (breaker, machine-wide
    lock, duty-cycle pacing, telemetry); voucher requests are scoped to the day / range they ask for."""

    def __init__(self, client: TallyClient, pause_seconds: float = 0.5, guard: Optional[TallyGuard] = None,
                 books_from: Optional[date] = None):
        self.client = client
        self.pause = pause_seconds  # kept for compatibility; pacing is the guard's duty cycle
        self.scope: Optional[tx.Scope] = None
        self.guard = guard
        self.books_from = books_from

    def set_scope(self, scope: tx.Scope) -> None:
        self.scope = scope

    def _root(self, xml: str, kind: str = "request") -> ET.Element:
        if self.guard is None:
            return self.client.execute_tdl(xml)
        return self.guard.request(kind, lambda: self.client.execute_tdl(xml),
                                  size_of=lambda r: len(r) if r is not None else 0,
                                  connection_errors=(TallyConnectionError,))

    def masters(self, cached: Optional[X.Masters] = None, debtor_min_alter: int = 0, full_debtors: bool = False) -> X.Masters:
        groups = self._root(tx.groups_request(), "masters:groups")
        ledgers = self._root(tx.all_ledgers_request(), "masters:ledgers")
        vtypes = self._root(tx.voucher_types_request(), "masters:vtypes")
        debtors = self._root(tx.debtors_request(None if full_debtors or cached is None else (debtor_min_alter or None),
                                                scope=self.scope), "masters:debtors")
        m = X.parse_masters(groups, ledgers, debtors, vtypes)
        if cached is not None and not full_debtors:
            merged = dict(cached.debtors)
            merged.update(m.debtors)  # changed debtors replace cached details
            m.debtors = merged
        if m.missing_debtor_details():  # a ledger just moved into / created under Sundry Debtors
            full = X.parse_masters(groups, ledgers, self._root(tx.debtors_request(None, scope=self.scope), "masters:debtors"), vtypes)
            m.debtors = full.debtors
        return m

    def creditors(self) -> Dict[str, Dict[str, Any]]:
        return X.parse_ledger_balances(self._root(tx.creditors_request(scope=self.scope), "balances:creditors"))

    def debtor_balances(self) -> Dict[str, Dict[str, Any]]:
        return X.parse_ledger_balances(self._root(tx.debtors_request(None, scope=self.scope), "balances:debtors"))

    def group_summary_net(self, group: str, date_from: date, date_to: date) -> Decimal:
        company = self.scope.company if self.scope else None
        return X.parse_group_summary_net(self._root(tx.group_summary_request(group, date_from, date_to, company), "group_summary"))

    def changed_headers(self, date_from: date, date_to: date, min_alter_id: int) -> List[tuple]:
        """[(GUID, YYYYMMDD, AlterID)] of vouchers dated date_from..date_to with AlterID > min_alter_id
        (request scoped to that range; min_alter_id must be a positive int - B10)."""
        root = self._root(tx.voucher_request(tx.MANIFEST_FETCH, date_from=date_from, date_to=date_to,
                                             min_alter_id=min_alter_id, scope=self.scope), "incremental:headers")
        return X.parse_manifest_entries(root)

    def future_headers(self, date_from: date, date_to: date, fy_end: date, min_alter_id: Optional[int] = None) -> List[tuple]:
        """2.2.3 (M4): [(GUID, YYYYMMDD, AlterID)] of POST-DATED vouchers: dated date_from..date_to, both after the window
        end and on or before the FY end. HEADERS ONLY (no ledger lines), one request evaluated in that typed range
        (B11), optionally AlterID > min_alter_id (positive int). The engine's scope stops at today, so this one request
        is checked against the FY (period start .. FY end) instead."""
        if self.scope is None:
            raise ValueError("future_headers needs the FY + company scope (apply_scope first)")
        if not (self.scope.period_to < date_from <= date_to <= fy_end):
            raise ValueError(f"future range {date_from}..{date_to} must lie after {self.scope.period_to} and on or before {fy_end}")
        sc = tx.Scope(self.scope.period_from, fy_end, self.scope.company)
        root = self._root(tx.voucher_request(tx.MANIFEST_FETCH, date_from=date_from, date_to=date_to,
                                             min_alter_id=min_alter_id, scope=sc), "future:headers")
        err = X.line_error(root)
        if err:
            raise ManifestRangeUntrusted(f"Tally error: {err[:200]}")
        return X.parse_manifest_entries(root)

    def changed_vouchers_on(self, m: X.Masters, day: date, min_alter_id: int):
        """The changed vouchers of one day (lean, day-scoped, AlterID > checkpoint)."""
        return X.parse_vouchers(self._root(tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=day, min_alter_id=min_alter_id,
                                                              scope=self.scope), "incremental:vouchers"), m)

    def day_vouchers(self, m: X.Masters, day: date):
        return X.parse_vouchers(self._root(tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=day, scope=self.scope), "day:vouchers"), m)

    def day_manifest(self, day: date):
        return X.parse_manifest(self._root(tx.voucher_request(tx.MANIFEST_FETCH, day=day, scope=self.scope), "day:headers"))

    def range_manifest(self, date_from: date, date_to: date):
        """[(GUID, YYYYMMDD, AlterID)] for date_from..date_to; raises ManifestRangeUntrusted on a Tally LINEERROR."""
        root = self._root(tx.voucher_request(tx.MANIFEST_FETCH, date_from=date_from, date_to=date_to, scope=self.scope),
                          "month:headers")
        err = X.line_error(root)
        if err:
            raise ManifestRangeUntrusted(f"Tally error: {err[:200]}")
        return X.parse_manifest_entries(root)

    def _books_from(self) -> date:
        if self.books_from is None:
            raise ValueError("books_from (the company's books start) is needed for a bills report (typed form, A3)")
        return self.books_from

    def bills(self, m: X.Masters, as_of: date) -> List[Dict[str, Any]]:
        company = self.scope.company if self.scope else None
        root = self._root(tx.bills_receivable_request(as_of, company, self._books_from()), "bills:receivable")
        check_bill_dates(X.parse_bills_any(root), as_of, "Bills Receivable")
        return X.parse_bills_receivable(root, m)

    def bills_payable(self, as_of: date, parties: Optional[set] = None) -> List[Dict[str, Any]]:
        company = self.scope.company if self.scope else None
        rows = X.parse_bills_any(self._root(tx.bills_payable_request(as_of, company, self._books_from()), "bills:payable"))
        check_bill_dates(rows, as_of, "Bills Payable")
        return [b for b in rows if parties is None or b["ledger_name"].strip().lower() in parties]


def check_bill_dates(bills: List[Dict[str, Any]], as_of: date, report: str) -> None:
    """Item 15: any bill dated after the as-of date means Tally did not answer for that date -> reject."""
    iso = as_of.isoformat()
    late = [b for b in bills if (b.get("bill_date") or "") > iso]
    if late:
        ex = late[0]
        raise BillsDateInvalid(f"{report} as of {iso} contains {len(late)} bill(s) dated after that date, e.g. "
                               f"{ex.get('bill_date')} {ex.get('bill_name')!r}: the report is not for {iso}; rejected")


def bills_sanity(bills: List[Dict[str, Any]], debtor_closing_sum: Decimal, billwise_receivable_debtors: int) -> Dict[str, Any]:
    """Item 23: refuse an implausible bills answer; report (never suppress) the difference to the balances."""
    keys = [(b["ledger_name"].strip().lower(), b.get("bill_name"), b.get("bill_date")) for b in bills]
    dups = len(keys) - len(set(keys))
    if not bills and billwise_receivable_debtors:
        raise BillsSanityFailed(f"Bills Receivable is empty although {billwise_receivable_debtors} bill-wise debtors "
                                "have a receivable balance")
    if dups:
        raise BillsSanityFailed(f"Bills Receivable lists {dups} duplicate bill(s) (same party, name and date)")
    total = sum((Decimal(str(b.get("pending_amount") or "0")) for b in bills), Decimal("0"))
    return {"bills": len(bills), "bills_sum": str(total), "debtor_closing_sum": str(debtor_closing_sum),
            "difference_bills_minus_balances": str(total - debtor_closing_sum),
            "note": "on-account / unallocated amounts appear in the balances but in no bill (reported, not suppressed)"}


def default_guard(data_dir: Path) -> TallyGuard:
    return guard_for(Path(data_dir), duty_factor=settings.tally_duty_factor, min_pause=settings.tally_min_pause_seconds,
                     lock_wait=settings.tally_lock_wait_seconds, base_cooldown=settings.tally_cooldown_seconds,
                     max_cooldown=settings.tally_cooldown_max_seconds)


def books_from_of(company: Optional[Dict[str, Any]]) -> Optional[date]:
    """The company's BOOKSFROM (YYYYMMDD), else the start of the earliest configured FY (both 1-Apr-2024 here)."""
    raw = ((company or {}).get("books_from") or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    from tally_sync_agent.config.fiscal import parse_fy_list
    fys = parse_fy_list(settings.financial_years)
    return min(f.start for f in fys) if fys else None


def _quarantined_date(q: Dict[str, Any]) -> Optional[str]:
    """The voucher date (YYYY-MM-DD) stored with a quarantine entry: a backend rejection keeps the whole payload
    ("date"), a parser rejection keeps {"raw": {"date": ...}}. None when it cannot be read."""
    try:
        rec = json.loads(q.get("record_json") or "{}")
    except (TypeError, ValueError):
        return None
    d = rec.get("date") or (rec.get("raw") or {}).get("date")
    if not d:
        return None
    d = str(d).strip()
    if len(d) == 8 and d.isdigit():
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    try:
        return date.fromisoformat(d[:10]).isoformat()
    except ValueError:
        return None


def _new_counters() -> Dict[str, int]:
    return {"extracted": 0, "validated": 0, "rejected_local": 0, "outside_fy": 0, "uploaded": 0,
            "accepted": 0, "rejected_backend": 0, "queued": 0}


class SyncEngineV2:
    def __init__(
        self,
        tally_client: Optional[TallyClient] = None,
        backend_client: Optional[BackendClient] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        retry_queue: Optional[RetryQueue] = None,
        quarantine_store: Optional[QuarantineStore] = None,
        data_dir: Optional[Path] = None,
        source: Optional[TallyV2Source] = None,
        today: Callable[[], date] = ist_today,
        state: Optional[Any] = None,
        fy: Optional[FyContext] = None,
        deferred_store: Optional[DeferredStore] = None,
    ):
        self.tally = tally_client or TallyClient()
        self.backend = backend_client or BackendClient()
        self.checkpoints = checkpoint_manager or CheckpointManager()
        self.retry_queue = retry_queue or RetryQueue()
        self.quarantine = quarantine_store or QuarantineStore()
        # 2.2.3 (M4): post-dated vouchers; same SQLite file as the quarantine (and the checkpoints) by default
        self.deferred = deferred_store or DeferredStore(getattr(self.quarantine, "db_path", None))
        self.data_dir = Path(data_dir or DATA_DIR)
        self.src = source or TallyV2Source(self.tally, settings.day_request_pause_seconds, guard=default_guard(self.data_dir))
        self.today = today
        self.fy: FyContext = fy or legacy_context(settings.sync_from_date)
        self.masters: Optional[X.Masters] = None
        self.company_name: Optional[str] = None
        self.company_guid: Optional[str] = None
        self.period_start = self.fy.fy.start
        self.period_end = self.fy.fy.end
        # Daemon: an AgentState the heartbeat thread reads. When set, the engine publishes progress
        # there and sends NO heartbeat itself (single sender). None = sync/dry-run CLI use.
        self.state = state
        self.auth_error = False
        self.counters = _new_counters()

    # ------------------------------------------------------------------ scope / window

    def window_end(self) -> date:
        """Last day of this FY that can hold vouchers today (IST)."""
        return min(self.today(), self.period_end)

    def apply_scope(self) -> None:
        """Every collection of this engine is evaluated in this FY up to the WINDOW END (today in the live FY,
        the FY end in a past FY) and this company (R1). Balances are therefore read to the same date as
        Group Summary and the bills (A5); voucher requests narrow it further to their day / month (B11)."""
        set_scope = getattr(self.src, "set_scope", None)
        if set_scope is not None and self.company_name:
            set_scope(tx.Scope(self.period_start, self.window_end(), self.company_name))

    def _in_fy(self, vouchers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Only vouchers dated inside this FY are processed under it (no cross-FY duplicates)."""
        lo, hi = self.period_start.isoformat(), self.period_end.isoformat()
        keep = [v for v in vouchers if lo <= (v.get("date") or "") <= hi]
        out = len(vouchers) - len(keep)
        if out:
            self.counters["outside_fy"] += out
            logger.warning(f"FY {self.fy.label}: {out} voucher(s) dated outside the FY ignored")
        return keep

    def _count_extraction(self, good: List[Dict[str, Any]], bad: List[Dict[str, Any]], kept: List[Dict[str, Any]]) -> None:
        self.counters["extracted"] += len(good) + len(bad)
        self.counters["rejected_local"] += len(bad)
        self.counters["validated"] += len(kept)

    def _publish_counters(self) -> None:
        if self.state is not None and hasattr(self.state, "set_fy"):
            self.state.set_fy(self.fy.label, {"counters": dict(self.counters)})

    # ------------------------------------------------------------------ helpers

    def _chunks(self, items: List[Any], size: int) -> List[List[Any]]:
        return [items[i:i + size] for i in range(0, len(items), size)] or [[]]

    def process_retry_queue(self) -> Dict[str, int]:
        """Replay every due batch independently (2.1.0). A failing item never blocks the others.

        * success                 -> removed from the queue
        * 4xx (not 401/403)       -> kept, flagged rejected_4xx, retried hourly, reported; pass continues
        * connection error / 5xx  -> item backs off; after 3 CONSECUTIVE such errors the pass stops
        * 401/403                 -> item backs off, pass stops, cycle reports AUTH_ERROR
        Voucher batches carry their FY in the batch type ("vouchers" / "vouchers@2025-26") and are
        quarantined under that FY. Nothing is ever deleted except on success."""
        stats = {"replayed": 0, "failed": 0, "rejected": 0, "stopped_early": 0}
        consecutive = 0
        for item in self.retry_queue.get_pending_ready():
            try:
                bt = item["batch_type"]
                if bt == Q_VOUCHERS or bt.startswith(Q_VOUCHERS + "@"):
                    res = self.backend.sync_vouchers(item["batch_id"], item["company_guid"], item["records"])
                    self._handle_voucher_errors(item["records"], res, entity=bt)
                elif bt == "customers":
                    self.backend.sync_customers(item["batch_id"], item["company_guid"], item["records"])
                elif bt == "invoices":
                    self.backend.sync_invoices(item["batch_id"], item["company_guid"], item["records"])
                elif bt == "payments":
                    self.backend.sync_payments(item["batch_id"], item["company_guid"], item["records"])
                self.retry_queue.mark_success(item["id"])
                stats["replayed"] += 1
                consecutive = 0
            except BackendAuthError as ex:
                self.retry_queue.mark_failure(item["id"], str(ex))
                self.auth_error = True
                self._record_error(f"Backend rejected the agent key: {ex}")
                stats["failed"] += 1
                stats["stopped_early"] = 1
                break
            except Exception as ex:
                if getattr(ex, "is_rejection", False):
                    self.retry_queue.mark_failure(item["id"], str(ex), rejected=True)
                    self._record_error(f"Backend rejected a queued batch: {ex}")
                    stats["rejected"] += 1
                    consecutive = 0
                    continue
                self.retry_queue.mark_failure(item["id"], str(ex))
                stats["failed"] += 1
                consecutive += 1
                if consecutive >= 3:
                    logger.warning("RETRY_PASS_STOPPED after 3 consecutive connection errors; items keep their schedule")
                    stats["stopped_early"] = 1
                    break
        return stats

    def _handle_voucher_errors(self, batch: List[Dict[str, Any]], res: Dict[str, Any],
                               entity: Optional[str] = None) -> List[Dict[str, Any]]:
        entity = entity or self.fy.quarantine_entity
        failed = {e.get("identifier") for e in (res.get("errors") or []) if e.get("identifier")}
        by_guid = {v["guid"]: v for v in batch}
        rejected = []
        for e in res.get("errors") or []:
            v = by_guid.get(e.get("identifier"))
            if v is not None:
                self.quarantine.add(entity, v["guid"], v.get("alter_id"), e.get("error") or "rejected", v)
                rejected.append(v)
        for v in batch:
            if v["guid"] not in failed:
                self.quarantine.mark_resolved(entity, v["guid"])
        return rejected

    def upload_vouchers(self, company_guid: Optional[str], vouchers: List[Dict[str, Any]]) -> Dict[str, int]:
        """Upload in batches. -> counts. Network failures go to the durable retry queue."""
        stats = {"sent": 0, "created": 0, "updated": 0, "retired": 0, "failed": 0, "queued": 0}
        for batch in self._chunks(vouchers, settings.batch_size):
            if not batch:
                continue
            b_id = str(uuid.uuid4())
            try:
                res = self.backend.sync_vouchers(b_id, company_guid, batch)
                failed = len(self._handle_voucher_errors(batch, res))
                stats["sent"] += len(batch)
                stats["created"] += res.get("created_count", 0)
                stats["updated"] += res.get("updated_count", 0)
                stats["retired"] += res.get("retired_count", 0)
                stats["failed"] += failed
                self.counters["uploaded"] += len(batch)
                self.counters["accepted"] += len(batch) - failed
                self.counters["rejected_backend"] += failed
            except BackendAuthError:
                # Not queued: nothing advances, the same vouchers are re-read once the key is fixed.
                raise
            except Exception as ex:
                logger.error(f"Voucher batch upload failed, saved to the retry queue: {ex}")
                # If this enqueue itself fails, the exception propagates and the caller's checkpoint
                # is NOT advanced, so the vouchers are read again next cycle (never lost).
                qid = self.retry_queue.enqueue(self.fy.batch_type, b_id, company_guid, batch)
                if getattr(ex, "is_rejection", False):
                    self.retry_queue.mark_failure(qid, str(ex), rejected=True)
                self._record_error(f"Voucher batch queued for retry: {ex}")
                stats["queued"] += len(batch)
                self.counters["queued"] += len(batch)
        return stats

    # ------------------------------------------------------------------ state publishing

    def _phase(self, phase: str, detail: str = "") -> None:
        if self.state is not None:
            self.state.set_phase(phase, f"FY {self.fy.label} {detail}".strip() if self.fy.historical else detail)

    def _success(self, *streams: str) -> None:
        if self.state is not None and not self.fy.historical:
            self.state.mark_success(*streams)

    def _record_error(self, message: Any) -> None:
        if self.state is not None:
            self.state.record_error(f"FY {self.fy.label}: {message}" if self.fy.historical else message)

    def _log_rejections(self, rejected: List[Dict[str, Any]]) -> None:
        for r in rejected:
            if r.get("source_reference"):
                # Identifiable (has a GUID) but unusable: quarantine; it caps this FY's checkpoint.
                self.quarantine.add(self.fy.quarantine_entity, r["source_reference"], r.get("alter_id"), r["validation_error"], r)
            else:
                logger.warning(f"VOUCHER_WITHOUT_GUID skipped (not stored in Tally / being keyed in): {r}")

    # ------------------------------------------------------------------ balance check (R2)

    def check_debtor_balances(self, m: X.Masters) -> Dict[str, Any]:
        """Σ per-ledger closing must equal Tally's Group Summary (Sundry Debtors) at the window end, and
        Σ per-ledger opening must equal the previous FY's Group Summary. A wrong scope (all zero, or
        opening = closing) cannot pass this. Skipped only for test sources without Group Summary."""
        gs = getattr(self.src, "group_summary_net", None)
        if gs is None:
            return {"checked": False}
        sum_close = sum((Decimal(str(d.get("closing_balance") or "0")) for d in m.debtors.values()), Decimal("0"))
        sum_open = sum((Decimal(str(d.get("opening_balance") or "0")) for d in m.debtors.values()), Decimal("0"))
        tally_close = gs("Sundry Debtors", self.period_start, self.window_end())
        prev = self.fy.fy.previous
        tally_open = gs("Sundry Debtors", prev.start, prev.end)
        result = {"checked": True, "debtors": len(m.debtors), "sum_closing": str(sum_close), "group_summary_closing": str(tally_close),
                  "sum_opening": str(sum_open), "group_summary_previous_fy_closing": str(tally_open)}
        if abs(sum_close - tally_close) > TOLERANCE or abs(sum_open - tally_open) > TOLERANCE:
            raise BalanceCheckFailed(f"FY {self.fy.label} debtor balances do not match Tally's Group Summary: {result}")
        return result

    # ------------------------------------------------------------------ snapshots (live FY only)

    def ledger_snapshot(self, company_guid: Optional[str]) -> Dict[str, Any]:
        if self.fy.historical:
            raise RuntimeError("a historical FY never uploads a ledger snapshot (it would move the live opening anchor)")
        self.apply_scope()
        if self.state is not None and self.state.phase != "INITIAL_LOAD":
            self._phase("SNAPSHOT", "ledgers")
        m = self.masters = self.src.masters(full_debtors=True)
        check = self.check_debtor_balances(m)  # raises BalanceCheckFailed -> nothing uploaded
        items = X.ledger_snapshot_items(m)
        sid = f"LEDGERS-{uuid.uuid4().hex}"
        as_of = _iso_now()
        chunks = self._chunks(items, settings.snapshot_chunk_size)
        res: Dict[str, Any] = {}
        for i, chunk in enumerate(chunks):
            res = self.backend.sync_ledgers(str(uuid.uuid4()), company_guid, chunk, snapshot_id=sid,
                                            is_final_chunk=i == len(chunks) - 1, as_of=as_of,
                                            period_start=self.period_start.isoformat())
        self.checkpoints.update_checkpoint(self.fy.cp_debtors, alter_id=max(
            [d.get("alter_id") or 0 for d in m.debtors.values()] or [0]), records_count=len(items))
        self._success("ledgers", "masters")
        return {"ledgers": len(items), "debtors": len(m.debtors), "balance_check": check, "result": res.get("details", {})}

    def bills_snapshot(self, company_guid: Optional[str], as_of: Optional[date] = None) -> Dict[str, Any]:
        if self.fy.historical:
            raise RuntimeError("a historical FY never uploads a bills snapshot")
        self.apply_scope()
        as_of = as_of or self.window_end()
        if self.state is not None and self.state.phase != "INITIAL_LOAD":
            self._phase("SNAPSHOT", "bills")
        m = self.masters or self.src.masters(full_debtors=True)
        bills = self.src.bills(m, as_of)  # BillsDateInvalid -> nothing uploaded
        close = sum((Decimal(str(d.get("closing_balance") or "0")) for d in m.debtors.values()), Decimal("0"))
        # Only BILL-WISE debtors with a receivable (debit, negative) balance must have an open bill.
        billwise_receivable = sum(1 for d in m.debtors.values()
                                  if d.get("is_bill_wise") and Decimal(str(d.get("closing_balance") or "0")) < 0)
        sanity = bills_sanity(bills, close, billwise_receivable)  # BillsSanityFailed -> nothing uploaded
        logger.info(f"BILLS_SANITY fy={self.fy.label} as_of={as_of} {json.dumps(sanity)}")
        sid = f"BILLS-{uuid.uuid4().hex}"
        chunks = self._chunks(bills, settings.snapshot_chunk_size)
        res: Dict[str, Any] = {}
        for i, chunk in enumerate(chunks):
            res = self.backend.sync_bills(str(uuid.uuid4()), company_guid, chunk, snapshot_id=sid,
                                          as_of_date=as_of.isoformat(), is_final_chunk=i == len(chunks) - 1)
        self._success("bills")
        return {"bills": len(bills), "as_of": as_of.isoformat(), "with_due_date": sum(1 for b in bills if b.get("due_date")),
                "sanity": sanity, "result": res.get("details", {})}

    def _due(self, cp_name: str, delta: timedelta, never_run: bool) -> bool:
        last = self.checkpoints.get_checkpoint(cp_name).get("last_successful_sync_at")
        if not last:
            return never_run
        return datetime.now(timezone.utc) - datetime.fromisoformat(last) >= delta

    def balances_due(self) -> bool:
        return self._due(self.fy.cp_balances, timedelta(minutes=settings.balance_interval_minutes), True)

    def manifest_due(self) -> bool:
        hours = settings.history_manifest_hours if self.fy.historical else settings.manifest_interval_hours
        return self._due(self.fy.cp_manifest, timedelta(hours=hours), False)  # the first load uploads the first one

    # ------------------------------------------------------------------ manifest

    def _scan_days(self, a: date, b: date) -> tuple[set, int]:
        guids: set[str] = set()
        max_alter = 0
        for d in _days(a, b):
            g, m = self.src.day_manifest(d)
            guids.update(g)
            max_alter = max(max_alter, m)
        return guids, max_alter

    def _scan_range(self, a: date, b: date) -> tuple[set, int]:
        """One range request, accepted only if every voucher is dated inside a..b and the month is not empty."""
        entries = self.src.range_manifest(a, b)
        lo, hi = a.strftime("%Y%m%d"), b.strftime("%Y%m%d")
        outside = [e for e in entries if not (lo <= e[1] <= hi)]
        if outside:
            raise ManifestRangeUntrusted(f"{len(outside)} voucher(s) dated outside the window, e.g. {outside[0][:2]}")
        if not entries:
            raise ManifestRangeUntrusted("empty answer (confirmed one day at a time)")
        return {e[0] for e in entries}, max([e[2] for e in entries] or [0])

    def _scan_chunk(self, a: date, b: date) -> tuple[set, int, str]:
        if settings.manifest_scan_mode == "day":
            return (*self._scan_days(a, b), "day")
        try:
            return (*self._scan_range(a, b), "range")
        except ManifestRangeUntrusted as ex:
            # 2.2.1 (B5): ONLY an untrusted answer falls back to day requests. A failed / timed-out request
            # propagates (the breaker is open): 2.2.0 fired up to 31 day requests right after a timeout.
            logger.warning(f"MANIFEST_SCAN {a}..{b} range answer not used ({ex}); reading this month one day per request")
            return (*self._scan_days(a, b), "day-fallback")

    def scan_manifest(self, extra_guids: Optional[set] = None, resume_after: Optional[date] = None,
                      resume_max_alter: int = 0, on_chunk: Optional[Callable[[date, set, int], None]] = None,
                      phase: str = "MANIFEST") -> tuple[list[str], int]:
        """Every voucher GUID dated in this FY up to the window end, and the highest AlterID seen."""
        self.apply_scope()
        guids: set[str] = set(extra_guids or ())
        max_alter = int(resume_max_alter or 0)
        start = resume_after + timedelta(days=1) if resume_after else self.period_start
        t0 = time.time()
        stats = {"chunks": 0, "day_fallbacks": 0}
        label = "pre-scan" if phase == "INITIAL_LOAD" else "manifest"
        for a, b in month_chunks(start, self.window_end()):
            t = time.time()
            self._phase(phase, f"{label} {a}..{b}")
            g, m, mode = self._scan_chunk(a, b)
            guids.update(g)
            max_alter = max(max_alter, m)
            stats["chunks"] += 1
            stats["day_fallbacks"] += mode == "day-fallback"
            logger.info(f"MANIFEST_SCAN {a}..{b} mode={mode} guids={len(g)} max_alter={m} "
                        f"total_guids={len(guids)} {time.time() - t:.1f}s fy={self.fy.label}")
            if on_chunk:
                on_chunk(b, guids, max_alter)
        logger.info(f"MANIFEST_SCAN_DONE from={start} to={self.window_end()} chunks={stats['chunks']} "
                    f"day_fallbacks={stats['day_fallbacks']} guids={len(guids)} max_alter={max_alter} {time.time() - t0:.1f}s "
                    f"fy={self.fy.label}")
        self.last_scan_stats = {**stats, "guids": len(guids), "seconds": round(time.time() - t0, 1)}
        return sorted(guids), max_alter

    def upload_manifest(self, company_guid: Optional[str], guids: List[str]) -> Dict[str, Any]:
        """Never empty; never below half of the last manifest the backend ACCEPTED for this FY (R7)."""
        if not guids:
            raise ManifestRejected(f"FY {self.fy.label}: refusing to send an empty manifest (local check)")
        last = int(self.checkpoints.get_checkpoint(self.fy.cp_manifest_count).get("last_alter_id") or 0)
        if last and len(guids) * 2 < last:
            raise ManifestRejected(f"FY {self.fy.label}: manifest lists {len(guids)} GUIDs, less than half of the "
                                   f"last accepted {last} (local check); not sent")
        sid = f"MANIFEST-{uuid.uuid4().hex}"
        chunks = self._chunks(guids, settings.snapshot_chunk_size * 5)
        res: Dict[str, Any] = {}
        for i, chunk in enumerate(chunks):
            res = self.backend.sync_manifest(str(uuid.uuid4()), company_guid, chunk, snapshot_id=sid,
                                             window_from=self.period_start.isoformat(),
                                             window_to=self.window_end().isoformat(), is_final_chunk=i == len(chunks) - 1)
        details = (res or {}).get("details") or {}
        if details.get("error"):
            # The backend applied nothing; do not record a manifest that did not happen.
            logger.error(f"MANIFEST_REJECTED fy={self.fy.label} by the backend ({len(guids)} GUIDs): {details['error']}")
            raise ManifestRejected(str(details["error"]))
        self.checkpoints.update_checkpoint(self.fy.cp_manifest, last_sync_date=self.window_end().isoformat(), records_count=len(guids))
        self.checkpoints.update_checkpoint(self.fy.cp_manifest_count, alter_id=len(guids))
        released = self.release_absent_quarantine(set(guids))
        if released:
            details = {**details, "quarantine_released": released}
        self._success("manifest")
        return details

    def release_absent_quarantine(self, present: set) -> List[str]:
        """2.2.2 (M1): a quarantined voucher caps this FY's checkpoint until it uploads successfully. If it has
        been DELETED in Tally (or re-dated out of this FY) it is never read again, so it would cap the checkpoint
        forever and every cycle would re-read a growing range. After an ACCEPTED manifest, which lists every
        voucher of the FY window, an entry whose GUID is no longer listed is released.

        Kept (not released): an entry dated after the window end (a post-dated voucher is legitimately absent
        from today's manifest) and an entry whose date is unknown."""
        released: List[str] = []
        end = self.window_end().isoformat()
        for q in self.quarantine.list_unresolved(self.fy.quarantine_entity):
            g = q.get("source_reference")
            if not g or g in present:
                continue
            d = _quarantined_date(q)
            if d is None or d > end:
                continue
            self.quarantine.mark_resolved(self.fy.quarantine_entity, g)
            released.append(g)
            logger.warning(f"QUARANTINE_RELEASED fy={self.fy.label} guid={g} alter_id={q.get('alter_id')} date={d}: "
                           f"no longer in Tally's voucher list (deleted or re-dated out of the FY); it no longer caps the checkpoint")
        return released

    def stale_quarantine(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        """2.2.2 (M1): quarantined vouchers of this FY first seen more than `hours` ago (still capping the checkpoint)."""
        limit = datetime.now(timezone.utc) - timedelta(hours=hours)
        out = []
        for q in self.quarantine.list_unresolved(self.fy.quarantine_entity):
            try:
                seen = datetime.fromisoformat(str(q.get("first_seen_at")))
            except ValueError:
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if seen < limit:
                out.append(q)
        return out

    # ------------------------------------------------------------------ first-load state

    def _empty_completion(self) -> bool:
        """A first load that 2.1.0 marked complete although it extracted nothing (checkpoint at AlterID 0,
        0 records). Treated as not done, so the day-by-day load runs again instead of one huge AlterId > 0
        request. Nothing is deleted: the checkpoints are only overwritten when the new load completes."""
        cp = self.checkpoints.get_checkpoint(self.fy.cp_vouchers)
        return bool(cp.get("last_successful_sync_at")) and int(cp.get("last_alter_id") or 0) == 0 \
            and int(cp.get("total_synced_records") or 0) == 0

    def first_load_approved(self) -> bool:
        """`approve-first-load <fy>` writes this marker (explicit, logged). Item 1: without it a zero / missing
        checkpoint stops the agent instead of starting a load."""
        return (self.data_dir / f"approve_first_load_{self.fy.label}.json").exists()

    def checkpoint_status(self) -> str:
        """'OK' | 'EMPTY_COMPLETION' | 'NEVER_LOADED' | 'IN_PROGRESS' | 'INVALID: ...' for this FY's vouchers."""
        cp = self.checkpoints.get_checkpoint(self.fy.cp_vouchers)
        raw = cp.get("last_alter_id")
        done = bool(cp.get("last_successful_sync_at"))
        state = self._load_state() if self._state_path().exists() else {}
        if state.get("m0") is not None and not state.get("completed_at") or state.get("prescan_through") and not state.get("completed_at"):
            return "IN_PROGRESS"
        if not done and raw in (None, 0):
            return "NEVER_LOADED"
        if isinstance(raw, bool) or not isinstance(raw, int):
            return f"INVALID: last_alter_id={raw!r} is not an integer"
        if raw < 0:
            return f"INVALID: last_alter_id={raw} is negative"
        if raw == 0:
            records = cp.get("total_synced_records") or 0
            if records == 0:
                return "EMPTY_COMPLETION"
            return f"INVALID: last_alter_id=0 with {records} records synced"
        return "OK"

    _PROGRESS_KEYS = ("m0", "prescan_through", "prescan_guids", "prescan_max_alter", "loaded_through", "completed_at",
                      "movements")

    def _discard_progress(self, state: Dict[str, Any], why: str) -> None:
        for k in self._PROGRESS_KEYS:
            state.pop(k, None)
        state["last_discarded"] = {"at": _iso_now(), "why": why}
        self._save_state(state)

    def _state_path(self) -> Path:
        return self.data_dir / self.fy.state_file

    def _load_state(self) -> Dict[str, Any]:
        p = self._state_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        tmp = self._state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(self._state_path())

    @staticmethod
    def _add_movements(state: Dict[str, Any], vouchers: List[Dict[str, Any]]) -> None:
        mv = state.setdefault("movements", {})
        for v in vouchers:
            if not posts_to_ledgers(v):
                continue
            for line in v.get("debtor_lines") or []:
                g = line.get("ledger_guid")
                if g:
                    mv[g] = str(Decimal(mv.get(g, "0")) + Decimal(str(line.get("amount") or "0")))

    def reconcile_movements(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Per debtor: Tally opening(FY) + Σ debtor lines of the loaded vouchers = Tally closing(FY)."""
        bal_fn = getattr(self.src, "debtor_balances", None)
        if bal_fn is None:
            return {"checked": False}
        self.apply_scope()
        balances = bal_fn()
        mv = {g: Decimal(a) for g, a in (state.get("movements") or {}).items()}
        bad = []
        for b in balances.values():
            g = b.get("guid")
            expected = b["opening"] + mv.get(g, Decimal("0"))
            if abs(expected - b["closing"]) > TOLERANCE:
                bad.append({"ledger": b["name"], "opening": str(b["opening"]), "movements": str(mv.get(g, Decimal("0"))),
                            "closing": str(b["closing"]), "difference": str(b["closing"] - expected)})
        result = {"checked": True, "fy": self.fy.label, "debtors": len(balances), "mismatched": len(bad),
                  "examples": bad[:20], "at": _iso_now()}
        (self.data_dir / self.fy.validation_file).write_text(json.dumps(result, indent=1), encoding="utf-8")
        if bad:
            logger.error(f"FY_RECONCILIATION fy={self.fy.label} {len(bad)} of {len(balances)} debtors do not reconcile")
            self._record_error(f"FY {self.fy.label}: {len(bad)} debtors do not reconcile (see {self.fy.validation_file})")
        else:
            logger.info(f"FY_RECONCILIATION fy={self.fy.label} all {len(balances)} debtors reconcile")
        return result

    # ------------------------------------------------------------------ first full load

    def initial_load(self, company_guid: Optional[str], max_days: Optional[int] = None) -> Dict[str, Any]:
        self.apply_scope()
        state = self._load_state()
        if state.get("completed_at") and not state.get("prescan_guids"):
            # 2.1.0 marked a load complete that found no voucher at all: read the window again, with
            # fresh snapshots (its ledger snapshot carried 0.00 balances) (R5).
            logger.warning(f"INITIAL_LOAD fy={self.fy.label} previous load completed with 0 vouchers; reloading")
            state.pop("snapshots_done", None)
            self._discard_progress(state, "previous load completed with 0 vouchers")
        report: Dict[str, Any] = {"fy": self.fy.label}
        if not self.fy.historical and not state.get("snapshots_done"):
            self._phase("INITIAL_LOAD", "ledger and bills snapshot")
            report["ledgers"] = self.ledger_snapshot(company_guid)
            report["bills"] = self.bills_snapshot(company_guid)
            state["snapshots_done"] = True
            self._save_state(state)
        m = self.masters or self.src.masters(full_debtors=True)
        self.masters = m
        if "m0" not in state:
            # Resumable pre-scan: progress is saved after every month. M0 is only set once the whole window
            # is scanned, and the day-by-day load starts after that, so anything altered after a month was
            # scanned is either read by the load or has AlterID > M0.
            through = state.get("prescan_through")

            def save_progress(last: date, guids: set, max_alter: int) -> None:
                state.update({"prescan_through": last.isoformat(), "prescan_guids": sorted(guids),
                              "prescan_max_alter": max_alter})
                self._save_state(state)
                self._heartbeat("INITIAL_LOAD", self.company_name, company_guid)  # backend: offline after 180 s

            guids, m0 = self.scan_manifest(
                extra_guids=set(state.get("prescan_guids", [])) if through else None,
                resume_after=date.fromisoformat(through) if through else None,
                resume_max_alter=int(state.get("prescan_max_alter") or 0) if through else 0,
                on_chunk=save_progress, phase="INITIAL_LOAD")
            if not guids:
                self._discard_progress(state, "pre-scan found no voucher")
                raise InitialLoadEmpty(f"FY {self.fy.label}: pre-scan of {self.period_start}..{self.window_end()} found no "
                                       "voucher in Tally; first load not marked complete, no checkpoint written")
            # 2.2.3 (M4): post-dated vouchers are not read by the day-by-day load (it stops at today); register all
            # of them now, before M0 is recorded, so none can fall behind the checkpoint.
            report["post_dated_registered"] = len(self.register_post_dated(None))
            state.update({"m0": m0, "prescan_guids": guids})
            self._save_state(state)
            report["manifest_scan"] = getattr(self, "last_scan_stats", {})
        seen = set(state.get("prescan_guids", []))
        start = date.fromisoformat(state["loaded_through"]) + timedelta(days=1) if state.get("loaded_through") else self.period_start
        totals = {"days": 0, "vouchers": 0, "rejected": 0, "outside_fy": 0, "created": 0, "updated": 0, "retired": 0,
                  "failed": 0, "queued": 0}
        end = self.window_end()
        n_days = (end - self.period_start).days + 1
        for d in _days(start, end):
            if max_days is not None and totals["days"] >= max_days:
                report["vouchers"] = totals
                report["partial"] = True
                report["loaded_through"] = state.get("loaded_through")
                return report
            self._phase("INITIAL_LOAD", f"day {d} ({(d - self.period_start).days + 1}/{n_days})")
            good, bad = self.src.day_vouchers(m, d)
            self._log_rejections(bad)
            kept = self._in_fy(good)
            self._count_extraction(good, bad, kept)
            st = self.upload_vouchers(company_guid, kept)
            seen.update(v["guid"] for v in kept)
            self._add_movements(state, kept)
            totals["days"] += 1
            totals["vouchers"] += len(kept)
            totals["rejected"] += len(bad)
            totals["outside_fy"] += len(good) - len(kept)
            for k in ("created", "updated", "retired", "failed", "queued"):
                totals[k] += st[k]
            state["loaded_through"] = d.isoformat()
            state["prescan_guids"] = sorted(seen)
            self._save_state(state)
            self._heartbeat("INITIAL_LOAD", self.company_name, company_guid)
            logger.info(f"INITIAL_LOAD fy={self.fy.label} day={d} vouchers={len(kept)} rejected={len(bad)} {st}")
        report["vouchers"] = totals
        if not seen:
            self._discard_progress(state, "every day returned no voucher")
            raise InitialLoadEmpty(f"FY {self.fy.label}: every day {self.period_start}..{end} returned no voucher; "
                                   "first load not marked complete, no checkpoint written")
        # A rejected manifest raises ManifestRejected here: no checkpoint, completed_at not set.
        report["manifest"] = self.upload_manifest(company_guid, sorted(seen))
        self.checkpoints.update_checkpoint(self.fy.cp_vouchers, alter_id=int(state["m0"]), records_count=totals["vouchers"])
        if not self.fy.historical:
            self.checkpoints.update_checkpoint(self.fy.cp_balances, records_count=0)
        state["completed_at"] = _iso_now()
        self._save_state(state)
        self._success("vouchers")
        try:
            report["reconciliation"] = self.reconcile_movements(state)
        except TallyConnectionError:
            raise
        except Exception as ex:  # reporting only; never undoes an accepted load
            logger.warning(f"FY {self.fy.label} reconciliation could not run: {ex}")
            report["reconciliation"] = {"checked": False, "error": str(ex)}
        return report

    # ------------------------------------------------------------------ post-dated vouchers (2.2.3, M4)

    def _future_range(self) -> Optional[tuple]:
        """(tomorrow, FY end) for the live FY while the FY is not over; None for a past FY (its window is the whole FY)."""
        start = self.window_end() + timedelta(days=1)
        if self.fy.historical or start > self.period_end:
            return None
        return start, self.period_end

    def register_post_dated(self, min_alter_id: Optional[int]) -> Dict[str, tuple]:
        """Header-only read of tomorrow..FY end (one request); every voucher found is recorded in the durable deferred
        register (GUID, date, AlterID). min_alter_id None = all post-dated vouchers (first load and the one-time 2.2.3
        catch-up); otherwise only those created / altered since the checkpoint."""
        rng = self._future_range()
        reader = getattr(self.src, "future_headers", None)
        if rng is None or reader is None:
            return {}
        a, b = rng
        lo, hi = a.strftime("%Y%m%d"), b.strftime("%Y%m%d")
        found: Dict[str, tuple] = {}
        for g, ymd, alter in reader(a, b, self.period_end, min_alter_id):
            if g and ymd and lo <= ymd <= hi:
                found[g] = (ymd, alter)
                self.deferred.upsert(self.fy.label, g, f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", alter)
        if min_alter_id is None:
            self.deferred.mark_scanned(self.fy.label, b.isoformat())
        if found:
            logger.info(f"POST_DATED fy={self.fy.label} {len(found)} voucher(s) dated {a}..{b} registered; uploaded when "
                        f"their date arrives (pending {self.deferred.count(self.fy.label)})")
        return found

    # ------------------------------------------------------------------ cycle

    def incremental_vouchers(self, company_guid: Optional[str]) -> Dict[str, Any]:
        """B4/B10: month-scoped headers (AlterID > checkpoint), then each changed date's vouchers in one
        day-scoped lean request. Requires a positive integer checkpoint; never an unfiltered request."""
        self.apply_scope()
        status = self.checkpoint_status()
        if status in ("EMPTY_COMPLETION", "NEVER_LOADED"):
            raise CheckpointZero(f"FY {self.fy.label}: voucher checkpoint is {status}; no incremental request sent")
        if status != "OK":
            raise CheckpointInvalid(f"FY {self.fy.label}: voucher checkpoint {status}; nothing requested, checkpoint unchanged")
        current = int(self.checkpoints.get_checkpoint(self.fy.cp_vouchers)["last_alter_id"])
        changed: Dict[str, tuple] = {}
        for a, b in month_chunks(self.period_start, self.window_end()):
            for g, ymd, alter in self.src.changed_headers(a, b, current):
                changed[g] = (ymd, alter)
        # 2.2.3 (M4): post-dated vouchers (dated after today, in this FY) are registered, never uploaded early.
        # The first 2.2.3 cycle of an FY reads all of them once (vouchers entered under an earlier version).
        future = self.register_post_dated(None if not self.deferred.scanned(self.fy.label) else current)
        due = self.deferred.due(self.fy.label, self.window_end().isoformat())
        due_guids = {e["guid"] for e in due}
        good, bad = [], []
        days = sorted({ymd for ymd, _ in changed.values() if ymd})
        for ymd in days:
            d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
            if not (self.period_start <= d <= self.window_end()):
                continue
            g_, b_ = self.src.changed_vouchers_on(self.masters, d, current)
            good.extend(g_)
            bad.extend(b_)
        # 2.2.3 (M4): registered post-dated vouchers whose date has arrived - one day request per due date, only
        # those GUIDs taken (the rest of that day is already synced).
        have = {v["guid"] for v in good} | {r.get("source_reference") for r in bad}
        due_seen: set = set()
        for dd in sorted({e["voucher_date"] for e in due}):
            g_, b_ = self.src.day_vouchers(self.masters, date.fromisoformat(dd))
            due_seen.update(v["guid"] for v in g_)
            due_seen.update(r.get("source_reference") for r in b_)
            good.extend(v for v in g_ if v["guid"] in due_guids and v["guid"] not in have)
            bad.extend(r for r in b_ if r.get("source_reference") in due_guids and r.get("source_reference") not in have)
        fetched = {v["guid"] for v in good} | {r.get("source_reference") for r in bad}
        missing = [g for g in changed if g not in fetched]
        if missing:  # deleted / re-dated between the two reads: logged; the manifest retires deletions
            logger.warning(f"INCREMENTAL fy={self.fy.label} {len(missing)} changed voucher(s) not returned by the day "
                           f"requests (deleted or re-dated meanwhile), e.g. {missing[:3]}")
        self._log_rejections(bad)
        kept = self._in_fy(good)
        self._count_extraction(good, bad, kept)
        st = self.upload_vouchers(company_guid, kept)
        unresolved = [u for u in self.quarantine.list_unresolved(self.fy.quarantine_entity)]
        # 2.2.3 (M4): settle the register. Uploaded (or durably queued) -> removed; rejected -> kept and retried next
        # cycle; no longer on its date (deleted / re-dated; a re-dated voucher has a new AlterID) -> removed.
        rejected_now = {u.get("source_reference") for u in unresolved}
        registered = {e["guid"] for e in self.deferred.list(self.fy.label)}
        uploaded_ok = {v["guid"] for v in kept} - rejected_now
        gone = {g for g in due_guids if g not in due_seen and g not in fetched}
        self.deferred.remove(self.fy.label, (uploaded_ok & registered) | gone)
        for g in due_guids & rejected_now:
            self.deferred.note_attempt(self.fy.label, g, "rejected; retried next cycle")
        if gone:
            logger.warning(f"POST_DATED fy={self.fy.label} {len(gone)} registered voucher(s) no longer on their date in Tally "
                           f"(deleted or re-dated), e.g. {sorted(gone)[:3]}")
        # A registered post-dated voucher no longer needs the checkpoint to stay below it: the register brings it in.
        cp_items = [v for v in kept if v.get("alter_id") is not None] + [{"alter_id": a} for _, a in future.values() if a]
        target = _safe_checkpoint_alter_id(cp_items, unresolved, current)
        if not kept and not bad and not future:
            target = current  # nothing new: the checkpoint is not rewritten
        # Batches that failed to upload are in the durable retry queue: advancing is safe.
        if target != current:
            self.checkpoints.update_checkpoint(self.fy.cp_vouchers, alter_id=target, records_count=len(kept))
        stale = self.stale_quarantine()
        if stale:  # 2.2.2 (M1): visible in the log and the heartbeat's last_error, every cycle until resolved
            oldest = stale[0]
            msg = (f"QUARANTINE_STALE fy={self.fy.label}: {len(stale)} voucher(s) quarantined for more than 24 h cap the "
                   f"checkpoint; oldest GUID {oldest.get('source_reference')} (AlterID {oldest.get('alter_id')}, since "
                   f"{oldest.get('first_seen_at')}): {str(oldest.get('error'))[:200]}")
            logger.warning(msg)
            self._record_error(msg)
        self._success("vouchers")
        return {"changed_headers": len(changed), "days": len(days), "extracted": len(good) + len(bad), "validated": len(kept),
                "rejected": len(bad), "outside_fy": len(good) - len(kept), "not_returned": len(missing), **st,
                "checkpoint": target, "quarantine_stale": len(stale),
                "post_dated": {"registered": len(future), "due": len(due_guids), "uploaded": len(uploaded_ok & due_guids),
                               "no_longer_on_date": len(gone), "pending": self.deferred.count(self.fy.label)}}

    def historical_step(self, company_guid: Optional[str]) -> Dict[str, Any]:
        """One bounded unit of work for a historical FY (multi_fy runs it after the live FY's cycle)."""
        if not self.fy.historical:
            raise RuntimeError("historical_step is for historical FYs only")
        self.company_guid = company_guid
        self.apply_scope()
        state = self._load_state()
        if not state.get("completed_at"):
            out = self.initial_load(company_guid, max_days=settings.history_days_per_cycle)
            out["status"] = "LOADING" if out.get("partial") else "LOADED"
            self._publish_counters()
            return out
        out: Dict[str, Any] = {"fy": self.fy.label, "status": "IDLE"}
        if self._due(self.fy.cp_vouchers, timedelta(minutes=settings.history_incremental_minutes), True):
            self.masters = self.src.masters(full_debtors=True)
            out["vouchers"] = self.incremental_vouchers(company_guid)
            out["status"] = "INCREMENTAL"
        if self.manifest_due():
            guids, _ = self.scan_manifest()
            out["manifest"] = self.upload_manifest(company_guid, guids)
        self._publish_counters()
        return out

    def run_sync(self, is_initial: bool = False) -> Dict[str, Any]:
        """The live FY's cycle."""
        started = time.time()
        results: Dict[str, Any] = {"status": "COMPLETED", "agent_version": AGENT_VERSION, "fy": self.fy.label}
        self.auth_error = False
        try:
            results["retry"] = self.process_retry_queue()
        except Exception as ex:
            logger.warning(f"Retry queue error: {ex}")
            self._record_error(f"Retry queue error: {ex}")
        guard = getattr(self.src, "guard", None)
        try:
            if guard is not None:  # the company probe is a Tally request too: breaker, lock, pacing
                company = guard.request("company", self.tally.get_company_info, connection_errors=(TallyConnectionError,))
            else:
                company = self.tally.get_company_info()
        except TallyCoolingDown as tcd:
            logger.warning(f"TALLY_COOLDOWN: {tcd}")
            results["status"] = "TALLY_COOLDOWN"
            self._record_error(str(tcd))
            self._heartbeat("OFFLINE", None, None)
            return results
        except TallyBusy as tb:
            logger.warning(f"TALLY_BUSY: {tb}")
            results["status"] = "TALLY_BUSY"
            self._record_error(str(tb))
            return results
        except TallyConnectionError as tce:
            logger.warning(f"TallyPrime is not reachable: {tce}")
            results["status"] = "TALLY_UNAVAILABLE"
            self._record_error(f"TallyPrime is not reachable: {tce}")
            self._heartbeat("OFFLINE", None, None)
            return results
        if company and company.get("error"):
            results["status"] = company["error"]
            msg = f"{company['error']}: loaded companies {company.get('companies')}; expected GUID {settings.expected_company_guid}"
            logger.error(f"Not syncing - {msg}")
            self._record_error(msg)
            self._heartbeat(company["error"], company.get("name"), company.get("guid"))
            return results
        if not company or not company.get("name"):
            results["status"] = "NO_COMPANY_LOADED"
            self._heartbeat("NO_COMPANY", None, None)
            return results
        name, guid = company["name"], company.get("guid")
        self.company_name, self.company_guid = name, guid
        if hasattr(self.src, "books_from") and getattr(self.src, "books_from", None) is None:
            self.src.books_from = books_from_of(company)
        self._heartbeat("ONLINE", name, guid)
        self.apply_scope()  # before the masters request too (debtor balances are period values)
        if settings.writeback_enabled:
            logger.warning("TALLY_WRITEBACK_ENABLED is set, but agent 2.x performs no write-back; ignoring.")

        try:
            cp_status = self.checkpoint_status()
            results["checkpoint_status"] = cp_status
            if cp_status.startswith("INVALID"):
                raise CheckpointInvalid(f"FY {self.fy.label}: voucher checkpoint {cp_status}; nothing requested, checkpoint unchanged")
            first_run = is_initial or cp_status in ("NEVER_LOADED", "EMPTY_COMPLETION", "IN_PROGRESS")
            if first_run:
                if not self.first_load_approved():
                    raise CheckpointZero(
                        f"FY {self.fy.label}: voucher checkpoint is {cp_status if not is_initial else 'forced initial'}: no "
                        f"incremental is possible and a first load needs explicit approval "
                        f"(FieldTrackTallyAgent.exe approve-first-load {self.fy.label}). Nothing was requested.")
                results["initial_load"] = self.initial_load(guid)
            else:
                dcp = int(self.checkpoints.get_checkpoint(self.fy.cp_debtors).get("last_alter_id") or 0)
                self.masters = self.src.masters(self.masters, debtor_min_alter=dcp, full_debtors=self.masters is None)
                self._success("masters")
                changed = [d for d in self.masters.debtors.values() if (d.get("alter_id") or 0) > dcp]
                if changed:
                    self.backend.sync_ledgers(str(uuid.uuid4()), guid, changed)
                    self.checkpoints.update_checkpoint(self.fy.cp_debtors, alter_id=max(d.get("alter_id") or 0 for d in changed),
                                                       records_count=len(changed))
                results["vouchers"] = self.incremental_vouchers(guid)
                if self.balances_due():
                    results["ledgers"] = self.ledger_snapshot(guid)
                    results["bills"] = self.bills_snapshot(guid)
                    self.checkpoints.update_checkpoint(self.fy.cp_balances, records_count=results["bills"]["bills"])
                if self.manifest_due():
                    # The daemon loop is blocked meanwhile; keep the backend's 180 s online window fed.
                    guids, _ = self.scan_manifest(on_chunk=lambda *_: self._heartbeat("ONLINE", name, guid))
                    results["manifest"] = self.upload_manifest(guid, guids)
        except TallyConnectionError as tce:
            logger.warning(f"Tally stopped answering during the cycle: {tce}")
            results["status"] = "TALLY_UNAVAILABLE"
            self._record_error(f"Tally stopped answering: {tce}")
        except TallyCoolingDown as tcd:
            results["status"] = "TALLY_COOLDOWN"
            self._record_error(str(tcd))
        except TallyBusy as tb:
            results["status"] = "TALLY_BUSY"
            self._record_error(str(tb))
        except CheckpointZero as cz:
            logger.error(f"CHECKPOINT_ZERO: {cz}")
            results["status"] = "CHECKPOINT_ZERO"
            self._record_error(str(cz)[:500])
        except CheckpointInvalid as ci:
            logger.error(f"CHECKPOINT_INVALID: {ci}")
            results["status"] = "CHECKPOINT_INVALID"
            self._record_error(str(ci)[:500])
        except BillsDateInvalid as bdi:
            logger.error(f"BILLS_DATE_INVALID: {bdi}")
            results["status"] = "BILLS_DATE_INVALID"
            self._record_error(str(bdi)[:500])
        except BillsSanityFailed as bsf:
            logger.error(f"BILLS_SANITY_FAILED: {bsf}")
            results["status"] = "BILLS_SANITY_FAILED"
            self._record_error(str(bsf)[:500])
        except tx.UnfilteredRequestRefused as urr:
            logger.error(f"REQUEST_REFUSED: {urr}")
            results["status"] = "REQUEST_REFUSED"
            self._record_error(str(urr)[:500])
        except InitialLoadEmpty as ile:
            logger.error(f"INITIAL_LOAD_EMPTY: {ile}")
            results["status"] = "INITIAL_LOAD_EMPTY"
            self._record_error(f"First load found no voucher: {ile}")
        except ManifestRejected as mr:
            results["status"] = "MANIFEST_REJECTED"
            self._record_error(f"Manifest not applied: {mr}")
        except BalanceCheckFailed as bcf:
            logger.error(f"BALANCE_CHECK_FAILED: {bcf}")
            results["status"] = "BALANCE_CHECK_FAILED"
            self._record_error(str(bcf)[:500])
        except BackendAuthError as bae:
            logger.error(f"Backend rejected the agent credentials: {bae}")
            results["status"] = "AUTH_ERROR"
            self._record_error(f"Backend rejected the agent credentials: {bae}")
        except BackendServerError as bse:
            logger.error(f"Backend error during the cycle: {bse}")
            results["status"] = "BACKEND_ERROR"
            self._record_error(f"Backend error: {bse}")
        if self.auth_error and results["status"] == "COMPLETED":
            results["status"] = "AUTH_ERROR"
        results["counters"] = dict(self.counters)
        if guard is not None:
            results["tally_requests"] = guard.telemetry.summary()
        self._publish_counters()
        results["duration_seconds"] = round(time.time() - started, 2)
        logger.info(f"SYNC_CYCLE_FINISHED v2 {json.dumps(results, default=str)[:2000]}")
        return results

    def _heartbeat(self, status: str, name: Optional[str], guid: Optional[str]) -> None:
        if self.state is not None:
            # Daemon mode: the heartbeat thread is the only sender; just publish the company.
            if self.state.set_company(name, guid):
                logger.info(f"COMPANY name={name} guid={guid}")
            return
        try:
            self.backend.heartbeat(agent_version=AGENT_VERSION, tally_status=status, company_name=name,
                                   company_guid=guid, checkpoints=self.checkpoints.get_all_checkpoints())
        except Exception as ex:
            logger.warning(f"Heartbeat failed: {ex}")
