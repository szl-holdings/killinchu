"""Atomic idempotency for the Defend durable-state seam (demo/SQLite path).

Synthetic data only. Covers: a different body under a live key is a conflict
(never a silent overwrite), and idempotent_claim lets exactly one of N
concurrent callers run the side effect.
"""

import tempfile
import threading
from pathlib import Path

import pytest

from app.defend.durable_state import DurableState


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
