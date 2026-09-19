"""Real-file regression checks for the opt-in, non-production SQLite ledger."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from killinchu_ledger import DURABLE_EXTERNAL, LedgerRuntime, LedgerUnavailable
from killinchu_ledger_sqlite import SQLiteLedgerAdapter, SQLiteLedgerError, provision
from killinchu_receipt_export import build_receipt_export


ROOT = Path(__file__).resolve().parents[1]


def _digest(receipt, parents):
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode())
    for parent in parents:
        digest.update(parent.encode())
    return digest.hexdigest()


def _node(index, previous=None, tag="test"):
    receipt = {"schema": "sqlite-test/v1", "index": index, "tag": tag}
    parents = [] if previous is None else [previous]
    return {
        "index": index,
        "receipt": receipt,
        "parents": parents,
        "digest": _digest(receipt, parents),
        "dsse": {"signatures": []},
    }


class SQLiteLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="killinchu-ledger-test-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.sqlite3"
        self.store_id = provision(self.path)
        self.adapter = SQLiteLedgerAdapter(self.path, self.store_id, timeout_s=0.05)

    def _runtime(self, adapter=None):
        return LedgerRuntime(
            [], threading.RLock(), _digest, mode=DURABLE_EXTERNAL,
            adapter=self.adapter if adapter is None else adapter,
            recovery_interval_s=0,
        )

    def _sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(statement, parameters)

    def _child(self, action, node=None):
        # Both operations import the adapter in a genuinely different process.
        code = (
            "import json,sys; from killinchu_ledger_sqlite import SQLiteLedgerAdapter; "
            "a=SQLiteLedgerAdapter(sys.argv[1],sys.argv[2]); a.startup(); "
            "a.append(json.loads(sys.argv[4])) if sys.argv[3]=='append' else None; "
            "print(json.dumps(a.replay(),sort_keys=True))"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code, str(self.path), self.store_id,
             action, json.dumps(node)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_append_and_replay_survive_separate_processes(self):
        first = _node(0)
        self.assertEqual(self._child("append", first), [first])
        self.assertEqual(self._child("replay"), [first])
        second = _node(1, first["digest"])
        self.assertEqual(self._child("append", second), [first, second])
        self.assertEqual(self._child("replay"), [first, second])

    def test_independent_writers_cannot_commit_different_children_of_same_head(self):
        first_writer = SQLiteLedgerAdapter(self.path, self.store_id, timeout_s=5)
        other = SQLiteLedgerAdapter(self.path, self.store_id, timeout_s=5)
        barrier = threading.Barrier(2)

        def append(adapter, tag):
            barrier.wait(timeout=5)
            try:
                adapter.append(_node(0, tag=tag))
                return "committed"
            except SQLiteLedgerError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(append, first_writer, "a"), pool.submit(append, other, "b")]
            self.assertEqual(sorted(result.result(timeout=10) for result in results),
                             ["committed", "conflict"])
        self.assertEqual(len(self.adapter.replay()), 1)
        self.assertTrue(self.adapter.readiness()["ready"])

    def test_exact_duplicate_is_idempotent_even_after_later_append(self):
        first = _node(0)
        second = _node(1, first["digest"])
        self.adapter.append(first)
        self.adapter.append(second)
        self.adapter.append(first)
        self.assertEqual(self.adapter.replay(), [first, second])

    def test_duplicate_digest_with_changed_dsse_is_rejected(self):
        first = _node(0)
        self.adapter.append(first)
        changed = json.loads(json.dumps(first))
        changed["dsse"]["signatures"] = [{"keyid": "changed", "sig": "not-a-signature"}]
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.append(changed)
        self.assertEqual(self.adapter.replay(), [first])

    def test_stale_parent_and_non_monotonic_index_are_rejected(self):
        first = _node(0)
        self.adapter.append(first)
        for invalid in (_node(1, "0" * 64), _node(2, first["digest"])):
            with self.subTest(node=invalid), self.assertRaises(SQLiteLedgerError):
                self.adapter.append(invalid)
        self.assertEqual(self.adapter.replay(), [first])

    def test_boolean_index_is_not_an_integer_index(self):
        node = _node(0)
        node["index"] = False
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.append(node)
        self.assertEqual(self.adapter.replay(), [])

    def test_nan_infinity_and_non_json_values_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), ("tuple",), {"set"}):
            node = _node(0)
            node["dsse"]["extra"] = value
            with self.subTest(value=repr(value)), self.assertRaises((ValueError, SQLiteLedgerError)):
                self.adapter.append(node)
        self.assertEqual(self.adapter.replay(), [])

    def test_non_string_object_keys_are_rejected(self):
        node = _node(0)
        node["dsse"][1] = "invalid"
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.append(node)

    def test_oversized_node_is_rejected(self):
        node = _node(0)
        node["dsse"]["extra"] = "x" * 1_048_576
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.append(node)
        self.assertEqual(self.adapter.replay(), [])

    def test_noncanonical_stored_json_is_rejected(self):
        node = _node(0)
        self.adapter.append(node)
        self._sql("UPDATE ledger_nodes SET node_json = ?",
                  (json.dumps(node, sort_keys=True, separators=(",", ":")),))
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.replay()
        self.assertFalse(self.adapter.readiness()["ready"])

    def test_duplicate_stored_json_keys_are_rejected(self):
        node = _node(0)
        self.adapter.append(node)
        encoded = json.dumps(node, sort_keys=True)
        self._sql("UPDATE ledger_nodes SET node_json = ?", ('{"index": 0, ' + encoded[1:],))
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.replay()

    def test_canonical_receipt_tampering_is_rejected(self):
        node = _node(0)
        self.adapter.append(node)
        node["receipt"]["tag"] = "tampered"
        self._sql("UPDATE ledger_nodes SET node_json = ?", (json.dumps(node, sort_keys=True),))
        self.assertFalse(self.adapter.verify_integrity([node])["verified"])
        self.assertFalse(self.adapter.readiness()["ready"])

    def test_digest_column_tampering_is_rejected(self):
        self.adapter.append(_node(0))
        self._sql("UPDATE ledger_nodes SET digest = ?", ("0" * 64,))
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.replay()

    def test_metadata_head_and_count_tampering_is_rejected(self):
        self.adapter.append(_node(0))
        self._sql("UPDATE ledger_meta SET node_count = 0, head = NULL")
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.replay()

    def test_schema_tampering_is_rejected_without_repair(self):
        self._sql("CREATE TABLE unexpected (value TEXT)")
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.startup()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'unexpected'"
            ).fetchone())

    def test_schema_version_tampering_is_rejected(self):
        self._sql("UPDATE ledger_meta SET schema_version = 2")
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.startup()

    def test_near_reserved_schema_name_is_not_hidden_from_validation(self):
        # '_' in SQL LIKE is a wildcard; it must not hide sqliteXextra.
        self._sql("CREATE TABLE sqliteXextra (value TEXT)")
        with self.assertRaises(SQLiteLedgerError):
            self.adapter.startup()

    def test_stored_nan_boolean_index_and_malformed_json_are_rejected(self):
        node = _node(0)
        self.adapter.append(node)
        nan_node = json.loads(json.dumps(node))
        nan_node["dsse"]["extra"] = float("nan")
        boolean_node = json.loads(json.dumps(node))
        boolean_node["index"] = False
        for encoded in (json.dumps(nan_node, sort_keys=True),
                        json.dumps(boolean_node, sort_keys=True), '{"digest":'):
            with self.subTest(encoded=encoded):
                self._sql("UPDATE ledger_nodes SET node_json = ?", (encoded,))
                with self.assertRaises((ValueError, SQLiteLedgerError)):
                    self.adapter.replay()
                self.assertFalse(self.adapter.readiness()["ready"])
                self.assertFalse(self.adapter.verify_integrity([node])["verified"])

    def test_incorrect_store_identity_is_rejected(self):
        other_path = Path(self.temporary.name) / "other.sqlite3"
        other_id = provision(other_path)
        other = SQLiteLedgerAdapter(self.path, other_id)
        self.assertFalse(other.readiness()["ready"])
        with self.assertRaises(SQLiteLedgerError):
            other.startup()

    def test_noncanonical_store_identity_and_relative_path_are_rejected(self):
        for identity in ("", "not-a-uuid", "{" + self.store_id + "}"):
            with self.subTest(identity=identity), self.assertRaises(SQLiteLedgerError):
                SQLiteLedgerAdapter(self.path, identity)
        with self.assertRaises(SQLiteLedgerError):
            SQLiteLedgerAdapter("relative.sqlite3", self.store_id)

    def test_provision_refuses_existing_database_without_changes(self):
        node = _node(0)
        self.adapter.append(node)
        with self.assertRaises(FileExistsError):
            provision(self.path)
        self.assertEqual(self.adapter.replay(), [node])

    def test_missing_file_never_recreated_by_runtime_operations(self):
        self.adapter.append(_node(0))
        saved = self.path.with_suffix(".saved")
        self.path.rename(saved)
        self.assertFalse(self.adapter.readiness()["ready"])
        self.assertFalse(self.adapter.verify_integrity([])["verified"])
        for operation in (self.adapter.startup, self.adapter.replay,
                          lambda: self.adapter.append(_node(0))):
            with self.subTest(operation=operation), self.assertRaises(SQLiteLedgerError):
                operation()
            self.assertFalse(self.path.exists())

    def test_missing_file_at_first_startup_does_not_initialize(self):
        missing = Path(self.temporary.name) / "missing.sqlite3"
        adapter = SQLiteLedgerAdapter(missing, self.store_id)
        self.assertFalse(adapter.readiness()["ready"])
        with self.assertRaises(SQLiteLedgerError):
            adapter.startup()
        self.assertFalse(missing.exists())

    def test_writer_lock_causes_unready_and_recovers_after_release(self):
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self.assertFalse(self.adapter.readiness()["ready"])
            with self.assertRaises(sqlite3.OperationalError):
                self.adapter.append(_node(0))
        finally:
            connection.rollback()
            connection.close()
        self.assertTrue(self.adapter.readiness()["ready"])
        self.assertEqual(self.adapter.replay(), [])

    def test_lost_append_acknowledgment_replays_committed_node_once(self):
        class LostAcknowledgment(SQLiteLedgerAdapter):
            def append(self, node):
                super().append(node)
                raise RuntimeError("simulated lost acknowledgment after commit")

        adapter = LostAcknowledgment(self.path, self.store_id)
        runtime = self._runtime(adapter)
        self.assertTrue(runtime.startup()["ready"])
        node = _node(0)
        with self.assertRaises(LedgerUnavailable):
            runtime.append(node)
        self.assertEqual(runtime.snapshot(), [])
        self.assertEqual(self.adapter.replay(), [node])
        self.assertTrue(runtime.readiness()["ready"])
        self.assertEqual(runtime.snapshot(), [node])
        self.adapter.append(node)
        self.assertEqual(len(self.adapter.replay()), 1)

    def test_runtime_replays_after_storage_outage_before_claiming_ready(self):
        runtime = self._runtime()
        self.assertTrue(runtime.startup()["ready"])
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self.assertFalse(runtime.readiness()["ready"])
        finally:
            connection.rollback()
            connection.close()
        node = _node(0)
        SQLiteLedgerAdapter(self.path, self.store_id).append(node)
        self.assertEqual(runtime.snapshot(), [])
        self.assertTrue(runtime.readiness()["ready"])
        self.assertEqual(runtime.snapshot(), [node])

    def test_runtime_rejects_write_without_exposing_memory_on_missing_store(self):
        runtime = self._runtime()
        self.assertTrue(runtime.startup()["ready"])
        self.path.rename(self.path.with_suffix(".saved"))
        with self.assertRaises(LedgerUnavailable):
            runtime.append(_node(0))
        self.assertEqual(runtime.snapshot(), [])
        self.assertFalse(self.path.exists())

    def test_healthy_sqlite_is_ready_but_never_production_ready(self):
        state = self._runtime().startup()
        self.assertTrue(state["ready"])
        self.assertFalse(state["production_ready"])
        self.assertEqual(state["persistence_scope"], "LOCAL_FILESYSTEM")
        self.assertEqual(state["production_readiness_basis"], "EXPLICIT_ADAPTER_CONTRACT")
        public = json.dumps(state)
        self.assertNotIn(str(self.path), public)
        self.assertNotIn(self.store_id, public)

    def test_production_veto_requires_true_boolean_not_truthiness(self):
        for value in (False, None, 0, 1, "true"):
            with self.subTest(value=value), patch.object(
                self.adapter, "readiness",
                return_value={"ready": True, "production_ready": value,
                              "persistence_scope": "LOCAL_FILESYSTEM"},
            ):
                state = self._runtime().startup()
                self.assertTrue(state["ready"])
                self.assertFalse(state["production_ready"])

    def test_receipt_export_carries_local_filesystem_limit(self):
        runtime = self._runtime()
        runtime.startup()
        node = _node(0)
        runtime.append(node)
        body, status = build_receipt_export(runtime.snapshot(), ledger=runtime.readiness())
        self.assertEqual(status, 200)
        self.assertFalse(body["ledger"]["production_ready"])
        self.assertEqual(body["ledger"]["persistence_scope"], "LOCAL_FILESYSTEM")
        self.assertTrue(any("LOCAL_FILESYSTEM" in limit["code"] for limit in body["limits"]))

    def test_environment_factory_is_wired_without_default_activation(self):
        config = {
            "KILLINCHU_LEDGER_MODE": DURABLE_EXTERNAL,
            "KILLINCHU_LEDGER_ADAPTER": "killinchu_ledger_sqlite:from_environment",
            "KILLINCHU_LEDGER_SQLITE_PATH": str(self.path),
            "KILLINCHU_LEDGER_SQLITE_ID": self.store_id,
        }
        with patch.dict(os.environ, config):
            runtime = LedgerRuntime.from_environment([], threading.RLock(), _digest)
            self.assertTrue(runtime.startup()["ready"])
            self.assertFalse(runtime.readiness()["production_ready"])
        default = LedgerRuntime.from_environment([], threading.RLock(), _digest, environ={})
        self.assertEqual(default.startup()["durability_state"], "EPHEMERAL")

    def test_missing_factory_path_configuration_fails_closed(self):
        config = {
            "KILLINCHU_LEDGER_MODE": DURABLE_EXTERNAL,
            "KILLINCHU_LEDGER_ADAPTER": "killinchu_ledger_sqlite:from_environment",
            "KILLINCHU_LEDGER_SQLITE_PATH": "",
            "KILLINCHU_LEDGER_SQLITE_ID": self.store_id,
        }
        with patch.dict(os.environ, config):
            runtime = LedgerRuntime.from_environment([], threading.RLock(), _digest)
            self.assertFalse(runtime.startup()["ready"])

    def test_both_docker_images_copy_the_optional_adapter(self):
        for dockerfile in (ROOT / "Dockerfile", ROOT / "deploy" / "space" / "Dockerfile"):
            with self.subTest(dockerfile=dockerfile):
                self.assertIn("COPY killinchu_ledger_sqlite.py ./killinchu_ledger_sqlite.py",
                              dockerfile.read_text(encoding="utf-8").splitlines())

    def test_cli_provisions_and_refuses_existing_store_without_leaking_path(self):
        path = Path(self.temporary.name) / "cli.sqlite3"
        command = [sys.executable, "-B", "-m", "killinchu_ledger_sqlite", "init", str(path)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"store_id", "persistence_scope", "production_ready"})
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["persistence_scope"], "LOCAL_FILESYSTEM")
        self.assertNotIn(str(path), result.stdout + result.stderr)
        adapter = SQLiteLedgerAdapter(path, report["store_id"])
        node = _node(0)
        adapter.append(node)
        refused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 timeout=20, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(refused.stdout, "")
        self.assertIn("no existing file was overwritten", refused.stderr)
        self.assertNotIn(str(path), refused.stderr)
        self.assertNotIn(report["store_id"], refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)
        self.assertEqual(adapter.replay(), [node])


if __name__ == "__main__":
    unittest.main()
