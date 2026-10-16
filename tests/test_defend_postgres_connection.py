"""Source-contract tests; no provider or live production qualification."""

from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from app.defend.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnectionError,
    PostgresConnectionFactory,
    validated_url,
)


PRODUCTION_URL = (
    "postgresql://defend:CREDENTIAL_CANARY@database.example/defend"
    "?sslmode=verify-full&sslrootcert=system"
)
LOCAL_URL = "postgresql://test:test@127.0.0.1:5432/defend?sslmode=disable"


@pytest.mark.parametrize("query", ["", "sslmode=require", "sslmode=verify-ca",
                                    "sslmode=disable", "sslmode=verify-full"])
def test_production_requires_certificate_and_server_identity_verification(query):
    with pytest.raises(PostgresConfigurationError, match="TLS_IDENTITY_VERIFICATION_REQUIRED"):
        validated_url("postgresql://defend:canary@database.example/defend?" + query)


@pytest.mark.parametrize("option", [
    "host=127.0.0.1", "hostaddr=127.0.0.1", "service=unsafe", "options=-c%20ssl=off",
    "sslmode=disable", "sslrootcert=other",
])
def test_query_overrides_and_ambiguous_tls_options_are_rejected(option):
    with pytest.raises(PostgresConfigurationError):
        validated_url(PRODUCTION_URL + "&" + option)


@pytest.mark.parametrize("host", ["localhost", "database.example"])
def test_local_test_escape_hatch_only_accepts_literal_loopback(host):
    with pytest.raises(PostgresConfigurationError, match="LOCAL_TEST_REQUIRES_LOOPBACK"):
        validated_url(LOCAL_URL.replace("127.0.0.1", host), allow_local_test=True)


def test_multiple_hosts_cannot_multiply_the_connection_timeout():
    with pytest.raises(PostgresConfigurationError, match="SINGLE_DATABASE_HOST_REQUIRED"):
        validated_url(PRODUCTION_URL.replace("database.example", "one.example,two.example"))


@pytest.mark.parametrize("host", ["@defend_socket", r"C:\pgsocket", "/var/run/postgresql",
                                 "host name", "bad_host", "fe80::1%interface"])
def test_socket_path_and_non_hostname_targets_are_rejected(host):
    # Construct the URL object to avoid syntax parsing hiding the target test.
    from sqlalchemy.engine import URL
    url = URL.create("postgresql", username="test", password="canary", host=host,
                     database="defend", query={"sslmode": "verify-full", "sslrootcert": "system"})
    with pytest.raises(PostgresConfigurationError):
        validated_url(url.render_as_string(hide_password=False))


@pytest.mark.parametrize("name", ["PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE"])
@pytest.mark.parametrize("local_test", [False, True])
def test_inherited_libpq_target_overrides_fail_before_engine_creation(monkeypatch, name, local_test):
    monkeypatch.setenv(name, "TARGET_OVERRIDE_CANARY")
    with pytest.raises(PostgresConfigurationError, match="^DATABASE_ENVIRONMENT_OVERRIDE_UNSUPPORTED$"):
        PostgresConnectionFactory(LOCAL_URL if local_test else PRODUCTION_URL,
                                  allow_local_test=local_test)


def test_default_port_and_tls_transport_are_explicit(monkeypatch):
    from app.defend import postgres_connection
    captured = {}
    original_create_engine = postgres_connection.create_engine

    def capture_engine(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return original_create_engine(url, **kwargs)

    monkeypatch.setattr(postgres_connection, "create_engine", capture_engine)
    factory = PostgresConnectionFactory(PRODUCTION_URL)
    try:
        assert captured["url"].port == 5432
        assert captured["connect_args"]["gssencmode"] == "disable"
    finally:
        factory.close()


def test_late_environment_override_is_rejected_before_dbapi_connect(monkeypatch):
    factory = PostgresConnectionFactory(LOCAL_URL, allow_local_test=True)
    attempted = []

    def forbidden_connect(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("driver must not receive an overridden target")

    monkeypatch.setattr(factory.engine.dialect.loaded_dbapi, "connect", forbidden_connect)
    monkeypatch.setenv("PGHOSTADDR", "198.51.100.1")
    try:
        with pytest.raises(PostgresConnectionError, match="^DATABASE_CONNECTION_UNAVAILABLE$"):
            factory(LOCAL_URL)
        assert attempted == []
    finally:
        factory.close()


def test_local_url_is_not_accepted_by_default():
    with pytest.raises(PostgresConfigurationError, match="TLS_IDENTITY_VERIFICATION_REQUIRED"):
        validated_url(LOCAL_URL)
    assert validated_url(LOCAL_URL, allow_local_test=True).drivername == "postgresql+psycopg"


@pytest.mark.parametrize("url", [
    "CREDENTIAL_CANARY invalid", "postgresql://user:CREDENTIAL_CANARY@host:notaport/db",
    "sqlite:///CREDENTIAL_CANARY", "postgresql:///CREDENTIAL_CANARY",
])
def test_invalid_configuration_never_echoes_input(url):
    with pytest.raises(PostgresConfigurationError) as failure:
        validated_url(url)
    assert "CREDENTIAL_CANARY" not in str(failure.value)


def test_real_engine_has_bounded_pool_and_redacted_parameters():
    factory = PostgresConnectionFactory(PRODUCTION_URL)
    try:
        assert factory.engine.pool.size() == 5
        assert factory.engine.pool._max_overflow == 5
        assert factory.engine.pool.timeout() == 30
        assert factory.engine.pool._recycle == 1800
        assert factory.engine.pool._reset_on_return.name == "reset_rollback"
        assert factory.engine.hide_parameters is True
        assert factory.engine.echo is False
        assert factory.engine.pool.checkedout() == 0
    finally:
        factory.close()


def test_pool_connection_failure_is_typed_and_target_cannot_change(monkeypatch):
    factory = PostgresConnectionFactory(PRODUCTION_URL)

    def fail():
        raise RuntimeError("provider failure containing CREDENTIAL_CANARY")

    monkeypatch.setattr(factory.engine, "raw_connection", fail)
    try:
        with pytest.raises(PostgresConnectionError, match="^DATABASE_CONNECTION_UNAVAILABLE$"):
            factory(PRODUCTION_URL)
        with pytest.raises(PostgresConfigurationError, match="^DATABASE_TARGET_MISMATCH$"):
            factory("postgresql://other:CREDENTIAL_CANARY@other/db")
    finally:
        factory.close()


def test_postgresql_older_than_16_is_rejected_and_loan_returned(monkeypatch):
    factory = PostgresConnectionFactory(PRODUCTION_URL)
    returned = []
    loan = SimpleNamespace(
        driver_connection=SimpleNamespace(info=SimpleNamespace(server_version=150000)),
        close=lambda: returned.append(True),
    )
    monkeypatch.setattr(factory.engine, "raw_connection", lambda: loan)
    try:
        with pytest.raises(PostgresConnectionError, match="^POSTGRESQL_16_REQUIRED$"):
            factory(PRODUCTION_URL)
        assert returned == [True]
    finally:
        factory.close()
