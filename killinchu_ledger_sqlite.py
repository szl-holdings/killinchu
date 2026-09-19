"""Opt-in, single-host receipt storage; not a provider durability attestation.

Provision explicitly with ``python -m killinchu_ledger_sqlite init ABSOLUTE_PATH``.
Runtime opens only an existing database with a matching provisioned store ID.
No credentials, automatic initialization, schema repair, or in-memory fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
MAX_NODE_BYTES = 1_048_576
_SCHEMA = {
    "ledger_meta": "CREATE TABLE ledger_meta (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), schema_version INTEGER NOT NULL, store_id TEXT NOT NULL, node_count INTEGER NOT NULL CHECK (node_count >= 0), head TEXT)",
    "ledger_nodes": "CREATE TABLE ledger_nodes (node_index INTEGER PRIMARY KEY CHECK (node_index >= 0), digest TEXT NOT NULL UNIQUE, node_json TEXT NOT NULL)",
}


class SQLiteLedgerError(RuntimeError):
    """A configuration, continuity, storage, or integrity failure."""


def _path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.name or path.is_symlink():
        raise SQLiteLedgerError("ledger requires an absolute, non-symlink file path")
    if not path.parent.is_dir():
        raise SQLiteLedgerError("ledger parent directory must already exist")
    return path


def _json_value(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        # json.dumps below rejects NaN and infinities.
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise SQLiteLedgerError("receipt must contain only JSON values and string keys")


def _encode(node: Mapping[str, Any]) -> str:
    _json_value(node)
    value = json.dumps(node, sort_keys=True, allow_nan=False)
    if len(value.encode("utf-8")) > MAX_NODE_BYTES:
        raise SQLiteLedgerError("receipt exceeds the storage limit")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SQLiteLedgerError("stored JSON contains duplicate keys")
        result[key] = value
    return result


def _validate_node(node: Any, index: int, parent: str | None) -> None:
    if not isinstance(node, dict) or type(node.get("index")) is not int:
        raise SQLiteLedgerError("receipt index must be an integer")
    if node["index"] != index or node.get("parents") != ([] if parent is None else [parent]):
        raise SQLiteLedgerError("receipt does not extend the stored head")
    if type(node.get("parents")) is not list or type(node.get("receipt")) is not dict:
        raise SQLiteLedgerError("receipt shape is invalid")
    digest = hashlib.sha256(json.dumps(node["receipt"], sort_keys=True, allow_nan=False).encode())
    for previous in node["parents"]:
        digest.update(previous.encode())
    if node.get("digest") != digest.hexdigest():
        raise SQLiteLedgerError("receipt digest does not match its content")


def provision(path: str | Path) -> str:
    """Create a NEW store exclusively; never initialize or overwrite an old file.

    Returns a non-secret identity to pin in runtime configuration. If provisioning
    fails, preserve the file for inspection instead of silently recreating it.
    """
    target = _path(path)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    store_id = str(uuid.uuid4())
    connection = sqlite3.connect(target.as_uri() + "?mode=rw", uri=True, isolation_level=None)
    try:
        if connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            raise SQLiteLedgerError("rollback journaling is unavailable")
        connection.execute("PRAGMA synchronous=FULL")
        if connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise SQLiteLedgerError("full synchronization is unavailable")
        connection.execute("BEGIN IMMEDIATE")
        for statement in _SCHEMA.values():
            connection.execute(statement)
        connection.execute("INSERT INTO ledger_meta VALUES (1, ?, ?, 0, NULL)", (SCHEMA_VERSION, store_id))
        connection.commit()
    finally:
        connection.close()
    return store_id


class SQLiteLedgerAdapter:
    """Existing LedgerRuntime contract backed by SQLite on a local filesystem.

    This is hash-chain integrity, not DSSE signature validation or protection
    against a privileged writer replacing/rolling back the entire database.
    """

    def __init__(self, path: str | Path, store_id: str, *, timeout_s: float = 5.0):
        self._path = _path(path)
        try:
            if str(uuid.UUID(store_id)) != store_id:
                raise ValueError("noncanonical store identity")
        except (ValueError, TypeError, AttributeError) as exc:
            raise SQLiteLedgerError("a provisioned store identity is required") from exc
        self._store_id = store_id
        self._timeout_s = timeout_s

    @contextmanager
    def _transaction(self, *, write: bool = False):
        _path(self._path)
        if not self._path.is_file():
            raise SQLiteLedgerError("provisioned ledger file is unavailable")
        # mode=rw is important: reconnect/readiness must NEVER create a new file.
        connection = sqlite3.connect(
            self._path.as_uri() + "?mode=rw", uri=True,
            isolation_level=None, timeout=self._timeout_s,
        )
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            if connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise SQLiteLedgerError("full synchronization is unavailable")
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise SQLiteLedgerError("unsupported ledger journal mode")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            if write:
                connection.commit()
        finally:
            # close rolls back a pending transaction on every exceptional exit.
            connection.close()

    def _read(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        objects = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' ORDER BY name"
        ).fetchall()
        if dict(objects) != _SCHEMA:
            raise SQLiteLedgerError("ledger schema is not recognized")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise SQLiteLedgerError("SQLite integrity check failed")
        meta = connection.execute(
            "SELECT singleton, schema_version, store_id, node_count, head FROM ledger_meta"
        ).fetchall()
        if len(meta) != 1 or meta[0][:3] != (1, SCHEMA_VERSION, self._store_id):
            raise SQLiteLedgerError("ledger identity or version does not match")
        nodes: list[dict[str, Any]] = []
        parent = None
        for position, (index, digest, encoded) in enumerate(connection.execute(
            "SELECT node_index, digest, node_json FROM ledger_nodes ORDER BY node_index"
        )):
            if type(encoded) is not str or len(encoded.encode("utf-8")) > MAX_NODE_BYTES:
                raise SQLiteLedgerError("stored receipt exceeds the storage limit")
            node = json.loads(encoded, object_pairs_hook=_pairs)
            if _encode(node) != encoded or index != position:
                raise SQLiteLedgerError("stored receipt is not canonical or sequential")
            _validate_node(node, position, parent)
            if digest != node["digest"]:
                raise SQLiteLedgerError("stored receipt digest column does not match")
            nodes.append(node)
            parent = digest
        if meta[0][3:] != (len(nodes), parent):
            raise SQLiteLedgerError("ledger head or count does not match stored receipts")
        return nodes

    def startup(self) -> None:
        self.replay()

    def replay(self) -> list[dict[str, Any]]:
        with self._transaction() as connection:
            return self._read(connection)

    def append(self, node: Mapping[str, Any]) -> None:
        encoded = _encode(node)
        with self._transaction(write=True) as connection:
            nodes = self._read(connection)
            # Check the complete payload, including DSSE, on idempotent retries.
            existing = connection.execute(
                "SELECT node_json FROM ledger_nodes WHERE digest = ?", (node.get("digest"),)
            ).fetchone()
            if existing is not None:
                if existing[0] != encoded:
                    raise SQLiteLedgerError("receipt digest already has different stored content")
                return
            _validate_node(node, len(nodes), nodes[-1]["digest"] if nodes else None)
            connection.execute("INSERT INTO ledger_nodes VALUES (?, ?, ?)",
                               (node["index"], node["digest"], encoded))
            connection.execute("UPDATE ledger_meta SET node_count = ?, head = ? WHERE singleton = 1",
                               (len(nodes) + 1, node["digest"]))
            if self._read(connection) != [*nodes, dict(node)]:
                raise SQLiteLedgerError("stored append verification failed")

    def verify_integrity(self, nodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        try:
            replayed = self.replay()
            verified = [_encode(node) for node in replayed] == [_encode(dict(node)) for node in nodes]
        except Exception:
            verified = False
        return {"verified": verified}

    def readiness(self) -> dict[str, Any]:
        try:
            # Test writer-lock acquisition as well as replay. Actual append may
            # still fail (for example disk full); LedgerRuntime handles that.
            with self._transaction(write=True) as connection:
                self._read(connection)
            ready = True
        except Exception:
            ready = False
        return {
            "ready": ready,
            "production_ready": False,
            "persistence_scope": "LOCAL_FILESYSTEM",
        }


def from_environment() -> SQLiteLedgerAdapter:
    return SQLiteLedgerAdapter(
        os.environ.get("KILLINCHU_LEDGER_SQLITE_PATH", ""),
        os.environ.get("KILLINCHU_LEDGER_SQLITE_ID", ""),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init"])
    parser.add_argument("path", help="Absolute path to a new ledger file in an existing directory")
    args = parser.parse_args()
    try:
        store_id = provision(args.path)
    except (SQLiteLedgerError, OSError, sqlite3.Error):
        parser.exit(1, "Ledger provisioning failed; no existing file was overwritten.\n")
    print(json.dumps({"store_id": store_id, "persistence_scope": "LOCAL_FILESYSTEM", "production_ready": False}))


if __name__ == "__main__":
    main()
