import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger


class QuarantineStore:
    """
    Durable record of records that failed VALIDATION (e.g. missing customer_name) and were
    therefore never sent to the backend at all.

    This is intentionally separate from RetryQueue: RetryQueue holds already-valid batches
    that failed to *upload* (network/backend errors) and are automatically replayed by
    SyncEngine. Quarantine holds records that never passed validation in the first place -
    there is nothing to "retry" against the backend until the underlying data or extraction
    logic is fixed, so these are surfaced for visibility/reporting instead.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else settings.db_path
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS validation_quarantine (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    alter_id INTEGER,
                    error TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    resolved_at TEXT,
                    UNIQUE(entity_type, source_reference)
                )
                """
            )
            conn.commit()

    def add(
        self,
        entity_type: str,
        source_reference: str,
        alter_id: Optional[int],
        error: str,
        record: Dict[str, Any],
    ) -> None:
        """
        Records a validation failure. Safe to call repeatedly for the same
        (entity_type, source_reference) across sync cycles - it updates the existing row
        (last_seen_at, error, occurrences) instead of creating a duplicate entry.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(record, default=str)

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO validation_quarantine
                    (entity_type, source_reference, alter_id, error, record_json, first_seen_at, last_seen_at, occurrences)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(entity_type, source_reference) DO UPDATE SET
                    alter_id = excluded.alter_id,
                    error = excluded.error,
                    record_json = excluded.record_json,
                    last_seen_at = excluded.last_seen_at,
                    occurrences = occurrences + 1,
                    resolved_at = NULL
                """,
                (entity_type, source_reference, alter_id, error, payload, now, now),
            )
            conn.commit()
        logger.warning(
            f"QUARANTINED entity={entity_type} source_reference={source_reference} alter_id={alter_id} error={error}"
        )

    def mark_resolved(self, entity_type: str, source_reference: str) -> None:
        """Marks a previously quarantined record as resolved (e.g. it later synced successfully)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE validation_quarantine SET resolved_at = ? WHERE entity_type = ? AND source_reference = ?",
                (now, entity_type, source_reference),
            )
            conn.commit()

    def list_unresolved(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns quarantined records that have not been marked resolved."""
        with self._connection() as conn:
            if entity_type:
                rows = conn.execute(
                    "SELECT * FROM validation_quarantine WHERE resolved_at IS NULL AND entity_type = ? ORDER BY id ASC",
                    (entity_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM validation_quarantine WHERE resolved_at IS NULL ORDER BY id ASC"
                ).fetchall()
            return [dict(r) for r in rows]

    def count_unresolved(self, entity_type: Optional[str] = None) -> int:
        with self._connection() as conn:
            if entity_type:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM validation_quarantine WHERE resolved_at IS NULL AND entity_type = ?",
                    (entity_type,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM validation_quarantine WHERE resolved_at IS NULL"
                ).fetchone()
            return row["cnt"] if row else 0
