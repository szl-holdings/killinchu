"""Defend audit chain + incident receipts — killinchu #399 §4 per spec #401.

Append-only hash-chained audit log: every event carries the SHA-256 of the
canonical prior event; any insertion, deletion, or reorder breaks the chain
and `verify` names the first broken link. Incident receipts bundle the
trigger event hash, environment snapshot, action timeline, blast-radius
estimate, timeline hash, and backup dump SHA into one artifact whose own
hash is itself appended to the chain (BACKUP_COMMITTED, RECEIPT_SEALED).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


@dataclass
class AuditEvent:
    event_id: str
    event_type: str
    payload: dict
    prior_hash: str
    event_hash: str
    at_epoch: float


class AuditChain:
    """Append-only; there is deliberately no update or delete method."""

    def __init__(self):
        self._events: list[AuditEvent] = []

    def append(self, event_type: str, payload: dict,
               now: float | None = None) -> AuditEvent:
        now = time.time() if now is None else now
        prior = self._events[-1].event_hash if self._events else GENESIS
        body = {"event_id": str(uuid.uuid4()), "event_type": event_type,
                "payload": payload, "prior_hash": prior, "at_epoch": now}
        event = AuditEvent(event_hash=_hash(body), **body)
        self._events.append(event)
        return event

    def verify(self) -> tuple[bool, str | None]:
        prior = GENESIS
        for event in self._events:
            if event.prior_hash != prior:
                return False, event.event_id
            body = {"event_id": event.event_id, "event_type": event.event_type,
                    "payload": event.payload, "prior_hash": event.prior_hash,
                    "at_epoch": event.at_epoch}
            if _hash(body) != event.event_hash:
                return False, event.event_id
            prior = event.event_hash
        return True, None

    @property
    def head(self) -> str:
        return self._events[-1].event_hash if self._events else GENESIS

    def __len__(self) -> int:
        return len(self._events)


@dataclass
class IncidentReceipt:
    receipt_id: str
    trigger_event_hash: str
    environment_snapshot: dict
    timeline: list[dict]
    blast_radius: dict
    timeline_hash: str
    backup_dump_sha256: str
    receipt_hash: str
    sealed_at_epoch: float


def seal_incident_receipt(chain: AuditChain, *, trigger_event_hash: str,
                          environment_snapshot: dict, timeline: list[dict],
                          blast_radius: dict, backup_dump_sha256: str,
                          now: float | None = None) -> IncidentReceipt:
    """Seal an incident receipt and anchor it in the audit chain."""
    now = time.time() if now is None else now
    timeline_hash = _hash({"timeline": timeline})
    body = {"receipt_id": str(uuid.uuid4()),
            "trigger_event_hash": trigger_event_hash,
            "environment_snapshot": environment_snapshot,
            "timeline_hash": timeline_hash,
            "blast_radius": blast_radius,
            "backup_dump_sha256": backup_dump_sha256,
            "sealed_at_epoch": now}
    receipt = IncidentReceipt(timeline=timeline, receipt_hash=_hash(body), **body)
    chain.append("BACKUP_COMMITTED", {"dump_sha256": backup_dump_sha256}, now=now)
    chain.append("RECEIPT_SEALED", {"receipt_id": receipt.receipt_id,
                                    "receipt_hash": receipt.receipt_hash,
                                    "trigger_event_hash": trigger_event_hash},
                 now=now)
    return receipt
