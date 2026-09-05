"""Defend composition root — killinchu #399 §6 per spec #401.

One assembly point that wires the merged seams into a single request path:
ScopeRegistry -> KillSwitch -> ApprovalWorkflow -> EffectorGuard ->
AuditChain, over the DurableState idempotency store. Routes/handlers hold
no policy; they call `handle_effector_request` and return the decision.
Readiness aggregates the durable store, registry non-emptiness, and chain
integrity — the plane is only "ready" when every seam it depends on is.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.defend.approval_workflow import ApprovalWorkflow
from app.defend.audit_chain import AuditChain
from app.defend.durable_state import DurableState
from app.defend.effector_guard import Denial, EffectorGuard, GuardDecision
from app.defend.kill_switch import KillSwitch, ScopeRegistry


@dataclass
class DefendPlane:
    store: DurableState
    chain: AuditChain
    registry: ScopeRegistry
    kill_switch: KillSwitch
    approvals: ApprovalWorkflow
    guard: EffectorGuard


def assemble(*, database_url: str | None = None, demo_mode: bool = False) -> DefendPlane:
    """Build the plane with every seam wired; nothing effectful bypasses it."""
    store = DurableState(database_url=database_url, demo_mode=demo_mode)
    chain = AuditChain()
    registry = ScopeRegistry()
    kill = KillSwitch(chain)
    approvals = ApprovalWorkflow()
    guard = EffectorGuard(store, registry.allowlist(),
                          kill_switch_engaged=kill.guard_flag())
    return DefendPlane(store=store, chain=chain, registry=registry,
                       kill_switch=kill, approvals=approvals, guard=guard)


def refresh_guard(plane: DefendPlane) -> None:
    """Per-request refresh: registry and kill state are live, not cached."""
    plane.guard.allowed_scopes = plane.registry.allowlist()
    plane.guard.kill_switch_engaged = plane.kill_switch.guard_flag()


def handle_effector_request(plane: DefendPlane, *, principal: str, scope: str,
                            idempotency_key: str, request_body: dict,
                            approval_request_id: str | None,
                            effector, now: float | None = None) -> GuardDecision:
    """The single entry point for effectful work. Always audited."""
    now = time.time() if now is None else now
    refresh_guard(plane)
    if plane.kill_switch.halted(scope):
        decision = plane.guard.execute(
            principal=principal, scope=scope, idempotency_key=idempotency_key,
            request_body=request_body, approval=None, effector=effector, now=now)
        decision.denial = Denial.KILL_SWITCH
        decision.receipt_fragment = {"principal": principal, "scope": scope,
                                     "denial": Denial.KILL_SWITCH.value}
    else:
        approval = (plane.approvals.authorization_for_guard(approval_request_id, now=now)
                    if approval_request_id else None)
        decision = plane.guard.execute(
            principal=principal, scope=scope, idempotency_key=idempotency_key,
            request_body=request_body, approval=approval, effector=effector, now=now)
    plane.chain.append(
        "EFFECTOR_ALLOWED" if decision.allowed else "EFFECTOR_DENIED",
        decision.receipt_fragment, now=now)
    return decision


def readyz(plane: DefendPlane) -> tuple[bool, dict]:
    """Aggregate readiness: store, registry, chain integrity."""
    store_ok, store_info = plane.store.readyz()
    chain_ok, broken = plane.chain.verify()
    registry_ok = bool(plane.registry.allowlist())
    ok = store_ok and chain_ok and registry_ok
    return ok, {"durable_store": store_info, "registry_scopes": len(plane.registry.allowlist()),
                "audit_chain": {"intact": chain_ok, "broken_at": broken,
                                "events": len(plane.chain)}}
