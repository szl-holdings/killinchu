# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
"""
test_watchlist_recovery.py — real edge-triggered ntfy tests for watchlist
fire->clear "recovered" notices.

NO mocks of the storage layer: the watchlist store writes to a real temp SQLite
DB and _evaluate_watchlists runs the real evaluation. Only the network egress
(_ntfy_send_raw) is captured so the test never hits ntfy. Each scenario asserts
the EDGE semantics: a fire pages once (high priority), a fire->clear pages one
lower-priority "recovered" notice, and staying clear is silent.

Run:  KILLINCHU_NTFY_BLOCKING=1 pytest -q test_watchlist_recovery.py
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


@pytest.fixture()
def kb(tmp_path, monkeypatch):
    """Import killinchu_backend with a clean sqlite store + captured ntfy egress."""
    # Force the durable-sqlite fallback into a temp dir (no Postgres in tests).
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    # Configure a push channel + synchronous send so assertions are deterministic.
    monkeypatch.setenv("KILLINCHU_NTFY_URL", "https://ntfy.example/test-topic")
    monkeypatch.setenv("KILLINCHU_NTFY_BLOCKING", "1")
    monkeypatch.delenv("KILLINCHU_NTFY_RECOVERY", raising=False)
    monkeypatch.delenv("KILLINCHU_NTFY_RECOVERY_PRIORITY", raising=False)

    mod = importlib.import_module("killinchu_backend")
    importlib.reload(mod)

    # Capture every push instead of hitting the network.
    sent = []

    def _capture(url, body, headers, timeout=8.0):
        sent.append({"url": url, "body": body.decode("utf-8"), "headers": dict(headers)})
        return 200

    monkeypatch.setattr(mod, "_ntfy_send_raw", _capture)
    mod._NTFY_STATE.clear()
    mod._sent = sent  # type: ignore[attr-defined]
    return mod


def _store_with_trigger(mod, field="count", op="gt", threshold="3"):
    st = mod._Store()
    assert st.ok(), "expected a durable sqlite store"
    wid = st.insert_returning_id(
        "INSERT INTO watchlists(name, description, enabled, created_at, updated_at) VALUES(?,?,?,?,?)",
        ("mil-surge", "", 1, "2026-06-11T00:00:00Z", "2026-06-11T00:00:00Z"),
    )
    st.execute(
        "INSERT INTO triggers(watchlist_id, field, op, threshold, created_at) VALUES(?,?,?,?,?)",
        (wid, field, op, threshold, "2026-06-11T00:00:00Z"),
    )
    return st


def _eval(mod, st, count, ts="2026-06-11T00:00:00Z"):
    return mod._evaluate_watchlists(st, 1, 1, count, [], ts)


def test_fire_then_recover_then_quiet(kb):
    mod = kb
    sent = mod._sent
    st = _store_with_trigger(mod, op="gt", threshold="3")

    # 1) Clears (count below threshold) before ever firing: NO push (no edge).
    _eval(mod, st, count=1)
    assert sent == []

    # 2) Fires (count above threshold): one HIGH-priority alert push.
    _eval(mod, st, count=9)
    assert len(sent) == 1
    assert sent[0]["headers"]["Priority"] == "high"
    assert "recovered" not in sent[0]["headers"]["Title"]

    # 3) Still firing: edge-triggered, NO re-page.
    _eval(mod, st, count=9)
    assert len(sent) == 1

    # 4) Fire->clear edge: one LOW-priority "recovered" push.
    _eval(mod, st, count=1)
    assert len(sent) == 2
    rec = sent[1]
    assert rec["headers"]["Priority"] == "low"
    assert "recovered" in rec["headers"]["Title"]
    assert rec["headers"]["Tags"] == "white_check_mark"
    assert "cleared" in rec["body"]

    # 5) Stays clear: silent (no spam while it remains clear).
    _eval(mod, st, count=0)
    assert len(sent) == 2


def test_recovery_toggle_disables_recovered_push(monkeypatch, kb):
    mod = kb
    sent = mod._sent
    monkeypatch.setenv("KILLINCHU_NTFY_RECOVERY", "0")
    st = _store_with_trigger(mod, op="gt", threshold="3")

    _eval(mod, st, count=9)           # fire
    assert len(sent) == 1
    _eval(mod, st, count=1)           # clear -> no recovery push (disabled)
    assert len(sent) == 1


def test_unevaluatable_after_fire_recovers(kb):
    mod = kb
    sent = mod._sent
    # Trigger references a field that won't be present once facts go empty.
    st = _store_with_trigger(mod, field="type:F-22", op="gte", threshold="1")

    # Fire: inject the matching fact.
    facts = [("type", "airframe:F-22", "2")]
    mod._evaluate_watchlists(st, 1, 1, 0, facts, "2026-06-11T00:00:00Z")
    assert len(sent) == 1
    assert sent[0]["headers"]["Priority"] == "high"

    # Next snapshot has no such fact -> un-evaluatable -> fire->clear recovery.
    mod._evaluate_watchlists(st, 2, 2, 0, [], "2026-06-11T00:05:00Z")
    assert len(sent) == 2
    assert sent[1]["headers"]["Priority"] == "low"
    assert "no longer evaluatable" in sent[1]["body"]


def test_no_channel_no_state_or_push(monkeypatch, kb):
    mod = kb
    sent = mod._sent
    # Remove the channel: _ntfy_config() returns None -> never pushes, never tracks.
    monkeypatch.delenv("KILLINCHU_NTFY_URL", raising=False)
    st = _store_with_trigger(mod, op="gt", threshold="3")
    _eval(mod, st, count=9)
    _eval(mod, st, count=1)
    assert sent == []
    assert mod._NTFY_STATE == {}
