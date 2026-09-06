"""Agent coordination — killinchu seam 7.

Agents are registered identities; every effector request must carry a
registered agent_id (#426). The ConflictDetector watches for two agents
touching the same scope within a conflict window and responds with a
TRUCE: the scope freezes, both agents are denied, and only a human can
resolve it. Truces and resolutions are chained events.

Fix (seam 9 follow-up): resolve_truce clears the conflict slate. Without
`self._recent.pop(scope, None)`, the first action after a human resolves
a truce instantly re-freezes the scope, because the prior agent's action
still sits inside the conflict window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

CONFLICT_WINDOW_SECONDS = 300


@dataclass
class AgentIdentity:
    agent_id: str
    display_name: str
    registered_at_epoch: float


class AgentRegistry:
    """Registered agent identities (#426). Unregistered agents cannot act."""

    def __init__(self, chain):
        self.chain = chain
        self._agents = {}

    def register(self, agent_id, display_name, now=None):
        now = time.time() if now is None else now
        if agent_id in self._agents:
            raise ValueError(f"agent {agent_id!r} already registered")
        ident = AgentIdentity(agent_id=agent_id, display_name=display_name,
                              registered_at_epoch=now)
        self._agents[agent_id] = ident
        self.chain.append("AGENT_REGISTERED", {"agent_id": agent_id,
                                               "display_name": display_name}, now=now)
        return ident

    def is_registered(self, agent_id):
        return agent_id in self._agents


class ConflictDetector:
    """TRUCE on cross-agent scope conflict (#426); human-only resolution."""

    def __init__(self, chain, registry, window_seconds=CONFLICT_WINDOW_SECONDS):
        self.chain = chain
        self.registry = registry
        self.window = window_seconds
        self._recent = {}
        self._frozen = set()

    def record_action(self, *, agent_id, scope, now=None):
        now = time.time() if now is None else now
        if not self.registry.is_registered(agent_id):
            raise ValueError(f"unregistered agent {agent_id!r} cannot act")
        if scope in self._frozen:
            return False
        prior = self._recent.get(scope)
        if prior and prior[0] != agent_id and now - prior[1] <= self.window:
            self._frozen.add(scope)
            self.chain.append("TRUCE", {"scope": scope, "agents": [prior[0], agent_id],
                                        "resolution": "human_approval_required"}, now=now)
            return False
        self._recent[scope] = (agent_id, now)
        return True

    def resolve_truce(self, scope, *, approval_authorized, actor, now=None):
        if not approval_authorized:
            raise PermissionError("truce resolution requires human approval")
        self._frozen.discard(scope)
        self._recent.pop(scope, None)  # resolution clears the slate
        self.chain.append("TRUCE_RESOLVED", {"scope": scope, "actor": actor}, now=now)

    def frozen(self, scope):
        return scope in self._frozen
