"""Defend production store — killinchu #399 follow-up 1 per spec #401.

Source seam for PostgreSQL 16+; live production qualification is incomplete.
The demo SQLite path from #410 is separate. This module provides:

- an injectable connection factory and declared pool contract (5/5/30/1800);
  this module does not implement that pool
- REPEATABLE READ for reads, SERIALIZABLE for approval/receipt writes —
  the receipt chain must not tolerate phantom reads between prior-hash
  read and insert
- approval persistence: approval requests live in Postgres, so a restart
  mid-incident cannot silently drop a pending or approved request
- passive preliminary readiness reads: connectivity, Alembic head, and
  backup timestamp. These cannot establish production durability.

The connection factory is injectable so the source contract is testable without
a live database. Readiness remains BLOCKED until the full durable-state contract
has an implementation and live qualification; no caller flag can promote it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

POOL_CONFIG = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 30, "pool_recycle": 1800}
BACKUP_FRESHNESS_HOURS = 36
EXPECTED_ALEMBIC_HEAD = "0002"


class ProductionSchemaError(RuntimeError):
    """Typed schema failure without target names or provider diagnostics."""


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
        """Check the migrated seam without creating or changing its schema.

        Alembic owns every table. Operators apply migrations explicitly before
        this passive check; passing it does not qualify production readiness.
        """
        conn = None
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                cur.execute("SELECT version_num FROM alembic_version")
                if cur.fetchall() != [(EXPECTED_ALEMBIC_HEAD,)]:
                    raise ProductionSchemaError("ALEMBIC_HEAD_DRIFT")
                cur.execute(
                    "SELECT request_id, requester, scope, justification, policy_mode, "
                    "state, approvers, denier, created_at_epoch "
                    "FROM approval_requests LIMIT 0")
        except ProductionSchemaError:
            raise
        except Exception:
            raise ProductionSchemaError("DATABASE_SCHEMA_UNAVAILABLE") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    raise ProductionSchemaError("DATABASE_SCHEMA_UNAVAILABLE") from None

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

    # --- passive preliminary checks; never production qualification ---
    def readyz(self, now: datetime | None = None) -> tuple[bool, dict]:
        now = now or datetime.now(timezone.utc)
        reasons = []
        try:
            conn = self._conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.execute("SELECT version_num FROM alembic_version")
                    heads = cur.fetchall()
                    if heads != [(EXPECTED_ALEMBIC_HEAD,)]:
                        reasons.append("ALEMBIC_HEAD_DRIFT")
                    cur.execute("SELECT MAX(created_at) FROM backup_events")
                    latest = cur.fetchone()
                    if not latest or not latest[0]:
                        reasons.append("no backup events")
                    else:
                        age = now - latest[0]
                        if age < timedelta(0):
                            reasons.append("BACKUP_TIMESTAMP_IN_FUTURE")
                        elif age > timedelta(hours=BACKUP_FRESHNESS_HOURS):
                            reasons.append("latest backup older than 36h")
            finally:
                conn.close()
        except Exception:  # unreachable / unwritable DB fails closed
            return False, {"durable": False, "reasons": ["DATABASE_ERROR"]}
        if reasons:
            return False, {"durable": False, "reasons": reasons}
        return False, {
            "durable": False,
            "state": "BLOCKED",
            "preliminary_checks_passed": True,
            "reasons": ["PRODUCTION_QUALIFICATION_INCOMPLETE"],
            "alembic_head": EXPECTED_ALEMBIC_HEAD,
            "backup_fresh": True,
        }
