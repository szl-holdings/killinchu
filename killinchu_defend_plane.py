# SPDX-License-Identifier: Apache-2.0
"""Killinchu Defend plane: source-bound, defensive-only incident workflow.

This module closes the public-product boundary recorded in
``docs/KILLINCHU-CYBER-RESILIENCE-CONSOLIDATION.md``.  Killinchu is the sole
public runtime.  Aegis remains a portfolio name and Sentra remains the internal
name of the defensive-control-plane capability.

The implementation ports the externally useful contract of
``szl-holdings/szl-defensive-control-plane`` at the exact source revision below:

* bounded event ingestion with replay/collision handling;
* deterministic detections and incident cases;
* immutable, data-only containment proposals;
* independent human approval;
* simulation-only rehearsal with an explicit rollback plan;
* append-only hash-chained receipts, optionally HMAC signed by a write-only
  Space secret; and
* independent receipt verification.

No route accepts shell commands, scripts, arbitrary URLs, credentials, exploit
payloads or an instruction to operate against a third party.  No public route
calls an external effector.  ``APPROVED`` therefore means approved for a
bounded rehearsal, never approval for an unattended real-world action.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

PRODUCT = "Killinchu"
PLANE = "Defend"
CONTRACT_VERSION = "1.0.0"
SOURCE_REPOSITORY = "szl-holdings/szl-defensive-control-plane"
SOURCE_REVISION = "e3483562a440e72cfbde4c25cffef339545778d3"
SOURCE_PACKAGE_VERSION = "0.4.0"
ZERO_HASH = "0" * 64
MAX_REQUEST_BYTES = 64 * 1024
MAX_CASES = 100
SESSION_RE = re.compile(r"^[A-Za-z0-9._~-]{32,128}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
RECEIPT_ID_RE = re.compile(r"^rcpt_[0-9a-f]{32}$")
CASE_ID_RE = re.compile(r"^case_[0-9a-f]{32}$")
PROPOSAL_ID_RE = re.compile(r"^prop_[0-9a-f]{32}$")

EVENT_TYPES = frozenset(
    {
        "identity.privilege_change",
        "asset.public_exposure",
        "vulnerability.known_exploited",
        "agent.policy_violation",
        "network.anomalous_egress",
        "custom.defensive_signal",
    }
)
SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
ALLOWED_ACTIONS = frozenset(
    {"monitor", "open_ticket", "disable_session", "isolate_asset"}
)
ALLOWED_FIELDS = frozenset(
    {
        "source_event_id",
        "event_type",
        "asset_ref",
        "actor_id",
        "severity",
        "summary",
        "requested_by",
        "indicators",
    }
)
ALLOWED_INDICATORS = frozenset(
    {
        "source_authenticated",
        "asset_owner_known",
        "rollback_available",
        "known_exploited",
        "public_exposure",
        "privilege_escalation",
        "agent_tool_policy_violation",
        "destructive_capability",
        "evidence_count",
    }
)
SEVERITY_BASE = {"LOW": 0.20, "MEDIUM": 0.45, "HIGH": 0.72, "CRITICAL": 0.90}

_STORES: dict[str, "DefendStore"] = {}
_STORES_LOCK = threading.RLock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime | None = None) -> str:
    return (value or _utcnow()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, material).hex}"


def _bounded_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if IDENTIFIER_RE.fullmatch(normalized) is None:
        raise ValueError(f"{field} is not a valid bounded identifier")
    return normalized


def _bounded_text(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field} must contain 1-{maximum} characters")
    return normalized


def _session_scope(request: Request) -> str:
    token = (request.headers.get("X-SZL-Session") or "").strip()
    if SESSION_RE.fullmatch(token) is None:
        raise ValueError(
            "X-SZL-Session must be a caller-held 32-128 character token using "
            "A-Z, a-z, 0-9, '.', '_', '~' or '-'"
        )
    return _sha256(token.encode("utf-8"))


def _signing_key() -> tuple[bytes | None, str]:
    for name in ("KILLINCHU_DEFEND_SIGNING_KEY", "SENTRA_SIGNING_KEY"):
        value = os.environ.get(name, "")
        if len(value.encode("utf-8")) >= 16:
            return value.encode("utf-8"), name
    return None, "UNAVAILABLE"


def _sign(chain_hash: str) -> tuple[str, str]:
    key, source = _signing_key()
    if key is None:
        return "UNSIGNED_RUNTIME_SECRET_UNAVAILABLE", ""
    return f"HMAC_SHA256:{source}", hmac.new(key, chain_hash.encode("ascii"), hashlib.sha256).hexdigest()


def _verify_signature(chain_hash: str, signature_state: str, signature: str) -> bool | None:
    if not signature_state.startswith("HMAC_SHA256:"):
        return None
    key, source = _signing_key()
    if key is None or signature_state != f"HMAC_SHA256:{source}":
        return False
    expected = hmac.new(key, chain_hash.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _lambda_score(axes: dict[str, float]) -> float:
    values = [max(0.0, min(1.0, float(item))) for item in axes.values()]
    if not values or any(item == 0.0 for item in values):
        return 0.0
    return round(math.exp(sum(math.log(item) for item in values) / len(values)), 6)


def _state_path() -> str:
    return os.environ.get("KILLINCHU_DEFEND_STATE_PATH", "/tmp/killinchu-defend.sqlite3")


class DefendStore:
    """Single-writer SQLite store with append-only receipt evidence."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._lock:
            connection = self.connect()
            try:
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        source_event_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        asset_ref TEXT NOT NULL,
                        actor_id TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        normalized_json TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(scope, source_event_id)
                    );
                    CREATE TABLE IF NOT EXISTS cases (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        event_id TEXT NOT NULL REFERENCES events(id),
                        title TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS proposals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        case_id TEXT NOT NULL REFERENCES cases(id),
                        action_type TEXT NOT NULL,
                        target_ref TEXT NOT NULL,
                        parameters_json TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        policy_score REAL NOT NULL,
                        policy_axes_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        proposal_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS approvals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(id),
                        approver TEXT NOT NULL,
                        approval_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS rehearsals (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(id),
                        result_json TEXT NOT NULL,
                        result_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS receipts (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        object_id TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        chain_hash TEXT NOT NULL UNIQUE,
                        signature_state TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TRIGGER IF NOT EXISTS defend_receipt_no_update
                    BEFORE UPDATE ON receipts BEGIN
                        SELECT RAISE(ABORT, 'defend receipts are append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS defend_receipt_no_delete
                    BEFORE DELETE ON receipts BEGIN
                        SELECT RAISE(ABORT, 'defend receipts are append-only');
                    END;
                    COMMIT;
                    """
                )
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def status(self) -> dict[str, Any]:
        try:
            connection = self.connect()
            try:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
                counts = {
                    table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in ("events", "cases", "proposals", "approvals", "rehearsals", "receipts")
                }
            finally:
                connection.close()
            return {
                "state": "WRITABLE" if integrity == "ok" else "FAILED_CLOSED",
                "integrity": integrity,
                "backend": "SQLITE_SINGLE_WRITER",
                "path_disclosed": False,
                "counts": counts,
            }
        except Exception as exc:
            return {
                "state": "FAILED_CLOSED",
                "integrity": "UNAVAILABLE",
                "backend": "SQLITE_SINGLE_WRITER",
                "path_disclosed": False,
                "error": type(exc).__name__,
                "counts": {},
            }

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def _receipt(
        self,
        connection: sqlite3.Connection,
        *,
        scope: str,
        kind: str,
        object_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        previous = connection.execute(
            "SELECT chain_hash FROM receipts WHERE scope=? ORDER BY rowid DESC LIMIT 1",
            (scope,),
        ).fetchone()
        previous_hash = str(previous["chain_hash"]) if previous else ZERO_HASH
        payload_json = _canonical(payload).decode("utf-8")
        payload_hash = _sha256(payload_json.encode("utf-8"))
        basis = {
            "scope": scope,
            "kind": kind,
            "object_id": object_id,
            "previous_hash": previous_hash,
            "payload_hash": payload_hash,
        }
        chain_hash = _sha256(_canonical(basis))
        signature_state, signature = _sign(chain_hash)
        receipt_id = _stable_id("rcpt", scope, chain_hash)
        created_at = _rfc3339()
        connection.execute(
            """
            INSERT INTO receipts(
                id,scope,kind,object_id,previous_hash,payload_json,payload_hash,
                chain_hash,signature_state,signature,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                receipt_id,
                scope,
                kind,
                object_id,
                previous_hash,
                payload_json,
                payload_hash,
                chain_hash,
                signature_state,
                signature,
                created_at,
            ),
        )
        return {
            "id": receipt_id,
            "kind": kind,
            "object_id": object_id,
            "previous_hash": previous_hash,
            "payload_hash": payload_hash,
            "chain_hash": chain_hash,
            "signature_state": signature_state,
            "signature_present": bool(signature),
            "created_at": created_at,
        }

    def analyze(self, scope: str, event: dict[str, Any]) -> dict[str, Any]:
        normalized_json = _canonical(event).decode("utf-8")
        payload_hash = _sha256(normalized_json.encode("utf-8"))
        source_event_id = str(event["source_event_id"])
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM events WHERE scope=? AND source_event_id=?",
                    (scope, source_event_id),
                ).fetchone()
                if existing:
                    if str(existing["payload_hash"]) != payload_hash:
                        receipt = self._receipt(
                            connection,
                            scope=scope,
                            kind="EVENT_ID_COLLISION",
                            object_id=str(existing["id"]),
                            payload={
                                "source_event_id": source_event_id,
                                "stored_payload_hash": str(existing["payload_hash"]),
                                "presented_payload_hash": payload_hash,
                                "decision": "QUARANTINE",
                            },
                        )
                        connection.commit()
                        return {"collision": True, "receipt": receipt}
                    case = connection.execute(
                        "SELECT * FROM cases WHERE scope=? AND event_id=?",
                        (scope, str(existing["id"])),
                    ).fetchone()
                    proposal = connection.execute(
                        "SELECT * FROM proposals WHERE scope=? AND case_id=?",
                        (scope, str(case["id"])),
                    ).fetchone()
                    connection.commit()
                    return {
                        "replayed": True,
                        "event": self._event_public(existing),
                        "case": self._case_public(case),
                        "proposal": self._proposal_public(proposal),
                    }

                risk, axes, score, action = _evaluate(event)
                event_id = _stable_id("evt", scope, source_event_id, payload_hash)
                case_id = _stable_id("case", scope, event_id)
                proposal_id = _stable_id("prop", scope, case_id, action)
                now = _utcnow()
                created_at = _rfc3339(now)
                expires_at = _rfc3339(now + timedelta(minutes=30))
                proposal_state = "PROPOSED" if score >= 0.75 and axes["evidence"] >= 0.50 else "ABSTAIN"
                parameters = {
                    "mode": "SIMULATION_ONLY",
                    "risk_score": risk,
                    "rollback_required": True,
                    "external_effectors": False,
                }
                proposal_basis = {
                    "case_id": case_id,
                    "action_type": action,
                    "target_ref": event["asset_ref"],
                    "parameters": parameters,
                    "requested_by": event["requested_by"],
                    "policy_score": score,
                    "policy_axes": axes,
                    "expires_at": expires_at,
                }
                proposal_hash = _sha256(_canonical(proposal_basis))
                connection.execute(
                    "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event_id,
                        scope,
                        source_event_id,
                        event["event_type"],
                        event["asset_ref"],
                        event["actor_id"],
                        event["severity"],
                        event["summary"],
                        normalized_json,
                        payload_hash,
                        created_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",
                    (
                        case_id,
                        scope,
                        event_id,
                        f"{event['event_type']} on {event['asset_ref']}",
                        event["severity"],
                        "OPEN" if proposal_state == "PROPOSED" else "EVIDENCE_HOLD",
                        created_at,
                        created_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        proposal_id,
                        scope,
                        case_id,
                        action,
                        event["asset_ref"],
                        _canonical(parameters).decode("utf-8"),
                        event["requested_by"],
                        score,
                        _canonical(axes).decode("utf-8"),
                        proposal_state,
                        proposal_hash,
                        created_at,
                        expires_at,
                    ),
                )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="DETECTION_AND_PROPOSAL",
                    object_id=proposal_id,
                    payload={
                        "event_id": event_id,
                        "case_id": case_id,
                        "proposal_id": proposal_id,
                        "event_payload_hash": payload_hash,
                        "proposal_hash": proposal_hash,
                        "risk_score": risk,
                        "policy_axes": axes,
                        "policy_score": score,
                        "decision": proposal_state,
                        "action_type": action,
                    },
                )
                connection.commit()
                return {
                    "replayed": False,
                    "event": {
                        "id": event_id,
                        "source_event_id": source_event_id,
                        "event_type": event["event_type"],
                        "asset_ref": event["asset_ref"],
                        "severity": event["severity"],
                        "payload_hash": payload_hash,
                        "created_at": created_at,
                    },
                    "case": {
                        "id": case_id,
                        "title": f"{event['event_type']} on {event['asset_ref']}",
                        "severity": event["severity"],
                        "state": "OPEN" if proposal_state == "PROPOSED" else "EVIDENCE_HOLD",
                        "created_at": created_at,
                    },
                    "proposal": {
                        "id": proposal_id,
                        "action_type": action,
                        "target_ref": event["asset_ref"],
                        "requested_by": event["requested_by"],
                        "policy_score": score,
                        "policy_axes": axes,
                        "state": proposal_state,
                        "proposal_hash": proposal_hash,
                        "expires_at": expires_at,
                        "can_execute": False,
                    },
                    "receipt": receipt,
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def approve(self, scope: str, proposal_id: str, approver: str) -> dict[str, Any]:
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                proposal = connection.execute(
                    "SELECT * FROM proposals WHERE scope=? AND id=?",
                    (scope, proposal_id),
                ).fetchone()
                if proposal is None:
                    raise LookupError("proposal not found in caller session")
                if str(proposal["state"]) != "PROPOSED":
                    raise RuntimeError(f"proposal is not approvable: {proposal['state']}")
                if approver == str(proposal["requested_by"]):
                    raise PermissionError("approver must be independent from requester")
                expiry = datetime.fromisoformat(str(proposal["expires_at"]).replace("Z", "+00:00"))
                if expiry <= _utcnow():
                    raise RuntimeError("proposal has expired")
                approval_basis = {
                    "proposal_id": proposal_id,
                    "proposal_hash": str(proposal["proposal_hash"]),
                    "approver": approver,
                    "scope": scope,
                    "authority": "HUMAN_REHEARSAL_APPROVAL",
                }
                approval_hash = _sha256(_canonical(approval_basis))
                approval_id = _stable_id("appr", scope, proposal_id, approver)
                created_at = _rfc3339()
                connection.execute(
                    "INSERT INTO approvals VALUES(?,?,?,?,?,?)",
                    (approval_id, scope, proposal_id, approver, approval_hash, created_at),
                )
                connection.execute(
                    "UPDATE proposals SET state='APPROVED_FOR_REHEARSAL' WHERE id=? AND scope=?",
                    (proposal_id, scope),
                )
                connection.execute(
                    "UPDATE cases SET state='HUMAN_APPROVED',updated_at=? WHERE id=? AND scope=?",
                    (created_at, str(proposal["case_id"]), scope),
                )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="HUMAN_APPROVAL",
                    object_id=approval_id,
                    payload={
                        "approval_id": approval_id,
                        "proposal_id": proposal_id,
                        "proposal_hash": str(proposal["proposal_hash"]),
                        "approval_hash": approval_hash,
                        "approver": approver,
                        "authority": "REHEARSAL_ONLY",
                    },
                )
                connection.commit()
                return {
                    "approval": {
                        "id": approval_id,
                        "proposal_id": proposal_id,
                        "approver": approver,
                        "approval_hash": approval_hash,
                        "authority": "REHEARSAL_ONLY",
                        "created_at": created_at,
                    },
                    "proposal_state": "APPROVED_FOR_REHEARSAL",
                    "can_execute_external_action": False,
                    "receipt": receipt,
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def rehearse(self, scope: str, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                proposal = connection.execute(
                    "SELECT * FROM proposals WHERE scope=? AND id=?",
                    (scope, proposal_id),
                ).fetchone()
                if proposal is None:
                    raise LookupError("proposal not found in caller session")
                if str(proposal["state"]) != "APPROVED_FOR_REHEARSAL":
                    raise RuntimeError(f"proposal is not ready for rehearsal: {proposal['state']}")
                action = str(proposal["action_type"])
                target = str(proposal["target_ref"])
                result = {
                    "mode": "DETERMINISTIC_REHEARSAL",
                    "action_type": action,
                    "target_ref": target,
                    "expected_effect": _expected_effect(action),
                    "rollback_plan": _rollback_plan(action, target),
                    "external_calls": 0,
                    "external_effectors": False,
                    "truth_label": "MODELED",
                }
                result_hash = _sha256(_canonical(result))
                rehearsal_id = _stable_id("sim", scope, proposal_id, result_hash)
                created_at = _rfc3339()
                connection.execute(
                    "INSERT INTO rehearsals VALUES(?,?,?,?,?,?)",
                    (
                        rehearsal_id,
                        scope,
                        proposal_id,
                        _canonical(result).decode("utf-8"),
                        result_hash,
                        created_at,
                    ),
                )
                connection.execute(
                    "UPDATE proposals SET state='REHEARSED' WHERE id=? AND scope=?",
                    (proposal_id, scope),
                )
                connection.execute(
                    "UPDATE cases SET state='REHEARSED_AND_VERIFIED',updated_at=? WHERE id=? AND scope=?",
                    (created_at, str(proposal["case_id"]), scope),
                )
                receipt = self._receipt(
                    connection,
                    scope=scope,
                    kind="REHEARSAL_RESULT",
                    object_id=rehearsal_id,
                    payload={
                        "rehearsal_id": rehearsal_id,
                        "proposal_id": proposal_id,
                        "proposal_hash": str(proposal["proposal_hash"]),
                        "result_hash": result_hash,
                        "result": result,
                    },
                )
                connection.commit()
                return {
                    "rehearsal": {
                        "id": rehearsal_id,
                        "proposal_id": proposal_id,
                        "result_hash": result_hash,
                        "created_at": created_at,
                        **result,
                    },
                    "proposal_state": "REHEARSED",
                    "receipt": receipt,
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def verify(self, scope: str, receipt_id: str) -> dict[str, Any]:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM receipts WHERE scope=? AND id=?",
                (scope, receipt_id),
            ).fetchone()
            if row is None:
                raise LookupError("receipt not found in caller session")
            payload_hash = _sha256(str(row["payload_json"]).encode("utf-8"))
            basis = {
                "scope": scope,
                "kind": str(row["kind"]),
                "object_id": str(row["object_id"]),
                "previous_hash": str(row["previous_hash"]),
                "payload_hash": payload_hash,
            }
            chain_hash = _sha256(_canonical(basis))
            predecessor_ok = str(row["previous_hash"]) == ZERO_HASH or connection.execute(
                "SELECT 1 FROM receipts WHERE scope=? AND chain_hash=?",
                (scope, str(row["previous_hash"])),
            ).fetchone() is not None
            hash_ok = (
                payload_hash == str(row["payload_hash"])
                and chain_hash == str(row["chain_hash"])
                and predecessor_ok
            )
            signature_verified = _verify_signature(
                chain_hash,
                str(row["signature_state"]),
                str(row["signature"]),
            )
            return {
                "receipt_id": receipt_id,
                "integrity_verified": hash_ok,
                "predecessor_verified": predecessor_ok,
                "signature_verified": signature_verified,
                "signature_state": str(row["signature_state"]),
                "chain_hash": chain_hash,
                "truth_label": "MEASURED",
            }
        finally:
            connection.close()

    def cases(self, scope: str, limit: int = 25) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM cases WHERE scope=? ORDER BY rowid DESC LIMIT ?",
                (scope, max(1, min(MAX_CASES, limit))),
            ).fetchall()
            output: list[dict[str, Any]] = []
            for case in rows:
                event = connection.execute(
                    "SELECT * FROM events WHERE scope=? AND id=?",
                    (scope, str(case["event_id"])),
                ).fetchone()
                proposal = connection.execute(
                    "SELECT * FROM proposals WHERE scope=? AND case_id=?",
                    (scope, str(case["id"])),
                ).fetchone()
                output.append(
                    {
                        **self._case_public(case),
                        "event": self._event_public(event),
                        "proposal": self._proposal_public(proposal),
                    }
                )
            return output
        finally:
            connection.close()

    def receipt(self, scope: str, receipt_id: str) -> dict[str, Any]:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM receipts WHERE scope=? AND id=?",
                (scope, receipt_id),
            ).fetchone()
            if row is None:
                raise LookupError("receipt not found in caller session")
            return {
                "id": str(row["id"]),
                "kind": str(row["kind"]),
                "object_id": str(row["object_id"]),
                "previous_hash": str(row["previous_hash"]),
                "payload": json.loads(str(row["payload_json"])),
                "payload_hash": str(row["payload_hash"]),
                "chain_hash": str(row["chain_hash"]),
                "signature_state": str(row["signature_state"]),
                "signature_present": bool(str(row["signature"])),
                "created_at": str(row["created_at"]),
            }
        finally:
            connection.close()

    @staticmethod
    def _event_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            key: row[key]
            for key in (
                "id",
                "source_event_id",
                "event_type",
                "asset_ref",
                "actor_id",
                "severity",
                "summary",
                "payload_hash",
                "created_at",
            )
        }

    @staticmethod
    def _case_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            key: row[key]
            for key in ("id", "event_id", "title", "severity", "state", "created_at", "updated_at")
        }

    @staticmethod
    def _proposal_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "case_id": row["case_id"],
            "action_type": row["action_type"],
            "target_ref": row["target_ref"],
            "parameters": json.loads(str(row["parameters_json"])),
            "requested_by": row["requested_by"],
            "policy_score": row["policy_score"],
            "policy_axes": json.loads(str(row["policy_axes_json"])),
            "state": row["state"],
            "proposal_hash": row["proposal_hash"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "can_execute": False,
        }


