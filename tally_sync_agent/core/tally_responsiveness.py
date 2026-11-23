"""
Agent 2.2.1 (B8) - samples whether TallyPrime's window is responding, once per second, in a background thread.

Windows only (IsHungAppWindow: true when a window has not processed messages for 5 s - the same signal as
Task Manager's / PowerShell's "Not Responding"). Elsewhere, or when no tally.exe window is found, samples
are recorded as -1 (unknown) and the report says NOT VERIFIED.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _tally_pids() -> List[int]:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq tally.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower().strip('"') == "tally.exe":
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def _hung_state(pids: List[int]) -> int:
    """1 responding, 0 not responding (any visible top-level window of tally.exe hung), -1 unknown."""
    if sys.platform != "win32" or not pids:
        return -1
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    found, hung = [False], [False]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            found[0] = True
            if user32.IsHungAppWindow(hwnd):
                hung[0] = True
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found[0]:
        return -1
    return 0 if hung[0] else 1


class ResponsivenessSampler:
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.samples: List[Tuple[float, int]] = []
        self._stop = threading.Event()
        self._t: Optional[threading.Thread] = None
        self._pids: List[int] = []

    def start(self) -> "ResponsivenessSampler":
        self._pids = _tally_pids()
        self._t = threading.Thread(target=self._run, name="tally-responsiveness", daemon=True)
        self._t.start()
        return self

    def _run(self) -> None:
        n = 0
        while not self._stop.is_set():
            if n % 60 == 0 and not self._pids:
                self._pids = _tally_pids()
            try:
                v = _hung_state(self._pids)
            except Exception:
                v = -1
            self.samples.append((time.time(), v))
            n += 1
            self._stop.wait(self.interval)

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        if self._t:
            self._t.join(5)
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        known = [(t, v) for t, v in self.samples if v >= 0]
        stretches, cur = [], None
        for t, v in self.samples:
            if v == 0 and cur is None:
                cur = t
            elif v != 0 and cur is not None:
                stretches.append((t - cur, cur))
                cur = None
        if cur is not None and self.samples:
            stretches.append((self.samples[-1][0] - cur, cur))
        longest = max((s for s, _ in stretches), default=0.0)
        return {"samples": len(self.samples), "known_samples": len(known),
                "verified": bool(known) and len(known) >= 0.9 * max(1, len(self.samples)),
                "not_responding_stretches": len(stretches), "longest_not_responding_seconds": round(longest, 1),
                "worst": [{"seconds": round(s, 1), "from_utc": datetime.fromtimestamp(a, timezone.utc).isoformat()}
                          for s, a in sorted(stretches, reverse=True)[:10]]}
