# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_watchlist_ntfy_edge.py — REAL, committed guard for the watchlist alert
# anti-spam contract (Task #599 behaviour).
#
# A standing watchlist condition that keeps firing on every crawl must page the
# shared ntfy channel ONCE on the clear->fire edge — never on every snapshot —
# or it would flood the team's alert channel. This drives the real
# `_evaluate_watchlists` against a temp SQLite DB with KILLINCHU_NTFY_BLOCKING=1
# and a monkeypatched `_ntfy_send_raw` (so no network is touched), asserting:
#   * no channel configured  -> no push, no error (alert row still written)
#   * first fire             -> pages once
#   * standing condition     -> does NOT re-page
#   * clear then re-fire      -> pages again
#   * cooldown               -> re-pages only after the quiet window elapses
#
# NO MOCKS of the logic under test: the Store writes to a real SQLite file and
# the edge/de-dupe state machine runs exactly as it does in production. Only the
# final raw HTTP POST is intercepted.
from __future__ import annotations

import os

import pytest

import killinchu_backend as kb

NTFY_ENV = (
    "KILLINCHU_NTFY_URL",
    "NTFY_URL",
    "NTFY_TOPIC_URL",
    "KILLINCHU_NTFY_TOKEN",
    "NTFY_TOKEN",
    "KILLINCHU_NTFY_PRIORITY",
    "NTFY_PRIORITY",
    "KILLINCHU_NTFY_COOLDOWN",
)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A fresh durable-SQLite Store in a temp dir (no Postgres, no network)."""
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    # Synchronous pushes so a single _evaluate_watchlists call is fully resolved
    # by the time it returns — no daemon thread races in the assertions.
    monkeypatch.setenv("KILLINCHU_NTFY_BLOCKING", "1")
    for var in NTFY_ENV:
        monkeypatch.delenv(var, raising=False)
    # Isolate the in-memory edge-trigger state from any other test / import.
    with kb._NTFY_STATE_LOCK:
        kb._NTFY_STATE.clear()
    st = kb._Store()
    assert st.backend == "sqlite", f"expected sqlite fallback, got {st.backend!r}"
    return st


@pytest.fixture()
def pushes(monkeypatch):
    """Intercept the raw ntfy POST; record every send instead of hitting net."""
    sent = []

    def _fake_send_raw(url, body, headers, timeout=8.0):
        sent.append({"url": url, "body": body, "headers": headers})
        return 200

    monkeypatch.setattr(kb, "_ntfy_send_raw", _fake_send_raw)
    return sent


def _seed(st, field="count", op="gt", threshold="3"):
    now = kb._now_iso()
    wid = st.insert_returning_id(
        "INSERT INTO watchlists(name, description, enabled, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        ("edge-test", "anti-spam guard", 1, now, now),
    )
    tid = st.insert_returning_id(
        "INSERT INTO triggers(watchlist_id, field, op, threshold, created_at) "
        "VALUES(?,?,?,?,?)",
        (wid, field, op, threshold, now),
    )
    return int(wid), int(tid)


def _evaluate(st, count):
    """Run one crawl's worth of watchlist evaluation for a given mil count."""
    return kb._evaluate_watchlists(
        st, snap_id=1, event_id=1, count=count, facts=[], ts=kb._now_iso()
    )


def _notif_count(st):
    return st.query("SELECT COUNT(*) AS c FROM notifications")[0]["c"]


# ---------------------------------------------------------------------------


def test_no_channel_means_no_push_and_no_error(store, pushes):
    """With NO ntfy channel configured, a firing trigger still writes the in-app
    alert row but must never attempt a push (and must never raise)."""
    assert kb._ntfy_config() is None  # confirm no channel
    _seed(store)

    created = _evaluate(store, count=10)  # 10 > 3 -> fires

    assert len(created) == 1, "firing trigger must write exactly one alert row"
    assert _notif_count(store) == 1
    assert pushes == [], "no push channel => no ntfy send"


def test_standing_condition_pages_once_then_goes_quiet(store, pushes, monkeypatch):
    """The core anti-spam contract: a condition that keeps firing pages ONCE on
    the clear->fire edge, then stays quiet while it remains firing."""
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    assert kb._ntfy_config() is not None
    _seed(store)

    # First fire: clear -> fire edge -> exactly one page.
    _evaluate(store, count=10)
    assert len(pushes) == 1, "first fire must page once"

    # Standing condition: same trigger fires on the next several crawls. Each
    # writes its in-app alert row, but NONE may re-page the channel.
    for _ in range(5):
        _evaluate(store, count=10)
    assert len(pushes) == 1, "standing condition must NOT re-page (anti-spam)"

    # Sanity: the in-app alert rows were still recorded every crawl (6 fires).
    assert _notif_count(store) == 6


def test_clear_then_refire_pages_again(store, pushes, monkeypatch):
    """A genuine new incident — fire, clear, fire again — pages on each fresh
    clear->fire edge."""
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    _seed(store)

    _evaluate(store, count=10)          # fire -> page
    assert len(pushes) == 1

    _evaluate(store, count=0)           # clear (0 < 3) -> no page
    assert len(pushes) == 1

    _evaluate(store, count=10)          # fresh edge -> page again
    assert len(pushes) == 2


def test_unevaluatable_snapshot_clears_the_edge(store, pushes, monkeypatch):
    """A snapshot where the field can't be evaluated must reset the edge so the
    next real fire pages as a fresh clear->fire edge (no missed alert), while
    itself producing no push and no alert row."""
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    # Trigger on a per-type field that is absent unless facts carry it.
    _seed(store, field="type:F-16", op="gte", threshold="1")

    # No facts => field absent => un-evaluatable => no push, no alert row.
    kb._evaluate_watchlists(store, 1, 1, count=10, facts=[], ts=kb._now_iso())
    assert pushes == []
    assert _notif_count(store) == 0

    # Now the type appears -> first real fire pages once.
    facts = [("type", "airframe:F-16", "2")]
    kb._evaluate_watchlists(store, 1, 1, count=10, facts=facts, ts=kb._now_iso())
    assert len(pushes) == 1
    assert _notif_count(store) == 1


def test_cooldown_repages_only_after_window(store, pushes, monkeypatch):
    """With a cooldown configured, a still-firing condition re-pages only after
    the quiet window has elapsed — and not one crawl sooner."""
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/killinchu-test")
    monkeypatch.setenv("KILLINCHU_NTFY_COOLDOWN", "100")
    cfg = kb._ntfy_config()
    assert cfg is not None and cfg["cooldown"] == 100.0
    _seed(store)

    # Controllable clock so the test is deterministic (no real sleeping).
    clock = {"t": 1000.0}
    monkeypatch.setattr(kb.time, "time", lambda: clock["t"])

    _evaluate(store, count=10)          # t=1000: first fire -> page
    assert len(pushes) == 1

    clock["t"] = 1050.0                  # +50s: within cooldown -> no re-page
    _evaluate(store, count=10)
    assert len(pushes) == 1

    clock["t"] = 1099.9                  # still < 100s since last push -> quiet
    _evaluate(store, count=10)
    assert len(pushes) == 1

    clock["t"] = 1100.0                  # exactly 100s elapsed -> re-page
    _evaluate(store, count=10)
    assert len(pushes) == 2

    clock["t"] = 1150.0                  # within the new window -> quiet again
    _evaluate(store, count=10)
    assert len(pushes) == 2