def _store() -> DefendStore:
    path = _state_path()
    with _STORES_LOCK:
        store = _STORES.get(path)
        if store is None:
            store = DefendStore(path)
            _STORES[path] = store
        return store


def _normalize_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    unknown = set(value) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"unsupported fields: {sorted(unknown)}")
    event_type = _bounded_identifier(value.get("event_type"), "event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported event_type: {event_type}")
    severity = _bounded_identifier(value.get("severity"), "severity").upper()
    if severity not in SEVERITIES:
        raise ValueError(f"unsupported severity: {severity}")
    indicators = value.get("indicators", {})
    if not isinstance(indicators, dict):
        raise ValueError("indicators must be a JSON object")
    unknown_indicators = set(indicators) - ALLOWED_INDICATORS
    if unknown_indicators:
        raise ValueError(f"unsupported indicators: {sorted(unknown_indicators)}")
    clean_indicators: dict[str, Any] = {}
    for name in sorted(ALLOWED_INDICATORS):
        if name == "evidence_count":
            count = indicators.get(name, 0)
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 32:
                raise ValueError("evidence_count must be an integer within 0-32")
            clean_indicators[name] = count
        else:
            flag = indicators.get(name, False)
            if not isinstance(flag, bool):
                raise ValueError(f"{name} must be a boolean")
            clean_indicators[name] = flag
    return {
        "source_event_id": _bounded_identifier(value.get("source_event_id"), "source_event_id"),
        "event_type": event_type,
        "asset_ref": _bounded_identifier(value.get("asset_ref"), "asset_ref"),
        "actor_id": _bounded_identifier(value.get("actor_id"), "actor_id"),
        "severity": severity,
        "summary": _bounded_text(value.get("summary"), "summary", maximum=500),
        "requested_by": _bounded_identifier(value.get("requested_by"), "requested_by"),
        "indicators": clean_indicators,
    }


