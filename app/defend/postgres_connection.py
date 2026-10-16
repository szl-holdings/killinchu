"""Bounded PostgreSQL connections for the unqualified Defend source seam.

Installing or constructing this adapter does not establish production readiness.
Production connections require certificate and hostname verification. The local
test escape hatch is explicit and restricted to literal loopback addresses.
"""

from __future__ import annotations

import ipaddress
import os
import re

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import QueuePool

POOL_CONFIG = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 30, "pool_recycle": 1800}
CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 30_000
LOCK_TIMEOUT_MS = 5_000
UNSAFE_TARGET_ENVIRONMENT = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE")


class PostgresConfigurationError(ValueError):
    """Configuration failure whose text never includes a connection URL."""


class PostgresConnectionError(RuntimeError):
    """Typed connection failure without provider diagnostics or credentials."""


def _reject_environment_overrides() -> None:
    if any(os.environ.get(name) for name in UNSAFE_TARGET_ENVIRONMENT):
        raise PostgresConfigurationError("DATABASE_ENVIRONMENT_OVERRIDE_UNSUPPORTED")


def validated_url(database_url: str, *, allow_local_test: bool = False) -> URL:
    """Validate transport before a driver can interpret URL or query options."""
    _reject_environment_overrides()
    try:
        url = make_url(database_url)
    except Exception:
        raise PostgresConfigurationError("DATABASE_URL_INVALID") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise PostgresConfigurationError("POSTGRESQL_REQUIRED")
    if not url.host or not url.database or not url.username:
        raise PostgresConfigurationError("DATABASE_TARGET_REQUIRED")
    try:
        ipaddress.ip_address(url.host)
        valid_host = "%" not in url.host
    except ValueError:
        hostname = url.host.removesuffix(".")
        valid_host = len(hostname) <= 253 and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in hostname.split(".")
        )
    if not valid_host:
        raise PostgresConfigurationError("SINGLE_DATABASE_HOST_REQUIRED")
    if url.port is not None and not 1 <= url.port <= 65535:
        raise PostgresConfigurationError("DATABASE_PORT_INVALID")
    # libpq host/service/options query parameters can replace the parsed target
    # or safety settings. Only these TLS settings belong in this seam's URL.
    if set(url.query) - {"sslmode", "sslrootcert"}:
        raise PostgresConfigurationError("DATABASE_URL_OPTIONS_UNSUPPORTED")
    if any(not isinstance(value, str) for value in url.query.values()):
        raise PostgresConfigurationError("DATABASE_URL_OPTIONS_AMBIGUOUS")
    if allow_local_test:
        if url.host not in {"127.0.0.1", "::1"}:
            raise PostgresConfigurationError("LOCAL_TEST_REQUIRES_LOOPBACK")
        if url.query.get("sslmode") != "disable" or "sslrootcert" in url.query:
            raise PostgresConfigurationError("LOCAL_TEST_TLS_MODE_INVALID")
    elif (url.query.get("sslmode") != "verify-full"
          or not url.query.get("sslrootcert")):
        raise PostgresConfigurationError("TLS_IDENTITY_VERIFICATION_REQUIRED")
    return url.set(drivername="postgresql+psycopg", port=url.port or 5432)


class PostgresConnectionFactory:
    """One fixed target and one bounded pool; close() returns a rolled-back loan.

    This is callable as ``connect(database_url)`` for ProductionStore injection.
    Acquiring connections does not retry a transaction or an unknown commit.
    """

    def __init__(self, database_url: str, *, allow_local_test: bool = False):
        url = validated_url(database_url, allow_local_test=allow_local_test)
        self._database_url = database_url
        try:
            self.engine = create_engine(
                url,
                poolclass=QueuePool,
                **POOL_CONFIG,
                pool_reset_on_return="rollback",
                pool_pre_ping=True,
                echo=False,
                echo_pool=False,
                hide_parameters=True,
                connect_args={
                    "connect_timeout": CONNECT_TIMEOUT_SECONDS,
                    # libpq otherwise prefers GSS encryption when available,
                    # even when sslmode requires certificate verification.
                    "gssencmode": "disable",
                    "options": (f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                                f"-c lock_timeout={LOCK_TIMEOUT_MS}"),
                },
            )
            # Lazy connections can be created after the process environment has
            # changed, including through Alembic's direct engine connection.
            event.listen(self.engine, "do_connect", self._before_driver_connect)
        except Exception:
            raise PostgresConfigurationError("POSTGRES_ADAPTER_UNAVAILABLE") from None

    @staticmethod
    def _before_driver_connect(dialect, connection_record, connection_args, connection_parameters):
        _reject_environment_overrides()

    def __call__(self, database_url: str):
        if database_url != self._database_url:
            raise PostgresConfigurationError("DATABASE_TARGET_MISMATCH")
        connection = None
        try:
            connection = self.engine.raw_connection()
            if connection.driver_connection.info.server_version < 160000:
                connection.close()
                raise PostgresConnectionError("POSTGRESQL_16_REQUIRED")
            return connection
        except PostgresConnectionError:
            raise
        except Exception:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise PostgresConnectionError("DATABASE_CONNECTION_UNAVAILABLE") from None

    def close(self) -> None:
        """Dispose idle pool connections when the owning process shuts down."""
        self.engine.dispose()
