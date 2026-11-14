# SPDX-License-Identifier: Apache-2.0
"""Status observations reject unsafe SQLite snapshots without touching them."""
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

import killinchu_defend_plane as defend


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "defend.sqlite3"
    with sqlite3.connect(path) as connection:
        for table in ("events", "cases", "proposals", "approvals", "rehearsals", "receipts"):
            connection.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY)")
    return path


def _files(directory):
    return {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest())
        for path in directory.iterdir() if path.is_file()
    }


def test_active_rollback_writer_is_not_observed_as_readable(snapshot, monkeypatch):
    writer = sqlite3.connect(snapshot, isolation_level=None)
    try:
        assert writer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO events VALUES ('pending')")
        assert Path(f"{snapshot}-journal").exists()
        before = _files(snapshot.parent)
        actual_connect = defend.sqlite3.connect
        opened = []

        def audited_connect(*args, **kwargs):
            opened.append(args[0])
            return actual_connect(*args, **kwargs)

        monkeypatch.setattr(defend.sqlite3, "connect", audited_connect)
        result = defend.DefendStore.observe(str(snapshot))
        assert result["state"] == "FAILED_CLOSED"
        assert result["error"] == "ACTIVE_ROLLBACK_JOURNAL"
        assert opened == []
        assert _files(snapshot.parent) == before
        assert writer.in_transaction
    finally:
        writer.rollback()
        writer.close()


@pytest.mark.parametrize("kind", ("directory", "fifo"))
def test_non_regular_snapshot_is_rejected_before_sqlite(tmp_path, monkeypatch, kind):
    path = tmp_path / "defend.sqlite3"
    if kind == "directory":
        path.mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(path)
    else:
        pytest.skip("POSIX FIFO creation is unavailable")
    opened = []

    def forbidden_connect(*args, **kwargs):
        opened.append(args[0])
        raise AssertionError("SQLite must not open a non-regular snapshot")

    monkeypatch.setattr(defend.sqlite3, "connect", forbidden_connect)
    result = defend.DefendStore.observe(str(path))
    assert result["state"] == "FAILED_CLOSED"
    assert result["error"] == "NON_REGULAR_DATABASE"
    assert opened == []


@pytest.mark.parametrize("change", ("replace", "rollback_journal"))
def test_snapshot_changed_during_observation_is_not_readable(snapshot, monkeypatch, change):
    original_stat = snapshot.stat()
    replacement = snapshot.with_suffix(".replacement")
    if change == "replace":
        shutil.copyfile(snapshot, replacement)
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    actual_connect = defend.sqlite3.connect

    class ChangeOnClose:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, *args, **kwargs):
            return self.connection.execute(*args, **kwargs)

        def close(self):
            self.connection.close()
            if change == "replace":
                os.replace(replacement, snapshot)
                assert snapshot.stat().st_size == original_stat.st_size
                assert snapshot.stat().st_mtime_ns == original_stat.st_mtime_ns
            else:
                Path(f"{snapshot}-journal").write_bytes(b"external writer marker")

    monkeypatch.setattr(defend.sqlite3, "connect", lambda *a, **kw: ChangeOnClose(actual_connect(*a, **kw)))
    result = defend.DefendStore.observe(str(snapshot))
    assert result["state"] == "FAILED_CLOSED"
    assert result["error"] == "SNAPSHOT_CHANGED"


def test_clean_snapshot_stays_readable_and_unchanged(snapshot):
    before = _files(snapshot.parent)
    result = defend.DefendStore.observe(str(snapshot))
    assert result["state"] == "READABLE"
    assert result["integrity"] == "ok"
    assert result["counts"] == dict.fromkeys(("events", "cases", "proposals", "approvals", "rehearsals", "receipts"), 0)
    assert _files(snapshot.parent) == before
