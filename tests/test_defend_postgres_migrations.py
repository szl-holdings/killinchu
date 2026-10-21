"""Migration rendering tests are source evidence, not a database qualification."""

from io import StringIO
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")
pytest.importorskip("alembic")

from alembic import command
from alembic.config import Config

from app.defend.postgres_connection import PostgresConfigurationError


REPO = Path(__file__).resolve().parents[1]


def test_existing_migration_renders_offline_without_disclosing_target(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:CREDENTIAL_CANARY@database.example/defend"
                       "?sslmode=verify-full&sslrootcert=system")
    monkeypatch.delenv("DEFEND_POSTGRES_LOCAL_TEST", raising=False)
    output = StringIO()
    config = Config(str(REPO / "app/defend/alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(REPO / "app/defend/migrations"))
    command.upgrade(config, "head", sql=True)
    rendered = output.getvalue()
    assert "CREATE TABLE IF NOT EXISTS idempotency_keys" in rendered
    assert "CREATE TABLE IF NOT EXISTS backup_events" in rendered
    assert "CREATE TABLE approval_requests" in rendered
    assert "CREATE TABLE IF NOT EXISTS approval_requests" not in rendered
    assert "COMMIT" in rendered
    assert "CREDENTIAL_CANARY" not in rendered
    assert "database.example" not in rendered


def test_migration_defaults_reject_unverified_transport_before_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:CREDENTIAL_CANARY@127.0.0.1/defend?sslmode=disable")
    monkeypatch.delenv("DEFEND_POSTGRES_LOCAL_TEST", raising=False)
    config = Config(str(REPO / "app/defend/alembic.ini"))
    config.set_main_option("script_location", str(REPO / "app/defend/migrations"))
    with pytest.raises(PostgresConfigurationError, match="^TLS_IDENTITY_VERIFICATION_REQUIRED$") as failure:
        command.upgrade(config, "head")
    assert "CREDENTIAL_CANARY" not in str(failure.value)