def _evaluate(event: dict[str, Any]) -> tuple[float, dict[str, float], float, str]:
    indicators = event["indicators"]
    risk = SEVERITY_BASE[event["severity"]]
    for name, weight in (
        ("known_exploited", 0.10),
        ("public_exposure", 0.08),
        ("privilege_escalation", 0.08),
        ("agent_tool_policy_violation", 0.07),
        ("destructive_capability", 0.10),
    ):
        if indicators[name]:
            risk += weight
    risk = round(min(0.99, risk), 4)
    evidence_count = int(indicators["evidence_count"])
    axes = {
        "evidence": round(min(1.0, evidence_count / 2.0) * (1.0 if indicators["source_authenticated"] else 0.35), 4),
        "source_integrity": 1.0 if indicators["source_authenticated"] else 0.35,
        "authority": 1.0 if indicators["asset_owner_known"] else 0.65,
        "reversibility": 1.0 if indicators["rollback_available"] else 0.55,
    }
    score = _lambda_score(axes)
    if risk >= 0.85:
        action = "isolate_asset"
    elif risk >= 0.70:
        action = "disable_session"
    elif risk >= 0.45:
        action = "open_ticket"
    else:
        action = "monitor"
    if action not in ALLOWED_ACTIONS:
        raise RuntimeError("internal action escaped allowlist")
    return risk, axes, score, action


