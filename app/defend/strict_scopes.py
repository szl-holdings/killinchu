"""Defend strict scopes + withheld evals — killinchu seam 8.

Per-scope schema validation inside the guard boundary: an effector request
whose body fails its scope's schema dies before the idempotency hash is ever
computed, and the rejection is chained. Schemas use a strict stdlib subset
(type, required, properties, additionalProperties, enum) — no third-party
validator, no eval, no surprises. Booleans are not integers.

Withheld drill registry: scenarios are sealed with a keyed stream at rest
and only opened at drill time by the operator holding the key. Registration
and execution are both chained, so the estate can prove which scenarios a
build agent never saw — anti-Goodhart by construction.

Chain checkpoints: CHAIN_CHECKPOINT pins the head and event count; resume
proves the pinned head still sits at its pinned position and the whole
chain verifies, so rewritten history fails the resume.
"""

from __future__ import annotations

import hashlib
import json
import time

from app.defend.chain_store import PersistentAuditChain

_TYPES = {"object": dict, "array": list, "string": str, "number": (int, float),
          "integer": int, "boolean": bool, "null": type(None)}


class SchemaViolation(ValueError):
    pass


def validate(body, schema: dict, path: str = "$") -> None:
    """Strict JSON-Schema subset; rejects anything outside the subset."""
    allowed_keys = {"type", "required", "properties", "additionalProperties", "enum"}
    unknown = set(schema) - allowed_keys
    if unknown:
        raise SchemaViolation(f"unsupported schema keys at {path}: {sorted(unknown)}")
    if "type" in schema:
        expected = _TYPES[schema["type"]]
        if not isinstance(body, expected) or (
                schema["type"] == "integer" and isinstance(body, bool)) or (
                schema["type"] == "number" and isinstance(body, bool)):
            raise SchemaViolation(f"{path}: expected {schema['type']}")
    if "enum" in schema and body not in schema["enum"]:
        raise SchemaViolation(f"{path}: {body!r} not in enum")
    if schema.get("type") == "object":
        for req in schema.get("required", []):
            if req not in body:
                raise SchemaViolation(f"{path}: missing required {req!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(body) - set(props)
            if extra:
                raise SchemaViolation(f"{path}: unexpected fields {sorted(extra)}")
        for key, subschema in props.items():
            if key in body:
                validate(body[key], subschema, f"{path}.{key}")


class ScopeSchemas:
    """Schema registry consulted at the guard boundary, before hashing."""

    def __init__(self, chain: PersistentAuditChain):
        self.chain = chain
        self._schemas: dict[str, dict] = {}

    def bind(self, scope: str, schema: dict, now: float | None = None) -> None:
        self._schemas[scope] = schema
        self.chain.append("SCOPE_SCHEMA_BOUND",
                          {"scope": scope,
                           "schema_sha256": hashlib.sha256(
                               json.dumps(schema, sort_keys=True).encode()).hexdigest()},
                          now=now)

    def check(self, scope: str, body: dict, now: float | None = None) -> None:
        schema = self._schemas.get(scope)
        if schema is None:
            return  # schema binding is the registry's concern, not ours
        try:
            validate(body, schema)
        except SchemaViolation as exc:
            self.chain.append("SCHEMA_REJECTED",
                              {"scope": scope, "violation": str(exc)}, now=now)
            raise


def _keystream(key: bytes, n: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(key + counter.to_bytes(8, "big")).digest()
        counter += 1
    return out[:n]


class WithheldDrillRegistry:
    """Sealed scenarios; only the key-holder can open them, at drill time."""

    def __init__(self, chain: PersistentAuditChain):
        self.chain = chain
        self._sealed: dict[str, bytes] = {}

    def register(self, drill_id: str, scenario: dict, key: bytes,
                 now: float | None = None) -> None:
        raw = json.dumps(scenario, sort_keys=True).encode()
        self._sealed[drill_id] = bytes(a ^ b for a, b in zip(raw, _keystream(key, len(raw))))
        self.chain.append("WITHHELD_DRILL_REGISTERED",
                          {"drill_id": drill_id,
                           "sealed_sha256": hashlib.sha256(self._sealed[drill_id]).hexdigest()},
                          now=now)

    def execute(self, drill_id: str, key: bytes, now: float | None = None) -> dict:
        sealed = self._sealed[drill_id]
        raw = bytes(a ^ b for a, b in zip(sealed, _keystream(key, len(sealed))))
        scenario = json.loads(raw.decode())  # wrong key fails here, before chaining
        self.chain.append("WITHHELD_DRILL_EXECUTED", {"drill_id": drill_id}, now=now)
        return scenario


def checkpoint(chain: PersistentAuditChain, now: float | None = None) -> dict:
    """Pin the current head and event count as a chained checkpoint."""
    return chain.append("CHAIN_CHECKPOINT",
                        {"head": chain.head, "events": len(chain)}, now=now)


def resume_verified(chain: PersistentAuditChain) -> tuple[bool, str]:
    """A restarted plane proves the pinned head still sits at its pinned
    position and the whole chain verifies. The checkpoint pins the head
    after N events; a valid resume has the event at position N equal to the
    pinned head, with everything after it intact."""
    rows = chain._conn.execute(
        "SELECT payload FROM audit_events WHERE event_type='CHAIN_CHECKPOINT' "
        "ORDER BY seq DESC LIMIT 1").fetchone()
    ok, broken = chain.verify()
    if not ok:
        return False, f"chain broken at {broken}"
    if not rows:
        return True, "no checkpoint recorded; genesis-only trust"
    pinned = json.loads(rows[0])
    row = chain._conn.execute(
        "SELECT event_hash FROM audit_events WHERE seq = ?",
        (pinned["events"],)).fetchone()
    if not row or row[0] != pinned["head"]:
        return False, "pinned head missing or moved; history was rewritten"
    if len(chain) == pinned["events"] + 1:
        return True, "head matches checkpoint"
    return True, "chain extended past checkpoint and verifies"
