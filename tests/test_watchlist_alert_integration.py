# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_watchlist_alert_integration.py — REAL, committed proof that the watchlist
# ALERTING path actually fires end to end, and never double-pages.
#
# The existing tests/test_watchlist_ntfy_edge.py drives `_evaluate_watchlists`
# directly with hand-built facts. This test instead boots the WHOLE killinchu
# FastAPI app (TestClient context-manager, same pattern as
# tests/test_backend_scheduler.py) and exercises the full production path:
#
#   real-shaped ADS-B scrape  ->  run_crawl  ->  _derive_facts
#       ->  _evaluate_watchlists  ->  notification row (in-app alert)
#       ->  optional edge-triggered ntfy push
#
# all through the actual HTTP surface (POST /crawl/run, GET /alerts/recent,
# POST /watchlists). It proves:
#   * a first scrape that matches a watchlist trigger records exactly ONE alert
#     and attempts exactly ONE ntfy push,
#   * a repeated identical match (standing condition) does NOT page a second
#     time — the edge-dedup holds (the in-app history still records each crawl,
#     which is the intended "alert history" behaviour, but operators are not
#     spammed),
#   * a genuinely new match (the condition clears, then fires again) pages a
#     second time on the fresh clear->fire edge,
#   * with a cooldown configured, a still-firing condition re-pages only after
#     the quiet window elapses.
#
# NO MOCKS of the logic under test: the Store writes to a real temp SQLite DB and
# run_crawl / _derive_facts / _evaluate_watchlists / the edge-dedup state machine
# run exactly as in production. Only the upstream ADS-B fetch and the final raw
# ntfy POST are intercepted (so no network is touched and matches/pushes are
# deterministic).
from __future__ import annotations

import hashlib
import itertools

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_backend as kb

NS = "killinchu"
OPERATOR_TOKEN = "watchlist-integration-operator-token"
_CRAWL_KEYS = itertools.count(1)

# Env that influences the store, scheduler, and ntfy push; cleared so the host
# environment can never make these tests flaky.
NTFY_ENV = (
    "KILLINCHU_NTFY_URL",
    "NTFY_URL",
    "NTFY_TOPIC_URL",
    "KILLINCHU_NTFY_TOKEN",
    "NTFY_TOKEN",
    "KILLINCHU_NTFY_PRIORITY",
    "NTFY_PRIORITY",
    "KILLINCHU_NTFY_COOLDOWN",
    "KILLINCHU_NTFY_RECOVERY",
    "KILLINCHU_NTFY_RECOVERY_PRIORITY",
    "NTFY_RECOVERY_PRIORITY",
)
SCHED_ENV = (
    "KILLINCHU_AUTO_CRAWL",
    "KILLINCHU_CRAWL_INTERVAL_SECONDS",
    "KILLINCHU_CRAWL_JITTER_SECONDS",
    "KILLINCHU_CRAWL_INITIAL_DELAY_SECONDS",
    "KILLINCHU_CRAWL_MAX_BACKOFF_SECONDS",
)

# A real-shaped adsb.lol military payload carrying an F-16 — what `_fetch_mil_adsb`
# would return — so `_derive_facts` emits a `type:F-16` fact the watchlist matches.
MATCH_PAYLOAD = {"ac": [{"t": "F-16", "flag": "US"}, {"t": "C130", "flag": "US"}]}
# A payload with no F-16: the trigger's field is still evaluatable as 0, so the
# condition CLEARS (a genuine fire->clear edge).
CLEAR_PAYLOAD = {"ac": [{"t": "C130", "flag": "US"}]}


def _reset_scheduler_state() -> None:
    kb._SCHED_STARTED = False
    kb._sched_state.update({
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
    })
    if kb._sched_lock.acquire(blocking=False):
        kb._sched_lock.release()


