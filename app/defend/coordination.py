"""Defend coordination ledger — killinchu seam 7.

Applies Anthropic's multiagent-systems findings (Aug 2026) to the estate:

- Epistemic failure fix: agents get chained identities and a reputation
  derived from the audit chain — the "colleague who remembers" that agents
  otherwise lack. Trust becomes calibrated by record, not assumed.
- Incompatible-goals fix: when two agents act on overlapping scopes inside
  a conflict window, a TRUCE event is chained and the dispute routes to the
  human approval workflow. Agents never resolve conflicts against each
  other — deferral to humans was the study's only successful pattern.
- Conformity guardrail: reputation is computed per agent over independent
  outcomes, so correlated failure shows up as correlated record, visible.
- Telemetry: PR merge fraction and scope-sharing metrics are computed from
  the chain and chained back as evidence — the study's own health metrics.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.defend.chain_store import PersistentAuditChain

CONFLICT_WINDOW_SECONDS = 300


@dataclass
class AgentIdentity:
    agent_id: str
    display_name: str
    registered_at_epoch: float


class AgentRegistry:
    """Chained agent identities; registration is itself an audit event."""

    def __init__(self, chain: PersistentAuditChain):
        self.chain = chain
        self._agents: dict[str, AgentIdentity] = {}

    def register(self, agent_id: str, display_name: str,
                 now: float | None = None) -> AgentIdentity:
        now = time.time() if now is None else now
        if agent_id in self._agents:
            raise ValueError(f"agent {agent_id!r} already registered")
        ident = AgentIdentity(agent_id=agent_id, display_name=display_name,
                              registered_at_epoch=now)
        self._agents[agent_id] = ident
        self.chain.append("AGENT_REGISTERED",
                          {"agent_id": agent_id, "display_name": display_name},
                          now=now)
        return ident

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents


class ConflictDetector:
    """Two distinct registered agents on the same scope inside the window
    force a TRUCE: the event is chained and the scope is frozen for agents
    until a human resolves it through the approval workflow."""

    def __init__(self, chain: PersistentAuditChain, registry: AgentRegistry,
                 window_seconds: int = CONFLICT_WINDOW_SECONDS):
        self.chain = chain
        self.registry = registry
        self.window = window_seconds
        self._recent: dict[str, tuple[str, float]] = {}
        self._frozen: set[str] = set()

    def record_action(self, *, agent_id: str, scope: str,
                      now: float | None = None) -> bool:
        """Returns True when the action stands; False when a TRUCE froze it."""
        now = time.time() if now is None else now
        if not self.registry.is_registered(agent_id):
            raise ValueError(f"unregistered agent {agent_id!r} cannot act")
        if scope in self._frozen:
            return False
        prior = self._recent.get(scope)
        if prior and prior[0] != agent_id and now - prior[1] <= self.window:
            self._frozen.add(scope)
            self.chain.append("TRUCE",
                              {"scope": scope, "agents": [prior[0], agent_id],
                               "resolution": "human_approval_required"}, now=now)
            return False
        self._recent[scope] = (agent_id, now)
        return True

    def resolve_truce(self, scope: str, *, approval_authorized: bool,
                      actor: str, now: float | None = None) -> None:
        if not approval_authorized:
            raise PermissionError("truce resolution requires human approval")
        self._frozen.discard(scope)
        self.chain.append("TRUCE_RESOLVED", {"scope": scope, "actor": actor},
                          now=now)

    def frozen(self, scope: str) -> bool:
        return scope in self._frozen


def reputation(chain: PersistentAuditChain, agent_id: str) -> dict:
    """Derive an agent's record from the chain: actions, denials, truces."""
    rows = chain._conn.execute(
        "SELECT event_type, payload FROM audit_events ORDER BY seq").fetchall()
    actions = denials = truces = 0
    for event_type, payload in rows:
        p = json.loads(payload)
        if event_type == "EFFECTOR_ALLOWED" and p.get("principal") == agent_id:
            actions += 1
        elif event_type == "EFFECTOR_DENIED" and p.get("principal") == agent_id:
            denials += 1
        elif event_type == "TRUCE" and agent_id in p.get("agents", []):
            truces += 1
    total = actions + denials
    return {"agent_id": agent_id, "allowed": actions, "denied": denials,
            "truces": truces,
            "allow_rate": (actions / total) if total else None}


def coordination_telemetry(chain: PersistentAuditChain, *,
                           prs_proposed: int, prs_merged: int,
                           files_shared: int, files_total: int,
                           now: float | None = None) -> dict:
    """The study's health metrics, chained as evidence."""
    telemetry = {"pr_merge_fraction": (prs_merged / prs_proposed) if prs_proposed else None,
                 "code_share_fraction": (files_shared / files_total) if files_total else None}
    chain.append("COORDINATION_TELEMETRY", telemetry, now=now)
    return telemetry
