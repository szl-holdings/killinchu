import hashlib
import json
import threading
import unittest

from killinchu_ledger import DURABLE_EXTERNAL, EPHEMERAL, LedgerRuntime, LedgerUnavailable
from killinchu_receipt_export import build_receipt_export


def _digest(receipt, parents):
    h = hashlib.sha256()
    h.update(json.dumps(receipt, sort_keys=True).encode())
    for parent in parents:
        h.update(parent.encode())
    return h.hexdigest()


def _node(index, previous=None):
    receipt = {"schema": "test/v1", "kind": "test", "payload": {"index": index}}
    parents = [] if previous is None else [previous]
    return {
        "index": index,
        "receipt": receipt,
        "parents": parents,
        "digest": _digest(receipt, parents),
        "dsse": {"signatures": []},
    }


class _ExternalAdapter:
    def __init__(self, nodes=None, *, append_fails=False):
        self.nodes = list(nodes or [])
        self.append_fails = append_fails

    def startup(self):
        return None

    def replay(self):
        return list(self.nodes)

    def append(self, node):
        if self.append_fails:
            raise RuntimeError("test append failure")
        self.nodes.append(node)

    def verify_integrity(self, nodes):
        return {"verified": self.nodes == list(nodes)}

    def readiness(self):
        return {"ready": True}


class LedgerRuntimeTests(unittest.TestCase):
    def test_default_mode_is_truthful_ephemeral_and_not_production_ready(self):
        dag = []
        runtime = LedgerRuntime.from_environment(dag, threading.RLock(), _digest, environ={})
        state = runtime.startup()

        self.assertEqual(state["durability_state"], EPHEMERAL)
        self.assertTrue(state["ready"])
        self.assertFalse(state["production_ready"])
        self.assertEqual(state["replay"]["state"], "NOT_APPLICABLE")

    def test_external_mode_without_adapter_fails_closed(self):
        runtime = LedgerRuntime.from_environment(
            [],
            threading.RLock(),
            _digest,
            environ={"KILLINCHU_LEDGER_MODE": DURABLE_EXTERNAL},
        )
        state = runtime.startup()

        self.assertEqual(state["durability_state"], DURABLE_EXTERNAL)
        self.assertFalse(state["ready"])
        self.assertFalse(state["production_ready"])
        with self.assertRaises(LedgerUnavailable):
            runtime.append(_node(0))

    def test_external_replay_integrity_and_append_are_wired(self):
        first = _node(0)
        adapter = _ExternalAdapter([first])
        dag = []
        runtime = LedgerRuntime(
            dag,
            threading.RLock(),
            _digest,
            mode=DURABLE_EXTERNAL,
            adapter=adapter,
        )

        state = runtime.startup()
        second = _node(1, first["digest"])
        runtime.append(second)

        self.assertTrue(state["production_ready"])
        self.assertEqual(state["replay"], {"state": "VERIFIED", "nodes": 1})
        self.assertEqual([node["digest"] for node in runtime.snapshot()], [first["digest"], second["digest"]])
        self.assertEqual(adapter.nodes[-1]["digest"], second["digest"])

    def test_tampered_external_replay_is_rejected(self):
        bad = _node(0)
        bad["digest"] = "0" * 64
        runtime = LedgerRuntime(
            [],
            threading.RLock(),
            _digest,
            mode=DURABLE_EXTERNAL,
            adapter=_ExternalAdapter([bad]),
        )

        state = runtime.startup()
        self.assertFalse(state["ready"])
        self.assertEqual(state["integrity"]["state"], "FAILED")

    def test_failed_external_append_requires_replay_and_never_updates_projection(self):
        runtime = LedgerRuntime(
            [],
            threading.RLock(),
            _digest,
            mode=DURABLE_EXTERNAL,
            adapter=_ExternalAdapter(append_fails=True),
        )
        self.assertTrue(runtime.startup()["ready"])

        with self.assertRaises(LedgerUnavailable):
            runtime.append(_node(0))

        self.assertEqual(runtime.snapshot(), [])
        self.assertFalse(runtime.readiness()["ready"])

    def test_transient_startup_failure_recovers_on_readiness_without_restart(self):
        class RecoveringAdapter:
            def __init__(self):
                self.startup_calls = 0

            def startup(self):
                self.startup_calls += 1
                if self.startup_calls == 1:
                    raise RuntimeError("temporary outage")

            def replay(self):
                return []

            def append(self, _node):
                return None

            def verify_integrity(self, _nodes):
                return {"verified": True}

            def readiness(self):
                return {"ready": True}

        adapter = RecoveringAdapter()
        runtime = LedgerRuntime(
            [],
            threading.RLock(),
            _digest,
            mode=DURABLE_EXTERNAL,
            adapter=adapter,
            recovery_interval_s=0,
        )

        failed = runtime.startup()
        recovered = runtime.readiness()

        self.assertFalse(failed["ready"])
        self.assertTrue(recovered["ready"])
        self.assertTrue(recovered["production_ready"])
        self.assertEqual(recovered["replay"], {"state": "VERIFIED", "nodes": 0})
        self.assertEqual(recovered["recovery"]["attempts"], 2)
        self.assertEqual(adapter.startup_calls, 2)

    def test_failed_external_append_recovers_by_replay_without_restart(self):
        adapter = _ExternalAdapter(append_fails=True)
        runtime = LedgerRuntime(
            [],
            threading.RLock(),
            _digest,
            mode=DURABLE_EXTERNAL,
            adapter=adapter,
            recovery_interval_s=0,
        )
        self.assertTrue(runtime.startup()["ready"])

        with self.assertRaises(LedgerUnavailable):
            runtime.append(_node(0))

        adapter.append_fails = False
        self.assertTrue(runtime.readiness()["ready"])
        runtime.append(_node(0))
        self.assertEqual(len(runtime.snapshot()), 1)
        self.assertEqual(len(adapter.nodes), 1)

    def test_export_refuses_unready_external_ledger(self):
        body, status = build_receipt_export(
            [],
            ledger={
                "durability_state": DURABLE_EXTERNAL,
                "ready": False,
                "production_ready": False,
            },
        )

        self.assertEqual(status, 503)
        self.assertEqual(body["export_state"], "LEDGER_UNAVAILABLE")
        self.assertFalse(body["receipt_available"])
        self.assertEqual(body["ledger_durability"], DURABLE_EXTERNAL)


if __name__ == "__main__":
    unittest.main()
