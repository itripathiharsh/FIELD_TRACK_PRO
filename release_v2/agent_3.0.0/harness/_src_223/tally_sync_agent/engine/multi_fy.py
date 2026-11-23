"""
Agent 2.2.0 - one daemon cycle across financial years.

* The LIVE FY (today's, IST) runs exactly as the single-FY 2.x engine, with the 2.1.x state names.
* A HISTORICAL FY runs only when it is listed in HISTORY_UPLOAD (empty by default) AND the backend
  reports `history_safe` (backend B1/B4 deployed). It runs after the live FY's work, a bounded
  amount per cycle, with its own source, checkpoints, quarantine, retry type and state file.
  An exception in one historical FY is recorded for that FY only; it never touches the live FY
  or another historical FY.
* A configuration the agent cannot interpret safely (today's FY not configured, SYNC_FROM_DATE not
  the live FY start, HISTORY_UPLOAD outside FINANCIAL_YEARS) stops syncing with FY_CONFIG_ERROR;
  the heartbeat keeps reporting it.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tally_sync_agent.config.fiscal import FyConfigError, build_contexts, ist_today
from tally_sync_agent.config.settings import AGENT_VERSION, DATA_DIR, settings
from tally_sync_agent.core.backend_client import BackendClient
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.core.tally_guard import TallyBusy, TallyCoolingDown
from tally_sync_agent.engine.sync_engine_v2 import SyncEngineV2, TallyV2Source, default_guard


class MultiFySync:
    def __init__(self, state: Optional[Any] = None, today: Callable[[], date] = ist_today,
                 tally_client: Optional[TallyClient] = None, backend_client: Optional[BackendClient] = None,
                 checkpoint_manager: Optional[CheckpointManager] = None, retry_queue: Optional[RetryQueue] = None,
                 quarantine_store: Optional[QuarantineStore] = None, data_dir: Optional[Path] = None,
                 source_factory: Optional[Callable[[], Any]] = None):
        self.state = state
        self.today = today
        self.tally = tally_client or TallyClient()
        self.backend = backend_client or BackendClient()
        shared = dict(tally_client=self.tally, backend_client=self.backend,
                      checkpoint_manager=checkpoint_manager or CheckpointManager(),
                      retry_queue=retry_queue or RetryQueue(), quarantine_store=quarantine_store or QuarantineStore(),
                      data_dir=data_dir, today=today, state=state)
        guard = default_guard(Path(data_dir) if data_dir else DATA_DIR)  # one breaker / lock / pacing for every FY
        make_source = source_factory or (lambda: TallyV2Source(self.tally, settings.day_request_pause_seconds, guard=guard))
        self.config_error: Optional[str] = None
        self.live: Optional[SyncEngineV2] = None
        self.history: List[SyncEngineV2] = []
        self._history_safe: Optional[bool] = None
        try:
            ctx = build_contexts(settings.financial_years, settings.sync_from_date, settings.history_upload, today())
        except FyConfigError as ex:
            self.config_error = str(ex)
            logger.error(f"FY_CONFIG_ERROR: {ex}")
            return
        self.live = SyncEngineV2(source=make_source(), fy=ctx["live"], **shared)
        self.history = [SyncEngineV2(source=make_source(), fy=c, **shared) for c in ctx["historical"]]
        logger.info(f"FY setup: live={ctx['live'].label} configured={[f.label for f in ctx['configured']]} "
                    f"history_upload={[e.fy.label for e in self.history] or 'none (disabled)'}")

    def _backend_history_safe(self) -> bool:
        """Asked once per process: the backend must declare that historical rows cannot create pending-close
        periods, move live openings or distort dashboards (B1/B4). An older backend answers 404 -> not safe."""
        if self._history_safe is None:
            try:
                caps = self.backend.get_capabilities() or {}
                self._history_safe = bool(caps.get("history_safe"))
            except Exception as ex:
                logger.warning(f"Backend capabilities unavailable ({ex}); historical upload stays blocked")
                self._history_safe = False
        return self._history_safe

    def run_cycle(self) -> Dict[str, Any]:
        if self.config_error:
            if self.state is not None:
                self.state.record_error(f"FY configuration: {self.config_error}")
            return {"status": "FY_CONFIG_ERROR", "error": self.config_error, "agent_version": AGENT_VERSION}
        results = self.live.run_sync()
        if not self.history or results.get("status") != "COMPLETED":
            return results
        if not self._backend_history_safe():
            msg = "historical upload enabled but the backend does not report history_safe (B1/B4 not deployed): skipped"
            logger.error(f"HISTORY_BLOCKED {msg}")
            if self.state is not None:
                self.state.record_error(msg)
            results["history"] = {"blocked": msg}
            return results
        hist: Dict[str, Any] = {}
        for eng in self.history:
            eng.company_name = self.live.company_name
            if hasattr(eng.src, 'books_from') and hasattr(self.live.src, 'books_from'):
                eng.src.books_from = self.live.src.books_from
            try:
                hist[eng.fy.label] = eng.historical_step(self.live.company_guid)
            except (TallyConnectionError, TallyCoolingDown, TallyBusy) as ex:
                hist[eng.fy.label] = {"status": "TALLY_UNAVAILABLE", "error": str(ex)}
                break  # Tally is down / cooling down for every FY: never retried here
            except Exception as ex:  # isolated: recorded for this FY only
                logger.error(f"HISTORY fy={eng.fy.label} failed: {type(ex).__name__}: {ex}")
                hist[eng.fy.label] = {"status": type(ex).__name__, "error": str(ex)[:500]}
                if self.state is not None:
                    self.state.record_error(f"FY {eng.fy.label}: {type(ex).__name__}: {str(ex)[:300]}")
            if self.state is not None and hasattr(self.state, "set_fy"):
                self.state.set_fy(eng.fy.label, {"status": hist[eng.fy.label].get("status")})
        results["history"] = hist
        return results
