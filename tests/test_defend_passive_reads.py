# SPDX-License-Identifier: Apache-2.0
"""Defend read requests must not initialize, migrate, or journal local state."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import killinchu_defend_plane as defend

HEADERS = {"X-SZL-Session": "passive-test-session-012345678901234567890"}
OTHER_HEADERS = {"X-SZL-Session": "another-test-session-012345678901234567890"}
MISSING_RECEIPT = "rcpt_" + "0" * 32


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    path = tmp_path / "uninitialized" / "nested" / "defend.sqlite3"
    monkeypatch.setenv("KILLINCHU_DEFEND_STATE_PATH", str(path))
    monkeypatch.setenv("KILLINCHU_DEFEND_SIGNING_KEY", "synthetic-passive-test-key-not-production")
    app = FastAPI()
    defend.register(app)
    with TestClient(app) as client:
        yield client, path
    defend._STORES.pop(str(path), None)


def _event():
    return {
        "source_event_id": "passive-read-event",
        "event_type": "asset.public_exposure",
        "asset_ref": "asset/test",
        "actor_id": "actor/test",
        "severity": "HIGH",
        "summary": "Synthetic local regression fixture.",
        "requested_by": "operator/test",
        "indicators": {"source_authenticated": True, "asset_owner_known": True,
                       "rollback_available": True, "public_exposure": True, "evidence_count": 3},
    }


def _initialize(client):
    response = client.post("/api/defend/analyze", headers=HEADERS, json=_event())
    assert response.status_code == 200
    return response.json()["receipt"]["id"]


def _read(client, operation, receipt_id=MISSING_RECEIPT, headers=HEADERS):
    if operation == "cases":
        return client.get("/api/defend/cases?limit=25", headers=headers)
    if operation == "receipt":
        return client.get(f"/api/defend/receipts/{receipt_id}", headers=headers)
    return client.post("/api/defend/verify", headers=headers, json={"receipt_id": receipt_id})


def _filesystem(root, *, include_bytes=True):
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        stat = path.stat()
        result[str(path.relative_to(root))] = (
            path.is_dir(), stat.st_size, stat.st_mtime_ns,
            None if path.is_dir() or not include_bytes else hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return result


@pytest.mark.parametrize("operation", ("cases", "receipt", "verify"))
def test_missing_store_read_creates_no_directory_or_database(runtime, operation):
    client, path = runtime
    parent = path.parents[2]
    before = _filesystem(parent)
    response = _read(client, operation)
    assert response.status_code == 503
    assert response.json() == {"error": "LOCAL_STORE_UNAVAILABLE", "detail": "FileNotFoundError"}
    assert _filesystem(parent) == before
    assert not path.parent.exists()
    assert str(path) not in defend._STORES


@pytest.mark.parametrize("kind", ("directory", "fifo"))
def test_non_regular_database_never_reaches_sqlite_open(runtime, monkeypatch, kind):
    client, path = runtime
    if kind == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO creation is not supported on this platform")
    path.parent.mkdir(parents=True)
    if kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    before = _filesystem(path.parent, include_bytes=False)

    def forbidden_connect(*args, **kwargs):
        raise AssertionError("reader attempted SQLite open on a non-regular file")

    monkeypatch.setattr(defend.sqlite3, "connect", forbidden_connect)
    for operation in ("cases", "receipt", "verify"):
        response = _read(client, operation)
        assert response.status_code == 503
        assert response.json() == {"error": "LOCAL_STORE_UNAVAILABLE", "detail": "NON_REGULAR_DATABASE"}
        assert _filesystem(path.parent, include_bytes=False) == before
    assert str(path) not in defend._STORES


def test_existing_store_reads_preserve_files_schema_and_scope(runtime, monkeypatch):
    client, path = runtime
    receipt_id = _initialize(client)
    # Exercise a cold reader as well as one following a write in this process.
    defend._STORES.pop(str(path), None)
    before = _filesystem(path.parent)
    actual_connect = sqlite3.connect
    statements = []
    uris = []

    def read_only_connect(database, *args, **kwargs):
        assert kwargs.get("uri") is True
        assert str(database).endswith("?mode=ro&immutable=1")
        uris.append(str(database))
        connection = actual_connect(database, *args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(defend.sqlite3, "connect", read_only_connect)
    for operation in ("cases", "receipt", "verify"):
        response = _read(client, operation, receipt_id)
        assert response.status_code == 200, response.text
        if operation == "cases":
            assert response.json()["count"] == 1
        elif operation == "receipt":
            assert response.json()["receipt"]["id"] == receipt_id
        else:
            assert response.json()["integrity_verified"] is True
            assert response.json()["signature_verified"] is True
        other = _read(client, operation, receipt_id, OTHER_HEADERS)
        assert other.status_code == (200 if operation == "cases" else 404)
        if operation == "cases":
            assert other.json()["cases"] == []
        assert _filesystem(path.parent) == before
    assert len(uris) == 6
    assert statements and all(
        statement.lstrip().upper().startswith("SELECT ") or statement == "PRAGMA query_only = ON"
        for statement in statements
    )
    assert str(path) not in defend._STORES


@pytest.mark.parametrize("operation", ("cases", "receipt", "verify"))
def test_active_wal_writer_is_not_checkpointed_or_waited_for(runtime, monkeypatch, operation):
    client, path = runtime
    receipt_id = _initialize(client)
    writer = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        assert Path(f"{path}-wal").exists()
        # Windows locks the active SHM against byte reads. Compare metadata and
        # additionally prove no SQLite connection is attempted by the reader.
        before = _filesystem(path.parent, include_bytes=False)

        def forbidden_connect(*args, **kwargs):
            raise AssertionError("reader attempted to open an active WAL database")

        monkeypatch.setattr(defend.sqlite3, "connect", forbidden_connect)
        started = time.monotonic()
        response = _read(client, operation, receipt_id)
        assert time.monotonic() - started < 2
        assert response.status_code == 503
        assert response.json() == {"error": "LOCAL_STORE_UNAVAILABLE", "detail": "ACTIVE_SQLITE_SIDECAR"}
        assert _filesystem(path.parent, include_bytes=False) == before
        assert writer.in_transaction
    finally:
        writer.rollback()
        writer.close()


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_existing_sidecars_are_not_recovered_or_removed(runtime, suffix):
    client, path = runtime
    receipt_id = _initialize(client)
    Path(f"{path}{suffix}").write_bytes(b"synthetic sidecar; do not recover")
    before = _filesystem(path.parent)
    for operation in ("cases", "receipt", "verify"):
        response = _read(client, operation, receipt_id)
        assert response.status_code == 503
        assert response.json()["detail"] == "ACTIVE_SQLITE_SIDECAR"
        assert _filesystem(path.parent) == before


@pytest.mark.parametrize("malformation", ("missing-schema", "corrupt"))
def test_existing_invalid_database_is_not_repaired_or_migrated(runtime, malformation):
    client, path = runtime
    path.parent.mkdir(parents=True)
    if malformation == "missing-schema":
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.close()
    else:
        path.write_bytes(b"synthetic non-SQLite content")
    before = _filesystem(path.parent)
    for operation in ("cases", "receipt", "verify"):
        response = _read(client, operation)
        assert response.status_code == 503
        assert response.json()["detail"] in {"OperationalError", "DatabaseError"}
        assert _filesystem(path.parent) == before
    assert str(path) not in defend._STORES


@pytest.mark.parametrize("operation", ("cases", "receipt", "verify"))
@pytest.mark.parametrize("lookup_missing", (False, True))
def test_snapshot_replacement_is_rejected_before_returning_data_or_not_found(
    runtime, monkeypatch, operation, lookup_missing,
):
    client, path = runtime
    receipt_id = _initialize(client)
    original = path.stat()
    replacement = path.with_suffix(".replacement")
    replacement.write_bytes(path.read_bytes())
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    actual_connect = sqlite3.connect

    class ReplaceOnClose(sqlite3.Connection):
        def close(self):
            super().close()
            os.replace(replacement, path)

    def connect_and_replace(*args, **kwargs):
        return actual_connect(*args, **kwargs, factory=ReplaceOnClose)

    monkeypatch.setattr(defend.sqlite3, "connect", connect_and_replace)
    response = _read(client, operation, MISSING_RECEIPT if lookup_missing else receipt_id)
    assert response.status_code == 503
    assert response.json() == {"error": "LOCAL_STORE_UNAVAILABLE", "detail": "SNAPSHOT_CHANGED"}


def test_only_valid_demo_write_requests_initialize_local_store(runtime):
    client, path = runtime
    missing_scope = client.post("/api/defend/analyze", json=_event())
    assert missing_scope.status_code == 422
    invalid_event = client.post("/api/defend/analyze", headers=HEADERS, json={"command": "rejected"})
    assert invalid_event.status_code == 422
    assert not path.parent.exists()
    receipt_id = _initialize(client)
    assert path.is_file()
    assert _read(client, "receipt", receipt_id).status_code == 200
    ready = client.get("/api/defend/readyz")
    assert ready.status_code == 503
    assert ready.json()["production_ready"] is False
    assert ready.json()["production_gate"] == "DURABLE_STATE_AND_IDENTITY_UNVERIFIED"
    assert ready.json()["external_effectors_enabled"] is False


def test_passive_store_cannot_be_used_as_a_writer(runtime):
    _, path = runtime
    reader = defend._read_store()
    with pytest.raises(RuntimeError, match="^READ_ONLY_STORE$"):
        reader.connect()
    assert not path.parent.exists()
