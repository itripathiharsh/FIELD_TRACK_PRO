"""
Agent 3.0 - the agent's small state, in the SAME SQLite database as the checkpoints, the retry queue and the
quarantine (data/sync_agent.db). Before 3.0 this state lived in separate JSON files:

  initial_load_v2.json / initial_load_fy<label>.json   first-load progress           -> key initial_load:<label>
  tally_breaker.json                                    Tally circuit breaker         -> key tally_breaker
  agent_state.json                                      last health (status command)  -> key agent_health
  approve_first_load_<label>.json                       first-load approval           -> key approve_first_load:<label>
  validation_fy<label>.json                             first-load reconciliation     -> key validation:<label>

`get(key, legacy_file=...)` migrates a legacy file the first time the key is read: its JSON is copied into the
table and the file is renamed to <name>.migrated-3.0 (kept, never deleted), so an upgrade loses nothing and a
rollback to 2.2.x can rename it back.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger

MIGRATED_SUFFIX = ".migrated-3.0"


class KvStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS agent_kv (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, "
                         "updated_at TEXT NOT NULL)")
            conn.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield conn
        finally:
            conn.close()

    def get(self, key: str, default: Any = None, legacy_file: Optional[Path] = None) -> Any:
        with self._connection() as conn:
            row = conn.execute("SELECT value_json FROM agent_kv WHERE key = ?", (key,)).fetchone()
        if row is not None:
            try:
                return json.loads(row[0])
            except ValueError:
                logger.error(f"STATE_UNREADABLE key={key}: stored value is not JSON; treated as absent")
                return default
        if legacy_file is not None and Path(legacy_file).exists():
            p = Path(legacy_file)
            try:
                value = json.loads(p.read_text(encoding="utf-8"))
            except ValueError as ex:
                logger.error(f"STATE_MIGRATION key={key}: {p.name} is not JSON ({ex}); left in place, not migrated")
                return default
            self.set(key, value)
            try:
                p.replace(p.with_name(p.name + MIGRATED_SUFFIX))
            except OSError as ex:
                logger.warning(f"STATE_MIGRATION key={key}: copied, but {p.name} could not be renamed ({ex})")
            logger.info(f"STATE_MIGRATED key={key} from {p.name} (file kept as {p.name}{MIGRATED_SUFFIX})")
            return value
        return default

    def set(self, key: str, value: Any) -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO agent_kv (key, value_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE "
                         "SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                         (key, json.dumps(value, default=str), datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def delete(self, key: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM agent_kv WHERE key = ?", (key,))
            conn.commit()

    def exists(self, key: str, legacy_file: Optional[Path] = None) -> bool:
        return self.get(key, None, legacy_file) is not None

    def all(self, prefix: str = "") -> Dict[str, Any]:
        with self._connection() as conn:
            rows = conn.execute("SELECT key, value_json FROM agent_kv WHERE key LIKE ? ORDER BY key",
                                (prefix.replace("%", "") + "%",)).fetchall()
        out = {}
        for k, v in rows:
            try:
                out[k] = json.loads(v)
            except ValueError:
                out[k] = None
        return out
