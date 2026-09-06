"""Defend composition root v2 — killinchu seam 9.

Wires seams 7 and 8 into the request path. handle_effector_request now
runs the full stack in fixed order: registered agent identity (#426) ->
per-scope schema validation before any hashing (#427) -> conflict
detection (#426) -> kill switch (#415) -> approval freshness (#412/#420)
-> scope allowlist (#415) -> rate limit (#411) -> durable idempotency
(#410) -> guarded effector call. Every outcome lands in the persistent
chain (#424), which is the default store here.

New denials in v2: UNREGISTERED_AGENT (identity precedes everything),
SCHEMA_REJECTED (before hashing), TRUCE_FROZEN (conflict pending human
resolution). All fail closed, all chained.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from app.defend.chain_store import PersistentAuditChain
from app.defend.coordination import AgentRegistry, ConflictDetector
from app.defend.durable_state import DurableState
from app.defend.effector_guard import Denial, EffectorGuard, GuardDecision
from app.defend.kill_switch import KillSwitch, ScopeRegistry
from app.defend.strict_scopes import SchemaViolation, ScopeSchemas


class V2Denial(str, Enum):
    UNREGISTERED_AGENT = "unregistered_agent"
    SCHEMA_REJECTED = "schema_rejected"
    TRUCE_FROZEN = "truce_frozen"


@dataclass
class DefendPlaneV2:
    store: DurableState
    chain: PersistentAuditChain
    registry: ScopeRegistry
    kill_switch: KillSwitch
    agents: AgentRegistry
    conflicts: ConflictDetector
    schemas: ScopeSchemas
    guard: EffectorGuard


def assemble_v2(*, database_url: str | None = None, demo_mode: bool = False,
                chain_path: str = ":memory:") -> DefendPlaneV2:
    store = DurableState(database_url=database_url, demo_mode=demo_mode)
    chain = PersistentAuditChain(chain_path)
    registry = ScopeRegistry()
    kill = KillSwitch(chain)
    agents = AgentRegistry(chain)
    conflicts = ConflictDetector(chain, agents)
    schemas = ScopeSchemas(chain)
    guard = EffectorGuard(store, registry.allowlist(),
                          kill_switch_engaged=kill.guard_flag())
    return DefendPlaneV2(store=store, chain=chain, registry=registry,
                         kill_switch=kill, agents=agents, conflicts=conflicts,
                         schemas=schemas, guard=guard)


def _deny(chain, denial, agent_id, scope, now):
    fragment = {"principal": agent_id, "scope": scope, "denial": denial}
    chain.append("EFFECTOR_DENIED", fragment, now=now)
    return GuardDecision(allowed=False, receipt_fragment=fragment)


def handle_effector_request(plane: DefendPlaneV2, *, agent_id: str, scope: str,
                            idempotency_key: str, request_body: dict,
                            approval, effector, now: float | None = None) -> GuardDecision:
    """The single audited entry point, full stack, fixed order."""
    now = time.time() if now is None else now

    if not plane.agents.is_registered(agent_id):
        return _deny(plane.chain, V2Denial.UNREGISTERED_AGENT.value, agent_id, scope, now)

    try:
        plane.schemas.check(scope, request_body, now=now)
    except SchemaViolation:
        return _deny(plane.chain, V2Denial.SCHEMA_REJECTED.value, agent_id, scope, now)

    if not plane.conflicts.record_action(agent_id=agent_id, scope=scope, now=now):
        return _deny(plane.chain, V2Denial.TRUCE_FROZEN.value, agent_id, scope, now)

    plane.guard.allowed_scopes = plane.registry.allowlist()
    plane.guard.kill_switch_engaged = plane.kill_switch.guard_flag()

    if plane.kill_switch.halted(scope):
        return _deny(plane.chain, Denial.KILL_SWITCH.value, agent_id, scope, now)

    decision = plane.guard.execute(
        principal=agent_id, scope=scope, idempotency_key=idempotency_key,
        request_body=request_body, approval=approval, effector=effector, now=now)
    plane.chain.append(
        "EFFECTOR_ALLOWED" if decision.allowed else "EFFECTOR_DENIED",
        decision.receipt_fragment, now=now)
    return decision


def readyz(plane: DefendPlaneV2) -> tuple[bool, dict]:
    store_ok, store_info = plane.store.readyz() if hasattr(plane.store, "readyz") else (True, {})
    chain_ok, broken = plane.chain.verify()
    registry_ok = bool(plane.registry.allowlist())
    ok = store_ok and chain_ok and registry_ok
    return ok, {"durable_store": store_info,
                "registry_scopes": len(plane.registry.allowlist()),
                "audit_chain": {"intact": chain_ok, "broken_at": broken,
                                "events": len(plane.chain)}}
