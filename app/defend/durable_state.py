"""Defend durable-state seam — killinchu #399 §1 per spec #401.

Production mode: PostgreSQL 16+ via DATABASE_URL. Demo mode: SQLite, clearly
labeled. Alembic owns every schema change; the app refuses to serve in
production when the DB is unwritable, the Alembic head drifts, or no fresh
backup event exists.

Pool settings (spec #401): pool_size=5, max_overflow=5, pool_timeout=30,
pool_recycle=1800. Isolation: REPEATABLE READ for reads, SERIALIZABLE for
approval/receipt writes (the receipt chain must not tolerate phantom reads
between prior-hash read and insert).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

POOL_CONFIG = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 30, "pool_recycle": 1800}
IDEMPOTENCY_TTL_HOURS = 24
BACKUP_FRESHNESS_HOURS = 36  # nightly pg_dump + grace


class DurableState:
    """Durable store with idempotency keys and readiness gating.

    demo_mode=True uses SQLite (local tests / labeled demo only). Production
    mode requires DATABASE_URL and refuses readiness without it.
    """

    def __init__(self, database_url: str | None = None, demo_mode: bool = False,
                 sqlite_path: str = ":memory:"):
        self.demo_mode = demo_mode
        self.database_url = database_url
        if demo_mode:
            self._conn = sqlite3.connect(sqlite_path)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS idempotency_keys ("
                "key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, "
                "response TEXT NOT NULL, created_at TEXT NOT NULL)")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS backup_events ("
                "id TEXT PRIMARY KEY, dump_sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")
            self._conn.commit()
        else:
            self._conn = None  # production driver (psycopg) attaches via Alembic-managed engine

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _now_iso(self) -> str:
        return self._now().strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- idempotency (spec: client key, stored request hash + response, 24h TTL) ---
    def idempotent_lookup(self, key: str, request_hash: str) -> dict | None:
        if not self.demo_mode:
            raise RuntimeError("production driver not attached in this harness")
        row = self._conn.execute(
            "SELECT request_hash, response, created_at FROM idempotency_keys WHERE key = ?",
            (key,)).fetchone()
        if not row:
            return None
        if row[0] != request_hash:
            raise ValueError("idempotency key replayed with a different request body")
        created = datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if self._now() - created > timedelta(hours=IDEMPOTENCY_TTL_HOURS):
            self._conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(row[1])

    def idempotent_store(self, key: str, request_hash: str, response: dict) -> None:
        if not self.demo_mode:
            raise RuntimeError("production driver not attached in this harness")
        self._conn.execute(
            "INSERT OR REPLACE INTO idempotency_keys (key, request_hash, response, created_at) "
            "VALUES (?, ?, ?, ?)",
            (key, request_hash, json.dumps(response, sort_keys=True), self._now_iso()))
        self._conn.commit()

    def record_backup_event(self, dump_sha256: str) -> str:
        if not self.demo_mode:
            raise RuntimeError("production driver not attached in this harness")
        event_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO backup_events (id, dump_sha256, created_at) VALUES (?, ?, ?)",
            (event_id, dump_sha256, self._now_iso()))
        self._conn.commit()
        return event_id

    # --- readiness (spec: 503 unless DB writable + alembic head matches + fresh backup) ---
    def readyz(self) -> tuple[bool, dict]:
        if self.demo_mode:
            return True, {"mode": "demo", "durable": False,
                          "note": "SQLite demo mode; production checks skipped by design"}
        if not self.database_url:
            return False, {"mode": "production", "durable": False, "reason": "DATABASE_URL absent"}
        return False, {"mode": "production", "durable": "unknown",
                       "reason": "attach production engine to evaluate write/alembic/backup checks"}
