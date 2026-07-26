# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_backend_scheduler.py — REAL, committed guard that the intel feed's
# auto-refresh loop actually fires (Task #744 behaviour).
#
# The scheduler helpers were previously only validated by py_compile + unit
# tests of the pieces. This boots the FastAPI app with a tiny interval +
# initial delay, lets the in-process asyncio loop run, and proves end to end:
#   * the periodic loop triggers a real crawl (observed via /crawl/status)
#   * a forced scrape failure records exactly ONE honest 'degraded' event and
#     fabricates NO snapshot/facts
#   * the overlap guard never double-starts a still-running crawl
#
# NO MOCKS of the logic under test: the Store writes to a real temp SQLite DB
# and run_crawl / run_crawl_guarded / the scheduler loop run exactly as in
# production. Only the upstream ADS-B fetch is intercepted (so no network is
# touched and failure can be forced deterministically).
from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_backend as kb

NS = "killinchu"
OPERATOR_TOKEN = "backend-scheduler-operator-token"
OPERATOR_HEADERS = {
    "Authorization": f"Bearer {OPERATOR_TOKEN}",
    "Idempotency-Key": "backend-scheduler-crawl-0001",
}

# Env that influences the scheduler / store; cleared so the host environment
# can never make these tests flaky.
SCHED_ENV = (
    "KILLINCHU_AUTO_CRAWL",
    "KILLINCHU_CRAWL_INTERVAL_SECONDS",
    "KILLINCHU_CRAWL_JITTER_SECONDS",
    "KILLINCHU_CRAWL_INITIAL_DELAY_SECONDS",
    "KILLINCHU_CRAWL_MAX_BACKOFF_SECONDS",
)


def _reset_scheduler_state() -> None:
    """Return the module-level scheduler singletons to a pristine state so each
    test starts from zero runs and an un-wired scheduler."""
    kb._SCHED_STARTED = False
    kb._sched_state.update({
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
    })
    # The overlap lock is non-reentrant; make sure no prior test left it held.
    if kb._sched_lock.acquire(blocking=False):
        kb._sched_lock.release()


@pytest.fixture()
def backend_env(tmp_path, monkeypatch):
    """A fresh durable-SQLite backend in a temp dir (no Postgres, no network),
    with the scheduler globals reset and a controllable upstream feed."""
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    monkeypatch.setenv(
        "A11OY_COMPUTE_TOKEN_SHA256",
        hashlib.sha256(OPERATOR_TOKEN.encode("utf-8")).hexdigest(),
    )
    for var in SCHED_ENV:
        monkeypatch.delenv(var, raising=False)

    _reset_scheduler_state()
    # Force a brand-new singleton store rooted in the temp dir.
    kb._STORE = None
    st = kb._store()
    assert st.backend == "sqlite", f"expected sqlite fallback, got {st.backend!r}"

    yield st

    _reset_scheduler_state()
    kb._STORE = None


def _counts(st):
    return {
        "snapshots": st.query("SELECT COUNT(*) AS c FROM snapshots")[0]["c"],
        "facts": st.query("SELECT COUNT(*) AS c FROM facts")[0]["c"],
        "events": st.query("SELECT COUNT(*) AS c FROM events")[0]["c"],
    }