@pytest.fixture()
def backend_env(tmp_path, monkeypatch):
    """A fresh durable-SQLite backend in a temp dir (no Postgres, no network),
    with the scheduler + ntfy edge state reset. Auto-crawl is disabled so only
    the explicit POST /crawl/run calls drive the watchlist evaluation (the test
    controls exactly how many crawls happen)."""
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    monkeypatch.setenv(
        "A11OY_COMPUTE_TOKEN_SHA256",
        hashlib.sha256(OPERATOR_TOKEN.encode("utf-8")).hexdigest(),
    )
    # Synchronous pushes so a single crawl is fully resolved when /crawl/run
    # returns — no daemon thread races in the assertions.
    monkeypatch.setenv("KILLINCHU_NTFY_BLOCKING", "1")
    # No auto-crawl: the in-process scheduler must not race the manual crawls.
    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "0")
    for var in NTFY_ENV:
        monkeypatch.delenv(var, raising=False)
    for var in SCHED_ENV:
        if var != "KILLINCHU_AUTO_CRAWL":
            monkeypatch.delenv(var, raising=False)

    _reset_scheduler_state()
    with kb._NTFY_STATE_LOCK:
        kb._NTFY_STATE.clear()
    # Force a brand-new singleton store rooted in the temp dir.
    kb._STORE = None
    st = kb._store()
    assert st.backend == "sqlite", f"expected sqlite fallback, got {st.backend!r}"

    yield st

    _reset_scheduler_state()
    with kb._NTFY_STATE_LOCK:
        kb._NTFY_STATE.clear()
    kb._STORE = None


@pytest.fixture()
def pushes(monkeypatch):
    """Intercept the raw ntfy POST; record every send instead of hitting net."""
    sent = []

    def _fake_send_raw(url, body, headers, timeout=8.0):
        sent.append({"url": url, "body": body, "headers": headers})
        return 200

    monkeypatch.setattr(kb, "_ntfy_send_raw", _fake_send_raw)
    return sent


def _make_client() -> TestClient:
    app = FastAPI(title="kc-watchlist-test", version="0.0.0")
    kb.register(app, ns=NS)
    return TestClient(app)


def _seed_f16_watchlist(client: TestClient) -> int:
    """Create, via the real POST /watchlists route, a watchlist that fires when
    one or more F-16s are observed (field type:F-16, gte 1)."""
    r = client.post(
        f"/api/{NS}/watchlists",
        json={
            "name": "F-16 presence",
            "description": "page when an F-16 shows up in the mil feed",
            "enabled": True,
            "triggers": [{"field": "type:F-16", "op": "gte", "threshold": 1}],
        },
        headers={
            "Authorization": f"Bearer {OPERATOR_TOKEN}",
            "Idempotency-Key": "watchlist-integration-seed-0001",
        },
    )
    assert r.status_code == 201, r.text
    return int(r.json()["watchlist"]["id"])


def _alerts_count(client: TestClient) -> int:
    r = client.get(f"/api/{NS}/alerts/recent")
    assert r.status_code == 200, r.text
    return r.json()["count"]


