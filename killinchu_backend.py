# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11
#
# killinchu_backend.py — the REAL, persistent backend for killinchu.
#
# Gives killinchu a live, Postgres-first API (with a durable SQLite fallback so it
# also runs on the HF Docker Space, which has no Postgres) at the SAME `/api/killinchu/*`
# origin convention as a11oy. Pure stdlib (urllib + sqlite3); `psycopg` (v3) is used
# ONLY when it is importable AND a DATABASE_URL is configured — otherwise we degrade to
# durable SQLite. The module NEVER crashes the host app: register() is fully guarded.
#
# Doctrine v11: every endpoint returns an envelope carrying {status, citations, fetchedAt}.
# Honest labels end-to-end: live | cached | degraded. No fabricated data — when a real
# upstream is unreachable we serve the last-good snapshot from the DB (status="cached")
# or an empty result (status="degraded"), never invented figures.
#
# Endpoints (all registered BEFORE the SPA /{full_path:path} catch-all):
#   GET    /api/killinchu/db/health           — backend + last DB ping (used by /healthz)
#   POST   /api/killinchu/live                 — on-demand scrape, cached, with citations
#   POST   /api/killinchu/crawl/run            — manual crawl trigger (writes snapshot/facts/events)
#   GET    /api/killinchu/timeline             — events timeline from Postgres/SQLite
#   GET    /api/killinchu/alerts/recent        — recent notifications (watchlist hits)
#   GET    /api/killinchu/watchlists           — list
#   POST   /api/killinchu/watchlists           — create (+ triggers)
#   PUT    /api/killinchu/watchlists/{wid}      — update (+ triggers)
#   DELETE /api/killinchu/watchlists/{wid}      — delete
#   GET    /api/killinchu/operator-mutations/{key_digest} — inspect receipt state
#   POST   /api/killinchu/operator-mutations/{key_digest}/reconcile — resolve state
#
# Tables: snapshots, facts, events, watchlists, triggers, notifications,
# operator_mutations.
"""Persistent, honest-by-default backend for the killinchu Space.

Exposes the ``/api/killinchu/*`` REST surface backed by a durable store that is
Postgres-first and falls back to SQLite so the module also runs on the Hugging
Face Docker Space (which has no Postgres). The backend is pure stdlib (``urllib``
+ ``sqlite3``); ``psycopg`` (v3) is imported lazily and used ONLY when it is both
importable and a ``DATABASE_URL`` is configured.

Doctrine v11 contract enforced here:

* ``register()`` is fully guarded and NEVER crashes the host FastAPI app.
* Every endpoint returns an envelope of ``{status, citations, fetchedAt}``.
* Status labels are honest end-to-end: ``live`` (fresh upstream read this
  request), ``cached`` (last-good snapshot served from the DB because the
  upstream was unreachable), or ``degraded`` (no durable backend / empty
  result). No figures are ever fabricated.

See the endpoint/table map in the header comment above for the full route list.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import sqlite3
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

# NOTE: `from __future__ import annotations` (above) stringifies every annotation,
# so FastAPI resolves route-handler param types via THIS module's globals at
# add_api_route() time. The handlers are nested inside register() and annotate
# `request: Request` — that name must therefore live at module scope, or FastAPI
# mis-reads `request` as a required query parameter (HTTP 422). These imports are
# guarded so the module still loads (and degrades) where FastAPI is absent; when
# register() actually runs, FastAPI is by definition present.
try:  # pragma: no cover - import-environment dependent
    from fastapi import Depends, Request, Security  # noqa: F401  (module-global for annotation resolution)
    from fastapi.responses import JSONResponse  # noqa: F401
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    _OPERATOR_BEARER = HTTPBearer(
        auto_error=False,
        scheme_name="OperatorBearer",
        description=(
            "Fail-closed operator bearer. The runtime stores only its SHA-256 "
            "digest in A11OY_COMPUTE_TOKEN_SHA256."
        ),
    )

    async def _declare_operator_bearer(
        credentials: Optional[HTTPAuthorizationCredentials] = Security(_OPERATOR_BEARER),
    ) -> None:
        """Declare the security scheme; handlers enforce the canonical gate."""
        del credentials
except Exception:  # FastAPI not installed in this context; register() won't be called
    Depends = Any  # type: ignore
    Request = Any  # type: ignore
    Security = Any  # type: ignore
    JSONResponse = Any  # type: ignore

    async def _declare_operator_bearer() -> None:
        return None

DOCTRINE = "v11"
_START_TS = time.time()

# Real, public OSINT source used by the crawl/live scrape. adsb.lol publishes
# unauthenticated military ADS-B; killinchu_live_feeds already uses it. Decoded
# ADS-B is an UNAUTHENTICATED broadcast CLAIM, not attested truth (honest label).
_MIL_ADSB_URL = "https://api.adsb.lol/v2/mil"
_LIVE_CACHE_TTL = 60  # seconds a "live" scrape stays fresh before a re-fetch
_USER_AGENT = "killinchu-backend/1.0 (+https://killinchu.a-11-oy.com)"
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_MUTATION_RECEIPT_SCHEMA = "szl.killinchu.operator-mutation-receipt/v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Optional push notifications (ntfy) for watchlist alerts.
#
# When a crawl creates a watchlist notification we can ALSO push it to the team's
# shared ntfy topic (the same channel the box uptime monitor uses) so operators
# are paged without polling the console. This is OPTIONAL and env-configured: with
# no channel set, alerts stay in-app only and nothing errors.
#
# Pushes are EDGE-TRIGGERED + de-duped — a trigger that keeps firing on every
# crawl (a standing condition) pages once on the clear->fire edge, NOT on every
# snapshot. An optional cooldown re-pages a still-firing condition after a quiet
# window; the default (0) disables re-paging, i.e. pure edge.
#
# Env (all optional):
#   KILLINCHU_NTFY_URL | NTFY_URL | NTFY_TOPIC_URL  — ntfy topic URL; empty=disabled
#   KILLINCHU_NTFY_TOKEN | NTFY_TOKEN               — bearer token (optional)
#   KILLINCHU_NTFY_PRIORITY | NTFY_PRIORITY         — ntfy priority (default "high")
#   KILLINCHU_NTFY_COOLDOWN                         — re-page window seconds (default 0)
#   KILLINCHU_NTFY_BLOCKING                         — "1" sends synchronously (tests)
#   KILLINCHU_NTFY_RECOVERY                         — "0"/"false" disables fire->clear
#                                                     "recovered" notices (default on)
#   KILLINCHU_NTFY_RECOVERY_PRIORITY                — priority for recovery notices
#                                                     (default "low")
# ---------------------------------------------------------------------------
def _ntfy_config() -> Optional[Dict[str, Any]]:
    url = (
        os.environ.get("KILLINCHU_NTFY_URL")
        or os.environ.get("NTFY_URL")
        or os.environ.get("NTFY_TOPIC_URL")
        or ""
    ).strip()
    if not url:
        return None
    token = (os.environ.get("KILLINCHU_NTFY_TOKEN") or os.environ.get("NTFY_TOKEN") or "").strip()
    priority = (os.environ.get("KILLINCHU_NTFY_PRIORITY") or os.environ.get("NTFY_PRIORITY") or "high").strip()
    try:
        cooldown = float(os.environ.get("KILLINCHU_NTFY_COOLDOWN", "0") or "0")
    except Exception:
        cooldown = 0.0
    recovery_raw = (os.environ.get("KILLINCHU_NTFY_RECOVERY") or "").strip().lower()
    recovery = recovery_raw not in ("0", "false", "no", "off")
    recovery_priority = (
        os.environ.get("KILLINCHU_NTFY_RECOVERY_PRIORITY")
        or os.environ.get("NTFY_RECOVERY_PRIORITY")
        or "low"
    ).strip()
    return {
        "url": url,
        "token": token,
        "priority": priority,
        "cooldown": max(0.0, cooldown),
        "recovery": recovery,
        "recovery_priority": recovery_priority,
    }


# Edge-trigger / de-dupe state, keyed by (watchlist_id, trigger_id):
#   firing       — was this trigger firing at the previous evaluation?
#   last_push_ts — wall-clock time of the last push for this trigger.
# In-memory only: after a restart the first firing trigger pages once (treated as
# a fresh edge), which is the desired "page current conditions on boot" behaviour.
_NTFY_STATE: Dict[Tuple[int, int], Dict[str, Any]] = {}
_NTFY_STATE_LOCK = threading.Lock()


def _ntfy_send_raw(url: str, body: bytes, headers: Dict[str, str], timeout: float = 8.0) -> int:
    """POST a plain-text message to an ntfy topic. Returns HTTP status (0 on error)."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"[killinchu-backend] ntfy push failed: {e!r}", file=sys.stderr)
        return 0


