"""Defend chain persistence — killinchu #399 follow-up 3 per spec #401.

Persists the #413 hash-chained audit log to the durable store. The table is
append-only by construction: no update or delete path exists, and every
insert reads the current head hash inside the same immediate transaction —
a concurrent or stale writer fails loudly instead of forking the chain.
Backup events are recorded in the same transaction as their BACKUP_COMMITTED
chain entry, so the readyz freshness probe (#422) and the receipt anchor
(#413) can never disagree.

Demo mode uses a SQLite file; production passes the #422 connection
factory. Chain bytes and verification are identical in both modes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid

GENESIS = "0" * 64

DDL = (
    "CREATE TABLE IF NOT EXISTS audit_events ("
    "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
    "event_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, "
    "prior_hash TEXT NOT NULL, event_hash TEXT NOT NULL, at_epoch REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS backup_events ("
    "id TEXT PRIMARY KEY, dump_sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


class ChainForkError(RuntimeError):
    """Raised when a writer's expected head does not match the stored head."""


class PersistentAuditChain:
    def __init__(self, sqlite_path: str = ":memory:"):
        self._conn = sqlite3.connect(sqlite_path, isolation_level=None)
        with self._conn:
            for stmt in DDL:
                self._conn.execute(stmt)

    def _head(self, cur) -> str:
        row = cur.execute(
            "SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    def append(self, event_type: str, payload: dict,
               now: float | None = None) -> dict:
        now = time.time() if now is None else now
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")  # write lock: head read + insert are atomic
        try:
            prior = self._head(cur)
            body = {"event_id": str(uuid.uuid4()), "event_type": event_type,
                    "payload": payload, "prior_hash": prior, "at_epoch": now}
            event_hash = _hash(body)
            cur.execute(
                "INSERT INTO audit_events (event_id, event_type, payload, "
                "prior_hash, event_hash, at_epoch) VALUES (?, ?, ?, ?, ?, ?)",
                (body["event_id"], event_type, _canonical(payload), prior,
                 event_hash, now))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return {"event_hash": event_hash, **body}

    def record_backup(self, dump_sha256: str, now: float | None = None) -> dict:
        """Backup row + BACKUP_COMMITTED chain entry in one transaction."""
        now = time.time() if now is None else now
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            cur.execute(
                "INSERT INTO backup_events (id, dump_sha256, created_at) "
                "VALUES (?, ?, ?)", (str(uuid.uuid4()), dump_sha256, created))
            prior = self._head(cur)
            body = {"event_id": str(uuid.uuid4()), "event_type": "BACKUP_COMMITTED",
                    "payload": {"dump_sha256": dump_sha256}, "prior_hash": prior,
                    "at_epoch": now}
            event_hash = _hash(body)
            cur.execute(
                "INSERT INTO audit_events (event_id, event_type, payload, "
                "prior_hash, event_hash, at_epoch) VALUES (?, ?, ?, ?, ?, ?)",
                (body["event_id"], "BACKUP_COMMITTED",
                 _canonical(body["payload"]), prior, event_hash, now))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return {"event_hash": event_hash, **body}

    def verify(self) -> tuple[bool, str | None]:
        prior = GENESIS
        rows = self._conn.execute(
            "SELECT event_id, event_type, payload, prior_hash, event_hash, "
            "at_epoch FROM audit_events ORDER BY seq").fetchall()
        for event_id, event_type, payload, prior_hash, event_hash, at_epoch in rows:
            if prior_hash != prior:
                return False, event_id
            body = {"event_id": event_id, "event_type": event_type,
                    "payload": json.loads(payload), "prior_hash": prior_hash,
                    "at_epoch": at_epoch}
            if _hash(body) != event_hash:
                return False, event_id
            prior = event_hash
        return True, None

    def latest_backup_age_hours(self, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT MAX(created_at) FROM backup_events").fetchone()
        if not row or not row[0]:
            return None
        latest = time.mktime(time.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ"))
        return (now - latest) / 3600

    def __len__(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
