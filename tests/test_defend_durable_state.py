"""Tests for the Defend durable-state seam (killinchu #399 §1 / spec #401).

Demo mode uses in-memory SQLite; production-mode paths are tested for
fail-closed behavior only. No fixture data ever ships in a runtime path.
"""

import hashlib

import pytest

from app.defend.durable_state import DurableState, POOL_CONFIG


def _req_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def test_pool_config_matches_spec_401():
    assert POOL_CONFIG == {"pool_size": 5, "max_overflow": 5,
                           "pool_timeout": 30, "pool_recycle": 1800}


def test_idempotent_replay_returns_stored_response():
    ds = DurableState(demo_mode=True)
    h = _req_hash(b'{"case":"x"}')
    ds.idempotent_store("k1", h, {"status": "created"})
    assert ds.idempotent_lookup("k1", h) == {"status": "created"}


def test_idempotency_key_reuse_with_different_body_is_rejected():
    ds = DurableState(demo_mode=True)
    ds.idempotent_store("k1", _req_hash(b'{"case":"x"}'), {"status": "created"})
    with pytest.raises(ValueError):
        ds.idempotent_lookup("k1", _req_hash(b'{"case":"y"}'))


def test_unknown_key_returns_none():
    assert DurableState(demo_mode=True).idempotent_lookup("nope", _req_hash(b"x")) is None


def test_demo_readyz_is_honest_about_non_durability():
    ok, info = DurableState(demo_mode=True).readyz()
    assert ok is True
    assert info["durable"] is False
    assert "demo" in info["note"]


def test_production_readyz_fails_closed_without_database_url():
    ok, info = DurableState(database_url=None, demo_mode=False).readyz()
    assert ok is False
    assert info["reason"] == "DATABASE_URL absent"


def test_backup_event_is_recorded_and_queryable():
    ds = DurableState(demo_mode=True)
    event_id = ds.record_backup_event("ab" * 32)
    row = ds._conn.execute("SELECT dump_sha256 FROM backup_events WHERE id = ?",
                           (event_id,)).fetchone()
    assert row is not None and row[0] == "ab" * 32