def _push_ntfy(title: str, message: str, cfg: Dict[str, Any],
               priority: Optional[str] = None, tags: str = "rotating_light") -> None:
    """Fire a single ntfy push for a watchlist alert. Never raises."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Content-Type": "text/plain; charset=utf-8",
        "Title": title,
        "Priority": priority or cfg.get("priority") or "high",
        "Tags": tags,
    }
    if cfg.get("token"):
        headers["Authorization"] = "Bearer " + cfg["token"]
    body = message.encode("utf-8")
    url = cfg["url"]

    def _go() -> None:
        _ntfy_send_raw(url, body, headers)

    # Off the request path by default so a slow/unreachable ntfy never stalls a
    # crawl; KILLINCHU_NTFY_BLOCKING=1 makes it synchronous for deterministic tests.
    if os.environ.get("KILLINCHU_NTFY_BLOCKING") == "1":
        _go()
    else:
        threading.Thread(target=_go, name="killinchu-ntfy", daemon=True).start()


def _ntfy_should_push(key: Tuple[int, int], cfg: Dict[str, Any], now_ts: float) -> bool:
    """True only on a clear->fire edge, or after the optional cooldown re-page window."""
    with _NTFY_STATE_LOCK:
        prev = _NTFY_STATE.get(key) or {}
        was_firing = bool(prev.get("firing"))
        last_push = float(prev.get("last_push_ts") or 0.0)
    if not was_firing:
        return True  # off -> on edge
    cooldown = float(cfg.get("cooldown") or 0.0)
    if cooldown > 0 and (now_ts - last_push) >= cooldown:
        return True  # still firing, but the quiet window elapsed -> re-page
    return False


def _ntfy_mark(key: Tuple[int, int], firing: bool, pushed: bool, now_ts: float) -> None:
    """Record this trigger's firing state (and last push time) for edge detection."""
    with _NTFY_STATE_LOCK:
        prev = _NTFY_STATE.get(key) or {}
        last_push = float(prev.get("last_push_ts") or 0.0)
        if pushed:
            last_push = now_ts
        _NTFY_STATE[key] = {"firing": firing, "last_push_ts": last_push}


def _ntfy_was_firing(key: Tuple[int, int]) -> bool:
    """True if this trigger was firing at the previous evaluation."""
    with _NTFY_STATE_LOCK:
        prev = _NTFY_STATE.get(key) or {}
        return bool(prev.get("firing"))


def _queue_ntfy_transition(
    actions: List[Dict[str, Any]],
    *,
    key: Tuple[int, int],
    cfg: Optional[Dict[str, Any]],
    firing: bool,
    title: str,
    message: str,
    now_ts: float,
) -> None:
    """Queue an alert transition without performing an external side effect.

    Watchlist evaluation runs inside the crawl transaction. Sending ntfy, or
    advancing its edge/de-dup state, before that transaction commits can page
    on rolled-back data and suppress the next legitimate alert. Callers deliver
    these immutable intents only after a successful commit.
    """
    if cfg is None:
        return
    if firing:
        priority = cfg.get("priority") or "high"
        tags = "rotating_light"
    else:
        priority = cfg.get("recovery_priority") or "low"
        tags = "white_check_mark"
    actions.append({
        "key": key,
        "cfg": dict(cfg),
        "firing": firing,
        "title": title,
        "message": message,
        "priority": priority,
        "tags": tags,
        "now_ts": now_ts,
    })


def _deliver_ntfy_actions(actions: List[Dict[str, Any]]) -> None:
    """Deliver committed ntfy intents, then advance edge/de-dup state."""
    for action in actions:
        firing = bool(action["firing"])
        should_send = (
            _ntfy_should_push(
                action["key"],
                action["cfg"],
                float(action["now_ts"]),
            )
            if firing
            else bool(
                action["cfg"].get("recovery")
                and _ntfy_was_firing(action["key"])
            )
        )
        if should_send:
            _push_ntfy(
                action["title"],
                action["message"],
                action["cfg"],
                priority=action["priority"],
                tags=action["tags"],
            )
        _ntfy_mark(
            action["key"],
            firing,
            should_send,
            float(action["now_ts"]),
        )


