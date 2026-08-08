"""Fail-closed receipt-ledger runtime contract for Killinchu.

The default mode is explicitly EPHEMERAL. Setting
``KILLINCHU_LEDGER_MODE=DURABLE_EXTERNAL`` selects an external adapter through
the non-secret ``KILLINCHU_LEDGER_ADAPTER=module:factory`` configuration. This
module deliberately ships no external-store implementation and accepts no
credentials. A durable claim is emitted only after adapter startup, replay,
local hash-chain verification, and adapter integrity verification all succeed.

An external adapter must implement:

* ``startup()``
* ``replay() -> Sequence[Mapping]``
* ``append(node)`` (idempotent by node digest)
* ``verify_integrity(nodes) -> Mapping`` with ``verified is True``
* ``readiness() -> Mapping`` with ``ready is True``
"""

from __future__ import annotations

import importlib
import os
import time
from copy import deepcopy
from threading import RLock
from typing import Any, Callable, Mapping, MutableSequence, Sequence


EPHEMERAL = "EPHEMERAL"
DURABLE_EXTERNAL = "DURABLE_EXTERNAL"
READINESS_SCHEMA = "szl.killinchu.ledger-readiness/v1"


class LedgerUnavailable(RuntimeError):
    """Raised when a receipt write cannot satisfy the selected durability mode."""