def _crawl(client: TestClient) -> dict:
    r = client.post(
        f"/api/{NS}/crawl/run",
        headers={
            "Authorization": f"Bearer {OPERATOR_TOKEN}",
            "Idempotency-Key": f"watchlist-integration-crawl-{next(_CRAWL_KEYS):04d}",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_operator_mutation_routes_keep_openapi_security_contract(backend_env):
    """This file is a protected CI target, so route/auth drift fails CI."""
    app = FastAPI(title="kc-watchlist-openapi-contract", version="0.0.0")
    kb.register(app, ns=NS)
    schema = app.openapi()
    protected = {
        (f"/api/{NS}/crawl/run", "post"),
        (f"/api/{NS}/watchlists", "post"),
        (f"/api/{NS}/watchlists/{{wid}}", "put"),
        (f"/api/{NS}/watchlists/{{wid}}", "delete"),
    }
    assert schema["components"]["securitySchemes"]["OperatorBearer"]["type"] == "http"
    for path, method in protected:
        assert schema["paths"][path][method]["security"] == [{"OperatorBearer": []}]
    assert "security" not in schema["paths"][f"/api/{NS}/watchlists"]["get"]


# ---------------------------------------------------------------------------
# 1) A real-shaped scrape that matches a watchlist fires exactly one alert and
#    attempts exactly one ntfy push — proven through the full HTTP surface.
# ---------------------------------------------------------------------------
def test_match_fires_one_alert_and_one_push(backend_env, pushes, monkeypatch):
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    monkeypatch.setattr(kb, "_fetch_mil_adsb", lambda timeout=12.0: (MATCH_PAYLOAD, 200, None))
    assert kb._ntfy_config() is not None

    with _make_client() as client:
        _seed_f16_watchlist(client)
        assert _alerts_count(client) == 0  # nothing fired yet

        body = _crawl(client)
        assert body["status"] == "live", body
        # Exactly one watchlist alert recorded for this first match.
        assert body["alerts_created"] == 1
        assert _alerts_count(client) == 1
        # And exactly one ntfy push was attempted (captured, not sent).
        assert len(pushes) == 1, "first match must page exactly once"
        # The push really carried the matched trigger (no fabricated content).
        assert b"type:F-16" in pushes[0]["body"]


# ---------------------------------------------------------------------------
# 2) Anti-spam: a standing condition does NOT re-page; a genuine clear->re-fire
#    pages again.
# ---------------------------------------------------------------------------
def test_repeat_does_not_double_page_but_clear_refire_does(backend_env, pushes, monkeypatch):
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    # Keep the assertions focused on FIRE pushes: disable the separate
    # fire->clear "recovered" notice (covered by tests/test_watchlist_recovery.py).
    monkeypatch.setenv("KILLINCHU_NTFY_RECOVERY", "0")

    feed = {"payload": MATCH_PAYLOAD}
    monkeypatch.setattr(kb, "_fetch_mil_adsb", lambda timeout=12.0: (feed["payload"], 200, None))

    with _make_client() as client:
        _seed_f16_watchlist(client)

        # First match: clear -> fire edge -> exactly one page.
        _crawl(client)
        assert len(pushes) == 1
        assert _alerts_count(client) == 1

        # Repeated IDENTICAL match (standing condition): each crawl still records
        # an in-app alert (intended history), but the channel is NOT re-paged.
        for _ in range(3):
            _crawl(client)
        assert len(pushes) == 1, "standing condition must NOT re-page (edge-dedup)"
        assert _alerts_count(client) == 4, "in-app history records every firing crawl"

        # The condition CLEARS (no F-16 in the feed): no new fire page.
        feed["payload"] = CLEAR_PAYLOAD
        _crawl(client)
        assert len(pushes) == 1, "a cleared condition must not page a fire alert"
        assert _alerts_count(client) == 4, "a non-match writes no alert row"

        # A genuinely NEW match (fresh clear->fire edge) pages again.
        feed["payload"] = MATCH_PAYLOAD
        _crawl(client)
        assert len(pushes) == 2, "a fresh clear->fire edge must page again"
        assert _alerts_count(client) == 5


# ---------------------------------------------------------------------------
# 3) Cooldown window: a still-firing condition re-pages only after the quiet
#    window elapses — driven through the full crawl path with a controllable
#    clock (no real sleeping).
# ---------------------------------------------------------------------------
def test_cooldown_repages_only_after_window(backend_env, pushes, monkeypatch):
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    monkeypatch.setenv("KILLINCHU_NTFY_COOLDOWN", "100")
    monkeypatch.setenv("KILLINCHU_NTFY_RECOVERY", "0")
    monkeypatch.setattr(kb, "_fetch_mil_adsb", lambda timeout=12.0: (MATCH_PAYLOAD, 200, None))

    cfg = kb._ntfy_config()
    assert cfg is not None and cfg["cooldown"] == 100.0

    # Deterministic clock used by the edge-dedup state machine.
    clock = {"t": 1000.0}
    monkeypatch.setattr(kb.time, "time", lambda: clock["t"])

    with _make_client() as client:
        _seed_f16_watchlist(client)

        _crawl(client)                  # t=1000: first fire -> page
        assert len(pushes) == 1

        clock["t"] = 1050.0             # +50s: still firing, within cooldown
        _crawl(client)
        assert len(pushes) == 1, "must not re-page within the cooldown window"

        clock["t"] = 1100.0             # exactly 100s elapsed -> re-page
        _crawl(client)
        assert len(pushes) == 2, "must re-page once the cooldown window elapses"

        clock["t"] = 1150.0             # within the new window -> quiet again
        _crawl(client)
        assert len(pushes) == 2
