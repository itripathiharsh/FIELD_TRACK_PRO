"""
Agent 2.1.0: heartbeat thread, independent of the sync loop.

Runs every HEARTBEAT_INTERVAL_SECONDS with its OWN BackendClient and its own store objects (every
store opens a fresh SQLite connection per call), so a sync cycle blocked in a 180 s Tally request,
the first load or the daily manifest never delays it. The heartbeat reports liveness and health
only; data moves exclusively in the sync loop.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from tally_sync_agent.core.agent_state import AgentState, build_health, write_state_file
from tally_sync_agent.core.logger import logger


class HeartbeatThread(threading.Thread):
    def __init__(self, state: AgentState, backend, checkpoints, retry_queue, quarantine,
                 interval_seconds: float, agent_version: str, state_file: Optional[object] = None,
                 on_sent: Optional[Callable[[dict], None]] = None):
        super().__init__(name="ftp-heartbeat", daemon=True)
        self.state = state
        self.backend = backend
        self.checkpoints = checkpoints
        self.retry_queue = retry_queue
        self.quarantine = quarantine
        self.interval = max(float(interval_seconds), 0.01)
        self.agent_version = agent_version
        self.state_file = state_file
        self.on_sent = on_sent
        self.stop_event = threading.Event()
        self.sent = 0

    def beat(self) -> None:
        """One heartbeat. Failures are logged and never stop the thread."""
        try:
            health = build_health(self.state, self.retry_queue, self.quarantine, self.checkpoints)
            if self.state_file is not None:
                try:
                    write_state_file(self.state_file, health)
                except Exception as ex:  # local status file only - never fatal
                    logger.warning(f"Could not write agent state file: {ex}")
            cps = self.checkpoints.get_all_checkpoints()
            cps["_health"] = health
            self.backend.heartbeat(
                agent_version=self.agent_version,
                tally_status=self.state.tally_status(),
                company_name=self.state.company_name,
                company_guid=self.state.company_guid,
                checkpoints=cps,
            )
            self.sent += 1
            if self.on_sent:
                self.on_sent(health)
        except Exception as ex:
            logger.warning(f"Heartbeat failed: {ex}")

    def run(self) -> None:
        logger.info(f"HEARTBEAT_THREAD_STARTED interval={self.interval}s")
        while not self.stop_event.is_set():
            self.beat()
            self.stop_event.wait(self.interval)

    def stop(self) -> None:
        self.stop_event.set()
