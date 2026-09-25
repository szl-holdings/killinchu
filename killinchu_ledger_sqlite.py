"""Opt-in, single-host receipt storage; not a provider durability attestation.

Provision explicitly with ``python -m killinchu_ledger_sqlite init ABSOLUTE_PATH``.
Runtime opens only an existing database with a matching provisioned store ID.
No credentials, automatic initialization, schema repair, or in-memory fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
MAX_NODE_BYTES = 1_048_576
CHECKPOINT_SCHEMA = "szl.killinchu.sqlite-checkpoint/v1"
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
    def _transaction(self, *, write: bool = False, read_only: bool = False):
        if write and read_only:
            raise SQLiteLedgerError("read-only ledger cannot acquire a writer transaction")
        _path(self._path)
        if not self._path.is_file():
            raise SQLiteLedgerError("provisioned ledger file is unavailable")
        # mode=rw is important: reconnect/readiness must NEVER create a new file.
        connection = sqlite3.connect(
            self._path.as_uri() + ("?mode=ro" if read_only else "?mode=rw"), uri=True,
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


def _checkpoint(store_id: str, nodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    content = hashlib.sha256(CHECKPOINT_SCHEMA.encode("ascii") + b"\x00")
    for node in nodes:
        payload = _encode(node).encode("utf-8")
        content.update(len(payload).to_bytes(8, "big"))
        content.update(payload)
    return {
        "schema": CHECKPOINT_SCHEMA,
        "store_id": store_id,
        "node_count": len(nodes),
        "head": nodes[-1]["digest"] if nodes else None,
        "content_sha256": content.hexdigest(),
        "evidence_class": "UNSIGNED_LOCAL_CHECKPOINT",
    }


def _validated_checkpoint(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schema", "store_id", "node_count", "head", "content_sha256", "evidence_class"}
    if type(value) is not dict or set(value) != fields:
        raise SQLiteLedgerError("checkpoint fields are invalid")
    if value["schema"] != CHECKPOINT_SCHEMA or value["evidence_class"] != "UNSIGNED_LOCAL_CHECKPOINT":
        raise SQLiteLedgerError("checkpoint format is unsupported")
    store_id = value["store_id"]
    try:
        if type(store_id) is not str or str(uuid.UUID(store_id)) != store_id:
            raise ValueError("invalid identity")
    except (ValueError, TypeError, AttributeError) as exc:
        raise SQLiteLedgerError("checkpoint identity is invalid") from exc
    count = value["node_count"]
    if type(count) is not int or count < 0:
        raise SQLiteLedgerError("checkpoint count is invalid")
    for field in ("head", "content_sha256"):
        entry = value[field]
        if field == "head" and count == 0 and entry is None:
            continue
        if type(entry) is not str or re.fullmatch(r"[0-9a-f]{64}", entry) is None:
            raise SQLiteLedgerError("checkpoint digest is invalid")
    if count == 0 and value["head"] is not None:
        raise SQLiteLedgerError("empty checkpoint has a head")
    return dict(value)


def verify_store(source: str | Path, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Compare an existing store to an independently retained, unsigned checkpoint.

    This checks content equality, NOT checkpoint authenticity or freshness.
    The complete canonical nodes, including DSSE metadata, are bound.
    """
    expected = _validated_checkpoint(checkpoint)
    adapter = SQLiteLedgerAdapter(source, expected["store_id"])
    with adapter._transaction(read_only=True) as connection:
        observed = _checkpoint(expected["store_id"], adapter._read(connection))
    if observed != expected:
        raise SQLiteLedgerError("snapshot does not match the expected checkpoint")
    return observed


