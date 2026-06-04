# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu.khipu — REAL append-only hash-chained Khipu DAG of signed receipts.
#
# Each node binds: prev_hash → this verdict's DSSE envelope → node_hash.
# This is a genuine Merkle-style chain (sha256), not a mock.  In-memory by
# default (resets on process restart — stated honestly); optionally persisted to
# a JSONL file when KILLINCHU_KHIPU_PATH is set, so receipts survive restarts.
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

GENESIS = "0" * 64


def _hash_node(prev_hash: str, envelope: dict[str, Any], ts: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode())
    h.update(ts.encode())
    return h.hexdigest()


class KhipuDAG:
    """Append-only, hash-chained receipt log. Thread-safe."""

    def __init__(self, persist_path: str | None = None):
        self._lock = threading.Lock()
        self._nodes: list[dict[str, Any]] = []
        self._persist = persist_path or os.environ.get("KILLINCHU_KHIPU_PATH")
        if self._persist and os.path.exists(self._persist):
            self._load()

    def _load(self) -> None:
        with open(self._persist, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._nodes.append(json.loads(line))

    @property
    def root(self) -> str:
        """Return the current DAG root hash.

        Returns:
            The ``node_hash`` of the most recently appended node, or the
            ``GENESIS`` sentinel when the chain is empty.
        """
        return self._nodes[-1]["node_hash"] if self._nodes else GENESIS

    def __len__(self) -> int:
        return len(self._nodes)

    def append(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Append a DSSE envelope as a new hash-linked node.

        Args:
            envelope: The DSSE verdict envelope to anchor.

        Returns:
            The newly created node dict (index, prev_hash, node_hash, ts,
            envelope). Thread-safe and, if configured, persisted as JSONL.
        """
        with self._lock:
            prev = self.root
            ts = datetime.now(timezone.utc).isoformat()
            node_hash = _hash_node(prev, envelope, ts)
            node = {
                "index": len(self._nodes),
                "prev_hash": prev,
                "node_hash": node_hash,
                "ts": ts,
                "envelope": envelope,
            }
            self._nodes.append(node)
            if self._persist:
                with open(self._persist, "a", encoding="utf-8") as f:
                    f.write(json.dumps(node, separators=(",", ":")) + "\n")
            return node

    def verify_chain(self) -> dict[str, Any]:
        """Recompute every node hash to confirm the chain is intact."""
        prev = GENESIS
        for i, node in enumerate(self._nodes):
            expect = _hash_node(prev, node["envelope"], node["ts"])
            if node["prev_hash"] != prev or node["node_hash"] != expect:
                return {"intact": False, "broken_at": i}
            prev = node["node_hash"]
        return {"intact": True, "length": len(self._nodes), "root": self.root}

    def nodes(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all chain nodes in append order.

        Returns:
            A new list of node dicts; mutating it does not affect the DAG.
        """
        return list(self._nodes)
