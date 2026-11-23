"""
Agent 2.2.3 (M4): durable register of POST-DATED vouchers.

The live FY's incremental reads vouchers dated up to TODAY (the window end), because a voucher dated in the future
does not belong in today's balances. A voucher entered today but dated later (a post-dated cheque receipt, an
advance-dated invoice) would otherwise be lost: the checkpoint moves past its AlterID with later vouchers, and when
its date arrives its AlterID is unchanged, so no incremental ever returns it.

Each such voucher is recorded here (per FY: GUID, voucher date, AlterID) the moment its header is seen. When its
date arrives the agent reads that one day and uploads it; the entry is removed only once the upload succeeded (or
went to the durable retry queue), or once Tally no longer holds the voucher on that date (deleted / re-dated: a
re-dated voucher carries a new AlterID and is seen again by the normal incremental).

Same SQLite file as the checkpoints, retry queue and quarantine.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from tally_sync_agent.config.settings import settings


class DeferredStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or settings.db_path)
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
                CREATE TABLE IF NOT EXISTS deferred_vouchers (
                    fy TEXT NOT NULL,
                    guid TEXT NOT NULL,
                    voucher_date TEXT NOT NULL,
                    alter_id INTEGER NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    PRIMARY KEY (fy, guid)
                )
                """
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS deferred_scans (fy TEXT PRIMARY KEY, scanned_at TEXT NOT NULL, through TEXT NOT NULL)"
            )
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert(self, fy: str, guid: str, voucher_date: str, alter_id: int) -> None:
        """Record (or update: a post-dated voucher altered again keeps one row) a post-dated voucher."""
        now = self._now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO deferred_vouchers (fy, guid, voucher_date, alter_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fy, guid) DO UPDATE SET
                    voucher_date = excluded.voucher_date,
                    alter_id = MAX(deferred_vouchers.alter_id, excluded.alter_id),
                    last_seen_at = excluded.last_seen_at
                """,
                (fy, guid, voucher_date, int(alter_id or 0), now, now),
            )
            conn.commit()

    def due(self, fy: str, through: str) -> List[Dict[str, Any]]:
        """Entries of this FY whose voucher date is on or before `through` (YYYY-MM-DD)."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deferred_vouchers WHERE fy = ? AND voucher_date <= ? ORDER BY voucher_date, guid",
                (fy, through),
            ).fetchall()
        return [dict(r) for r in rows]

    def list(self, fy: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            if fy is None:
                rows = conn.execute("SELECT * FROM deferred_vouchers ORDER BY fy, voucher_date, guid").fetchall()
            else:
                rows = conn.execute("SELECT * FROM deferred_vouchers WHERE fy = ? ORDER BY voucher_date, guid", (fy,)).fetchall()
        return [dict(r) for r in rows]

    def count(self, fy: Optional[str] = None) -> int:
        return len(self.list(fy))

    def remove(self, fy: str, guids) -> int:
        guids = list(guids)
        if not guids:
            return 0
        with self._connection() as conn:
            n = 0
            for g in guids:
                n += conn.execute("DELETE FROM deferred_vouchers WHERE fy = ? AND guid = ?", (fy, g)).rowcount
            conn.commit()
        return n

    def note_attempt(self, fy: str, guid: str, error: str) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE deferred_vouchers SET attempts = attempts + 1, last_error = ?, last_seen_at = ? "
                         "WHERE fy = ? AND guid = ?", (error[:500], self._now(), fy, guid))
            conn.commit()

    def scanned(self, fy: str) -> bool:
        """True once the one-time full scan of this FY's future dates has been done (2.2.3 catch-up)."""
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM deferred_scans WHERE fy = ?", (fy,)).fetchone() is not None

    def mark_scanned(self, fy: str, through: str) -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO deferred_scans (fy, scanned_at, through) VALUES (?, ?, ?) "
                         "ON CONFLICT(fy) DO UPDATE SET scanned_at = excluded.scanned_at, through = excluded.through",
                         (fy, self._now(), through))
            conn.commit()