def _copy_snapshot(
    source: str | Path, target: str | Path, store_id: str, *,
    expected: Mapping[str, Any] | None = None, timeout_s: float = 30.0,
) -> dict[str, Any]:
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300:
        raise SQLiteLedgerError("backup timeout must be positive and at most 300 seconds")
    deadline = time.monotonic() + timeout_s

    def progress(_status: int, _remaining: int, _total: int) -> None:
        # sqlite3.Connection.backup retries BUSY/LOCKED internally. A connection
        # timeout alone does not bound that loop; raise from every progress call.
        if time.monotonic() >= deadline:
            raise SQLiteLedgerError("snapshot copy exceeded its time budget")

    adapter = SQLiteLedgerAdapter(source, store_id, timeout_s=min(5.0, timeout_s))
    destination = _path(target)
    with adapter._transaction(read_only=True) as connection:
        checkpoint = _checkpoint(store_id, adapter._read(connection))
        if expected is not None and checkpoint != expected:
            raise SQLiteLedgerError("snapshot does not match the expected checkpoint")
        progress(0, 0, 0)
        # Refuse every existing target, including a hardlink to the source.
        # Failure leaves the exclusive partial target for inspection, never
        # resets the source or emits a successful checkpoint.
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(
            destination.as_uri() + "?mode=rw", uri=True, isolation_level=None,
            timeout=min(5.0, timeout_s),
        )) as output:
            if output.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise SQLiteLedgerError("rollback journaling is unavailable")
            output.execute("PRAGMA synchronous=FULL")
            if output.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise SQLiteLedgerError("full synchronization is unavailable")
            # The read transaction pins the validated source snapshot. In DELETE
            # journal mode this maintenance operation can delay other writers.
            connection.backup(output, pages=128, progress=progress, sleep=0.05)
    progress(0, 0, 0)
    # Close and reopen: a successful backup call alone is not our success gate.
    return verify_store(destination, checkpoint)


def backup_store(
    source: str | Path, target: str | Path, store_id: str, *, timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Create and verify a NEW snapshot, returning a local unsigned checkpoint."""
    return _copy_snapshot(source, target, store_id, timeout_s=timeout_s)


def restore_store(
    source: str | Path, target: str | Path, checkpoint: Mapping[str, Any], *,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Restore into a NEW file only, checking retained expectations before copying."""
    expected = _validated_checkpoint(checkpoint)
    return _copy_snapshot(source, target, expected["store_id"],
                          expected=expected, timeout_s=timeout_s)


def _load_checkpoint(path: str) -> dict[str, Any]:
    with _path(path).open("rb") as checkpoint_file:
        raw = checkpoint_file.read(8193)
    if len(raw) > 8192:
        raise SQLiteLedgerError("checkpoint exceeds the input limit")
    return _validated_checkpoint(json.loads(raw, object_pairs_hook=_pairs))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Exclusively provision a new local store")
    initialize.add_argument("path", help="Absolute path to a new ledger file in an existing directory")
    for name in ("backup", "restore", "verify"):
        command = commands.add_parser(name, help="Verify local content; no production or authority claim")
        command.add_argument("source", help="Absolute path to an existing ledger or snapshot")
        if name != "verify":
            command.add_argument("target", help="Absolute path to a NEW file; existing targets are refused")
            command.add_argument("--timeout", type=float, default=30.0)
        if name == "backup":
            command.add_argument("--store-id", required=True)
        else:
            command.add_argument("--expected-checkpoint", required=True,
                                 help="Absolute path to independently retained expected checkpoint JSON")
    args = parser.parse_args()
    try:
        if args.command == "init":
            store_id = provision(args.path)
            result = {"store_id": store_id, "persistence_scope": "LOCAL_FILESYSTEM", "production_ready": False}
        elif args.command == "backup":
            result = backup_store(args.source, args.target, args.store_id, timeout_s=args.timeout)
        else:
            expected = _load_checkpoint(args.expected_checkpoint)
            result = (
                verify_store(args.source, expected) if args.command == "verify"
                else restore_store(args.source, args.target, expected, timeout_s=args.timeout)
            )
    except Exception:
        operation = "provisioning" if args.command == "init" else "snapshot operation"
        parser.exit(1, f"Ledger {operation} failed; no existing file was overwritten.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