# ---------------------------------------------------------------------------
# Storage — Postgres-first, durable-SQLite fallback. One small portable layer.
# ---------------------------------------------------------------------------
class _Store:
    """Postgres-first persistence with a durable SQLite fallback.

    All SQL is written with `?` placeholders and translated to `%s` for psycopg.
    JSON payloads are stored as TEXT (json.dumps) so ONE schema works on both
    engines. Timestamps are ISO-8601 UTC TEXT. A single connection guarded by a
    lock is sufficient for this low-traffic governance surface; the connection is
    lazily re-established if it drops.
    """

    def __init__(self) -> None:
        self.backend = "none"
        self.dsn: Optional[str] = None
        self._lock = threading.RLock()
        self._pg = None  # psycopg connection
        self._sqlite: Optional[sqlite3.Connection] = None
        self._sqlite_path: Optional[str] = None
        self._transaction_active = False
        self.last_ping_ok: Optional[bool] = None
        self.last_ping_at: Optional[str] = None
        self.last_ping_ms: Optional[float] = None
        self.init_error: Optional[str] = None
        self._init()

    # -- connection setup ---------------------------------------------------
    def _init(self) -> None:
        dsn = (
            os.environ.get("KILLINCHU_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or ""
        ).strip()
        if dsn:
            try:
                import psycopg  # type: ignore

                self._pg = psycopg.connect(dsn, autocommit=True, connect_timeout=8)
                self.backend = "postgres"
                self.dsn = dsn
                self._ensure_schema()
                self.ping()
                return
            except Exception as e:  # fall through to sqlite
                self.init_error = f"postgres unavailable ({e!r}); using durable sqlite"
                print(f"[killinchu-backend] {self.init_error}", file=sys.stderr)
                self._pg = None
        # SQLite fallback (durable on the box volume; per-session on HF Spaces).
        for cand in (
            os.environ.get("KILLINCHU_DB_DIR"),
            "/data",
            "/app/data",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
            "/tmp",
        ):
            if not cand:
                continue
            try:
                os.makedirs(cand, exist_ok=True)
                path = os.path.join(cand, "killinchu_backend.sqlite3")
                self._sqlite = sqlite3.connect(path, check_same_thread=False)
                self._sqlite.row_factory = sqlite3.Row
                self._sqlite_path = path
                self.backend = "sqlite"
                self.dsn = path
                self._ensure_schema()
                self.ping()
                return
            except Exception as e:
                self.init_error = f"sqlite path {cand} unwritable ({e!r})"
                continue
        self.backend = "none"
        print(f"[killinchu-backend] NO durable backend available: {self.init_error}", file=sys.stderr)

    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "postgres" else sql

    def _ensure_schema(self) -> None:
        if self.backend == "postgres":
            pk = "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
        else:
            pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        ddl = [
            f"""CREATE TABLE IF NOT EXISTS snapshots (
                id {pk},
                source TEXT NOT NULL,
                source_url TEXT,
                mode TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                http_status INTEGER,
                record_count INTEGER DEFAULT 0,
                payload TEXT
            )""",
            f"""CREATE TABLE IF NOT EXISTS facts (
                id {pk},
                snapshot_id BIGINT,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                value TEXT,
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS events (
                id {pk},
                snapshot_id BIGINT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                severity TEXT DEFAULT 'info',
                source TEXT,
                source_url TEXT,
                ts TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS watchlists (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS triggers (
                id {pk},
                watchlist_id BIGINT NOT NULL,
                field TEXT NOT NULL,
                op TEXT NOT NULL,
                threshold TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS notifications (
                id {pk},
                watchlist_id BIGINT,
                trigger_id BIGINT,
                event_id BIGINT,
                title TEXT NOT NULL,
                detail TEXT,
                severity TEXT DEFAULT 'warn',
                source TEXT,
                source_url TEXT,
                ts TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS operator_mutations (
                idempotency_key_hash TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                status_code INTEGER,
                response_json TEXT,
                receipt_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)",
            "CREATE INDEX IF NOT EXISTS idx_notif_ts ON notifications(ts)",
            "CREATE INDEX IF NOT EXISTS idx_facts_snap ON facts(snapshot_id)",
            "CREATE INDEX IF NOT EXISTS idx_snap_src ON snapshots(source, fetched_at)",
            "CREATE INDEX IF NOT EXISTS idx_trig_wl ON triggers(watchlist_id)",
            "CREATE INDEX IF NOT EXISTS idx_operator_mutations_created ON operator_mutations(created_at)",
        ]
        with self._lock:
            cur = self._cursor()
            for stmt in ddl:
                cur.execute(stmt)
            self._commit()
            cur.close()

    # -- low-level helpers --------------------------------------------------
    def _cursor(self):
        if self.backend == "postgres":
            if self._pg is None or getattr(self._pg, "closed", True):
                import psycopg  # type: ignore
                self._pg = psycopg.connect(self.dsn, autocommit=True, connect_timeout=8)
            return self._pg.cursor()
        if self._sqlite is None:
            raise RuntimeError("no backend")
        return self._sqlite.cursor()

    def _commit(self) -> None:
        if (
            self.backend == "sqlite"
            and self._sqlite is not None
            and not self._transaction_active
        ):
            self._sqlite.commit()
        # postgres connection is autocommit

    @contextmanager
    def transaction(self) -> Iterator["_Store"]:
        """Hold one real database transaction across existing store helpers.

        The store lock remains held for the whole block. SQLite uses
        ``BEGIN IMMEDIATE`` so a competing writer cannot interleave. Psycopg's
        transaction context is used even though the connection normally runs in
        autocommit mode. Existing helper methods see ``_transaction_active`` and
        therefore do not commit individual SQLite statements.
        """
        with self._lock:
            if self._transaction_active:
                raise RuntimeError("nested killinchu backend transaction")
            if self.backend == "postgres":
                self._cursor().close()  # reconnect first when needed
                self._transaction_active = True
                try:
                    with self._pg.transaction():
                        yield self
                finally:
                    self._transaction_active = False
                return
            if self.backend != "sqlite" or self._sqlite is None:
                raise RuntimeError("no durable backend transaction")
            cur = self._sqlite.cursor()
            cur.execute("BEGIN IMMEDIATE")
            cur.close()
            self._transaction_active = True
            try:
                yield self
            except BaseException:
                self._sqlite.rollback()
                raise
            else:
                self._sqlite.commit()
            finally:
                self._transaction_active = False

    def ok(self) -> bool:
        """Return True when a durable backend (postgres or sqlite) is available."""
        return self.backend in ("postgres", "sqlite")

    def ping(self) -> bool:
        """Probe the backend with ``SELECT 1``, recording latency and outcome.

        Updates ``last_ping_ok``/``last_ping_ms``/``last_ping_at`` and returns the
        boolean result. Failures are logged to stderr and reported as False
        rather than raised, so callers can degrade honestly.
        """
        t0 = time.time()
        try:
            with self._lock:
                cur = self._cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
            self.last_ping_ok = True
        except Exception as e:
            self.last_ping_ok = False
            print(f"[killinchu-backend] db ping failed: {e!r}", file=sys.stderr)
        self.last_ping_ms = round((time.time() - t0) * 1000, 2)
        self.last_ping_at = _now_iso()
        return bool(self.last_ping_ok)

    def execute(self, sql: str, params: Tuple = ()) -> None:
        """Run a write statement under the store lock, then commit."""
        with self._lock:
            cur = self._cursor()
            cur.execute(self._q(sql), params)
            self._commit()
            cur.close()

    def insert_returning_id(self, sql: str, params: Tuple = ()) -> Optional[int]:
        """Insert a row and return its new ``id``, or None if nothing was returned.

        Appends ``RETURNING id`` to *sql*; works identically on Postgres and on
        the SQLite fallback (where the row is read back via ``sqlite3.Row``).
        """
        with self._lock:
            cur = self._cursor()
            cur.execute(self._q(sql + " RETURNING id"), params)
            row = cur.fetchone()
            self._commit()
            cur.close()
        if row is None:
            return None
        return int(row[0] if not isinstance(row, sqlite3.Row) else row["id"])

    def query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Run a read query and return rows as a list of column-keyed dicts."""
        with self._lock:
            cur = self._cursor()
            cur.execute(self._q(sql), params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            cur.close()
        out: List[Dict[str, Any]] = []
        for r in rows:
            if isinstance(r, sqlite3.Row):
                out.append({k: r[k] for k in r.keys()})
            else:
                out.append({cols[i]: r[i] for i in range(len(cols))})
        return out

    def claim_operator_mutation(
        self,
        *,
        key_hash: str,
        operation: str,
        actor_id: str,
        request_digest: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Reserve one mutation key before side effects.

        Returns ``("claimed", None)``, ``("replay", row)``,
        ``("receipt_pending", row)``, ``("in_progress", row)``, or
        ``("conflict", row)``. The durable reservation makes retries
        at-most-once even if the process fails after the mutation begins.
        """
        now = _now_iso()
        with self._lock:
            cur = self._cursor()
            cur.execute(
                self._q(
                    "INSERT INTO operator_mutations("
                    "idempotency_key_hash, operation, actor_id, request_digest, state, created_at"
                    ") VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(idempotency_key_hash) DO NOTHING"
                ),
                (key_hash, operation, actor_id, request_digest, "in_progress", now),
            )
            inserted = cur.rowcount == 1
            self._commit()
            if inserted:
                cur.close()
                return "claimed", None
            cur.execute(
                self._q(
                    "SELECT operation, actor_id, request_digest, state, status_code, "
                    "response_json, receipt_json, created_at, completed_at "
                    "FROM operator_mutations WHERE idempotency_key_hash=?"
                ),
                (key_hash,),
            )
            row = cur.fetchone()
            cols = [d[0] for d in cur.description] if cur.description else []
            if row is None:  # defensive: a concurrent delete is never expected
                cur.close()
                raise RuntimeError("idempotency claim disappeared")
            if isinstance(row, sqlite3.Row):
                existing = {k: row[k] for k in row.keys()}
            else:
                existing = {cols[i]: row[i] for i in range(len(cols))}
            cur.close()
        if (
            existing["operation"] != operation
            or existing["actor_id"] != actor_id
            or existing["request_digest"] != request_digest
        ):
            return "conflict", existing
        if existing["state"] == "completed":
            return "replay", existing
        if existing["state"] == "receipt_pending":
            return "receipt_pending", existing
        return "in_progress", existing

    def get_operator_mutation(self, *, key_hash: str) -> Optional[Dict[str, Any]]:
        """Return one durable mutation state for inspection/reconciliation."""
        rows = self.query(
            "SELECT idempotency_key_hash, operation, actor_id, request_digest, "
            "state, status_code, response_json, receipt_json, created_at, completed_at "
            "FROM operator_mutations WHERE idempotency_key_hash=?",
            (key_hash,),
        )
        return rows[0] if rows else None

    def stage_operator_mutation(
        self,
        *,
        key_hash: str,
        status_code: int,
        response: Dict[str, Any],
        receipt_request: Dict[str, Any],
    ) -> None:
        """Durably stage response + receipt material in the mutation transaction."""
        with self._lock:
            cur = self._cursor()
            cur.execute(
                self._q(
                    "UPDATE operator_mutations SET state=?, status_code=?, "
                    "response_json=?, receipt_json=? "
                    "WHERE idempotency_key_hash=? AND state=?"
                ),
                (
                    "receipt_pending",
                    status_code,
                    _canonical_json(response),
                    _canonical_json(receipt_request),
                    key_hash,
                    "in_progress",
                ),
            )
            if cur.rowcount != 1:
                cur.close()
                raise RuntimeError("idempotency claim is not stageable")
            self._commit()
            cur.close()

    def complete_operator_mutation(
        self,
        *,
        key_hash: str,
        status_code: int,
        response: Dict[str, Any],
        receipt: Dict[str, Any],
    ) -> None:
        """Persist the canonical receipt and replay response."""
        with self._lock:
            cur = self._cursor()
            cur.execute(
                self._q(
                    "UPDATE operator_mutations SET state=?, status_code=?, "
                    "response_json=?, receipt_json=?, completed_at=? "
                    "WHERE idempotency_key_hash=? AND state=?"
                ),
                (
                    "completed",
                    status_code,
                    _canonical_json(response),
                    _canonical_json(receipt),
                    _now_iso(),
                    key_hash,
                    "receipt_emitting",
                ),
            )
            if cur.rowcount != 1:
                cur.close()
                raise RuntimeError("pending receipt is not completable")
            self._commit()
            cur.close()

    def begin_receipt_emission(self, *, key_hash: str) -> bool:
        """Acquire the durable cross-process receipt-emission state."""
        with self._lock:
            cur = self._cursor()
            cur.execute(
                self._q(
                    "UPDATE operator_mutations SET state=? "
                    "WHERE idempotency_key_hash=? AND state=?"
                ),
                ("receipt_emitting", key_hash, "receipt_pending"),
            )
            acquired = cur.rowcount == 1
            self._commit()
            cur.close()
            return acquired

    def transition_operator_mutation(
        self,
        *,
        key_hash: str,
        from_state: str,
        to_state: str,
    ) -> bool:
        """Compare-and-set one reconciliation state."""
        with self._lock:
            cur = self._cursor()
            cur.execute(
                self._q(
                    "UPDATE operator_mutations SET state=? "
                    "WHERE idempotency_key_hash=? AND state=?"
                ),
                (to_state, key_hash, from_state),
            )
            changed = cur.rowcount == 1
            self._commit()
            cur.close()
            return changed

    def fail_operator_mutation(self, *, key_hash: str) -> None:
        """Keep an incomplete claim closed pending explicit operator review."""
        self.execute(
            "UPDATE operator_mutations SET state=? "
            "WHERE idempotency_key_hash=? AND state=?",
            ("needs_operator_review", key_hash, "in_progress"),
        )

    def health(self) -> Dict[str, Any]:
        """Ping the backend and return a health dict for ``/db/health`` + ``/healthz``.

        The returned mapping describes the active backend, whether it is durable,
        and the most recent ping outcome/latency.
        """
        self.ping()
        return {
            "backend": self.backend,
            "durable": self.backend in ("postgres", "sqlite"),
            "postgres_first": True,
            "dsn_kind": "postgres" if self.backend == "postgres" else ("sqlite:" + str(self._sqlite_path) if self._sqlite_path else "none"),
            "ping_ok": self.last_ping_ok,
            "ping_ms": self.last_ping_ms,
            "last_ping_at": self.last_ping_at,
            "init_error": self.init_error,
        }


_STORE: Optional[_Store] = None
_STORE_LOCK = threading.Lock()


def _store() -> _Store:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = _Store()
    return _STORE


# ---------------------------------------------------------------------------
# Doctrine v11 envelope helpers
# ---------------------------------------------------------------------------
def _envelope(status: str, data: Dict[str, Any], citations: List[Dict[str, str]]) -> Dict[str, Any]:
    body = {
        "status": status,           # ok | live | cached | degraded | error | failed
        "doctrine": DOCTRINE,
        "service": "killinchu",
        "citations": citations,
        "fetchedAt": _now_iso(),
    }
    body.update(data)
    return body


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _mutation_receipt_request(
    *,
    operation: str,
    actor_id: str,
    key_hash: str,
    request_digest: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build deterministic, non-secret material for the canonical emitter."""
    return {
        "schema": _MUTATION_RECEIPT_SCHEMA,
        "operation": operation,
        "actor_id": actor_id,
        "idempotency_key_hash": key_hash,
        "request_digest": request_digest,
        "result_digest": _sha256_json(result),
    }


def _unsigned_mutation_receipt(material: Dict[str, Any]) -> Dict[str, Any]:
    """Honest fallback for isolated apps that do not inject a Khipu emitter."""
    unsigned = {
        **material,
        "signed": False,
        "signature_state": "UNSIGNED_NO_EMITTER",
    }
    return {
        **unsigned,
        "receipt_digest": _sha256_json(unsigned),
    }


def _adsb_citation(extra: Optional[str] = None) -> List[Dict[str, str]]:
    c = [{
        "kind": "osint",
        "title": "adsb.lol — military ADS-B (unauthenticated broadcast)",
        "url": _MIL_ADSB_URL,
        "note": "Decoded ADS-B is an unauthenticated broadcast CLAIM, not attested truth.",
    }]
    if extra:
        c.append({"kind": "db", "title": extra, "url": ""})
    return c


# ---------------------------------------------------------------------------
# Real scrape -> persist snapshot/facts/events -> evaluate watchlists
# ---------------------------------------------------------------------------
def _fetch_mil_adsb(timeout: float = 12.0) -> Tuple[Optional[dict], int, Optional[str]]:
    req = urllib.request.Request(_MIL_ADSB_URL, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")), getattr(resp, "status", 200) or 200, None
    except urllib.error.HTTPError as e:
        return None, e.code, f"HTTP {e.code}"
    except Exception as e:
        return None, 0, repr(e)


def _derive_facts(payload: dict) -> List[Tuple[str, str, str]]:
    """(kind, label, value) facts derived from a real ADS-B snapshot."""
    ac = payload.get("ac") or payload.get("aircraft") or []
    n = len(ac)
    types: Dict[str, int] = {}
    countries: Dict[str, int] = {}
    for a in ac:
        t = (a.get("t") or a.get("type") or "unknown")
        types[t] = types.get(t, 0) + 1
        c = (a.get("flag") or a.get("country") or "")
        if c:
            countries[c] = countries.get(c, 0) + 1
    top_types = sorted(types.items(), key=lambda kv: -kv[1])[:5]
    facts = [
        ("count", "military aircraft observed", str(n)),
        ("count", "distinct airframe types", str(len(types))),
    ]
    for t, cnt in top_types:
        facts.append(("type", f"airframe:{t}", str(cnt)))
    return facts


def run_crawl(
    mode: str = "crawl",
    *,
    ntfy_actions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Fetch the real feed, persist snapshot/facts/events, evaluate watchlists.

    Honest status: 'live' when the upstream answered, 'cached' when it failed but a
    prior snapshot exists, 'degraded' when nothing is available. Never fabricates.
    """
    st = _store()
    if not st.ok():
        return _envelope("degraded", {"error": "no durable backend", "events_created": 0}, _adsb_citation())

    payload, http_status, err = _fetch_mil_adsb()
    fetched_at = _now_iso()

    if payload is None:
        # Upstream down — record an HONEST degraded event so the timeline reflects
        # the failed scrape, then fall back to the last-good snapshot if one exists.
        # We NEVER fabricate a snapshot/facts here; only the failure is recorded.
        rows = st.query("SELECT id, source, source_url, fetched_at, record_count FROM snapshots ORDER BY id DESC LIMIT 1")
        last = rows[0] if rows else None
        detail = f"adsb.lol military ADS-B unreachable: {err}"
        if last:
            detail += (f" · serving last-good snapshot #{last['id']} "
                       f"({last['record_count']} records @ {last['fetched_at']})")
        else:
            detail += " · no prior snapshot to serve"
        event_id = st.insert_returning_id(
            "INSERT INTO events(snapshot_id, kind, title, detail, severity, source, source_url, ts) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (None, "degraded", f"intel feed scrape failed ({mode})", detail,
             "warn", "adsb.lol/mil", _MIL_ADSB_URL, fetched_at),
        )
        if last:
            return _envelope("cached", {
                "error": err,
                "event_id": event_id,
                "snapshot_id": last["id"],
                "record_count": last["record_count"],
                "last_fetched_at": last["fetched_at"],
                "events_created": 1,
                "note": "live upstream unreachable; serving last-good snapshot from DB",
            }, _adsb_citation())
        return _envelope("degraded", {"error": err, "event_id": event_id, "events_created": 1,
                                       "note": "live upstream unreachable and no prior snapshot"}, _adsb_citation())

    ac = payload.get("ac") or payload.get("aircraft") or []
    n = len(ac)
    snap_id = st.insert_returning_id(
        "INSERT INTO snapshots(source, source_url, mode, fetched_at, http_status, record_count, payload) "
        "VALUES(?,?,?,?,?,?,?)",
        ("adsb.lol/mil", _MIL_ADSB_URL, mode, fetched_at, http_status, n, json.dumps(payload)[:200000]),
    )

    facts = _derive_facts(payload)
    for kind, label, value in facts:
        st.execute(
            "INSERT INTO facts(snapshot_id, kind, label, value, created_at) VALUES(?,?,?,?,?)",
            (snap_id, kind, label, value, fetched_at),
        )

    # One timeline event per crawl, carrying the observed count.
    event_id = st.insert_returning_id(
        "INSERT INTO events(snapshot_id, kind, title, detail, severity, source, source_url, ts) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (snap_id, "crawl",
         f"{n} military aircraft observed",
         f"adsb.lol military ADS-B snapshot · {len(facts)} facts derived",
         "info" if n else "low", "adsb.lol/mil", _MIL_ADSB_URL, fetched_at),
    )

    # Callers own the surrounding transaction and deliver these intents only
    # after it commits. A missing queue fails closed: in-app alerts persist,
    # while no external ntfy side effect is attempted.
    if ntfy_actions is None:
        ntfy_actions = []
    alerts = _evaluate_watchlists(
        st,
        snap_id,
        event_id,
        n,
        facts,
        fetched_at,
        ntfy_actions=ntfy_actions,
    )

    return _envelope("live", {
        "snapshot_id": snap_id,
        "event_id": event_id,
        "record_count": n,
        "facts_created": len(facts),
        "events_created": 1,
        "alerts_created": len(alerts),
        "http_status": http_status,
    }, _adsb_citation())


def _coerce_num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _evaluate_watchlists(st: _Store, snap_id: int, event_id: int, count: int,
                          facts: List[Tuple[str, str, str]], ts: str, *,
                          ntfy_actions: List[Dict[str, Any]]) -> List[int]:
    """Evaluate enabled watchlist triggers against this snapshot's facts.

    Supported fields: 'count' (the military-aircraft count) and 'type:<airframe>'
    (the per-type count). Ops: gt, gte, lt, lte, eq. A match writes a real
    notification row (the alert) linked to the watchlist/trigger/event.
    """
    fact_map: Dict[str, float] = {"count": float(count)}
    for kind, label, value in facts:
        if kind == "type" and label.startswith("airframe:"):
            num = _coerce_num(value)
            if num is not None:
                fact_map["type:" + label.split("airframe:", 1)[1]] = num
    created: List[int] = []
    cfg = _ntfy_config()  # None when no push channel is configured (in-app only)
    now_ts = time.time()
    wls = st.query("SELECT id, name FROM watchlists WHERE enabled=1")
    for wl in wls:
        trigs = st.query("SELECT id, field, op, threshold FROM triggers WHERE watchlist_id=?", (wl["id"],))
        for tg in trigs:
            key = (int(wl["id"]), int(tg["id"]))
            op = (tg["op"] or "gt").lower()
            actual = fact_map.get(tg["field"])
            thr = _coerce_num(tg["threshold"])
            if actual is None or thr is None:
                # Un-evaluatable this snapshot: treat as not firing so the next
                # real fire registers as a fresh clear->fire edge. If it was
                # firing, this is a fire->clear edge — page a recovery notice.
                # (State is only tracked when a push channel is configured.)
                _queue_ntfy_transition(
                    ntfy_actions,
                    key=key,
                    cfg=cfg,
                    firing=False,
                    title=f"killinchu · watchlist '{wl['name']}' recovered",
                    message=(
                        f"{tg['field']} {op} {tg['threshold']} no longer evaluatable "
                        f"(data unavailable)\nseverity info · {ts}"
                    ),
                    now_ts=now_ts,
                )
                continue
            hit = (
                (op == "gt" and actual > thr) or
                (op == "gte" and actual >= thr) or
                (op == "lt" and actual < thr) or
                (op == "lte" and actual <= thr) or
                (op == "eq" and actual == thr)
            )
            if not hit:
                # Condition no longer met this snapshot. On a fire->clear edge
                # (was firing, now clear) page a single recovery notice.
                _queue_ntfy_transition(
                    ntfy_actions,
                    key=key,
                    cfg=cfg,
                    firing=False,
                    title=f"killinchu · watchlist '{wl['name']}' recovered",
                    message=(
                        f"{tg['field']} {op} {tg['threshold']} cleared "
                        f"(observed {actual:g})\n"
                        f"severity info · source adsb.lol/mil · {ts}"
                    ),
                    now_ts=now_ts,
                )
                continue
            nid = st.insert_returning_id(
                "INSERT INTO notifications(watchlist_id, trigger_id, event_id, title, detail, severity, source, source_url, ts) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (wl["id"], tg["id"], event_id,
                 f"Watchlist '{wl['name']}' triggered",
                 f"{tg['field']} {op} {tg['threshold']} (observed {actual:g})",
                 "warn", "adsb.lol/mil", _MIL_ADSB_URL, ts),
            )
            if nid is not None:
                created.append(nid)
            # Optional, edge-triggered push: only on a clear->fire edge (or after
            # the cooldown re-page window). A standing condition that keeps firing
            # on every crawl does NOT re-page. No channel configured => no push and
            # no state tracking (so enabling a channel mid-condition still pages).
            if cfg is not None:
                _queue_ntfy_transition(
                    ntfy_actions,
                    key=key,
                    cfg=cfg,
                    firing=True,
                    title=f"killinchu · watchlist '{wl['name']}'",
                    message=(
                        f"{tg['field']} {op} {tg['threshold']} (observed {actual:g})\n"
                        f"severity warn · source adsb.lol/mil · {ts}"
                    ),
                    now_ts=now_ts,
                )
    return created


# ---------------------------------------------------------------------------
# Auto-crawl scheduler — keeps the intel feed updating itself on a schedule.
#
# An in-process asyncio task periodically runs the SAME run_crawl() the manual
# /crawl/run endpoint uses, so the timeline + alerts refresh and watchlist
# triggers fire with no human in the loop. Honest by construction: it reuses
# run_crawl(), which records a degraded event (never fabricates) when the
# upstream is unreachable.
#
# Env-configurable (all optional):
#   KILLINCHU_AUTO_CRAWL                  enable/disable (default on; "0"/"false" off)
#   KILLINCHU_CRAWL_INTERVAL_SECONDS      base interval between runs (default 300, floor 30)
#   KILLINCHU_CRAWL_JITTER_SECONDS        +/- random jitter per cycle (default min(30, interval/4))
#   KILLINCHU_CRAWL_INITIAL_DELAY_SECONDS delay before the first run (default 15)
#   KILLINCHU_CRAWL_MAX_BACKOFF_SECONDS   cap for exponential backoff on failures (default 6*interval)
# ---------------------------------------------------------------------------
_SCHED_STARTED = False
_sched_lock = threading.Lock()  # non-reentrant: guards against overlapping runs
_STORAGE_FAILURE_CLASS = "storage_unavailable"
_STORAGE_FAILURE_PATTERNS = (
    "database or disk is full",
    "disk i/o error",
    "no space left on device",
    "disk quota exceeded",
    "attempt to write a readonly database",
    "read-only file system",
    "enospc",
)
_STORAGE_REMEDIATION = (
    "Free writable storage for the Killinchu durable store, then restart the "
    "service. Scheduled and manual crawls remain fail-closed until restart."
)
_sched_state: Dict[str, Any] = {
    "enabled": None,
    "interval_seconds": None,
    "jitter_seconds": None,
    "running": False,
    "runs": 0,
    "last_run_at": None,
    "last_success_at": None,
    "last_status": None,
    "last_error": None,
    "consecutive_failures": 0,
    "next_run_at": None,
    "circuit_open": False,
    "failure_class": None,
    "paused_at": None,
    "operator_action": None,
}


def _scheduler_failure_class(error: Any) -> Optional[str]:
    """Classify only known non-retriable local-storage failures.

    Upstream timeouts, rate limits, and malformed responses remain ordinary
    degraded runs with exponential backoff. Storage failures are different:
    retrying the same write forever cannot recover the disk and can flood logs.
    """
    if isinstance(error, OSError) and getattr(error, "errno", None) in (28, 30, 122):
        return _STORAGE_FAILURE_CLASS
    normalized = str(error or "").casefold()
    if any(pattern in normalized for pattern in _STORAGE_FAILURE_PATTERNS):
        return _STORAGE_FAILURE_CLASS
    return None


def _open_scheduler_circuit(error: Any, paused_at: Optional[str] = None) -> None:
    """Halt crawl writes after a non-retriable storage failure."""
    _sched_state.update({
        "last_status": "error",
        "last_error": str(error),
        "next_run_at": None,
        "circuit_open": True,
        "failure_class": _STORAGE_FAILURE_CLASS,
        "paused_at": paused_at or _now_iso(),
        "operator_action": _STORAGE_REMEDIATION,
    })


def _scheduler_health(cfg: Dict[str, Any]) -> str:
    """Return the public scheduler health without equating wiring with health."""
    if _sched_state["circuit_open"]:
        return "failed"
    if not cfg["enabled"] or not _SCHED_STARTED:
        return "disabled"
    last_status = str(_sched_state.get("last_status") or "").lower()
    if last_status == "live":
        return "ok"
    if last_status in ("cached", "degraded", "error", "skipped"):
        return "degraded"
    return "starting"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "")).strip())
    except Exception:
        return default


def scheduler_config() -> Dict[str, Any]:
    """Resolve the auto-crawl config from the environment (honest, bounded)."""
    interval = max(30, _env_int("KILLINCHU_CRAWL_INTERVAL_SECONDS", 300))
    jitter = max(0, _env_int("KILLINCHU_CRAWL_JITTER_SECONDS", min(30, interval // 4)))
    initial = max(0, _env_int("KILLINCHU_CRAWL_INITIAL_DELAY_SECONDS", 15))
    max_backoff = max(interval, _env_int("KILLINCHU_CRAWL_MAX_BACKOFF_SECONDS", interval * 6))
    return {
        "enabled": _env_bool("KILLINCHU_AUTO_CRAWL", True),
        "interval": interval,
        "jitter": jitter,
        "initial": initial,
        "max_backoff": max_backoff,
    }


def run_crawl_guarded(mode: str = "auto") -> Optional[Dict[str, Any]]:
    """Run one crawl unless one is already in flight (no pile-up).

    Returns the run_crawl() envelope, or None if a run was already in progress
    and this call was skipped, or if the storage circuit is open. The lock is
    non-blocking so a slow run never causes scheduled cycles to queue up.
    """
    if _sched_state["circuit_open"]:
        return None
    if not _sched_lock.acquire(blocking=False):
        return None
    try:
        st = _store()
        if not st.ok():
            return run_crawl(mode=mode, ntfy_actions=[])
        ntfy_actions: List[Dict[str, Any]] = []
        with st.transaction():
            result = run_crawl(
                mode=mode,
                ntfy_actions=ntfy_actions,
            )
        _deliver_ntfy_actions(ntfy_actions)
        return result
    finally:
        _sched_lock.release()


async def _scheduler_loop() -> None:
    """Periodic auto-crawl loop with jitter + exponential backoff on failure."""
    import asyncio
    import random

    cfg = scheduler_config()
    _sched_state["enabled"] = True
    _sched_state["interval_seconds"] = cfg["interval"]
    _sched_state["jitter_seconds"] = cfg["jitter"]
    print(f"[killinchu-backend] auto-crawl loop started "
          f"interval={cfg['interval']}s jitter={cfg['jitter']}s "
          f"initial_delay={cfg['initial']}s", file=sys.stderr)

    await asyncio.sleep(cfg["initial"])

    while True:
        cfg = scheduler_config()  # re-read each cycle so tuning needs no code change
        _sched_state["interval_seconds"] = cfg["interval"]
        _sched_state["jitter_seconds"] = cfg["jitter"]
        _sched_state["running"] = True
        started = _now_iso()
        try:
            # run_crawl is blocking (urllib + sqlite); keep the event loop free.
            res = await asyncio.to_thread(run_crawl_guarded, "auto")
            if res is None:
                _sched_state["last_status"] = "skipped"  # overlap guard fired
            else:
                status = res.get("status")
                _sched_state["runs"] += 1
                _sched_state["last_run_at"] = started
                _sched_state["last_status"] = status
                if status == "live":
                    _sched_state["consecutive_failures"] = 0
                    _sched_state["last_error"] = None
                    _sched_state["last_success_at"] = started
                    _sched_state["failure_class"] = None
                    _sched_state["paused_at"] = None
                    _sched_state["operator_action"] = None
                else:
                    # 'cached'/'degraded' = the scrape did not get fresh data.
                    _sched_state["consecutive_failures"] += 1
                    error = res.get("error")
                    _sched_state["last_error"] = error
                    if _scheduler_failure_class(error) == _STORAGE_FAILURE_CLASS:
                        _open_scheduler_circuit(error, paused_at=started)
                        print(
                            "[killinchu-backend] auto-crawl halted: "
                            f"{_STORAGE_FAILURE_CLASS} ({error})",
                            file=sys.stderr,
                        )
                        return
        except Exception as e:  # never let the loop die
            _sched_state["consecutive_failures"] += 1
            _sched_state["last_run_at"] = started
            _sched_state["last_status"] = "error"
            _sched_state["last_error"] = repr(e)
            print(f"[killinchu-backend] auto-crawl cycle error: {e!r}", file=sys.stderr)
            if _scheduler_failure_class(e) == _STORAGE_FAILURE_CLASS:
                _open_scheduler_circuit(e, paused_at=started)
                print(
                    "[killinchu-backend] auto-crawl halted fail-closed; "
                    f"operator action: {_STORAGE_REMEDIATION}",
                    file=sys.stderr,
                )
                return
        finally:
            _sched_state["running"] = False

        cf = _sched_state["consecutive_failures"]
        if cf > 0:
            delay = min(cfg["max_backoff"], cfg["interval"] * (2 ** min(cf, 6)))
        else:
            delay = cfg["interval"]
        if cfg["jitter"]:
            delay += random.uniform(-cfg["jitter"], cfg["jitter"])
        delay = max(5.0, delay)
        try:
            _sched_state["next_run_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()
        except Exception:
            _sched_state["next_run_at"] = None
        await asyncio.sleep(delay)


def start_scheduler(app) -> str:
    """Wire the auto-crawl loop onto the app's startup (idempotent, guarded)."""
    global _SCHED_STARTED
    cfg = scheduler_config()
    if not cfg["enabled"]:
        _sched_state["enabled"] = False
        return "auto-crawl disabled (KILLINCHU_AUTO_CRAWL)"
    if _SCHED_STARTED:
        return "auto-crawl already wired"
    _SCHED_STARTED = True

    @app.on_event("startup")
    async def _kc_auto_crawl_startup():  # pragma: no cover - runtime only
        import asyncio
        asyncio.create_task(_scheduler_loop())

    return f"auto-crawl wired interval={cfg['interval']}s jitter={cfg['jitter']}s"


# ---------------------------------------------------------------------------
# FastAPI registration
# ---------------------------------------------------------------------------
def register(
    app,
    ns: str = "killinchu",
    *,
    emit_receipt: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
) -> str:
    """Mount the killinchu backend routes on *app* and return the base path.

    Registers every ``/api/{ns}/*`` handler BEFORE the SPA catch-all so the API
    is reachable, and returns the mounted base (e.g. ``/api/killinchu``). Follows
    the FastAPI 0.137.2 convention: POST handlers taking a raw ``Request`` are
    added via the router so they bind correctly. The whole body is caller-guarded
    upstream so a failure here can never crash the host app.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    base = f"/api/{ns}"
    st = _store()
    reconcile_lock = threading.RLock()

    async def _json_body(request: "Request") -> dict:
        try:
            b = await request.json()
        except Exception:
            return {}
        return b if isinstance(b, dict) else {}

    def _operator_authority(
        request: "Request",
    ) -> Tuple[Optional[str], Optional["JSONResponse"]]:
        """Require only the canonical fail-closed bearer authority."""
        try:
            from szl_provenance import _wire_d_authorize_request

            actor_id, authorization_error = _wire_d_authorize_request(request)
        except Exception:
            actor_id, authorization_error = None, "NOT_CONFIGURED"
        if authorization_error is not None:
            if authorization_error == "NOT_CONFIGURED":
                reason = "operator authority is not configured"
                status_code = 503
            elif authorization_error == "MISSING":
                reason = "missing operator bearer authority"
                status_code = 401
            else:
                reason = "invalid operator bearer authority"
                status_code = 401
            response = JSONResponse(
                _envelope("denied", {"error": reason}, []),
                status_code=status_code,
                headers={"WWW-Authenticate": "Bearer"},
            )
            return None, response
        return actor_id, None

    def _operator_gate(
        request: "Request",
    ) -> Tuple[Optional[str], Optional[str], Optional["JSONResponse"]]:
        """Require the canonical bearer and a bounded replay key."""
        actor_id, authority_error = _operator_authority(request)
        if authority_error is not None:
            return None, None, authority_error

        key = (request.headers.get("idempotency-key") or "").strip()
        if not _IDEMPOTENCY_KEY_RE.fullmatch(key):
            return None, None, JSONResponse(
                _envelope(
                    "error",
                    {
                        "error": (
                            "Idempotency-Key is required and must be 8-128 "
                            "characters from A-Z, a-z, 0-9, dot, underscore, colon, or dash"
                        )
                    },
                    [],
                ),
                status_code=400,
            )
        key_hash = "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        return actor_id, key_hash, None

    def _claim_mutation(
        *,
        operation: str,
        actor_id: str,
        key_hash: str,
        request_payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, str]], Optional["JSONResponse"]]:
        request_digest = _sha256_json(
            {"operation": operation, "payload": request_payload}
        )
        claim_state, existing = _store().claim_operator_mutation(
            key_hash=key_hash,
            operation=operation,
            actor_id=actor_id,
            request_digest=request_digest,
        )
        if claim_state == "replay" and existing is not None:
            response = json.loads(existing["response_json"])
            response["idempotency_replayed"] = True
            return None, JSONResponse(
                response,
                status_code=int(existing["status_code"]),
                headers={"Idempotency-Replayed": "true"},
            )
        if claim_state == "conflict":
            return None, JSONResponse(
                _envelope(
                    "conflict",
                    {"error": "Idempotency-Key was already used for a different mutation"},
                    [],
                ),
                status_code=409,
            )
        if claim_state == "receipt_pending":
            return None, _reconcile_mutation(key_hash, replayed=True)
        if claim_state == "in_progress":
            state = existing.get("state") if existing else "in_progress"
            return None, JSONResponse(
                _envelope(
                    "conflict",
                    {
                        "error": (
                            "A mutation with this Idempotency-Key is already in progress "
                            "or has an ambiguous receipt outcome; operator reconciliation "
                            "is required"
                        ),
                        "mutation_state": state,
                        "idempotency_key_hash": key_hash,
                    },
                    [],
                ),
                status_code=409,
            )
        return {
            "operation": operation,
            "actor_id": actor_id,
            "key_hash": key_hash,
            "request_digest": request_digest,
        }, None

    def _stage_mutation(
        context: Dict[str, str],
        result: Dict[str, Any],
        *,
        status_code: int = 200,
    ) -> None:
        """Stage replay data inside the same transaction as the mutation."""
        receipt_request = _mutation_receipt_request(
            operation=context["operation"],
            actor_id=context["actor_id"],
            key_hash=context["key_hash"],
            request_digest=context["request_digest"],
            result=result,
        )
        pending_response = {
            **result,
            "idempotency_replayed": False,
        }
        st.stage_operator_mutation(
            key_hash=context["key_hash"],
            status_code=status_code,
            response=pending_response,
            receipt_request=receipt_request,
        )

    def _emit_mutation_receipt(receipt_request: Dict[str, Any]) -> Dict[str, Any]:
        if emit_receipt is None:
            return _unsigned_mutation_receipt(receipt_request)
        receipt = emit_receipt("operator_mutation", receipt_request)
        if not isinstance(receipt, dict):
            raise RuntimeError("canonical receipt emitter returned a non-object")
        if not (receipt.get("digest") or receipt.get("receipt_digest")):
            raise RuntimeError("canonical receipt emitter returned no digest")
        if not isinstance(receipt.get("signed"), bool):
            raise RuntimeError("canonical receipt emitter omitted honest signed state")
        return receipt

    def _reconcile_mutation(
        key_hash: str,
        *,
        replayed: bool,
    ) -> "JSONResponse":
        """Resolve one durable pending receipt without replaying its mutation."""
        with reconcile_lock:
            row = st.get_operator_mutation(key_hash=key_hash)
            if row is None:
                return JSONResponse(
                    _envelope("error", {"error": "mutation state not found"}, []),
                    status_code=404,
                )
            if row["state"] == "completed":
                response = json.loads(row["response_json"])
                response["idempotency_replayed"] = replayed
                return JSONResponse(
                    response,
                    status_code=int(row["status_code"]),
                    headers={
                        "Idempotency-Replayed": "true" if replayed else "false"
                    },
                )
            if row["state"] != "receipt_pending":
                return JSONResponse(
                    _envelope(
                        "conflict",
                        {
                            "error": "mutation is not safely auto-reconcilable",
                            "mutation_state": row["state"],
                            "idempotency_key_hash": key_hash,
                        },
                        [],
                    ),
                    status_code=409,
                )
            if not st.begin_receipt_emission(key_hash=key_hash):
                return JSONResponse(
                    _envelope(
                        "conflict",
                        {
                            "error": "receipt reconciliation is already claimed",
                            "mutation_state": "receipt_emitting",
                            "idempotency_key_hash": key_hash,
                        },
                        [],
                    ),
                    status_code=409,
                )
            pending_response = json.loads(row["response_json"])
            receipt_request = json.loads(row["receipt_json"])
            try:
                receipt = _emit_mutation_receipt(receipt_request)
            except Exception as exc:
                print(
                    "[killinchu-backend] canonical mutation receipt emission "
                    f"needs reconciliation: {exc!r}",
                    file=sys.stderr,
                )
                return JSONResponse(
                    _envelope(
                        "degraded",
                        {
                            "error": "canonical receipt emission requires reconciliation",
                            "mutation_state": "receipt_emitting",
                            "idempotency_key_hash": key_hash,
                        },
                        [],
                    ),
                    status_code=503,
                )

            stored_response = {
                **pending_response,
                "mutation_receipt": receipt,
                "idempotency_replayed": False,
            }
            try:
                with st.transaction():
                    st.complete_operator_mutation(
                        key_hash=key_hash,
                        status_code=int(row["status_code"]),
                        response=stored_response,
                        receipt=receipt,
                    )
            except Exception as exc:
                print(
                    "[killinchu-backend] canonical receipt was emitted but durable "
                    f"completion needs reconciliation: {exc!r}",
                    file=sys.stderr,
                )
                return JSONResponse(
                    _envelope(
                        "degraded",
                        {
                            "error": "receipt emitted; durable completion is ambiguous",
                            "mutation_state": "receipt_emitting",
                            "idempotency_key_hash": key_hash,
                        },
                        [],
                    ),
                    status_code=503,
                )
            response = dict(stored_response)
            response["idempotency_replayed"] = replayed
        return JSONResponse(
            response,
            status_code=int(row["status_code"]),
            headers={"Idempotency-Replayed": "true" if replayed else "false"},
        )

    # -- db health (used by /healthz) --------------------------------------
    async def db_health(request: Request) -> JSONResponse:
        """GET /db/health — report the durable store's backend + last ping."""
        return JSONResponse(_envelope("ok", {"db": _store().health()}, []))

    # -- live (cached scrape) ---------------------------------------------
    async def live(request: Request) -> JSONResponse:
        """POST /live — on-demand cached read with citations; degrades honestly."""
        actor_id, key_hash, gate_error = _operator_gate(request)
        if gate_error is not None:
            return gate_error
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, _adsb_citation()), status_code=200)
        context, replay = _claim_mutation(
            operation="live.refresh",
            actor_id=actor_id,
            key_hash=key_hash,
            request_payload={},
        )
        if replay is not None:
            return replay
        if _sched_state["circuit_open"]:
            result = _envelope("failed", {
                "health": "failed",
                "error": _sched_state["last_error"],
                "failure_class": _sched_state["failure_class"],
                "circuit_open": True,
                "operator_action": _sched_state["operator_action"],
            }, _adsb_citation())
            with s.transaction():
                _stage_mutation(context, result, status_code=503)
            return _reconcile_mutation(key_hash, replayed=False)
        rows = s.query("SELECT id, fetched_at, record_count FROM snapshots ORDER BY id DESC LIMIT 1")
        if rows:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["fetched_at"])).total_seconds()
            except Exception:
                age = 1e9
            if age < _LIVE_CACHE_TTL:
                result = _envelope("cached", {
                    "snapshot_id": rows[0]["id"],
                    "record_count": rows[0]["record_count"],
                    "age_seconds": round(age, 1),
                    "cache_ttl": _LIVE_CACHE_TTL,
                }, _adsb_citation())
                with s.transaction():
                    _stage_mutation(context, result)
                return _reconcile_mutation(key_hash, replayed=False)
        # Cache-miss: run_crawl is blocking (urllib ADS-B fetch up to 12s +
        # sqlite). Run it off the event loop so a cold/slow scrape can't stall
        # the whole app. Its database writes and receipt-pending state commit in
        # one database transaction before the separate Khipu reconciliation.
        import asyncio

        def _refresh_and_stage() -> "JSONResponse":
            ntfy_actions: List[Dict[str, Any]] = []
            try:
                with s.transaction():
                    result = run_crawl(
                        mode="live",
                        ntfy_actions=ntfy_actions,
                    )
                    _stage_mutation(context, result)
            except Exception:
                s.fail_operator_mutation(key_hash=key_hash)
                raise
            _deliver_ntfy_actions(ntfy_actions)
            return _reconcile_mutation(key_hash, replayed=False)

        return await asyncio.to_thread(_refresh_and_stage)

    # -- crawl/run (manual) ------------------------------------------------
    async def crawl_run(request: Request) -> JSONResponse:
        """POST /crawl/run — trigger a manual crawl and return its result envelope."""
        actor_id, key_hash, gate_error = _operator_gate(request)
        if gate_error is not None:
            return gate_error
        context, replay = _claim_mutation(
            operation="crawl.run",
            actor_id=actor_id,
            key_hash=key_hash,
            request_payload={},
        )
        if replay is not None:
            return replay
        if _sched_state["circuit_open"]:
            st.fail_operator_mutation(key_hash=key_hash)
            return JSONResponse(_envelope("failed", {
                "health": "failed",
                "error": _sched_state["last_error"],
                "failure_class": _sched_state["failure_class"],
                "circuit_open": True,
                "operator_action": _sched_state["operator_action"],
            }, _adsb_citation()), status_code=503)
        ntfy_actions: List[Dict[str, Any]] = []
        try:
            with st.transaction():
                result = run_crawl(
                    mode="crawl",
                    ntfy_actions=ntfy_actions,
                )
                _stage_mutation(context, result)
        except Exception:
            st.fail_operator_mutation(key_hash=key_hash)
            raise
        _deliver_ntfy_actions(ntfy_actions)
        return _reconcile_mutation(key_hash, replayed=False)

    # -- crawl/status (auto-crawl scheduler health) ------------------------
    async def crawl_status(request: Request) -> JSONResponse:
        """GET /crawl/status — report the auto-crawl scheduler configuration + health."""
        cfg = scheduler_config()
        health = _scheduler_health(cfg)
        last_status = str(_sched_state.get("last_status") or "").lower()
        freshness = "fresh" if last_status == "live" else (
            "stale" if _sched_state.get("last_success_at") else "unverified"
        )
        data = {
            "health": health,
            "freshness": freshness,
            "config": {
                "enabled": cfg["enabled"],
                "interval_seconds": cfg["interval"],
                "jitter_seconds": cfg["jitter"],
                "initial_delay_seconds": cfg["initial"],
                "max_backoff_seconds": cfg["max_backoff"],
            },
            "scheduler": dict(_sched_state),
            "wired": _SCHED_STARTED,
            "circuit_open": _sched_state["circuit_open"],
            "failure_class": _sched_state["failure_class"],
            "paused_at": _sched_state["paused_at"],
            "operator_action": _sched_state["operator_action"],
        }
        return JSONResponse(_envelope(health, data, []))

    # -- timeline ----------------------------------------------------------
    async def timeline(request: Request) -> JSONResponse:
        """GET /timeline — return the events timeline from the durable store."""
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"events": []}, []))
        try:
            limit = max(1, min(200, int(request.query_params.get("limit", "50"))))
        except Exception:
            limit = 50
        rows = s.query(
            "SELECT id, kind, title, detail, severity, source, source_url, ts FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        status = "ok" if rows else "degraded"
        return JSONResponse(_envelope(status, {"events": rows, "count": len(rows)}, _adsb_citation()))

    # -- alerts/recent -----------------------------------------------------
    async def alerts_recent(request: Request) -> JSONResponse:
        """GET /alerts/recent — return recent watchlist-hit notifications."""
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"alerts": []}, []))
        try:
            limit = max(1, min(200, int(request.query_params.get("limit", "50"))))
        except Exception:
            limit = 50
        rows = s.query(
            "SELECT id, watchlist_id, trigger_id, event_id, title, detail, severity, source, source_url, ts "
            "FROM notifications ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        status = "ok" if rows else "degraded"
        return JSONResponse(_envelope(status, {"alerts": rows, "count": len(rows)}, _adsb_citation()))

    # -- watchlists CRUD ---------------------------------------------------
    def _watchlist_dto(s: _Store, wid: int) -> Optional[Dict[str, Any]]:
        wl = s.query("SELECT id, name, description, enabled, created_at, updated_at FROM watchlists WHERE id=?", (wid,))
        if not wl:
            return None
        d = wl[0]
        d["enabled"] = bool(d.get("enabled"))
        d["triggers"] = s.query(
            "SELECT id, field, op, threshold, created_at FROM triggers WHERE watchlist_id=? ORDER BY id", (wid,)
        )
        return d

    async def watchlists_list(request: Request) -> JSONResponse:
        """GET /watchlists — list watchlists (empty + degraded when no backend)."""
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"watchlists": []}, []))
        wls = s.query("SELECT id FROM watchlists ORDER BY id")
        out = [_watchlist_dto(s, w["id"]) for w in wls]
        return JSONResponse(_envelope("ok", {"watchlists": out, "count": len(out)}, []))

    async def watchlists_create(request: Request) -> JSONResponse:
        """POST /watchlists — create a watchlist and its triggers."""
        actor_id, key_hash, gate_error = _operator_gate(request)
        if gate_error is not None:
            return gate_error
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        body = await _json_body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return JSONResponse(_envelope("error", {"error": "name is required"}, []), status_code=400)
        context, replay = _claim_mutation(
            operation="watchlist.create",
            actor_id=actor_id,
            key_hash=key_hash,
            request_payload=body,
        )
        if replay is not None:
            return replay
        now = _now_iso()
        try:
            with s.transaction():
                wid = s.insert_returning_id(
                    "INSERT INTO watchlists(name, description, enabled, created_at, updated_at) VALUES(?,?,?,?,?)",
                    (name, body.get("description") or "", 1 if body.get("enabled", True) else 0, now, now),
                )
                for tg in (body.get("triggers") or []):
                    field = (tg.get("field") or "").strip()
                    op = (tg.get("op") or "gt").strip().lower()
                    thr = tg.get("threshold")
                    if not field or thr is None:
                        continue
                    s.execute(
                        "INSERT INTO triggers(watchlist_id, field, op, threshold, created_at) VALUES(?,?,?,?,?)",
                        (wid, field, op, str(thr), now),
                    )
                result = _envelope("ok", {"watchlist": _watchlist_dto(s, wid)}, [])
                _stage_mutation(context, result, status_code=201)
        except Exception:
            s.fail_operator_mutation(key_hash=key_hash)
            raise
        return _reconcile_mutation(key_hash, replayed=False)

    async def watchlists_update(request: Request) -> JSONResponse:
        """PUT /watchlists/{wid} — update a watchlist and its triggers."""
        actor_id, key_hash, gate_error = _operator_gate(request)
        if gate_error is not None:
            return gate_error
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        wid = int(request.path_params["wid"])
        body = await _json_body(request)
        context, replay = _claim_mutation(
            operation=f"watchlist.update:{wid}",
            actor_id=actor_id,
            key_hash=key_hash,
            request_payload=body,
        )
        if replay is not None:
            return replay
        if not _watchlist_dto(s, wid):
            s.fail_operator_mutation(key_hash=key_hash)
            return JSONResponse(_envelope("error", {"error": "not found"}, []), status_code=404)
        now = _now_iso()
        try:
            with s.transaction():
                sets, params = [], []
                if "name" in body:
                    sets.append("name=?"); params.append((body.get("name") or "").strip())
                if "description" in body:
                    sets.append("description=?"); params.append(body.get("description") or "")
                if "enabled" in body:
                    sets.append("enabled=?"); params.append(1 if body.get("enabled") else 0)
                sets.append("updated_at=?"); params.append(now)
                params.append(wid)
                s.execute(f"UPDATE watchlists SET {', '.join(sets)} WHERE id=?", tuple(params))
                # Replace triggers when provided.
                if "triggers" in body:
                    s.execute("DELETE FROM triggers WHERE watchlist_id=?", (wid,))
                    for tg in (body.get("triggers") or []):
                        field = (tg.get("field") or "").strip()
                        op = (tg.get("op") or "gt").strip().lower()
                        thr = tg.get("threshold")
                        if not field or thr is None:
                            continue
                        s.execute(
                            "INSERT INTO triggers(watchlist_id, field, op, threshold, created_at) VALUES(?,?,?,?,?)",
                            (wid, field, op, str(thr), now),
                        )
                result = _envelope("ok", {"watchlist": _watchlist_dto(s, wid)}, [])
                _stage_mutation(context, result)
        except Exception:
            s.fail_operator_mutation(key_hash=key_hash)
            raise
        return _reconcile_mutation(key_hash, replayed=False)

    async def watchlists_delete(request: Request) -> JSONResponse:
        """DELETE /watchlists/{wid} — delete a watchlist and its triggers."""
        actor_id, key_hash, gate_error = _operator_gate(request)
        if gate_error is not None:
            return gate_error
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        wid = int(request.path_params["wid"])
        context, replay = _claim_mutation(
            operation=f"watchlist.delete:{wid}",
            actor_id=actor_id,
            key_hash=key_hash,
            request_payload={},
        )
        if replay is not None:
            return replay
        if not _watchlist_dto(s, wid):
            s.fail_operator_mutation(key_hash=key_hash)
            return JSONResponse(_envelope("error", {"error": "not found"}, []), status_code=404)
        try:
            with s.transaction():
                s.execute("DELETE FROM triggers WHERE watchlist_id=?", (wid,))
                s.execute("DELETE FROM watchlists WHERE id=?", (wid,))
                result = _envelope("ok", {"deleted": wid}, [])
                _stage_mutation(context, result)
        except Exception:
            s.fail_operator_mutation(key_hash=key_hash)
            raise
        return _reconcile_mutation(key_hash, replayed=False)

    def _key_hash_from_path(request: "Request") -> Optional[str]:
        digest = str(request.path_params.get("key_digest") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        return f"sha256:{digest}"

    def _mutation_inspection(row: Dict[str, Any]) -> Dict[str, Any]:
        receipt_record = (
            json.loads(row["receipt_json"]) if row.get("receipt_json") else None
        )
        return {
            "idempotency_key_hash": row["idempotency_key_hash"],
            "operation": row["operation"],
            "actor_id": row["actor_id"],
            "request_digest": row["request_digest"],
            "state": row["state"],
            "status_code": row["status_code"],
            "response_digest": (
                _sha256_json(json.loads(row["response_json"]))
                if row.get("response_json")
                else None
            ),
            "receipt_record_digest": (
                _sha256_json(receipt_record) if receipt_record is not None else None
            ),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "safe_auto_reconcile": row["state"] == "receipt_pending",
            "requires_receipt_absence_confirmation": row["state"] == "receipt_emitting",
        }

    async def mutation_inspect(request: Request) -> JSONResponse:
        """Inspect a non-secret durable reconciliation state."""
        _, authority_error = _operator_authority(request)
        if authority_error is not None:
            return authority_error
        key_hash = _key_hash_from_path(request)
        if key_hash is None:
            return JSONResponse(
                _envelope("error", {"error": "invalid SHA-256 key digest"}, []),
                status_code=400,
            )
        row = st.get_operator_mutation(key_hash=key_hash)
        if row is None:
            return JSONResponse(
                _envelope("error", {"error": "mutation state not found"}, []),
                status_code=404,
            )
        return JSONResponse(
            _envelope("ok", {"mutation": _mutation_inspection(row)}, [])
        )

    async def mutation_reconcile(request: Request) -> JSONResponse:
        """Resolve a pending/ambiguous receipt without replaying the mutation."""
        _, authority_error = _operator_authority(request)
        if authority_error is not None:
            return authority_error
        key_hash = _key_hash_from_path(request)
        if key_hash is None:
            return JSONResponse(
                _envelope("error", {"error": "invalid SHA-256 key digest"}, []),
                status_code=400,
            )
        row = st.get_operator_mutation(key_hash=key_hash)
        if row is None:
            return JSONResponse(
                _envelope("error", {"error": "mutation state not found"}, []),
                status_code=404,
            )
        body = await _json_body(request)
        if row["state"] == "receipt_pending":
            return _reconcile_mutation(key_hash, replayed=True)
        if row["state"] == "receipt_emitting":
            if not (
                body.get("resolution") == "retry_receipt_emission"
                and body.get("receipt_absence_confirmed") is True
            ):
                return JSONResponse(
                    _envelope(
                        "conflict",
                        {
                            "error": (
                                "receipt outcome is ambiguous; confirm canonical "
                                "receipt absence before retrying emission"
                            ),
                            "mutation": _mutation_inspection(row),
                        },
                        [],
                    ),
                    status_code=409,
                )
            if not st.transition_operator_mutation(
                key_hash=key_hash,
                from_state="receipt_emitting",
                to_state="receipt_pending",
            ):
                return JSONResponse(
                    _envelope("conflict", {"error": "mutation state changed"}, []),
                    status_code=409,
                )
            return _reconcile_mutation(key_hash, replayed=True)
        if row["state"] in {"in_progress", "needs_operator_review"}:
            if not (
                body.get("resolution") == "close_without_replay"
                and body.get("side_effect_inspected") is True
            ):
                return JSONResponse(
                    _envelope(
                        "conflict",
                        {
                            "error": (
                                "side-effect state must be inspected before this "
                                "reservation can be closed without replay"
                            ),
                            "mutation": _mutation_inspection(row),
                        },
                        [],
                    ),
                    status_code=409,
                )
            if not st.transition_operator_mutation(
                key_hash=key_hash,
                from_state=row["state"],
                to_state="abandoned_after_review",
            ):
                return JSONResponse(
                    _envelope("conflict", {"error": "mutation state changed"}, []),
                    status_code=409,
                )
            closed = st.get_operator_mutation(key_hash=key_hash)
            return JSONResponse(
                _envelope(
                    "ok",
                    {
                        "mutation": _mutation_inspection(closed),
                        "replayed": False,
                        "side_effect_changed": False,
                    },
                    [],
                )
            )
        return JSONResponse(
            _envelope("ok", {"mutation": _mutation_inspection(row)}, [])
        )

    # Register all routes (early import => added before the SPA catch-all).
    operator_dependencies = [Depends(_declare_operator_bearer)]
    app.add_api_route(f"{base}/db/health", db_health, methods=["GET"])
    app.add_api_route(
        f"{base}/live",
        live,
        methods=["POST"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(
        f"{base}/crawl/run",
        crawl_run,
        methods=["POST"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(f"{base}/crawl/status", crawl_status, methods=["GET"])
    app.add_api_route(f"{base}/timeline", timeline, methods=["GET"])
    app.add_api_route(f"{base}/alerts/recent", alerts_recent, methods=["GET"])
    app.add_api_route(f"{base}/watchlists", watchlists_list, methods=["GET"])
    app.add_api_route(
        f"{base}/watchlists",
        watchlists_create,
        methods=["POST"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(
        f"{base}/watchlists/{{wid}}",
        watchlists_update,
        methods=["PUT"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(
        f"{base}/watchlists/{{wid}}",
        watchlists_delete,
        methods=["DELETE"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(
        f"{base}/operator-mutations/{{key_digest}}",
        mutation_inspect,
        methods=["GET"],
        dependencies=operator_dependencies,
    )
    app.add_api_route(
        f"{base}/operator-mutations/{{key_digest}}/reconcile",
        mutation_reconcile,
        methods=["POST"],
        dependencies=operator_dependencies,
    )

    # Start the self-updating auto-crawl scheduler (guarded so a failure here
    # never blocks route registration).
    try:
        sched_status = start_scheduler(app)
    except Exception as e:  # pragma: no cover - defensive
        sched_status = f"auto-crawl NOT wired ({e!r})"
        print(f"[killinchu-backend] {sched_status}", file=sys.stderr)

    return f"killinchu-backend-wired backend={st.backend} durable={st.ok()} | {sched_status}"


# Used by serve.py /healthz to add uptime + db ping without shadowing the route.
def health_fields() -> Dict[str, Any]:
    """Return backend health fields for the host ``/healthz`` payload.

    Reports process uptime and the durable-store health block. Any exception is
    swallowed and surfaced as ``db.backend == "error"`` so ``/healthz`` itself
    never breaks.
    """
    try:
        st = _store()
        return {"uptime_seconds": round(time.time() - _START_TS, 1), "db": st.health()}
    except Exception as e:  # never break /healthz
        return {"uptime_seconds": round(time.time() - _START_TS, 1), "db": {"backend": "error", "error": repr(e)}}
