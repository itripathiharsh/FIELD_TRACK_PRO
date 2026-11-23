"""
Agent 2.1.0: shared run state between the sync loop and the heartbeat thread.

The sync loop (engine) only PUBLISHES here (phase, cycle start/end, per-stream success, errors,
company). The heartbeat thread only READS here and is the single sender of heartbeats in daemon
mode, so a long extraction can never starve the heartbeat and two senders never race.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STREAMS = ("vouchers", "masters", "ledgers", "bills", "manifest", "reconcile")
MAX_ERROR_CHARS = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_error(message: Any, secrets: tuple = ()) -> str:
    """Truncate to 300 chars and blank out any configured secret value (agent key) if it appears."""
    text = str(message)
    for s in secrets:
        if s and len(s) >= 6:
            text = text.replace(s, "[REDACTED]")
    return text[:MAX_ERROR_CHARS]


class AgentState:
    def __init__(self, instance: str = "default", interval_seconds: int = 300, agent_version: str = "",
                 secrets: tuple = ()):
        self._lock = threading.Lock()
        self._secrets = secrets
        self.instance = instance
        self.interval_seconds = interval_seconds
        self.agent_version = agent_version
        self.phase = "IDLE"
        self.phase_detail = ""
        self.cycle_started_at: Optional[datetime] = None
        self.last_cycle_completed_at: Optional[str] = None
        self.last_cycle_status: Optional[str] = None
        self.last_cycle_duration_seconds: Optional[float] = None
        self.last_success: Dict[str, Optional[str]] = {s: None for s in STREAMS}
        self.last_error: Optional[Dict[str, str]] = None
        self.company_name: Optional[str] = None
        self.company_guid: Optional[str] = None
        self.company_logged = False
        self.financial_years: Dict[str, Dict[str, Any]] = {}  # 2.2.0: per-FY status and counters

    # ---- published by the sync loop -----------------------------------------------------------
    def set_phase(self, phase: str, detail: str = "") -> None:
        with self._lock:
            self.phase, self.phase_detail = phase, detail

    def cycle_start(self) -> None:
        with self._lock:
            self.cycle_started_at = datetime.now(timezone.utc)
            self.phase, self.phase_detail = "CYCLE", ""

    def cycle_end(self, status: str, duration_seconds: float) -> None:
        with self._lock:
            self.cycle_started_at = None
            self.last_cycle_completed_at = _now()
            self.last_cycle_status = status
            self.last_cycle_duration_seconds = round(duration_seconds, 2)
            self.phase, self.phase_detail = "IDLE", ""

    def mark_success(self, *streams: str) -> None:
        with self._lock:
            ts = _now()
            for s in streams:
                if s in self.last_success:
                    self.last_success[s] = ts

    def record_error(self, message: Any) -> None:
        with self._lock:
            self.last_error = {"at": _now(), "message": sanitize_error(message, self._secrets)}

    def set_company(self, name: Optional[str], guid: Optional[str]) -> bool:
        """-> True the first time a company is known (so the caller can log it once)."""
        with self._lock:
            if name:
                self.company_name, self.company_guid = name, guid
            first = bool(name) and not self.company_logged
            if first:
                self.company_logged = True
            return first

    def set_fy(self, label: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self.financial_years.setdefault(label, {}).update(data)

    # ---- read by the heartbeat thread ---------------------------------------------------------
    def tally_status(self) -> str:
        """Value for the heartbeat's existing `tally_status` field (unchanged meaning for the backend)."""
        with self._lock:
            if self.phase == "INITIAL_LOAD":
                return "INITIAL_LOAD"
            if self.last_cycle_status is None:
                return "STARTING"
            return "ONLINE" if self.last_cycle_status == "COMPLETED" else self.last_cycle_status

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            running = None
            if self.cycle_started_at:
                running = int((datetime.now(timezone.utc) - self.cycle_started_at).total_seconds())
            return {
                "instance": self.instance,
                "agent_version": self.agent_version,
                "phase": self.phase,
                "phase_detail": self.phase_detail,
                "cycle_started_at": self.cycle_started_at.isoformat() if self.cycle_started_at else None,
                "cycle_running_seconds": running if running is not None else 0,
                "last_cycle_completed_at": self.last_cycle_completed_at,
                "last_cycle_status": self.last_cycle_status,
                "last_cycle_duration_seconds": self.last_cycle_duration_seconds,
                "last_success": dict(self.last_success),
                "last_error": dict(self.last_error) if self.last_error else None,
                "interval_seconds": self.interval_seconds,
                "company_name": self.company_name,
                "company_guid": self.company_guid,
                "financial_years": {k: dict(v) for k, v in self.financial_years.items()},
            }


