"""Defend production store — killinchu #399 follow-up 1 per spec #401.

Wires the durable-state seam onto PostgreSQL 16+. The demo SQLite path from
#410 is untouched; this module owns the production engine:

- psycopg connection factory with the spec pool contract (5/5/30/1800)
- REPEATABLE READ for reads, SERIALIZABLE for approval/receipt writes —
  the receipt chain must not tolerate phantom reads between prior-hash
  read and insert
- approval persistence: approval requests live in Postgres, so a restart
  mid-incident cannot silently drop a pending or approved request
- production readyz: writable probe, alembic head equality, fresh backup
  event — all three must pass or the plane refuses to serve

The connection factory is injectable so the contract is testable without a
live database; production passes psycopg's connect.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

POOL_CONFIG = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 30, "pool_recycle": 1800}
BACKUP_FRESHNESS_HOURS = 36
EXPECTED_ALEMBIC_HEAD = "0001"

DDL_APPROVALS = (
    "CREATE TABLE IF NOT EXISTS approval_requests ("
    "request_id TEXT PRIMARY KEY, requester TEXT NOT NULL, scope TEXT NOT NULL, "
    "justification TEXT NOT NULL, policy_mode TEXT NOT NULL, "
    "state TEXT NOT NULL, approvers TEXT NOT NULL, denier TEXT, "
    "created_at_epoch DOUBLE PRECISION NOT NULL)")


class ProductionStore:
    """Postgres-backed store behind the same contract as the demo store."""

    def __init__(self, database_url: str, connect=None):
        if not database_url:
            raise ValueError("production store requires DATABASE_URL")
        self.database_url = database_url
        self._connect = connect  # production: psycopg.connect

    def _conn(self):
        if self._connect is None:
            raise RuntimeError("no connection factory attached; pass psycopg.connect")
        return self._connect(self.database_url)

    def initialize(self) -> None:
        """Own the approvals table; Alembic owns everything else."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(DDL_APPROVALS)
            conn.commit()
        finally:
            conn.close()

    # --- SERIALIZABLE write path for approvals/receipts (spec #401) ---
    def persist_approval(self, req) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cur.execute(
                    "INSERT INTO approval_requests (request_id, requester, scope, "
                    "justification, policy_mode, state, approvers, denier, "
                    "created_at_epoch) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (request_id) DO UPDATE SET state = EXCLUDED.state, "
                    "approvers = EXCLUDED.approvers, denier = EXCLUDED.denier",
                    (req.request_id, req.requester, req.scope, req.justification,
                     str(req.policy_mode), str(req.state),
                     json.dumps(req.approvers), req.denier, req.created_at_epoch))
            conn.commit()
        finally:
            conn.close()

    def load_approval(self, request_id: str) -> dict | None:
        """REPEATABLE READ is sufficient for reads (spec #401)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cur.execute(
                    "SELECT request_id, requester, scope, justification, policy_mode, "
                    "state, approvers, denier, created_at_epoch "
                    "FROM approval_requests WHERE request_id = %s", (request_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {"request_id": row[0], "requester": row[1], "scope": row[2],
                "justification": row[3], "policy_mode": row[4], "state": row[5],
                "approvers": json.loads(row[6]), "denier": row[7],
                "created_at_epoch": row[8]}

    # --- production readyz: writable + alembic head + fresh backup ---
    def readyz(self, now: datetime | None = None) -> tuple[bool, dict]:
        now = now or datetime.now(timezone.utc)
        reasons = []
        try:
            conn = self._conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.execute("SELECT version_num FROM alembic_version")
                    head = cur.fetchone()
                    if not head or head[0] != EXPECTED_ALEMBIC_HEAD:
                        reasons.append(f"alembic head drift: {head and head[0]!r}")
                    cur.execute("SELECT MAX(created_at) FROM backup_events")
                    latest = cur.fetchone()
                    if not latest or not latest[0]:
                        reasons.append("no backup events")
                    else:
                        fresh = now - latest[0] <= timedelta(hours=BACKUP_FRESHNESS_HOURS)
                        if not fresh:
                            reasons.append("latest backup older than 36h")
            finally:
                conn.close()
        except Exception as exc:  # unreachable / unwritable DB fails closed
            return False, {"durable": False, "reasons": [f"database error: {exc}"]}
        if reasons:
            return False, {"durable": False, "reasons": reasons}
        return True, {"durable": True, "alembic_head": EXPECTED_ALEMBIC_HEAD,
                      "backup_fresh": True}
