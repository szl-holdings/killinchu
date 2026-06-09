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
#
# Tables: snapshots, facts, events, watchlists, triggers, notifications.

from __future__ import annotations

import json
import os
import sys
import threading
import time
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# NOTE: `from __future__ import annotations` (above) stringifies every annotation,
# so FastAPI resolves route-handler param types via THIS module's globals at
# add_api_route() time. The handlers are nested inside register() and annotate
# `request: Request` — that name must therefore live at module scope, or FastAPI
# mis-reads `request` as a required query parameter (HTTP 422). These imports are
# guarded so the module still loads (and degrades) where FastAPI is absent; when
# register() actually runs, FastAPI is by definition present.
try:  # pragma: no cover - import-environment dependent
    from fastapi import Request  # noqa: F401  (module-global for annotation resolution)
    from fastapi.responses import JSONResponse  # noqa: F401
except Exception:  # FastAPI not installed in this context; register() won't be called
    Request = Any  # type: ignore
    JSONResponse = Any  # type: ignore

DOCTRINE = "v11"
_START_TS = time.time()

# Real, public OSINT source used by the crawl/live scrape. adsb.lol publishes
# unauthenticated military ADS-B; killinchu_live_feeds already uses it. Decoded
# ADS-B is an UNAUTHENTICATED broadcast CLAIM, not attested truth (honest label).
_MIL_ADSB_URL = "https://api.adsb.lol/v2/mil"
_LIVE_CACHE_TTL = 60  # seconds a "live" scrape stays fresh before a re-fetch
_USER_AGENT = "killinchu-backend/1.0 (+https://killinchu.a11oy.net)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)",
            "CREATE INDEX IF NOT EXISTS idx_notif_ts ON notifications(ts)",
            "CREATE INDEX IF NOT EXISTS idx_facts_snap ON facts(snapshot_id)",
            "CREATE INDEX IF NOT EXISTS idx_snap_src ON snapshots(source, fetched_at)",
            "CREATE INDEX IF NOT EXISTS idx_trig_wl ON triggers(watchlist_id)",
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
        if self.backend == "sqlite" and self._sqlite is not None:
            self._sqlite.commit()
        # postgres connection is autocommit

    def ok(self) -> bool:
        return self.backend in ("postgres", "sqlite")

    def ping(self) -> bool:
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
        with self._lock:
            cur = self._cursor()
            cur.execute(self._q(sql), params)
            self._commit()
            cur.close()

    def insert_returning_id(self, sql: str, params: Tuple = ()) -> Optional[int]:
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

    def health(self) -> Dict[str, Any]:
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
        "status": status,           # ok | live | cached | degraded | error
        "doctrine": DOCTRINE,
        "service": "killinchu",
        "citations": citations,
        "fetchedAt": _now_iso(),
    }
    body.update(data)
    return body


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