def _expected_effect(action: str) -> str:
    return {
        "monitor": "Increase observation frequency without changing the target.",
        "open_ticket": "Create a reviewable incident-work item without changing the target.",
        "disable_session": "Model revocation of the named session while preserving rollback evidence.",
        "isolate_asset": "Model bounded network isolation of the named asset while preserving a rollback route.",
    }[action]


def _rollback_plan(action: str, target: str) -> list[str]:
    shared = [
        f"Confirm the target identity still resolves to {target}.",
        "Verify an independent approver and the exact proposal hash.",
    ]
    action_steps = {
        "monitor": ["Restore the previous observation cadence."],
        "open_ticket": ["Close the modeled work item with a reason and receipt."],
        "disable_session": ["Re-enable only the exact session after identity verification."],
        "isolate_asset": ["Restore only the exact prior network policy after integrity checks."],
    }[action]
    return shared + action_steps + ["Mint a post-condition verification receipt."]


async def _json_body(request: Request) -> Any:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        raise ValueError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
    raw = await request.body()
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("request body must be valid UTF-8 JSON") from exc


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, ValueError):
        return JSONResponse({"error": "INVALID_REQUEST", "detail": str(exc)}, status_code=422)
    if isinstance(exc, LookupError):
        return JSONResponse({"error": "NOT_FOUND", "detail": str(exc)}, status_code=404)
    if isinstance(exc, PermissionError):
        return JSONResponse({"error": "INDEPENDENCE_REQUIRED", "detail": str(exc)}, status_code=409)
    if isinstance(exc, RuntimeError):
        return JSONResponse({"error": "FAILED_CLOSED", "detail": str(exc)}, status_code=409)
    return JSONResponse({"error": "INTERNAL_FAILED_CLOSED", "detail": type(exc).__name__}, status_code=500)


