"""Optional real PostgreSQL harness on a disposable local test database.

MEASURED outcomes apply to this harness only, never production qualification.
Set DEFEND_POSTGRES_TEST_URL to a PostgreSQL 16+ loopback test administrator URL
with sslmode=disable. Each test owns and removes one randomly named database.
An absent test target is reported as skipped; a configured broken target fails.
"""

import os
from pathlib import Path
import time
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")
pytest.importorskip("alembic")

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.defend.postgres_connection import PostgresConnectionError, PostgresConnectionFactory, validated_url


REPO = Path(__file__).resolve().parents[1]


def migration_config():
    config = Config(str(REPO / "app/defend/alembic.ini"))
    config.set_main_option("script_location", str(REPO / "app/defend/migrations"))
    return config


@pytest.fixture
def scratch_database(monkeypatch):
    admin_url = os.environ.get("DEFEND_POSTGRES_TEST_URL")
    if not admin_url:
        pytest.skip("DEFEND_POSTGRES_TEST_URL is not configured; live PostgreSQL NOT RUN")
    parsed = validated_url(admin_url, allow_local_test=True)
    admin = PostgresConnectionFactory(admin_url, allow_local_test=True)
    database_name = "defend_qualification_test_" + uuid4().hex
    # Generated solely above, never derived from an operator-selected target.
    assert database_name.startswith("defend_qualification_test_")
    scratch_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    scratch = None
    created = False
    try:
        with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            assert connection.dialect.server_version_info >= (16,), "PostgreSQL 16+ required"
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            created = True
        monkeypatch.setenv("DATABASE_URL", scratch_url)
        monkeypatch.setenv("DEFEND_POSTGRES_LOCAL_TEST", "1")
        command.upgrade(migration_config(), "head")
        scratch = PostgresConnectionFactory(scratch_url, allow_local_test=True)
        yield scratch_url, scratch
    finally:
        if scratch is not None:
            scratch.close()
        if created:
            with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        admin.close()


def test_migration_upgrade_is_repeatable_and_downgrade_round_trips(scratch_database):
    _, factory = scratch_database
    config = migration_config()
    command.upgrade(config, "head")
    with factory.engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
        assert connection.execute(text("SELECT count(*) FROM idempotency_keys")).scalar() == 0
        assert connection.execute(text("SELECT count(*) FROM backup_events")).scalar() == 0
    command.downgrade(config, "base")
    with factory.engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('backup_events')")).scalar() is None
        assert connection.execute(text("SELECT to_regclass('idempotency_keys')")).scalar() is None
    command.upgrade(config, "head")


def test_committed_probe_and_pool_return_rollback(scratch_database):
    url, factory = scratch_database
    connection = factory(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone()[0] == "30s"
            cursor.execute("SHOW lock_timeout")
            assert cursor.fetchone()[0] == "5s"
            cursor.execute("INSERT INTO idempotency_keys (key, request_hash, response) VALUES (%s, %s, %s)",
                           ("SIMULATED_ROLLBACK_PROBE", "SIMULATED", "SIMULATED"))
    finally:
        connection.close()  # Rolls back instead of leaking the pending write.
    connection = factory(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM idempotency_keys")
            assert cursor.fetchone()[0] == 0
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            cursor.execute("INSERT INTO idempotency_keys (key, request_hash, response) VALUES (%s, %s, %s)",
                           ("SIMULATED_COMMIT_PROBE", "SIMULATED", "SIMULATED"))
        connection.commit()
    finally:
        connection.close()
    connection = factory(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SELECT response FROM idempotency_keys WHERE key = %s", ("SIMULATED_COMMIT_PROBE",))
            assert cursor.fetchone() == ("SIMULATED",)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM idempotency_keys WHERE key = %s", ("SIMULATED_COMMIT_PROBE",))
        connection.commit()
    finally:
        connection.close()
    assert factory.engine.pool.checkedout() == 0


def test_pool_caps_at_ten_and_times_out(scratch_database):
    url, factory = scratch_database
    loans = []
    try:
        for _ in range(10):
            loans.append(factory(url))
        assert factory.engine.pool.checkedout() == 10
        started = time.monotonic()
        with pytest.raises(PostgresConnectionError, match="^DATABASE_CONNECTION_UNAVAILABLE$"):
            factory(url)
        assert 29 <= time.monotonic() - started < 40
        assert factory.engine.pool.checkedout() == 10
    finally:
        for loan in loans:
            loan.close()
    assert factory.engine.pool.checkedout() == 0
