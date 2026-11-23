"""
Agent 2.2.1 - protection of TallyPrime against our own load (B2, B5, B8, B12, items 10-12).

Every Tally request of the 2.x engine and of validate-fy goes through TallyGuard.request():

1. CIRCUIT BREAKER (persisted per agent folder, survives restarts): after a failed / timed-out request the
   breaker opens for a cool-down (180 s, doubling up to 30 min). While open NO request is sent - the cycle
   ends with TALLY_COOLDOWN. When the cool-down ends, the first request must be a small probe that answers
   within PROBE_MAX_SECONDS; a slow probe re-opens the breaker. A timeout therefore never causes requests
   to pile up behind a request Tally is still computing (18-Nov: 3 timeouts in a row).
2. MACHINE-WIDE REQUEST LOCK: a named mutex shared by every 2.2.1 process on the machine (production and
   staging agents, validate-fy, dry-run): only one of OUR requests is ever inside Tally at a time. Waiting
   longer than LOCK_WAIT_SECONDS ends the caller's unit of work with TallyBusy (no request sent).
   Agents older than 2.2.1 do not take this lock.
3. DUTY-CYCLE PACING: after each request, wait max(min_pause, duty_factor x its duration), so our share of
   Tally's time stays <= 1 / (1 + duty_factor) (50% with the default 1.0).
4. TELEMETRY: every request's kind, duration and size go to the log and to a rolling summary
   (count, total, max, requests over the 15 s target) published in health.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from tally_sync_agent.core.logger import logger

REQUEST_MUTEX_NAME = "Global\\FieldTrackTally_RequestLock_v1"
VALIDATE_MUTEX_NAME = "Global\\FieldTrackTally_ValidateFy_v1"
TARGET_REQUEST_SECONDS = 15.0


class TallyCoolingDown(Exception):
    """The breaker is open: no request is sent until the cool-down ends."""


class TallyBusy(Exception):
    """Another FieldTrack process held the machine-wide request lock for too long: nothing was sent."""


# ---------------------------------------------------------------------------- machine-wide lock

class _NamedMutex:
    """A Windows named mutex with OWNERSHIP semantics (WaitForSingleObject); a lock file elsewhere.
    The OS releases it if the owning process dies, so a crash never leaves Tally locked."""

    def __init__(self, name: str):
        self.name = name
        self._h = None
        self._fh = None
        self._win = sys.platform == "win32"

    def acquire(self, timeout_s: float) -> bool:
        if self._win:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.restype = wintypes.HANDLE
            k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k.WaitForSingleObject.restype = wintypes.DWORD
            if self._h is None:
                h = k.CreateMutexW(None, False, self.name)
                if not h:
                    raise ctypes.WinError(ctypes.get_last_error())
                self._h = h
            r = k.WaitForSingleObject(self._h, int(max(0.0, timeout_s) * 1000))
            return r in (0x0, 0x80)  # WAIT_OBJECT_0 / WAIT_ABANDONED (previous owner died: still ours now)
        import fcntl  # pragma: no cover - non-Windows test environments
        import tempfile
        path = Path(tempfile.gettempdir()) / (self.name.replace("\\", "_") + ".lock")
        self._fh = open(path, "a+")
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.2)

    def release(self) -> None:
        if self._win and self._h is not None:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.ReleaseMutex.argtypes = [wintypes.HANDLE]
            k.ReleaseMutex(self._h)
        elif self._fh is not None:  # pragma: no cover
            import fcntl
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

    def close(self) -> None:
        if self._win and self._h is not None:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            k.CloseHandle(self._h)
            self._h = None


class ExclusiveJobLock:
    """Non-blocking exclusive lock for a whole job (validate-fy): a second validation refuses to start."""

    def __init__(self, name: str = VALIDATE_MUTEX_NAME):
        self._m = _NamedMutex(name)
        self.held = False

    def acquire(self) -> bool:
        self.held = self._m.acquire(0)
        return self.held

    def release(self) -> None:
        if self.held:
            self._m.release()
            self.held = False
        self._m.close()


# ---------------------------------------------------------------------------- breaker

@dataclass
class BreakerState:
    open_until: float = 0.0          # epoch seconds
    consecutive_failures: int = 0
    last_failure: str = ""
    last_failure_at: str = ""
    half_open: bool = False          # cool-down over, the next request is the probe


class CircuitBreaker:
    """3.0: persisted in the agent's SQLite database (key tally_breaker) when a store is given; a 2.2.x
    tally_breaker.json (`path`) is migrated into it on first use. Without a store, `path` is used as before."""

    KEY = "tally_breaker"

    def __init__(self, path: Optional[Path], base_cooldown: float = 180.0, max_cooldown: float = 1800.0,
                 clock: Callable[[], float] = time.time, store: Any = None):
        self.path = path
        self.store = store
        self.base = base_cooldown
        self.max = max_cooldown
        self.clock = clock
        self.state = self._load()

    def _load(self) -> BreakerState:
        try:
            if self.store is not None:
                raw = self.store.get(self.KEY, None, legacy_file=self.path)
                return BreakerState(**raw) if raw else BreakerState()
            if self.path and self.path.exists():
                return BreakerState(**json.loads(self.path.read_text(encoding="utf-8")))
        except Exception as ex:  # a corrupt file must not disable the agent; start closed but log it
            logger.warning(f"TALLY_BREAKER state unreadable ({ex}); starting closed")
        return BreakerState()

    def _save(self) -> None:
        if self.store is not None:
            self.store.set(self.KEY, self.state.__dict__)
            return
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state.__dict__), encoding="utf-8")
        tmp.replace(self.path)

    def is_open(self) -> bool:
        return self.clock() < self.state.open_until

    def remaining(self) -> float:
        return max(0.0, self.state.open_until - self.clock())

    def check(self) -> None:
        if self.is_open():
            raise TallyCoolingDown(f"Tally cool-down: {self.remaining():.0f} s left after "
                                   f"{self.state.consecutive_failures} failure(s) ({self.state.last_failure[:120]})")
        if self.state.consecutive_failures and not self.state.half_open:
            self.state.half_open = True
            self._save()

    def trip(self, reason: str) -> float:
        self.state.consecutive_failures += 1
        cool = min(self.max, self.base * (2 ** (self.state.consecutive_failures - 1)))
        self.state.open_until = self.clock() + cool
        self.state.last_failure = reason
        self.state.last_failure_at = datetime.now(timezone.utc).isoformat()
        self.state.half_open = False
        self._save()
        logger.warning(f"TALLY_BREAKER_OPEN for {cool:.0f} s (failure {self.state.consecutive_failures}): {reason[:200]}")
        return cool

    def success(self) -> None:
        if self.state.consecutive_failures or self.state.open_until:
            logger.info("TALLY_BREAKER_CLOSED: Tally answered normally again")
        self.state = BreakerState()
        self._save()


# ---------------------------------------------------------------------------- guard

@dataclass
class Telemetry:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0
    max_kind: str = ""
    over_target: int = 0
    failures: int = 0
    last: Dict[str, Any] = field(default_factory=dict)
    rows: list = field(default_factory=list)      # (start epoch, seconds, kind, bytes), last 50,000 requests

    def record(self, kind: str, seconds: float, size: int, start: float = 0.0) -> None:
        self.rows.append((start, round(seconds, 3), kind, size))
        if len(self.rows) > 50000:
            del self.rows[:10000]
        self.count += 1
        self.total_seconds += seconds
        if seconds > self.max_seconds:
            self.max_seconds, self.max_kind = seconds, kind
        if seconds > TARGET_REQUEST_SECONDS:
            self.over_target += 1
        self.last = {"kind": kind, "seconds": round(seconds, 2), "bytes": size}

    def summary(self) -> Dict[str, Any]:
        return {"requests": self.count, "total_seconds": round(self.total_seconds, 1), "max_seconds": round(self.max_seconds, 2),
                "max_kind": self.max_kind, "over_15s": self.over_target, "failures": self.failures, "last": self.last}


class TallyGuard:
    """One per process (see guard_for()). Thread-safe; the request lock is machine-wide."""

    PROBE_MAX_SECONDS = 5.0

    def __init__(self, state_dir: Optional[Path], duty_factor: float = 1.0, min_pause: float = 2.0,
                 lock_wait: float = 300.0, base_cooldown: float = 180.0, max_cooldown: float = 1800.0,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time,
                 mutex_name: str = REQUEST_MUTEX_NAME):
        self.duty_factor = duty_factor
        self.min_pause = min_pause
        self.lock_wait = lock_wait
        self.sleep = sleep
        store = None
        if state_dir:
            from tally_sync_agent.core.state_store import KvStore  # the agent's one SQLite database
            store = KvStore(Path(state_dir) / "sync_agent.db")
        self.breaker = CircuitBreaker(Path(state_dir) / "tally_breaker.json" if state_dir else None,
                                      base_cooldown, max_cooldown, clock, store=store)
        self.telemetry = Telemetry()
        self._mutex = _NamedMutex(mutex_name)
        self._local = threading.Lock()

    def request(self, kind: str, call: Callable[[], Any], size_of: Callable[[Any], int] = lambda r: 0,
                connection_errors: tuple = ()) -> Any:
        """Run one Tally request under the breaker, the machine-wide lock and the duty cycle."""
        with self._local:
            self.breaker.check()                        # TallyCoolingDown: nothing sent
            probing = self.breaker.state.half_open
            if not self._mutex.acquire(self.lock_wait):
                raise TallyBusy(f"another FieldTrack process held the Tally request lock for over {self.lock_wait:.0f} s")
            t0 = time.monotonic()
            wall0 = time.time()
            try:
                result = call()
            except connection_errors as ex:
                dur = time.monotonic() - t0
                self._mutex.release()
                self.telemetry.failures += 1
                logger.warning(f"TALLY_REQUEST kind={kind} FAILED after {dur:.1f}s: {ex}")
                self.breaker.trip(f"{kind}: {ex}")
                raise
            except BaseException:
                self._mutex.release()
                raise
            dur = time.monotonic() - t0
            self._mutex.release()
            size = 0
            try:
                size = int(size_of(result) or 0)
            except Exception:
                pass
            self.telemetry.record(kind, dur, size, wall0)
            logger.info(f"TALLY_REQUEST kind={kind} seconds={dur:.2f} bytes={size}"
                        + (" OVER_15S" if dur > TARGET_REQUEST_SECONDS else ""))
            if probing and dur > self.PROBE_MAX_SECONDS:
                self.breaker.trip(f"{kind}: Tally still slow after the cool-down ({dur:.1f} s > {self.PROBE_MAX_SECONDS:.0f} s)")
            else:
                self.breaker.success()
            pause = max(self.min_pause, self.duty_factor * dur)
            self.sleep(pause)                           # duty cycle: our share of Tally's time stays bounded
            return result


_GUARDS: Dict[str, TallyGuard] = {}


def guard_for(state_dir: Path, **kw) -> TallyGuard:
    """The process-wide guard for an agent folder (one breaker file per folder)."""
    key = str(Path(state_dir).resolve())
    if key not in _GUARDS:
        _GUARDS[key] = TallyGuard(Path(state_dir), **kw)
    return _GUARDS[key]
