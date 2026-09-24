"""Small real-file and separate-process checks for local ledger recovery."""

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from killinchu_ledger_sqlite import (
    SQLiteLedgerAdapter,
    SQLiteLedgerError,
    backup_store,
    provision,
    restore_store,
    verify_store,
)


ROOT = Path(__file__).resolve().parents[1]
REJECTED = (SQLiteLedgerError, OSError, sqlite3.Error, ValueError)
CHECKPOINT_FIELDS = {
    "schema", "store_id", "node_count", "head", "content_sha256", "evidence_class",
}


def _node(index, previous=None):
    receipt = {"schema": "recovery-test/v1", "index": index, "payload": "small fixture"}
    parents = [] if previous is None else [previous]
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode())
    for parent in parents:
        digest.update(parent.encode())
    return {
        "index": index,
        "receipt": receipt,
        "parents": parents,
        "digest": digest.hexdigest(),
        "dsse": {"signatures": [{"keyid": "test-only", "sig": "not-a-real-signature"}]},
    }


class SQLiteLedgerRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="killinchu-recovery-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "source.sqlite3"
        self.snapshot = self.directory / "snapshot.sqlite3"
        self.restored = self.directory / "restored.sqlite3"
        self.store_id = provision(self.source)
        self.adapter = SQLiteLedgerAdapter(self.source, self.store_id)

    def _populate(self):
        first = _node(0)
        second = _node(1, first["digest"])
        self.adapter.append(first)
        self.adapter.append(second)
        return [first, second]

    def _backup(self):
        return backup_store(self.source, self.snapshot, self.store_id, timeout_s=5.0)

    def _checkpoint_file(self, checkpoint):
        path = self.directory / "checkpoint.json"
        path.write_text(json.dumps(checkpoint, sort_keys=True), encoding="utf-8")
        return path

    def _cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", "-m", "killinchu_ledger_sqlite", *map(str, arguments)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )

    def _sql(self, path, statement, parameters=()):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(statement, parameters)

    def _assert_cli_failure(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(str(self.directory), result.stderr)

    def test_backup_checkpoint_is_strict_and_explicitly_unsigned(self):
        nodes = self._populate()
        checkpoint = self._backup()
        self.assertEqual(set(checkpoint), CHECKPOINT_FIELDS)
        self.assertEqual(checkpoint["schema"], "szl.killinchu.sqlite-checkpoint/v1")
        self.assertEqual(checkpoint["store_id"], self.store_id)
        self.assertIs(type(checkpoint["node_count"]), int)
        self.assertEqual(checkpoint["node_count"], len(nodes))
        self.assertEqual(checkpoint["head"], nodes[-1]["digest"])
        self.assertRegex(checkpoint["content_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(checkpoint["evidence_class"], "UNSIGNED_LOCAL_CHECKPOINT")
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)
        self.assertNotIn(str(self.source), json.dumps(checkpoint))

    def test_empty_store_backup_verify_restore(self):
        checkpoint = self._backup()
        self.assertEqual(checkpoint["node_count"], 0)
        self.assertIsNone(checkpoint["head"])
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)
        self.assertEqual(restore_store(self.snapshot, self.restored, checkpoint), checkpoint)
        restored = SQLiteLedgerAdapter(self.restored, self.store_id)
        self.assertEqual(restored.replay(), [])
        self.assertFalse(restored.readiness()["production_ready"])

    def test_checkpoint_content_hash_matches_independent_framed_computation(self):
        nodes = self._populate()
        expected = hashlib.sha256(b"szl.killinchu.sqlite-checkpoint/v1\x00")
        for node in nodes:
            encoded = json.dumps(node, sort_keys=True, allow_nan=False).encode("utf-8")
            expected.update(len(encoded).to_bytes(8, "big"))
            expected.update(encoded)
        self.assertEqual(self._backup()["content_sha256"], expected.hexdigest())

    def test_empty_checkpoint_hash_includes_domain(self):
        expected = hashlib.sha256(b"szl.killinchu.sqlite-checkpoint/v1\x00").hexdigest()
        self.assertEqual(self._backup()["content_sha256"], expected)

    def test_restored_store_preserves_full_nodes_and_can_append(self):
        nodes = self._populate()
        checkpoint = self._backup()
        self.assertEqual(restore_store(self.snapshot, self.restored, checkpoint), checkpoint)
        restored = SQLiteLedgerAdapter(self.restored, self.store_id)
        self.assertEqual(restored.replay(), nodes)
        third = _node(2, nodes[-1]["digest"])
        restored.append(third)
        self.assertEqual(restored.replay(), [*nodes, third])
        self.assertEqual(self.adapter.replay(), nodes)
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)

    def test_source_bytes_are_unchanged_by_backup(self):
        self._populate()
        original = self.source.read_bytes()
        self._backup()
        self.assertEqual(self.source.read_bytes(), original)

    def test_later_source_append_does_not_change_snapshot(self):
        nodes = self._populate()
        checkpoint = self._backup()
        original = self.snapshot.read_bytes()
        self.adapter.append(_node(2, nodes[-1]["digest"]))
        self.assertEqual(self.snapshot.read_bytes(), original)
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)
        self.assertEqual(SQLiteLedgerAdapter(self.snapshot, self.store_id).replay(), nodes)

    def test_backup_pins_validated_snapshot_until_copy_finishes(self):
        nodes = self._populate()
        third = _node(2, nodes[-1]["digest"])
        writer = SQLiteLedgerAdapter(self.source, self.store_id, timeout_s=0.05)
        real_connect = sqlite3.connect
        test = self
        attempts = []

        class ObservedConnection(sqlite3.Connection):
            def backup(self, target, *, pages=-1, progress=None, name="main", sleep=0.250):
                test.assertTrue(self.in_transaction)
                # A second real connection can start writing, but its commit
                # cannot replace the source snapshot retained by this reader.
                with test.assertRaises(sqlite3.OperationalError):
                    writer.append(third)
                attempts.append("writer commit blocked")
                return super().backup(target, pages=pages, progress=progress, name=name, sleep=sleep)

        def connect(database, *args, **kwargs):
            if "mode=ro" in str(database):
                kwargs["factory"] = ObservedConnection
            return real_connect(database, *args, **kwargs)

        with patch("killinchu_ledger_sqlite.sqlite3.connect", side_effect=connect):
            checkpoint = self._backup()
        self.assertEqual(attempts, ["writer commit blocked"])
        self.assertEqual(self.adapter.replay(), nodes)
        self.assertEqual(SQLiteLedgerAdapter(self.snapshot, self.store_id).replay(), nodes)
        writer.append(third)
        self.assertEqual(self.adapter.replay(), [*nodes, third])
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)

    def test_stale_internally_consistent_snapshot_rejected_against_new_checkpoint(self):
        nodes = self._populate()
        self._backup()
        self.adapter.append(_node(2, nodes[-1]["digest"]))
        newest = backup_store(self.source, self.directory / "newest.sqlite3", self.store_id)
        with self.assertRaises(REJECTED):
            verify_store(self.snapshot, newest)
        with self.assertRaises(REJECTED):
            restore_store(self.snapshot, self.restored, newest)
        self.assertFalse(self.restored.exists())

    def test_dsse_only_change_is_rejected_even_when_chain_and_head_still_verify(self):
        nodes = self._populate()
        checkpoint = self._backup()
        changed = deepcopy(nodes[0])
        changed["dsse"]["signatures"][0]["sig"] = "different-untrusted-signature"
        self._sql(self.snapshot, "UPDATE ledger_nodes SET node_json = ? WHERE node_index = 0",
                  (json.dumps(changed, sort_keys=True),))
        replayed = SQLiteLedgerAdapter(self.snapshot, self.store_id).replay()
        self.assertEqual(replayed[-1]["digest"], checkpoint["head"])
        self.assertEqual(replayed[0]["digest"], nodes[0]["digest"])
        with self.assertRaises(REJECTED):
            verify_store(self.snapshot, checkpoint)
        with self.assertRaises(REJECTED):
            restore_store(self.snapshot, self.restored, checkpoint)
        self.assertFalse(self.restored.exists())

    def test_existing_backup_target_is_never_overwritten(self):
        self._populate()
        self.snapshot.write_bytes(b"existing target must survive")
        original = self.snapshot.read_bytes()
        with self.assertRaises(REJECTED):
            self._backup()
        self.assertEqual(self.snapshot.read_bytes(), original)

    def test_existing_restore_target_is_never_overwritten(self):
        self._populate()
        checkpoint = self._backup()
        self.restored.write_bytes(b"existing restored target must survive")
        original = self.restored.read_bytes()
        with self.assertRaises(REJECTED):
            restore_store(self.snapshot, self.restored, checkpoint)
        self.assertEqual(self.restored.read_bytes(), original)

    def test_backup_cannot_replace_source_itself(self):
        self._populate()
        original = self.source.read_bytes()
        with self.assertRaises(REJECTED):
            backup_store(self.source, self.source, self.store_id)
        self.assertEqual(self.source.read_bytes(), original)

    def test_backup_cannot_replace_a_hardlink_to_source(self):
        self._populate()
        original = self.source.read_bytes()
        try:
            os.link(self.source, self.snapshot)
        except OSError as exc:
            self.skipTest(f"hardlinks unavailable on the temporary filesystem: {exc}")
        with self.assertRaises(REJECTED):
            self._backup()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.snapshot.read_bytes(), original)

    def test_restore_cannot_replace_snapshot_itself(self):
        self._populate()
        checkpoint = self._backup()
        original = self.snapshot.read_bytes()
        with self.assertRaises(REJECTED):
            restore_store(self.snapshot, self.snapshot, checkpoint)
        self.assertEqual(self.snapshot.read_bytes(), original)

    def test_missing_source_is_not_created(self):
        missing = self.directory / "absent.sqlite3"
        with self.assertRaises(REJECTED):
            backup_store(missing, self.snapshot, self.store_id)
        self.assertFalse(missing.exists())
        self.assertFalse(self.snapshot.exists())

    def test_missing_snapshot_is_never_created_by_verify_or_restore(self):
        checkpoint = self._backup()
        missing = self.directory / "absent.sqlite3"
        with self.assertRaises(REJECTED):
            verify_store(missing, checkpoint)
        with self.assertRaises(REJECTED):
            restore_store(missing, self.restored, checkpoint)
        self.assertFalse(missing.exists())
        self.assertFalse(self.restored.exists())

    def test_wrong_source_identity_fails_before_creating_target(self):
        self._populate()
        with self.assertRaises(REJECTED):
            backup_store(self.source, self.snapshot, str(uuid.uuid4()))
        self.assertFalse(self.snapshot.exists())

    def test_corrupt_source_schema_fails_before_creating_target(self):
        self._sql(self.source, "CREATE TABLE unexpected (value TEXT)")
        original = self.source.read_bytes()
        with self.assertRaises(REJECTED):
            self._backup()
        self.assertFalse(self.snapshot.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_corrupt_snapshot_schema_is_rejected_without_repair(self):
        checkpoint = self._backup()
        self._sql(self.snapshot, "CREATE TABLE unexpected (value TEXT)")
        original = self.snapshot.read_bytes()
        with self.assertRaises(REJECTED):
            verify_store(self.snapshot, checkpoint)
        with self.assertRaises(REJECTED):
            restore_store(self.snapshot, self.restored, checkpoint)
        self.assertFalse(self.restored.exists())
        self.assertEqual(self.snapshot.read_bytes(), original)

    def test_checkpoint_requires_exact_field_set(self):
        checkpoint = self._backup()
        variants = []
        for key in CHECKPOINT_FIELDS:
            missing = dict(checkpoint)
            missing.pop(key)
            variants.append(missing)
        variants.append({**checkpoint, "production_ready": True})
        for candidate in variants:
            with self.subTest(keys=sorted(candidate)), self.assertRaises(REJECTED):
                verify_store(self.snapshot, candidate)

    def test_checkpoint_rejects_non_integer_and_negative_counts(self):
        checkpoint = self._backup()
        for value in (False, True, 0.0, "0", -1, None, float("nan"), float("inf")):
            candidate = {**checkpoint, "node_count": value}
            with self.subTest(value=repr(value)), self.assertRaises(REJECTED):
                verify_store(self.snapshot, candidate)
        self.assertEqual(verify_store(self.snapshot, checkpoint), checkpoint)

    def test_checkpoint_rejects_invalid_identity_schema_evidence_and_hashes(self):
        checkpoint = self._backup()
        cases = [
            ("schema", "szl.killinchu.sqlite-checkpoint/v2"),
            ("schema", None),
            ("store_id", "{" + self.store_id + "}"),
            ("store_id", str(uuid.uuid4())),
            ("evidence_class", "SIGNED_APPROVAL"),
            ("content_sha256", "0" * 64),
            ("content_sha256", "g" * 64),
            ("content_sha256", "A" * 64),
            ("content_sha256", "f" * 63),
            ("head", "0" * 64),
            ("head", False),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(REJECTED):
                verify_store(self.snapshot, {**checkpoint, field: value})

    def test_restore_rejects_malformed_checkpoint_before_creating_target(self):
        checkpoint = self._backup()
        for candidate in (None, [], {}, {**checkpoint, "node_count": False}):
            with self.subTest(candidate=candidate), self.assertRaises(REJECTED):
                restore_store(self.snapshot, self.restored, candidate)
            self.assertFalse(self.restored.exists())

    def test_invalid_timeout_fails_before_creating_target(self):
        for value in (False, True, 0, -1, 301, "30", None, float("nan"), float("inf")):
            with self.subTest(timeout=repr(value)), self.assertRaises(REJECTED):
                backup_store(self.source, self.snapshot, self.store_id, timeout_s=value)
            self.assertFalse(self.snapshot.exists())

    def test_copy_deadline_failure_preserves_partial_target_and_refuses_retry(self):
        self._populate()
        original = self.source.read_bytes()
        # Initial deadline, pre-copy check, then the real SQLite progress callback.
        with patch("killinchu_ledger_sqlite.time.monotonic", side_effect=[0.0, 0.0, 31.0]):
            with self.assertRaises(SQLiteLedgerError):
                backup_store(self.source, self.snapshot, self.store_id, timeout_s=30.0)
        self.assertTrue(self.snapshot.exists())
        partial = self.snapshot.read_bytes()
        with self.assertRaises(REJECTED):
            self._backup()
        self.assertEqual(self.snapshot.read_bytes(), partial)
        self.assertEqual(self.source.read_bytes(), original)

    def test_failed_reopen_verification_prevents_success(self):
        self._populate()
        original = self.source.read_bytes()
        with patch("killinchu_ledger_sqlite.verify_store",
                   side_effect=SQLiteLedgerError("simulated reopen verification failure")) as verify:
            with self.assertRaises(SQLiteLedgerError):
                self._backup()
        verify.assert_called_once()
        self.assertEqual(verify.call_args.args[0], self.snapshot)
        self.assertTrue(self.snapshot.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_busy_backup_progress_is_also_subject_to_deadline(self):
        real_connect = sqlite3.connect
        statuses = []

        class BusyConnection(sqlite3.Connection):
            def backup(self, target, *, pages=-1, progress=None, name="main", sleep=0.250):
                statuses.append(sqlite3.SQLITE_BUSY)
                progress(sqlite3.SQLITE_BUSY, 0, 0)
                raise AssertionError("expired busy callback must abort the copy")

        def connect(database, *args, **kwargs):
            if "mode=ro" in str(database):
                kwargs["factory"] = BusyConnection
            return real_connect(database, *args, **kwargs)

        with patch("killinchu_ledger_sqlite.sqlite3.connect", side_effect=connect):
            with patch("killinchu_ledger_sqlite.time.monotonic", side_effect=[0.0, 0.0, 31.0]):
                with self.assertRaises(SQLiteLedgerError):
                    backup_store(self.source, self.snapshot, self.store_id, timeout_s=30.0)
        self.assertEqual(statuses, [sqlite3.SQLITE_BUSY])
        self.assertTrue(self.snapshot.exists())

    def test_cli_backup_verify_restore_runs_in_separate_processes(self):
        nodes = self._populate()
        backup = self._cli("backup", self.source, self.snapshot, "--store-id", self.store_id)
        self.assertEqual(backup.returncode, 0, backup.stderr)
        checkpoint = json.loads(backup.stdout)
        self.assertEqual(set(checkpoint), CHECKPOINT_FIELDS)
        expected = self._checkpoint_file(checkpoint)
        verified = self._cli("verify", self.snapshot, "--expected-checkpoint", expected)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout), checkpoint)
        restored = self._cli("restore", self.snapshot, self.restored,
                             "--expected-checkpoint", expected)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(json.loads(restored.stdout), checkpoint)
        self.assertEqual(SQLiteLedgerAdapter(self.restored, self.store_id).replay(), nodes)
        for result in (backup, verified, restored):
            self.assertNotIn(str(self.directory), result.stdout + result.stderr)

    def test_cli_rejects_duplicate_checkpoint_json_keys(self):
        checkpoint = self._backup()
        expected = self._checkpoint_file(checkpoint)
        encoded = json.dumps(checkpoint, sort_keys=True)
        expected.write_text('{"node_count": 0, ' + encoded[1:], encoding="utf-8")
        self._assert_cli_failure(self._cli("verify", self.snapshot, "--expected-checkpoint", expected))
        self._assert_cli_failure(self._cli("restore", self.snapshot, self.restored,
                                           "--expected-checkpoint", expected))
        self.assertFalse(self.restored.exists())

    def test_cli_rejects_nan_checkpoint_count(self):
        checkpoint = self._backup()
        expected = self._checkpoint_file({**checkpoint, "node_count": float("nan")})
        self._assert_cli_failure(self._cli("verify", self.snapshot, "--expected-checkpoint", expected))

    def test_cli_rejects_oversized_checkpoint_file(self):
        checkpoint = self._backup()
        expected = self._checkpoint_file(checkpoint)
        expected.write_text(" " * 8193 + json.dumps(checkpoint), encoding="utf-8")
        self._assert_cli_failure(self._cli("restore", self.snapshot, self.restored,
                                           "--expected-checkpoint", expected))
        self.assertFalse(self.restored.exists())

    def test_cli_rejects_malformed_checkpoint_json(self):
        checkpoint = self._backup()
        expected = self._checkpoint_file(checkpoint)
        expected.write_text('{"schema": ', encoding="utf-8")
        self._assert_cli_failure(self._cli("verify", self.snapshot, "--expected-checkpoint", expected))

    def test_cli_requires_independently_supplied_checkpoint(self):
        self._backup()
        result = self._cli("restore", self.snapshot, self.restored)
        self._assert_cli_failure(result)
        self.assertFalse(self.restored.exists())

    def test_cli_missing_checkpoint_does_not_create_it_or_restore_target(self):
        self._backup()
        missing = self.directory / "missing.json"
        self._assert_cli_failure(self._cli("restore", self.snapshot, self.restored,
                                           "--expected-checkpoint", missing))
        self.assertFalse(missing.exists())
        self.assertFalse(self.restored.exists())

    def test_cli_existing_target_failure_has_no_success_output(self):
        self._populate()
        self._backup()
        original = self.snapshot.read_bytes()
        self._assert_cli_failure(self._cli("backup", self.source, self.snapshot,
                                           "--store-id", self.store_id))
        self.assertEqual(self.snapshot.read_bytes(), original)

    def test_cli_missing_source_failure_has_no_success_output(self):
        missing = self.directory / "missing.sqlite3"
        self._assert_cli_failure(self._cli("backup", missing, self.snapshot,
                                           "--store-id", self.store_id))
        self.assertFalse(missing.exists())
        self.assertFalse(self.snapshot.exists())


if __name__ == "__main__":
    unittest.main()
