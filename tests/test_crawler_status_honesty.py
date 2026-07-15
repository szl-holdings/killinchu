# SPDX-License-Identifier: Apache-2.0
"""Deterministic guards for the crawler's fail-closed storage circuit."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_backend as kb


NS = "killinchu"
_STATE_DEFAULTS = {
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


def _reset_state() -> None:
    kb._SCHED_STARTED = False
    kb._sched_state.clear()
    kb._sched_state.update(_STATE_DEFAULTS)
    if kb._sched_lock.acquire(blocking=False):
        kb._sched_lock.release()


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("KILLINCHU_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KILLINCHU_DB_DIR", str(tmp_path))
    monkeypatch.setenv("KILLINCHU_AUTO_CRAWL", "0")
    _reset_state()
    kb._STORE = None
    yield
    if kb._STORE is not None and kb._STORE._sqlite is not None:
        kb._STORE._sqlite.close()
    kb._STORE = None
    _reset_state()


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("database or disk is full"),
        sqlite3.OperationalError("attempt to write a readonly database"),
        OSError(28, "No space left on device"),
        "disk I/O error",
        "disk quota exceeded",
    ],
)
def test_storage_classifier_is_narrow_and_deterministic(error):
    assert kb._scheduler_failure_class(error) == "storage_unavailable"


@pytest.mark.parametrize(
    "error", ["HTTP 429", "upstream timeout", "invalid JSON", "provider quota exceeded"]
)
def test_retriable_upstream_failures_do_not_open_storage_circuit(error):
    assert kb._scheduler_failure_class(error) is None


def test_storage_failure_halts_loop_after_exactly_one_attempt(monkeypatch):
    calls = []

    def fail_once(mode="auto"):
        calls.append(mode)
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(kb, "run_crawl_guarded", fail_once)
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

    assert calls == ["auto"]
    assert kb._sched_state["running"] is False
    assert kb._sched_state["circuit_open"] is True
    assert kb._sched_state["failure_class"] == "storage_unavailable"
    assert kb._sched_state["last_status"] == "error"
    assert kb._sched_state["consecutive_failures"] == 1
    assert kb._sched_state["next_run_at"] is None
    assert kb._sched_state["paused_at"] is not None
    assert "restart" in kb._sched_state["operator_action"].lower()


def test_status_contract_reports_failed_never_ok_after_storage_failure():
    kb._SCHED_STARTED = True
    kb._sched_state["enabled"] = True
    kb._sched_state["consecutive_failures"] = 185
    kb._sched_state["last_run_at"] = "2026-07-15T13:10:00+00:00"
    kb._sched_state["last_success_at"] = "2026-07-15T12:40:00+00:00"
    kb._open_scheduler_circuit(
        sqlite3.OperationalError("database or disk is full"),
        paused_at="2026-07-15T13:10:00+00:00",
    )

    app = FastAPI()
    kb.register(app, ns=NS)
    with TestClient(app) as client:
        response = client.get(f"/api/{NS}/crawl/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["health"] == "failed"
    assert body["freshness"] == "stale"
    assert body["circuit_open"] is True
    assert body["failure_class"] == "storage_unavailable"
    assert body["paused_at"] == "2026-07-15T13:10:00+00:00"
    assert body["scheduler"]["next_run_at"] is None
    assert "Free writable storage" in body["operator_action"]


def test_open_circuit_blocks_manual_and_cache_miss_crawls(monkeypatch):
    calls = []
    kb._open_scheduler_circuit("database or disk is full")
    monkeypatch.setattr(kb, "run_crawl", lambda mode="crawl": calls.append(mode))

    app = FastAPI()
    kb.register(app, ns=NS)
    with TestClient(app) as client:
        manual = client.post(f"/api/{NS}/crawl/run")
        live = client.post(f"/api/{NS}/live")

    assert manual.status_code == 503
    assert live.status_code == 503
    assert manual.json()["status"] == "failed"
    assert live.json()["failure_class"] == "storage_unavailable"
    assert calls == []


def test_clean_process_state_allows_guarded_crawl(monkeypatch):
    kb._open_scheduler_circuit("database or disk is full")
    _reset_state()  # Equivalent module state after the documented service restart.
    calls = []

    def live(mode="auto"):
        calls.append(mode)
        return {"status": "live"}

    monkeypatch.setattr(kb, "run_crawl", live)
    assert kb.run_crawl_guarded("auto") == {"status": "live"}
    assert calls == ["auto"]


def test_elite_console_renders_halted_truth_without_static_live_claim():
    source = (
        Path(__file__).resolve().parents[1] / "killinchu_elite_console.py"
    ).read_text(encoding="utf-8")

    assert "Live intel feed \\u2014 auto-refresh" not in source
    assert "var halted=!!(j&&j.circuit_open)||health==='failed';" in source
    assert "outcome='HALTED'" in source
    assert "fail-closed \\u00b7 no retries" in source
    assert "(halted?'HALTED':freshness)" in source
    assert "j.operator_action" in source
    assert "cell('Next run',(enabled&&!halted)" in source
