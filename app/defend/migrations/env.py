"""Run immutable Defend migrations using the same bounded transport contract."""

from __future__ import annotations

import os

from alembic import context

from app.defend.postgres_connection import (
    PostgresConnectionFactory,
    PostgresConfigurationError,
    validated_url,
)


config = context.config


def run_migrations() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    local_test = os.environ.get("DEFEND_POSTGRES_LOCAL_TEST") == "1"
    if context.is_offline_mode():
        url = validated_url(database_url, allow_local_test=local_test)
        context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
        with context.begin_transaction():
            context.run_migrations()
        return

    factory = PostgresConnectionFactory(database_url, allow_local_test=local_test)
    try:
        with factory.engine.connect() as connection:
            if connection.dialect.server_version_info < (16,):
                raise PostgresConfigurationError("POSTGRESQL_16_REQUIRED")
            context.configure(connection=connection, target_metadata=None)
            with context.begin_transaction():
                context.run_migrations()
    except Exception:
        # Alembic's CLI would otherwise print raw DBAPI exceptions, potentially
        # including provider diagnostics. Keep the operator result typed.
        raise RuntimeError("DEFEND_MIGRATION_FAILED") from None
    finally:
        factory.close()


run_migrations()