def _status_payload() -> dict[str, Any]:
    store = _store().status()
    key, key_source = _signing_key()
    signing_ready = key is not None
    return {
        "schema": "szl.killinchu.defend-status/v1",
        "product": PRODUCT,
        "plane": PLANE,
        "contract_version": CONTRACT_VERSION,
        "state": "READY" if store["state"] == "WRITABLE" and signing_ready else "DEGRADED",
        "workflow_operational": store["state"] == "WRITABLE",
        "production_receipts_ready": store["state"] == "WRITABLE" and signing_ready,
        "same_origin": True,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "revision": SOURCE_REVISION,
            "package_version": SOURCE_PACKAGE_VERSION,
            "binding": "EXACT_CONTRACT_PORT",
        },
        "taxonomy": {
            "public_product": "Killinchu",
            "portfolio_name": "Aegis",
            "internal_engine": "Sentra",
            "separate_public_space_required": False,
        },
        "store": store,
        "signing": {
            "state": "HMAC_SHA256_READY" if signing_ready else "UNAVAILABLE",
            "key_source": key_source if signing_ready else "WRITE_ONLY_SPACE_SECRET_REQUIRED",
            "secret_value_exposed": False,
        },
        "routes": {
            "ui": "/defend",
            "overview": "/resilience",
            "analyze": "/api/defend/analyze",
            "approve": "/api/defend/approve",
            "rehearse": "/api/defend/rehearse",
            "verify": "/api/defend/verify",
            "cases": "/api/defend/cases",
        },
        "supported_event_types": sorted(EVENT_TYPES),
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "external_effectors_enabled": False,
        "arbitrary_commands_allowed": False,
        "arbitrary_urls_allowed": False,
        "human_approval_required": True,
        "truth_label": "MEASURED",
    }


async def _status(request: Request) -> JSONResponse:
    return JSONResponse(_status_payload(), status_code=200)


async def _source(request: Request) -> JSONResponse:
    status = _status_payload()
    return JSONResponse(
        {
            "schema": "szl.source-binding/v1",
            "product": PRODUCT,
            "plane": PLANE,
            "source": status["source"],
            "public_space": "SZLHOLDINGS/killinchu",
            "legacy_space": "SZLHOLDINGS/sentra",
            "legacy_state": "RETIRE_AFTER_REPLACEMENT_PROOF",
            "truth_label": "MEASURED",
        }
    )


