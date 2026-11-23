import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger


class CheckpointManager:
    """
    Persistently manages sync checkpoints in local SQLite storage.
    Ensures checkpoints advance ONLY after successful backend acknowledgement.
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
        """Create tables if not already present."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    entity_type TEXT PRIMARY KEY,
                    last_sync_date TEXT,
                    last_alter_id INTEGER DEFAULT 0,
                    last_successful_sync_at TEXT,
                    total_synced_records INTEGER DEFAULT 0
                )
                """
            )
            conn.commit()

    def get_checkpoint(self, entity_type: str) -> Dict[str, Any]:
        """Retrieves checkpoint details for an entity type."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE entity_type = ?", (entity_type,)
            ).fetchone()
            if row:
                return dict(row)
            return {
                "entity_type": entity_type,
                "last_sync_date": None,
                "last_alter_id": 0,
                "last_successful_sync_at": None,
                "total_synced_records": 0,
            }

    def update_checkpoint(
        self,
        entity_type: str,
        last_sync_date: Optional[str] = None,
        alter_id: Optional[int] = None,
        records_count: int = 0,
    ) -> None:
        """
        Advances the checkpoint.
        MUST ONLY BE CALLED AFTER BACKEND CONFIRMATION.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        current = self.get_checkpoint(entity_type)
        new_total = (current.get("total_synced_records") or 0) + records_count
        new_alter = alter_id if alter_id is not None else current.get("last_alter_id", 0)
        new_date = last_sync_date or current.get("last_sync_date")

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (entity_type, last_sync_date, last_alter_id, last_successful_sync_at, total_synced_records)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_type) DO UPDATE SET
                    last_sync_date = excluded.last_sync_date,
                    last_alter_id = excluded.last_alter_id,
                    last_successful_sync_at = excluded.last_successful_sync_at,
                    total_synced_records = excluded.total_synced_records
                """,
                (entity_type, new_date, new_alter, now_iso, new_total),
            )
            conn.commit()

        logger.info(
            f"CHECKPOINT_ADVANCED entity={entity_type} date={new_date} alter_id={new_alter} total={new_total}"
        )

    def get_all_checkpoints(self) -> Dict[str, Any]:
        """Returns all entity checkpoints as a dictionary."""
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM checkpoints").fetchall()
            return {r["entity_type"]: dict(r) for r in rows}
