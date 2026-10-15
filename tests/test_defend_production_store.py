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


def test_preliminary_reads_cannot_qualify_production_durability():
    db = make_db()
    ok, info = make_store(db).readyz(now=NOW)
    assert not ok and info["durable"] is False
    assert info["state"] == "BLOCKED"
    assert info["preliminary_checks_passed"] is True
    assert info["reasons"] == ["PRODUCTION_QUALIFICATION_INCOMPLETE"]
    assert info["backup_fresh"] is True
    # The probe is passive, including when every preliminary read succeeds.
    assert all(sql.startswith("SELECT ") for sql in db["statements"])
    assert db["commits"] == 0


def test_alembic_drift_fails_closed():
    sentinel = "SCHEMA_VALUE_CANARY_FOR_TEST_ONLY"
    ok, info = make_store(make_db(alembic_head=sentinel)).readyz(now=NOW)
    assert not ok and info["reasons"] == ["ALEMBIC_HEAD_DRIFT"]
    assert sentinel not in str(info)


@pytest.mark.parametrize("age, expected_reason", [
    (timedelta(microseconds=-1), "BACKUP_TIMESTAMP_IN_FUTURE"),
    (timedelta(0), "PRODUCTION_QUALIFICATION_INCOMPLETE"),
    (timedelta(hours=36), "PRODUCTION_QUALIFICATION_INCOMPLETE"),
    (timedelta(hours=36, microseconds=1), "latest backup older than 36h"),
])
def test_backup_freshness_has_both_time_bounds(age, expected_reason):
    ok, info = make_store(make_db(latest_backup=NOW - age)).readyz(now=NOW)
    assert not ok and info["durable"] is False
    assert info["reasons"] == [expected_reason]


@pytest.mark.parametrize("latest_backup", [
    NOW.replace(tzinfo=None), "2030-01-01T00:00:00Z", 1,
])
def test_malformed_backup_timestamp_fails_closed(latest_backup):
    ok, info = make_store(make_db(latest_backup=latest_backup)).readyz(now=NOW)
    assert not ok and info == {"durable": False, "reasons": ["DATABASE_ERROR"]}


def test_stale_or_missing_backup_fails_closed():
    ok, info = make_store(make_db(latest_backup=NOW - timedelta(hours=48))).readyz(now=NOW)
    assert not ok and any("36h" in r for r in info["reasons"])
    ok2, _ = make_store(make_db(latest_backup=None)).readyz(now=NOW)
    assert not ok2


def test_unreachable_database_fails_closed():
    sentinel = "CREDENTIAL_CANARY_FOR_TEST_ONLY"

    def boom(url):
        raise ConnectionError(f"refused; {sentinel}")
    ok, info = ProductionStore("postgres://x", connect=boom).readyz(now=NOW)
    assert not ok and info == {"durable": False, "reasons": ["DATABASE_ERROR"]}
    assert sentinel not in str(info)


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