class LedgerRuntime:
    """Coordinates an in-process projection with an optional external ledger."""

    def __init__(
        self,
        dag: MutableSequence[dict[str, Any]],
        lock: RLock,
        digest_node: Callable[[dict[str, Any], list[str]], str],
        *,
        mode: str = EPHEMERAL,
        adapter: Any = None,
        configuration_error: str | None = None,
        recovery_interval_s: float = 5.0,
    ) -> None:
        self._dag = dag
        self._lock = lock
        self._digest_node = digest_node
        self._mode = mode
        self._adapter = adapter
        self._configuration_error = configuration_error
        self._recovery_interval_s = max(0.0, float(recovery_interval_s))
        self._next_recovery_at = 0.0
        self._recovery_attempts = 0
        self._ready = False
        self._startup_state = "NOT_STARTED"
        self._reason = "startup has not run"
        self._integrity: dict[str, Any] = {
            "state": "NOT_VERIFIED",
            "verified": False,
            "nodes": 0,
        }
        self._replay: dict[str, Any] = {
            "state": "NOT_STARTED",
            "nodes": 0,
        }

    @classmethod
    def from_environment(
        cls,
        dag: MutableSequence[dict[str, Any]],
        lock: RLock,
        digest_node: Callable[[dict[str, Any], list[str]], str],
        *,
        environ: Mapping[str, str] | None = None,
    ) -> "LedgerRuntime":
        env = os.environ if environ is None else environ
        mode = str(env.get("KILLINCHU_LEDGER_MODE", EPHEMERAL)).strip().upper()
        if mode == EPHEMERAL:
            return cls(dag, lock, digest_node, mode=EPHEMERAL)
        if mode != DURABLE_EXTERNAL:
            return cls(
                dag,
                lock,
                digest_node,
                mode=mode or "INVALID",
                configuration_error="unsupported KILLINCHU_LEDGER_MODE",
            )

        adapter_path = str(env.get("KILLINCHU_LEDGER_ADAPTER", "")).strip()
        if not adapter_path or ":" not in adapter_path:
            return cls(
                dag,
                lock,
                digest_node,
                mode=DURABLE_EXTERNAL,
                configuration_error=(
                    "DURABLE_EXTERNAL requires KILLINCHU_LEDGER_ADAPTER=module:factory"
                ),
            )

        try:
            module_name, factory_name = adapter_path.split(":", 1)
            factory = getattr(importlib.import_module(module_name), factory_name)
            adapter = factory()
        except Exception:
            return cls(
                dag,
                lock,
                digest_node,
                mode=DURABLE_EXTERNAL,
                configuration_error="external ledger adapter could not be loaded",
            )
        return cls(dag, lock, digest_node, mode=DURABLE_EXTERNAL, adapter=adapter)

    def _local_integrity(self, nodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        previous_digest: str | None = None
        for position, raw_node in enumerate(nodes):
            node = dict(raw_node)
            receipt = node.get("receipt")
            parents = node.get("parents")
            if not isinstance(receipt, Mapping) or not isinstance(parents, list):
                return self._integrity_failure(position, "node shape is invalid")
            if node.get("index") != position:
                return self._integrity_failure(position, "node index is not monotonic")
            expected_parents = [] if previous_digest is None else [previous_digest]
            if parents != expected_parents:
                return self._integrity_failure(position, "parent chain is discontinuous")
            expected_digest = self._digest_node(dict(receipt), list(parents))
            if node.get("digest") != expected_digest:
                return self._integrity_failure(position, "node digest does not match receipt")
            previous_digest = expected_digest
        return {
            "state": "VERIFIED",
            "verified": True,
            "nodes": len(nodes),
            "root": previous_digest,
        }

    @staticmethod
    def _integrity_failure(position: int, reason: str) -> dict[str, Any]:
        return {
            "state": "FAILED",
            "verified": False,
            "nodes": position,
            "failed_index": position,
            "reason": reason,
        }

    @staticmethod
    def _adapter_contract(adapter: Any) -> bool:
        return all(
            callable(getattr(adapter, method, None))
            for method in ("startup", "replay", "append", "verify_integrity", "readiness")
        )

    def _fail(self, reason: str) -> None:
        self._ready = False
        self._startup_state = "FAILED"
        self._reason = reason
        if self._mode == DURABLE_EXTERNAL:
            self._next_recovery_at = max(
                self._next_recovery_at,
                time.monotonic() + self._recovery_interval_s,
            )

    def startup(self) -> dict[str, Any]:
        """Initialize the selected mode and replay external state before readiness."""

        with self._lock:
            if self._configuration_error:
                self._fail(self._configuration_error)
                return self.readiness(recover=False)
            if self._mode == EPHEMERAL:
                self._integrity = self._local_integrity(self._dag)
                self._ready = self._integrity["verified"] is True
                self._startup_state = "READY" if self._ready else "FAILED"
                self._reason = (
                    "ephemeral ledger is available for this process only"
                    if self._ready
                    else "ephemeral ledger integrity verification failed"
                )
                self._replay = {"state": "NOT_APPLICABLE", "nodes": len(self._dag)}
                return self.readiness(recover=False)

            if self._mode != DURABLE_EXTERNAL or not self._adapter_contract(self._adapter):
                self._fail("external ledger adapter contract is unavailable")
                return self.readiness(recover=False)

            self._recovery_attempts += 1
            self._next_recovery_at = time.monotonic() + self._recovery_interval_s
            try:
                self._adapter.startup()
                replayed = [deepcopy(dict(node)) for node in self._adapter.replay()]
                local_report = self._local_integrity(replayed)
                if local_report.get("verified") is not True:
                    self._integrity = local_report
                    self._fail("external ledger replay failed local integrity verification")
                    return self.readiness(recover=False)
                external_report = dict(self._adapter.verify_integrity(replayed))
                if external_report.get("verified") is not True:
                    self._integrity = {
                        "state": "FAILED",
                        "verified": False,
                        "nodes": len(replayed),
                        "reason": "external integrity hook did not verify replay",
                    }
                    self._fail("external ledger integrity verification failed")
                    return self.readiness(recover=False)
                self._dag[:] = replayed
                self._integrity = local_report
                self._replay = {"state": "VERIFIED", "nodes": len(replayed)}
                self._ready = True
                self._startup_state = "READY"
                self._reason = "external ledger replay and integrity verified"
                self._next_recovery_at = 0.0
            except Exception:
                self._fail("external ledger startup or replay failed")
            return self.readiness(recover=False)

    def readiness(self, *, recover: bool = True) -> dict[str, Any]:
        """Return a secret-free, fail-closed readiness and truth envelope."""

        with self._lock:
            now = time.monotonic()
            can_recover = (
                recover
                and self._mode == DURABLE_EXTERNAL
                and not self._ready
                and not self._configuration_error
                and self._adapter_contract(self._adapter)
                and now >= self._next_recovery_at
            )
            if can_recover:
                self.startup()
                now = time.monotonic()

            adapter_ready = True
            adapter_state = "NOT_APPLICABLE"
            if self._mode == DURABLE_EXTERNAL and self._ready:
                try:
                    report = dict(self._adapter.readiness())
                    adapter_ready = report.get("ready") is True
                    adapter_state = "READY" if adapter_ready else "UNAVAILABLE"
                except Exception:
                    adapter_ready = False
                    adapter_state = "UNAVAILABLE"
            elif self._mode == DURABLE_EXTERNAL:
                adapter_ready = False
                adapter_state = "UNAVAILABLE"

            ready = self._ready and adapter_ready
            durability_state = (
                self._mode if self._mode in {EPHEMERAL, DURABLE_EXTERNAL} else "UNAVAILABLE"
            )
            return {
                "schema": READINESS_SCHEMA,
                "durability_state": durability_state,
                "requested_mode": self._mode,
                "ready": ready,
                "production_ready": ready and durability_state == DURABLE_EXTERNAL,
                "startup_state": self._startup_state,
                "adapter_configured": self._adapter is not None,
                "adapter_state": adapter_state,
                "integrity": deepcopy(self._integrity),
                "replay": deepcopy(self._replay),
                "recovery": {
                    "attempts": self._recovery_attempts,
                    "retry_after_s": round(
                        max(0.0, self._next_recovery_at - now), 3
                    ) if self._mode == DURABLE_EXTERNAL and not ready else 0.0,
                },
                "reason": self._reason if ready or self._reason else "ledger unavailable",
            }

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(list(self._dag))

    def append(self, node: Mapping[str, Any]) -> None:
        """Append through the selected store before exposing the in-memory projection."""

        with self._lock:
            if self.readiness().get("ready") is not True:
                raise LedgerUnavailable("receipt ledger is not ready")
            candidate = [*self._dag, deepcopy(dict(node))]
            local_report = self._local_integrity(candidate)
            if local_report.get("verified") is not True:
                self._integrity = local_report
                self._fail("candidate receipt failed local integrity verification")
                raise LedgerUnavailable("receipt failed ledger integrity verification")

            if self._mode == DURABLE_EXTERNAL:
                try:
                    self._adapter.append(deepcopy(dict(node)))
                    external_report = dict(self._adapter.verify_integrity(candidate))
                except Exception as exc:
                    self._fail("external ledger append failed; replay is required")
                    raise LedgerUnavailable("external ledger append failed") from exc
                if external_report.get("verified") is not True:
                    self._fail("external ledger append integrity failed; replay is required")
                    raise LedgerUnavailable("external ledger integrity hook rejected append")

            self._dag.append(deepcopy(dict(node)))
            self._integrity = local_report


__all__ = [
    "DURABLE_EXTERNAL",
    "EPHEMERAL",
    "LedgerRuntime",
    "LedgerUnavailable",
    "READINESS_SCHEMA",
]