def _stale_count(entries: List[Dict[str, Any]], hours: float = 24.0) -> int:
    """2.2.2 (M1): quarantine entries (any FY) first seen more than `hours` ago."""
    limit = datetime.now(timezone.utc) - timedelta(hours=hours)
    n = 0
    for q in entries:
        try:
            seen = datetime.fromisoformat(str(q.get("first_seen_at")))
        except ValueError:
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        n += seen < limit
    return n


def build_health(state: AgentState, retry_queue, quarantine, checkpoints=None) -> Dict[str, Any]:
    """The `_health` object of contract C2. Missing per-stream success times fall back to the
    checkpoint table (so a freshly restarted agent still reports when each stream last succeeded)."""
    snap = state.snapshot()
    last_success = dict(snap["last_success"])
    if checkpoints is not None:
        cps = checkpoints.get_all_checkpoints()
        fallback = {"vouchers": "vouchers_v2", "masters": "debtors_v2", "ledgers": "balances_v2",
                    "bills": "balances_v2", "manifest": "manifest_v2", "reconcile": "reconcile_hourly_v3"}
        for stream, cp in fallback.items():
            if not last_success.get(stream):
                last_success[stream] = (cps.get(cp) or {}).get("last_successful_sync_at")
    unresolved = quarantine.list_unresolved("vouchers")
    by_entity: Dict[str, int] = {}
    for q in quarantine.list_unresolved():
        by_entity[q.get("entity_type") or "?"] = by_entity.get(q.get("entity_type") or "?", 0) + 1
    return {
        "instance": snap["instance"],
        "agent_version": snap["agent_version"],
        "phase": snap["phase"],
        "phase_detail": snap["phase_detail"],
        "cycle_started_at": snap["cycle_started_at"],
        "cycle_running_seconds": snap["cycle_running_seconds"],
        "last_cycle_completed_at": snap["last_cycle_completed_at"],
        "last_cycle_status": snap["last_cycle_status"],
        "last_cycle_duration_seconds": snap["last_cycle_duration_seconds"],
        "last_success": last_success,
        "retry_queue": retry_queue.health_stats(),
        "quarantine": {"unresolved": len(unresolved),
                       "oldest_guid": unresolved[0].get("source_reference") if unresolved else None,
                       "oldest_first_seen_at": unresolved[0].get("first_seen_at") if unresolved else None,
                       "stale_over_24h": _stale_count(quarantine.list_unresolved()),
                       "by_fy_entity": by_entity},
        "financial_years": snap.get("financial_years", {}),
        "last_error": snap["last_error"],
        "interval_seconds": snap["interval_seconds"],
    }


HEALTH_KEY = "agent_health"


def write_state_file(target, health: Dict[str, Any]) -> None:
    """Local copy of the last health object, read by the `status` command. 3.0: `target` is the agent's KvStore (key
    agent_health in the SQLite database); a Path still writes the 2.x JSON file (tests / tools)."""
    rec = {"written_at": _now(), "health": health}
    if hasattr(target, "set"):
        target.set(HEALTH_KEY, rec)
        return
    path = Path(target)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(path)
