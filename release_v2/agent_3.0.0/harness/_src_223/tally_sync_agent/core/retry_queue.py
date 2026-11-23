import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from tally_sync_agent.config.settings import settings
from tally_sync_agent.core.logger import logger


class RetryQueue:
    """
    Durable local queue for storing unsent batches during backend/network outages.
    Implements exponential backoff retries.
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
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_type TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    company_guid TEXT,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            # 2.1.0 columns, added in place to queues created by older agents (nothing is dropped).
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(retry_queue)").fetchall()}
            if "rejected_4xx" not in cols:
                conn.execute("ALTER TABLE retry_queue ADD COLUMN rejected_4xx INTEGER NOT NULL DEFAULT 0")
            if "last_attempt_at" not in cols:
                conn.execute("ALTER TABLE retry_queue ADD COLUMN last_attempt_at TEXT")
            conn.commit()

    def enqueue(
        self,
        batch_type: str,
        batch_id: str,
        company_guid: Optional[str],
        records: List[Dict[str, Any]],
        initial_delay_seconds: int = 60,
    ) -> int:
        """Adds a failed batch to the durable retry queue."""
        now = datetime.now(timezone.utc)
        next_retry = (now + timedelta(seconds=initial_delay_seconds)).isoformat()
        payload_str = json.dumps(records)

        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO retry_queue (batch_type, batch_id, company_guid, payload_json, retry_count, next_retry_at, created_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (batch_type, batch_id, company_guid, payload_str, next_retry, now.isoformat()),
            )
            conn.commit()
            queue_id = cur.lastrowid
            logger.info(f"ENQUEUED_FOR_RETRY id={queue_id} type={batch_type} batch_id={batch_id} records={len(records)}")
            return queue_id

    def get_pending_ready(self) -> List[Dict[str, Any]]:
        """Retrieves items eligible for retry right now."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, batch_type, batch_id, company_guid, payload_json, retry_count
                FROM retry_queue
                WHERE next_retry_at <= ?
                ORDER BY id ASC
                LIMIT 50
                """,
                (now_iso,),
            ).fetchall()

            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "batch_type": r["batch_type"],
                    "batch_id": r["batch_id"],
                    "company_guid": r["company_guid"],
                    "records": json.loads(r["payload_json"]),
                    "retry_count": r["retry_count"],
                })
            return result

    def mark_success(self, queue_id: int) -> None:
        """Removes successfully processed batch from the retry queue."""
        with self._connection() as conn:
            conn.execute("DELETE FROM retry_queue WHERE id = ?", (queue_id,))
            conn.commit()
        logger.info(f"RETRY_SUCCESS queue_id={queue_id}")

    def mark_failure(self, queue_id: int, error_msg: str, rejected: bool = False) -> None:
        """Records a failed attempt and schedules the next one. The item is NEVER deleted here.

        rejected=True: the backend refused the batch itself (HTTP 4xx other than 401/403). It is kept,
        flagged and retried at the maximum interval (1 h) so it is visible and recoverable once fixed;
        it never blocks the other items (each item has its own schedule)."""
        with self._connection() as conn:
            row = conn.execute("SELECT retry_count FROM retry_queue WHERE id = ?", (queue_id,)).fetchone()
            if not row:
                return

            retry_count = (row["retry_count"] or 0) + 1
            backoff_seconds = 3600 if rejected else min(60 * (2 ** (retry_count - 1)), 3600)
            now = datetime.now(timezone.utc)
            next_retry = (now + timedelta(seconds=backoff_seconds)).isoformat()

            conn.execute(
                """
                UPDATE retry_queue
                SET retry_count = ?, next_retry_at = ?, last_error = ?, last_attempt_at = ?,
                    rejected_4xx = CASE WHEN ? THEN 1 ELSE rejected_4xx END
                WHERE id = ?
                """,
                (retry_count, next_retry, str(error_msg)[:500], now.isoformat(), 1 if rejected else 0, queue_id),
            )
            conn.commit()
            logger.warning(
                f"RETRY_FAILED queue_id={queue_id} attempts={retry_count} rejected={rejected} next_retry_in={backoff_seconds}s"
            )

    def health_stats(self) -> Dict[str, Any]:
        """Queue health for the heartbeat / status: pending, oldest age, max attempts, rejected count, last error."""
        with self._connection() as conn:
            agg = conn.execute(
                "SELECT COUNT(*) AS n, MIN(created_at) AS oldest, COALESCE(MAX(retry_count), 0) AS max_attempts, "
                "COALESCE(SUM(rejected_4xx), 0) AS rejected FROM retry_queue"
            ).fetchone()
            last = conn.execute(
                "SELECT last_error FROM retry_queue WHERE last_error IS NOT NULL "
                "ORDER BY COALESCE(last_attempt_at, created_at) DESC, id DESC LIMIT 1"
            ).fetchone()
        oldest_age = None
        if agg["oldest"]:
            oldest_age = int((datetime.now(timezone.utc) - datetime.fromisoformat(agg["oldest"])).total_seconds())
        return {
            "pending": agg["n"] or 0,
            "oldest_age_seconds": oldest_age,
            "max_attempts": agg["max_attempts"] or 0,
            "rejected_4xx": agg["rejected"] or 0,
            "last_error": (last["last_error"][:300] if last and last["last_error"] else None),
        }

    def count_pending(self) -> int:
        """Returns total count of pending items in queue."""
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM retry_queue").fetchone()
            return row["cnt"] if row else 0