# ---------------------------------------------------------------------------
# 1) The periodic loop actually fires a crawl.
# ---------------------------------------------------------------------------
def test_scheduler_loop_actually_fires_a_crawl(backend_env, monkeypatch):
    """With a tiny interval + zero initial delay, booting the app must drive the
    in-process loop to run at least one real crawl, observable via /crawl/status
    and reflected by a persisted snapshot."""
    st = backend_env

    # A small, real-shaped ADS-B payload so run_crawl writes a 'live' snapshot
    # without any network call.
    payload = {"ac": [{"t": "F16", "flag": "US"}, {"t": "C130", "flag": "US"}]}
    monkeypatch.setattr(kb, "_fetch_mil_adsb", lambda timeout=12.0: (payload, 200, None))

    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "1")
    monkeypatch.setenv("KILLINCHU_CRAWL_INITIAL_DELAY_SECONDS", "0")
    monkeypatch.setenv("KILLINCHU_CRAWL_INTERVAL_SECONDS", "30")  # floor; first run is immediate
    monkeypatch.setenv("KILLINCHU_CRAWL_JITTER_SECONDS", "0")

    app = FastAPI(title="kc-sched-test", version="0.0.0")
    kb.register(app, ns=NS)
    wired = kb.start_scheduler(app)
    assert "wired" in wired

    # Entering the context fires the startup event -> creates the loop task.
    with TestClient(app) as c:
        deadline = time.time() + 15
        runs = 0
        body = {}
        while time.time() < deadline:
            body = c.get(f"/api/{NS}/crawl/status").json()
            runs = body["scheduler"]["runs"]
            if runs >= 1:
                break
            time.sleep(0.2)

        assert runs >= 1, f"scheduler never ran a crawl: {body}"
        assert body["scheduler"]["last_status"] == "live"
        assert body["scheduler"]["last_run_at"] is not None
        assert body["wired"] is True
        assert body["config"]["enabled"] is True
        assert body["config"]["interval_seconds"] == 30

    # The crawl really persisted a snapshot/facts/event (it actually ran).
    counts = _counts(st)
    assert counts["snapshots"] >= 1
    assert counts["facts"] >= 1
    assert counts["events"] >= 1


# ---------------------------------------------------------------------------
# 2) A forced scrape failure records exactly one honest DEGRADED event and
#    fabricates nothing.
# ---------------------------------------------------------------------------
def test_forced_scrape_failure_records_one_degraded_event_no_fabrication(backend_env, monkeypatch):
    st = backend_env

    # Force the upstream to be unreachable.
    monkeypatch.setattr(
        kb, "_fetch_mil_adsb",
        lambda timeout=12.0: (None, 0, "forced failure (upstream unreachable)"),
    )

    res = kb.run_crawl(mode="auto")

    # Honest envelope: degraded (no prior snapshot to serve), one event created.
    assert res["status"] == "degraded"
    assert res["events_created"] == 1

    # Exactly ONE event, and it is the honest 'degraded' record.
    events = st.query("SELECT kind, severity FROM events")
    assert len(events) == 1
    assert events[0]["kind"] == "degraded"
    assert events[0]["severity"] == "warn"

    # No fabricated snapshot or derived facts on a failed scrape.
    counts = _counts(st)
    assert counts["snapshots"] == 0, "a failed scrape must not fabricate a snapshot"
    assert counts["facts"] == 0, "a failed scrape must not fabricate facts"


def test_repeated_failures_record_one_degraded_event_each(backend_env, monkeypatch):
    """Each failed scrape records its own single degraded event (no pile-up, no
    fabrication), so the timeline honestly reflects every failed cycle."""
    st = backend_env
    monkeypatch.setattr(
        kb, "_fetch_mil_adsb",
        lambda timeout=12.0: (None, 0, "still unreachable"),
    )

    for _ in range(3):
        assert kb.run_crawl(mode="auto")["events_created"] == 1

    counts = _counts(st)
    assert counts["events"] == 3
    assert counts["snapshots"] == 0
    assert counts["facts"] == 0
    degraded = st.query("SELECT COUNT(*) AS c FROM events WHERE kind='degraded'")[0]["c"]
    assert degraded == 3


