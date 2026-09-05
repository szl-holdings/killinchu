"""Tests for the Defend production store (killinchu #399 follow-up 1).

No live Postgres in CI: the connection factory is injected, and a recording
fake pins the contract — isolation levels, commit behavior, and every
fail-closed readyz path.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.defend.production_store import POOL_CONFIG, ProductionStore

NOW = datetime(2026, 9, 5, 19, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db["statements"].append(sql)
        if "alembic_version" in sql:
            self._result = [(self.db["alembic_head"],)]
        elif "MAX(created_at)" in sql:
            self._result = [(self.db["latest_backup"],)]

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        self.db["commits"] += 1

    def close(self):
        pass


def make_db(alembic_head="0001", latest_backup=NOW - timedelta(hours=2)):
    return {"statements": [], "commits": 0, "alembic_head": alembic_head,
            "latest_backup": latest_backup}


def make_store(db):
    return ProductionStore("postgres://x", connect=lambda url: FakeConn(db))


def test_pool_config_matches_spec_401():
    assert POOL_CONFIG == {"pool_size": 5, "max_overflow": 5,
                           "pool_timeout": 30, "pool_recycle": 1800}


def test_empty_database_url_rejected():
    with pytest.raises(ValueError):
        ProductionStore("")


def test_healthy_database_readyz_passes():
    ok, info = make_store(make_db()).readyz(now=NOW)
    assert ok and info["durable"] and info["backup_fresh"]


def test_alembic_drift_fails_closed():
    ok, info = make_store(make_db(alembic_head="0002")).readyz(now=NOW)
    assert not ok and any("drift" in r for r in info["reasons"])


def test_stale_or_missing_backup_fails_closed():
    ok, info = make_store(make_db(latest_backup=NOW - timedelta(hours=48))).readyz(now=NOW)
    assert not ok and any("36h" in r for r in info["reasons"])
    ok2, _ = make_store(make_db(latest_backup=None)).readyz(now=NOW)
    assert not ok2


def test_unreachable_database_fails_closed():
    def boom(url):
        raise ConnectionError("refused")
    ok, info = ProductionStore("postgres://x", connect=boom).readyz(now=NOW)
    assert not ok and "database error" in info["reasons"][0]


def test_approval_writes_are_serializable_and_reads_repeatable():
    class Req:
        request_id = "r1"; requester = "stephen"; scope = "net.segment"
        justification = "j"; policy_mode = "solo"; state = "approved"
        approvers = ["stephen"]; denier = None; created_at_epoch = 1.0

    db = make_db()
    store = make_store(db)
    store.persist_approval(Req())
    assert any("SERIALIZABLE" in s for s in db["statements"])
    assert db["commits"] == 1

    db2 = make_db()
    make_store(db2).load_approval("r1")
    assert any("REPEATABLE READ" in s for s in db2["statements"])