async def _analyze(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        event = _normalize_event(await _json_body(request))
        result = _store().analyze(scope, event)
        if result.get("collision"):
            return JSONResponse(
                {
                    "schema": "szl.killinchu.defend-analysis/v1",
                    "decision": "QUARANTINE",
                    "reason": "SOURCE_EVENT_ID_COLLISION",
                    **result,
                    "external_effectors_enabled": False,
                },
                status_code=409,
            )
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-analysis/v1",
                "decision": result["proposal"]["state"],
                **result,
                "human_approval_required": True,
                "external_effectors_enabled": False,
                "truth_label": "MEASURED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _approve(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        body = await _json_body(request)
        if not isinstance(body, dict) or set(body) != {"proposal_id", "approver"}:
            raise ValueError("body must contain exactly proposal_id and approver")
        proposal_id = _bounded_identifier(body.get("proposal_id"), "proposal_id")
        if PROPOSAL_ID_RE.fullmatch(proposal_id) is None:
            raise ValueError("proposal_id has an invalid shape")
        approver = _bounded_identifier(body.get("approver"), "approver")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-approval/v1",
                **_store().approve(scope, proposal_id, approver),
                "truth_label": "MEASURED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _rehearse(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        body = await _json_body(request)
        if not isinstance(body, dict) or set(body) != {"proposal_id"}:
            raise ValueError("body must contain exactly proposal_id")
        proposal_id = _bounded_identifier(body.get("proposal_id"), "proposal_id")
        if PROPOSAL_ID_RE.fullmatch(proposal_id) is None:
            raise ValueError("proposal_id has an invalid shape")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-rehearsal/v1",
                **_store().rehearse(scope, proposal_id),
                "truth_label": "MODELED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _verify(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        body = await _json_body(request)
        if not isinstance(body, dict) or set(body) != {"receipt_id"}:
            raise ValueError("body must contain exactly receipt_id")
        receipt_id = _bounded_identifier(body.get("receipt_id"), "receipt_id")
        if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
            raise ValueError("receipt_id has an invalid shape")
        result = _store().verify(scope, receipt_id)
        return JSONResponse(
            {"schema": "szl.killinchu.defend-verification/v1", **result},
            status_code=200 if result["integrity_verified"] else 409,
        )
    except Exception as exc:
        return _error(exc)


async def _cases(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        raw = request.query_params.get("limit", "25")
        if not raw.isdigit():
            raise ValueError("limit must be an integer")
        cases = _store().cases(scope, int(raw))
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-cases/v1",
                "count": len(cases),
                "cases": cases,
                "session_scope": "HASHED_CALLER_TOKEN",
                "truth_label": "MEASURED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _receipt(request: Request) -> JSONResponse:
    try:
        scope = _session_scope(request)
        receipt_id = _bounded_identifier(request.path_params.get("receipt_id"), "receipt_id")
        if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
            raise ValueError("receipt_id has an invalid shape")
        return JSONResponse(
            {
                "schema": "szl.killinchu.defend-receipt/v1",
                "receipt": _store().receipt(scope, receipt_id),
                "truth_label": "MEASURED",
            }
        )
    except Exception as exc:
        return _error(exc)


async def _metrics(request: Request) -> JSONResponse:
    status = _status_payload()
    return JSONResponse(
        {
            "schema": "szl.killinchu.defend-metrics/v1",
            "store": status["store"],
            "workflow_operational": status["workflow_operational"],
            "production_receipts_ready": status["production_receipts_ready"],
            "external_effectors_enabled": False,
            "truth_label": "MEASURED",
        }
    )


async def _page(request: Request) -> HTMLResponse:
    return HTMLResponse(_PAGE)


async def _legacy_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse("/defend", status_code=308)


_TABS_CSS = r"""
<style data-killinchu-plane-tabs-style="v1">
.kc-plane-tabs{position:sticky;top:0;z-index:2147482000;display:flex;align-items:center;gap:5px;overflow-x:auto;min-height:48px;padding:5px max(12px,env(safe-area-inset-left));border-bottom:1px solid rgba(95,179,163,.28);background:rgba(5,8,12,.94);backdrop-filter:blur(18px);scrollbar-width:thin;color:#eef4f8;font:700 10px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;text-transform:uppercase}.kc-plane-tabs a{flex:0 0 auto;display:inline-flex;align-items:center;min-height:38px;padding:8px 11px;border:1px solid transparent;border-radius:8px;color:#aebbc7;text-decoration:none}.kc-plane-tabs a:hover,.kc-plane-tabs a:focus-visible,.kc-plane-tabs a[aria-current="page"]{border-color:rgba(201,183,135,.34);background:rgba(201,183,135,.07);color:#f5f7fa;outline-offset:2px}.kc-plane-tabs .kc-product{color:#d6c69a;margin-right:8px}.kc-plane-tabs .kc-state{margin-left:auto;color:#6fae8b}@media(max-width:620px){.kc-plane-tabs .kc-state{display:none}}@media(prefers-reduced-motion:reduce){.kc-plane-tabs *{scroll-behavior:auto!important;transition:none!important}}
</style>
""".encode("utf-8")
_TABS = r"""<nav class="kc-plane-tabs" data-killinchu-plane-tabs="v1" aria-label="Killinchu capability planes"><a class="kc-product" href="/resilience">Killinchu</a><a href="/defend">Defend</a><a href="/immune">Immune</a><a href="/elite/maritime">Maritime</a><a href="/elite#cuas_lab">Airspace</a><a href="/khipu">Evidence</a><span class="kc-state">One public runtime</span></nav>""".encode("utf-8")


class PlaneTabsMiddleware(BaseHTTPMiddleware):
    """Add the same-origin product-plane tab rail to existing HTML surfaces."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            content_type = (response.headers.get("content-type") or "").lower()
            path = request.url.path
            if (
                request.method != "GET"
                or "text/html" not in content_type
                or path.startswith(("/api/", "/assets/", "/static/", "/vendor/"))
            ):
                return response
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode("utf-8")
            if b'data-killinchu-plane-tabs="v1"' not in body:
                if b"</head>" in body:
                    body = body.replace(b"</head>", _TABS_CSS + b"</head>", 1)
                body_lower = body.lower()
                start = body_lower.find(b"<body")
                if start >= 0:
                    close = body.find(b">", start)
                    if close >= 0:
                        body = body[: close + 1] + _TABS + body[close + 1 :]
            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers.pop("content-type", None)
            rebuilt = Response(body, status_code=response.status_code, headers=headers)
            rebuilt.headers["content-type"] = "text/html; charset=utf-8"
            return rebuilt
        except Exception:
            return response


_PAGE = r"""<!doctype html>
<html lang="en" data-killinchu-defend="v1">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="/defend">
<title>Killinchu / Defend</title>
<meta name="description" content="Killinchu Defend — evidence-bound detection, cases, human approval, rehearsal, rollback and receipt verification. Aegis is the portfolio; Sentra is the internal engine; Killinchu is the single public runtime.">
<style>
:root{color-scheme:dark;--bg:#05080c;--panel:#0b1118;--panel2:#0f1721;--line:#243749;--ink:#f5f8fb;--muted:#9dabb9;--gold:#d6c69a;--teal:#5fb3a3;--good:#6fae8b;--warn:#d6b06a;--bad:#d08a78;--max:1220px}*{box-sizing:border-box;min-inline-size:0}html{overflow-x:clip;background:var(--bg)}body{margin:0;overflow-x:clip;color:var(--ink);font:15px/1.58 Inter,"Segoe UI",system-ui,sans-serif;background:radial-gradient(circle at 83% 6%,rgba(95,179,163,.12),transparent 34rem),linear-gradient(rgba(95,179,163,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(95,179,163,.025) 1px,transparent 1px),var(--bg);background-size:auto,32px 32px,32px 32px}a{color:inherit}.mono,.eyebrow,label,.state{font-family:"SFMono-Regular","Cascadia Code",ui-monospace,monospace}.kc-plane-tabs{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:5px;overflow-x:auto;min-height:52px;padding:5px max(12px,env(safe-area-inset-left));border-bottom:1px solid rgba(95,179,163,.28);background:rgba(5,8,12,.94);backdrop-filter:blur(18px);font:700 10px/1.2 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}.kc-plane-tabs a{flex:0 0 auto;display:inline-flex;align-items:center;min-height:40px;padding:8px 11px;border:1px solid transparent;border-radius:8px;color:#aebbc7;text-decoration:none}.kc-plane-tabs a:hover,.kc-plane-tabs a:focus-visible,.kc-plane-tabs a[aria-current="page"]{border-color:rgba(201,183,135,.34);background:rgba(201,183,135,.07);color:#fff}.kc-plane-tabs .kc-product{color:var(--gold);margin-right:8px}.kc-plane-tabs .kc-state{margin-left:auto;color:var(--good)}.shell{width:min(100%,var(--max));margin:auto;padding:clamp(28px,6vw,84px) clamp(16px,4vw,56px) 90px}.eyebrow{color:var(--teal);font-size:11px;letter-spacing:.14em;text-transform:uppercase}.hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:clamp(30px,7vw,90px);align-items:end;padding-bottom:52px;border-bottom:1px solid var(--line)}h1{margin:15px 0 22px;max-width:10ch;font-size:clamp(54px,9vw,118px);font-weight:560;line-height:.84;letter-spacing:-.07em}.lede{max-width:66ch;color:var(--muted);font-size:clamp(17px,2vw,22px)}.boundary{border:1px solid var(--line);border-radius:18px;background:linear-gradient(145deg,rgba(95,179,163,.09),transparent),var(--panel);padding:20px}.boundary strong{display:block;color:var(--gold);font-size:20px}.boundary p{color:var(--muted)}.chips{display:flex;gap:7px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:999px;padding:7px 9px;font:700 9px ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.chip.good{color:var(--good)}section{padding:54px 0;border-bottom:1px solid var(--line)}.section-head{display:flex;justify-content:space-between;gap:20px;align-items:end;flex-wrap:wrap;margin-bottom:20px}.section-head h2{margin:8px 0 0;font-size:clamp(34px,5vw,64px);line-height:.95;letter-spacing:-.05em}.section-head p{max-width:52ch;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.card{border:1px solid var(--line);border-radius:16px;background:rgba(11,17,24,.88);padding:18px}.card h3{margin:8px 0;font-size:23px}.card p,.card small{color:var(--muted)}.state{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--good)}form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}label{display:grid;gap:6px;color:var(--muted);font-size:10px;letter-spacing:.09em;text-transform:uppercase}label.wide{grid-column:1/-1}input,select,textarea,button{font:inherit}input,select,textarea{width:100%;min-height:46px;border:1px solid var(--line);border-radius:10px;background:#070b10;color:var(--ink);padding:10px 12px}textarea{min-height:94px;resize:vertical}.checks{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.checks label{display:flex;align-items:center;gap:8px;min-height:44px;border:1px solid var(--line);border-radius:10px;padding:8px;text-transform:none;letter-spacing:0}.checks input{width:18px;min-height:18px}.actions{grid-column:1/-1;display:flex;gap:9px;flex-wrap:wrap}button{min-height:46px;border:1px solid var(--line);border-radius:10px;background:var(--ink);color:#05080c;padding:10px 15px;font-weight:800;cursor:pointer}button.secondary{background:transparent;color:var(--ink)}button:disabled{opacity:.45;cursor:not-allowed}:focus-visible{outline:3px solid var(--teal);outline-offset:3px}pre{margin:0;max-height:540px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;color:#cbd8e4;font:12px/1.6 ui-monospace,monospace}.workflow{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:12px}.receipt-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.notice{margin-top:16px;color:var(--muted)}@media(max-width:880px){.hero,.workflow{grid-template-columns:1fr}.grid{grid-template-columns:1fr 1fr}}@media(max-width:620px){.grid,form,.checks{grid-template-columns:1fr}label.wide,.checks,.actions{grid-column:auto}.kc-plane-tabs .kc-state{display:none}h1{font-size:clamp(50px,17vw,76px)}}@media(pointer:coarse){a,button,input,select{min-height:48px}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}@media(forced-colors:active){*{forced-color-adjust:auto}.card,.boundary,input,select,textarea{border:1px solid CanvasText}}
</style>
</head>
<body>
<nav class="kc-plane-tabs" data-killinchu-plane-tabs="v1" aria-label="Killinchu capability planes"><a class="kc-product" href="/resilience">Killinchu</a><a href="/defend" aria-current="page">Defend</a><a href="/immune">Immune</a><a href="/elite/maritime">Maritime</a><a href="/elite#cuas_lab">Airspace</a><a href="/khipu">Evidence</a><span class="kc-state">One public runtime</span></nav>
<main class="shell">
<header class="hero"><div><div class="eyebrow">Cyber-physical resilience / defensive intelligence</div><h1>Killinchu / Defend</h1><p class="lede">Evidence-bound detection becomes a deterministic case and a bounded containment proposal, then independent human approval, simulation-only rehearsal, rollback state and an independently verifiable receipt.</p></div><aside class="boundary"><strong>One product. Distinct capability planes.</strong><p><b>Aegis</b> is the portfolio name. <b>Sentra</b> is the internal defensive-control-plane engine. <b>Killinchu</b> is the sole public product and Hugging Face runtime.</p><div class="chips"><span class="chip good">same-origin</span><span class="chip">source pinned</span><span class="chip">human authority</span><span class="chip">no public effector</span></div></aside></header>
<section><div class="section-head"><div><div class="eyebrow">01 / Runtime proof</div><h2>Operational truth</h2></div><p>Status comes from the running store, exact source binding and signing-secret availability. Reachability is never promoted into an authorization claim.</p></div><div class="grid"><article class="card"><span class="state" id="runtime-state">PROBING</span><h3>Control plane</h3><p id="runtime-copy">Loading exact runtime status.</p></article><article class="card"><span class="state">BOUNDED</span><h3>Authority</h3><p>Independent approval can authorize a rehearsal only. External effectors remain disabled.</p></article><article class="card"><span class="state">APPEND-ONLY</span><h3>Evidence</h3><p>Every detection, proposal, approval and rehearsal extends a session-scoped receipt chain.</p></article></div></section>
<section><div class="section-head"><div><div class="eyebrow">02 / Detect → approve → verify</div><h2>Run the governed loop</h2></div><p>The browser creates a private caller-held session token. The service stores only its SHA-256 scope, never the token.</p></div><div class="workflow"><form id="event-form" class="card"><label>Event type<select id="event_type"><option>vulnerability.known_exploited</option><option>identity.privilege_change</option><option>asset.public_exposure</option><option>agent.policy_violation</option><option>network.anomalous_egress</option><option>custom.defensive_signal</option></select></label><label>Severity<select id="severity"><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></label><label>Asset reference<input id="asset_ref" value="asset/demo-gateway" maxlength="128" required></label><label>Actor reference<input id="actor_id" value="actor/observed-service" maxlength="128" required></label><label>Requester<input id="requested_by" value="operator/requester" maxlength="128" required></label><label>Evidence count<input id="evidence_count" type="number" min="0" max="32" value="3"></label><label class="wide">Summary<textarea id="summary" maxlength="500">Known-exploited vulnerability observed on a public-facing asset; validate a reversible containment proposal.</textarea></label><div class="checks"><label><input id="source_authenticated" type="checkbox" checked>Source authenticated</label><label><input id="asset_owner_known" type="checkbox" checked>Asset owner known</label><label><input id="rollback_available" type="checkbox" checked>Rollback available</label><label><input id="known_exploited" type="checkbox" checked>Known exploited</label><label><input id="public_exposure" type="checkbox" checked>Public exposure</label><label><input id="privilege_escalation" type="checkbox">Privilege escalation</label></div><div class="actions"><button type="submit">Analyze event</button><button type="button" class="secondary" id="refresh-cases">Refresh cases</button></div></form><article class="card"><div class="eyebrow">Receipt-bound output</div><pre id="output" aria-live="polite">Ready. Submit an event to create a case and bounded proposal.</pre><div class="receipt-actions"><button type="button" class="secondary" id="approve" disabled>Approve rehearsal</button><button type="button" class="secondary" id="rehearse" disabled>Run rehearsal</button><button type="button" class="secondary" id="verify" disabled>Verify receipt</button></div></article></div><p class="notice">This is a real stateful decision-and-evidence workflow with deterministic calculations and durable process-local SQLite. The external action is intentionally not real: the public runtime cannot isolate an asset, disable a session, create a provider ticket or operate against another system.</p></section>
<section><div class="section-head"><div><div class="eyebrow">03 / Capability map</div><h2>What moved into Killinchu</h2></div><p>Public-product consolidation preserves component provenance rather than erasing it.</p></div><div class="grid"><article class="card"><span class="state">CAPTURED</span><h3>Sentra contract</h3><p>Replay-safe ingestion, deterministic detection, cases, proposals, human independence, rehearsal and receipts.</p></article><article class="card"><span class="state">CANONICAL</span><h3>Aegis portfolio</h3><p>The complete cyber-physical resilience family now resolves to this one product surface.</p></article><article class="card"><span class="state">SEPARATE PLANE</span><h3>Immune</h3><p>AI admission, signed authority and tripwire parity remain a distinct same-origin migration gate; no false completion claim is made here.</p></article></div></section>
<footer class="mono">SOURCE <a href="/api/defend/source">PIN</a> · STATUS <a href="/api/defend/status">JSON</a> · CASES <a href="/api/defend/cases">SESSION-SCOPED</a> · KILLINCHU / DEFEND {version}</footer>
</main>
<script>
const out=document.getElementById('output');let currentProposal=null,currentReceipt=null;const key='killinchu-defend-session-v1';function token(){let v=localStorage.getItem(key);if(!v||v.length<32){const a=new Uint8Array(32);crypto.getRandomValues(a);v=Array.from(a,b=>b.toString(16).padStart(2,'0')).join('');localStorage.setItem(key,v)}return v}const headers=()=>({'Content-Type':'application/json','X-SZL-Session':token()});async function call(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:body?headers():{'X-SZL-Session':token()},cache:'no-store',body:body?JSON.stringify(body):undefined});let j;try{j=await r.json()}catch(e){j={error:'NON_JSON_RESPONSE',status:r.status}}if(!r.ok)throw j;return j}function show(v){out.textContent=JSON.stringify(v,null,2)}async function status(){try{const j=await call('/api/defend/status');document.getElementById('runtime-state').textContent=j.state;document.getElementById('runtime-copy').textContent=`workflow ${j.workflow_operational?'operational':'failed closed'} · receipts ${j.production_receipts_ready?'signed':'unsigned'} · ${j.store.backend}`;}catch(e){document.getElementById('runtime-state').textContent='UNAVAILABLE';document.getElementById('runtime-copy').textContent='Runtime status could not be observed.'}}document.getElementById('event-form').addEventListener('submit',async e=>{e.preventDefault();try{const now=Date.now().toString(36);const indicators={source_authenticated:source_authenticated.checked,asset_owner_known:asset_owner_known.checked,rollback_available:rollback_available.checked,known_exploited:known_exploited.checked,public_exposure:public_exposure.checked,privilege_escalation:privilege_escalation.checked,agent_tool_policy_violation:event_type.value==='agent.policy_violation',destructive_capability:false,evidence_count:Number(evidence_count.value)};const j=await call('/api/defend/analyze',{source_event_id:`browser-${now}`,event_type:event_type.value,asset_ref:asset_ref.value,actor_id:actor_id.value,severity:severity.value,summary:summary.value,requested_by:requested_by.value,indicators});currentProposal=j.proposal?.id||null;currentReceipt=j.receipt?.id||null;approve.disabled=!currentProposal||j.proposal?.state!=='PROPOSED';rehearse.disabled=true;verify.disabled=!currentReceipt;show(j)}catch(e){show(e)}});document.getElementById('approve').onclick=async()=>{const approver=prompt('Independent approver identifier','operator/approver');if(!approver)return;try{const j=await call('/api/defend/approve',{proposal_id:currentProposal,approver});currentReceipt=j.receipt.id;approve.disabled=true;rehearse.disabled=false;verify.disabled=false;show(j)}catch(e){show(e)}};document.getElementById('rehearse').onclick=async()=>{try{const j=await call('/api/defend/rehearse',{proposal_id:currentProposal});currentReceipt=j.receipt.id;rehearse.disabled=true;verify.disabled=false;show(j)}catch(e){show(e)}};document.getElementById('verify').onclick=async()=>{try{show(await call('/api/defend/verify',{receipt_id:currentReceipt}))}catch(e){show(e)}};document.getElementById('refresh-cases').onclick=async()=>{try{show(await call('/api/defend/cases?limit=25'))}catch(e){show(e)}};status();
</script>
</body>
</html>
""".replace("{version}", CONTRACT_VERSION)


def _routes(ns: str) -> Iterable[Route]:
    return (
        Route("/defend", _page, methods=["GET"], name=f"{ns}_defend_page"),
        Route("/resilience", _page, methods=["GET"], name=f"{ns}_resilience_page"),
        Route("/aegis", _legacy_redirect, methods=["GET"], name=f"{ns}_aegis_alias"),
        Route("/sentra", _legacy_redirect, methods=["GET"], name=f"{ns}_sentra_alias"),
        Route("/api/defend/status", _status, methods=["GET"], name=f"{ns}_defend_status"),
        Route("/api/defend/readyz", _status, methods=["GET"], name=f"{ns}_defend_ready"),
        Route("/api/defend/source", _source, methods=["GET"], name=f"{ns}_defend_source"),
        Route("/api/defend/analyze", _analyze, methods=["POST"], name=f"{ns}_defend_analyze"),
        Route("/api/defend/approve", _approve, methods=["POST"], name=f"{ns}_defend_approve"),
        Route("/api/defend/rehearse", _rehearse, methods=["POST"], name=f"{ns}_defend_rehearse"),
        Route("/api/defend/verify", _verify, methods=["POST"], name=f"{ns}_defend_verify"),
        Route("/api/defend/cases", _cases, methods=["GET"], name=f"{ns}_defend_cases"),
        Route("/api/defend/receipts/{receipt_id}", _receipt, methods=["GET"], name=f"{ns}_defend_receipt"),
        Route("/api/defend/metrics", _metrics, methods=["GET"], name=f"{ns}_defend_metrics"),
        Route("/api/sentra/status", _status, methods=["GET"], name=f"{ns}_sentra_status_alias"),
    )


def register(app: Any, ns: str = "killinchu") -> dict[str, Any]:
    """Mount Defend before the SPA catch-all and add the product-plane tab rail."""
    if getattr(app.state, "killinchu_defend_registered", False):
        return {"status": "already_registered", "plane": PLANE}
    existing_names = {getattr(route, "name", None) for route in app.router.routes}
    routes = [route for route in _routes(ns) if route.name not in existing_names]
    for route in reversed(routes):
        app.router.routes.insert(0, route)
    app.add_middleware(PlaneTabsMiddleware)
    app.state.killinchu_defend_registered = True
    return {
        "status": "ok",
        "product": PRODUCT,
        "plane": PLANE,
        "contract_version": CONTRACT_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "routes": [route.path for route in routes],
        "external_effectors_enabled": False,
    }


__all__ = [
    "ALLOWED_ACTIONS",
    "CONTRACT_VERSION",
    "DefendStore",
    "EVENT_TYPES",
    "PLANE",
    "PRODUCT",
    "SOURCE_REPOSITORY",
    "SOURCE_REVISION",
    "register",
]
