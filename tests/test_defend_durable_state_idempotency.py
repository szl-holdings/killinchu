"""Atomic idempotency for the Defend durable-state seam (demo/SQLite path).

Synthetic data only. Covers: a different body under a live key is a conflict
(never a silent overwrite), and idempotent_claim lets exactly one of N
concurrent callers run the side effect.
"""

import tempfile
import threading
from pathlib import Path

import pytest

from app.defend.durable_state import DurableState, IdempotencyPending


def test_store_with_different_body_under_same_key_raises_and_keeps_original():
    ds = DurableState(demo_mode=True)
    ds.idempotent_store("k1", "hash-A", {"ok": "A"})
    with pytest.raises(ValueError):
        ds.idempotent_store("k1", "hash-B", {"ok": "B"})
    assert ds.idempotent_lookup("k1", "hash-A") == {"ok": "A"}


def test_store_same_body_twice_is_idempotent():
    ds = DurableState(demo_mode=True)
    ds.idempotent_store("k3", "h", {"v": 1})
    ds.idempotent_store("k3", "h", {"v": 1})
    assert ds.idempotent_lookup("k3", "h") == {"v": 1}


def test_claim_allows_exactly_one_execution_under_contention():
    path = str(Path(tempfile.mkdtemp()) / "idem.db")
    DurableState(demo_mode=True, sqlite_path=path)  # create schema once
    executions: list[int] = []
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        s = DurableState(demo_mode=True, sqlite_path=path)
        barrier.wait()
        for _ in range(50):
            try:
                if s.idempotent_claim("k2", "h"):
                    executions.append(i)
                    s.idempotent_complete("k2", "h", {"i": i})
                return
            except Exception as exc:  # sqlite "database is locked" under contention -> retry
                if "locked" not in str(exc):
                    raise

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(executions) == 1


def test_claim_with_different_body_is_a_conflict():
    ds = DurableState(demo_mode=True)
    assert ds.idempotent_claim("k4", "hash-A") is True
    with pytest.raises(ValueError):
        ds.idempotent_claim("k4", "hash-B")


def test_complete_without_matching_claim_raises():
    ds = DurableState(demo_mode=True)
    with pytest.raises(ValueError):
        ds.idempotent_complete("nope", "h", {"x": 1})


def test_pending_claim_is_never_served_as_a_result():
    ds = DurableState(demo_mode=True)
    assert ds.idempotent_claim("k5", "h") is True
    with pytest.raises(IdempotencyPending):
        ds.idempotent_lookup("k5", "h")
    assert ds.idempotent_claim("k5", "h") is False  # loser of the claim does not run the effect
    ds.idempotent_complete("k5", "h", {"done": True})
    assert ds.idempotent_lookup("k5", "h") == {"done": True}


def test_complete_cannot_overwrite_a_finished_response():
    ds = DurableState(demo_mode=True)
    assert ds.idempotent_claim("k6", "h") is True
    ds.idempotent_complete("k6", "h", {"v": 1})
    with pytest.raises(ValueError):
        ds.idempotent_complete("k6", "h", {"v": 2})
    ds.idempotent_store("k7", "h", {"v": 1})
    with pytest.raises(ValueError):
        ds.idempotent_complete("k7", "h", {"v": 2})
    assert ds.idempotent_lookup("k6", "h") == {"v": 1}
    assert ds.idempotent_lookup("k7", "h") == {"v": 1}


def test_claim_that_loses_the_insert_race_to_a_different_body_is_a_conflict():
    # Simulate the race: the pre-insert lookup sees an empty key, then a peer's claim lands.
    ds = DurableState(demo_mode=True)
    real_lookup = ds.idempotent_lookup

    def racing_lookup(key, request_hash):
        result = real_lookup(key, request_hash)
        ds._conn.execute(
            "INSERT INTO idempotency_keys (key, request_hash, response, created_at, state) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, "hash-peer", "null", ds._now_iso(), "pending"))
        ds._conn.commit()
        return result

    ds.idempotent_lookup = racing_lookup
    with pytest.raises(ValueError):
        ds.idempotent_claim("k8", "hash-mine")


def test_legacy_database_without_state_column_is_migrated(tmp_path):
    import sqlite3
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE idempotency_keys (key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, "
                 "response TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO idempotency_keys VALUES ('old', 'h', '{\"a\": 1}', '2999-01-01T00:00:00Z')")
    conn.commit()
    conn.close()
    ds = DurableState(demo_mode=True, sqlite_path=path)
    assert ds.idempotent_lookup("old", "h") == {"a": 1}