# ---------------------------------------------------------------------------
# 3) Overlap guard: a long-running crawl is never double-started.
# ---------------------------------------------------------------------------
def test_overlap_guard_does_not_double_start(backend_env, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def _slow_crawl(mode="crawl"):
        calls.append(mode)
        entered.set()
        # Hold the crawl "in flight" until the test lets it finish.
        assert release.wait(timeout=5), "slow crawl was never released"
        return {"status": "live"}

    monkeypatch.setattr(kb, "run_crawl", _slow_crawl)

    # Start one guarded crawl that blocks while holding the overlap lock.
    t = threading.Thread(target=lambda: kb.run_crawl_guarded("auto"), daemon=True)
    t.start()
    assert entered.wait(timeout=5), "first crawl never started"

    # A second concurrent attempt must be skipped (non-blocking lock held).
    assert kb.run_crawl_guarded("auto") is None, "overlap guard failed: crawl double-started"

    # Let the in-flight crawl finish; afterwards a fresh call runs normally.
    release.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert calls == ["auto"], "exactly one crawl should have actually run during overlap"

    # Lock is free again -> a subsequent crawl is allowed.
    release2 = threading.Event()
    release2.set()
    assert kb.run_crawl_guarded("auto") is not None
    assert calls == ["auto", "auto"]


# ---------------------------------------------------------------------------
# 4) The /live cache-miss scrape runs OFF the event loop (PERF: no stall).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_cache_miss_does_not_block_event_loop(backend_env, monkeypatch):
    """On a cache-miss, the /live handler runs the blocking ADS-B fetch via
    asyncio.to_thread, so the event loop stays free to service other coroutines
    while the (up to 12s) scrape is in flight. We hold the upstream fetch open
    on a worker thread and assert the loop can still make progress; if the
    handler ran the scrape inline it would await the awaitable below only AFTER
    the blocking call returned, and the loop would be stalled."""
    in_fetch = threading.Event()
    release = threading.Event()
    payload = {"ac": [{"t": "F16", "flag": "US"}]}

    def _blocking_fetch(timeout=12.0):
        in_fetch.set()
        # Simulate the slow upstream; runs on a worker thread iff off-loop.
        assert release.wait(timeout=5), "fetch was never released"
        return payload, 200, None

    monkeypatch.setattr(kb, "_fetch_mil_adsb", _blocking_fetch)

    app = FastAPI(title="kc-live-test", version="0.0.0")
    kb.register(app, ns=NS)

    # Grab the bound coroutine for the /live route and call it directly so we
    # exercise the real handler on THIS running event loop.
    live_route = next(r for r in app.router.routes
                      if getattr(r, "path", "") == f"/api/{NS}/live")

    class _Req:
        headers = {
            "authorization": f"Bearer {OPERATOR_TOKEN}",
            "idempotency-key": "backend-scheduler-live-0001",
        }

    live_task = asyncio.create_task(live_route.endpoint(_Req()))

    # The blocking fetch must start on a worker thread, and while it is held the
    # event loop must remain responsive (this sleep/await returns promptly).
    assert await asyncio.to_thread(in_fetch.wait, 5), "fetch never entered"
    loop_progressed = False
    for _ in range(5):
        await asyncio.sleep(0.01)  # would never resume if the loop were blocked
        loop_progressed = True
    assert loop_progressed, "event loop made no progress during the scrape"
    assert not live_task.done(), "handler returned before fetch was released"

    release.set()
    resp = await live_task
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5) Non-retriable storage failures halt fail-closed instead of spinning.
# ---------------------------------------------------------------------------
def test_storage_failure_opens_circuit_and_stops_scheduler(backend_env, monkeypatch):
    calls = []

    def _disk_full(mode="auto"):
        calls.append(mode)
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(kb, "run_crawl_guarded", _disk_full)
    monkeypatch.setattr(
        kb,
        "scheduler_config",
        lambda: {
            "enabled": True,
            "interval": 30,
            "jitter": 0,
            "initial": 0,
            "max_backoff": 180,
        },
    )

    asyncio.run(kb._scheduler_loop())

    assert calls == ["auto"], "a full disk must not trigger an unbounded retry loop"
    assert kb._sched_state["circuit_open"] is True
    assert kb._sched_state["failure_class"] == "storage_unavailable"
    assert kb._sched_state["next_run_at"] is None
    assert kb._sched_state["running"] is False


def test_open_circuit_is_failed_publicly_and_blocks_manual_crawl(backend_env, monkeypatch):
    calls = []
    kb._SCHED_STARTED = True
    kb._sched_state["last_success_at"] = "2026-07-15T12:40:00+00:00"
    kb._open_scheduler_circuit(
        sqlite3.OperationalError("database or disk is full"),
        paused_at="2026-07-15T13:10:00+00:00",
    )
    monkeypatch.setattr(kb, "run_crawl", lambda mode="crawl": calls.append(mode))

    app = FastAPI(title="kc-circuit-test", version="0.0.0")
    kb.register(app, ns=NS)
    with TestClient(app) as client:
        status = client.get(f"/api/{NS}/crawl/status")
        manual = client.post(f"/api/{NS}/crawl/run", headers=OPERATOR_HEADERS)

    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert body["health"] == "failed"
    assert body["freshness"] == "stale"
    assert body["failure_class"] == "storage_unavailable"
    assert body["scheduler"]["next_run_at"] is None
    assert manual.status_code == 503
    assert calls == []