def run_crawl(mode: str = "crawl") -> Dict[str, Any]:
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

    alerts = _evaluate_watchlists(st, snap_id, event_id, n, facts, fetched_at)

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
                          facts: List[Tuple[str, str, str]], ts: str) -> List[int]:
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
    wls = st.query("SELECT id, name FROM watchlists WHERE enabled=1")
    for wl in wls:
        trigs = st.query("SELECT id, field, op, threshold FROM triggers WHERE watchlist_id=?", (wl["id"],))
        for tg in trigs:
            actual = fact_map.get(tg["field"])
            thr = _coerce_num(tg["threshold"])
            if actual is None or thr is None:
                continue
            op = (tg["op"] or "gt").lower()
            hit = (
                (op == "gt" and actual > thr) or
                (op == "gte" and actual >= thr) or
                (op == "lt" and actual < thr) or
                (op == "lte" and actual <= thr) or
                (op == "eq" and actual == thr)
            )
            if not hit:
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
_sched_state: Dict[str, Any] = {
    "enabled": None,
    "interval_seconds": None,
    "jitter_seconds": None,
    "running": False,
    "runs": 0,
    "last_run_at": None,
    "last_status": None,
    "last_error": None,
    "consecutive_failures": 0,
    "next_run_at": None,
}


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
    and this call was skipped. The lock is non-blocking so a slow run never
    causes scheduled cycles to queue up.
    """
    if not _sched_lock.acquire(blocking=False):
        return None
    try:
        return run_crawl(mode=mode)
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
                else:
                    # 'cached'/'degraded' = the scrape did not get fresh data.
                    _sched_state["consecutive_failures"] += 1
                    _sched_state["last_error"] = (res.get("data") or {}).get("error")
        except Exception as e:  # never let the loop die
            _sched_state["consecutive_failures"] += 1
            _sched_state["last_status"] = "error"
            _sched_state["last_error"] = repr(e)
            print(f"[killinchu-backend] auto-crawl cycle error: {e!r}", file=sys.stderr)
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
def register(app, ns: str = "killinchu") -> str:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    base = f"/api/{ns}"
    st = _store()

    async def _json_body(request: "Request") -> dict:
        try:
            b = await request.json()
        except Exception:
            return {}
        return b if isinstance(b, dict) else {}

    # -- db health (used by /healthz) --------------------------------------
    async def db_health(request: Request) -> JSONResponse:
        return JSONResponse(_envelope("ok", {"db": _store().health()}, []))

    # -- live (cached scrape) ---------------------------------------------
    async def live(request: Request) -> JSONResponse:
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, _adsb_citation()), status_code=200)
        rows = s.query("SELECT id, fetched_at, record_count FROM snapshots ORDER BY id DESC LIMIT 1")
        if rows:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["fetched_at"])).total_seconds()
            except Exception:
                age = 1e9
            if age < _LIVE_CACHE_TTL:
                return JSONResponse(_envelope("cached", {
                    "snapshot_id": rows[0]["id"],
                    "record_count": rows[0]["record_count"],
                    "age_seconds": round(age, 1),
                    "cache_ttl": _LIVE_CACHE_TTL,
                }, _adsb_citation()))
        return JSONResponse(run_crawl(mode="live"))

    # -- crawl/run (manual) ------------------------------------------------
    async def crawl_run(request: Request) -> JSONResponse:
        return JSONResponse(run_crawl(mode="crawl"))

    # -- crawl/status (auto-crawl scheduler health) ------------------------
    async def crawl_status(request: Request) -> JSONResponse:
        cfg = scheduler_config()
        data = {
            "config": {
                "enabled": cfg["enabled"],
                "interval_seconds": cfg["interval"],
                "jitter_seconds": cfg["jitter"],
                "initial_delay_seconds": cfg["initial"],
                "max_backoff_seconds": cfg["max_backoff"],
            },
            "scheduler": dict(_sched_state),
            "wired": _SCHED_STARTED,
        }
        status = "ok" if (cfg["enabled"] and _SCHED_STARTED) else "disabled"
        return JSONResponse(_envelope(status, data, []))

    # -- timeline ----------------------------------------------------------
    async def timeline(request: Request) -> JSONResponse:
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
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"watchlists": []}, []))
        wls = s.query("SELECT id FROM watchlists ORDER BY id")
        out = [_watchlist_dto(s, w["id"]) for w in wls]
        return JSONResponse(_envelope("ok", {"watchlists": out, "count": len(out)}, []))

    async def watchlists_create(request: Request) -> JSONResponse:
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        body = await _json_body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return JSONResponse(_envelope("error", {"error": "name is required"}, []), status_code=400)
        now = _now_iso()
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
        return JSONResponse(_envelope("ok", {"watchlist": _watchlist_dto(s, wid)}, []), status_code=201)

    async def watchlists_update(request: Request) -> JSONResponse:
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        wid = int(request.path_params["wid"])
        if not _watchlist_dto(s, wid):
            return JSONResponse(_envelope("error", {"error": "not found"}, []), status_code=404)
        body = await _json_body(request)
        now = _now_iso()
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
        return JSONResponse(_envelope("ok", {"watchlist": _watchlist_dto(s, wid)}, []))

    async def watchlists_delete(request: Request) -> JSONResponse:
        s = _store()
        if not s.ok():
            return JSONResponse(_envelope("degraded", {"error": "no durable backend"}, []), status_code=503)
        wid = int(request.path_params["wid"])
        if not _watchlist_dto(s, wid):
            return JSONResponse(_envelope("error", {"error": "not found"}, []), status_code=404)
        s.execute("DELETE FROM triggers WHERE watchlist_id=?", (wid,))
        s.execute("DELETE FROM watchlists WHERE id=?", (wid,))
        return JSONResponse(_envelope("ok", {"deleted": wid}, []))

    # Register all routes (early import => added before the SPA catch-all).
    app.add_api_route(f"{base}/db/health", db_health, methods=["GET"])
    app.add_api_route(f"{base}/live", live, methods=["POST"])
    app.add_api_route(f"{base}/crawl/run", crawl_run, methods=["POST"])
    app.add_api_route(f"{base}/crawl/status", crawl_status, methods=["GET"])
    app.add_api_route(f"{base}/timeline", timeline, methods=["GET"])
    app.add_api_route(f"{base}/alerts/recent", alerts_recent, methods=["GET"])
    app.add_api_route(f"{base}/watchlists", watchlists_list, methods=["GET"])
    app.add_api_route(f"{base}/watchlists", watchlists_create, methods=["POST"])
    app.add_api_route(f"{base}/watchlists/{{wid}}", watchlists_update, methods=["PUT"])
    app.add_api_route(f"{base}/watchlists/{{wid}}", watchlists_delete, methods=["DELETE"])

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
    try:
        st = _store()
        return {"uptime_seconds": round(time.time() - _START_TS, 1), "db": st.health()}
    except Exception as e:  # never break /healthz
        return {"uptime_seconds": round(time.time() - _START_TS, 1), "db": {"backend": "error", "error": repr(e)}}
