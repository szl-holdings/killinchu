"""Defend kill switch + scope registry — killinchu #399 §5 per spec #401.

Two kill levels: GLOBAL halts every effectful scope; per-scope switches
halt one scope while the rest keep running. Engaging either level is an
unauthenticated-safe, always-permitted local action (you never need an
approval to stop things) and is always written to the audit chain.
Disengaging requires a fresh two-person approval — restarting effectors is
itself a high-blast-radius act. The scope registry is the single source of
truth the effector guard consults; unregistered scopes are not allowlisted
anywhere, which keeps the default posture deny.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from app.defend.audit_chain import AuditChain


class KillLevel(str, Enum):
    GLOBAL = "global"
    SCOPE = "scope"


@dataclass
class ScopeEntry:
    scope: str
    effector: str          # module/handler that executes the scope
    high_blast_radius: bool
    registered_at_epoch: float


class ScopeRegistry:
    """Single source of truth for what the guard may ever allow."""

    def __init__(self):
        self._scopes: dict[str, ScopeEntry] = {}

    def register(self, scope: str, effector: str, high_blast_radius: bool,
                 now: float | None = None) -> ScopeEntry:
        if scope in self._scopes:
            raise ValueError(f"scope {scope!r} already registered")
        entry = ScopeEntry(scope=scope, effector=effector,
                           high_blast_radius=high_blast_radius,
                           registered_at_epoch=time.time() if now is None else now)
        self._scopes[scope] = entry
        return entry

    def allowlist(self) -> set[str]:
        return set(self._scopes)

    def is_registered(self, scope: str) -> bool:
        return scope in self._scopes


class KillSwitch:
    """Global and per-scope halts. Engage freely; disengage via approval."""

    def __init__(self, chain: AuditChain):
        self._global = False
        self._scopes: set[str] = set()
        self.chain = chain

    def engage_global(self, *, actor: str, reason: str,
                      now: float | None = None) -> None:
        self._global = True
        self.chain.append("KILL_SWITCH_ENGAGED",
                          {"level": KillLevel.GLOBAL.value, "actor": actor,
                           "reason": reason}, now=now)

    def engage_scope(self, scope: str, *, actor: str, reason: str,
                     now: float | None = None) -> None:
        self._scopes.add(scope)
        self.chain.append("KILL_SWITCH_ENGAGED",
                          {"level": KillLevel.SCOPE.value, "scope": scope,
                           "actor": actor, "reason": reason}, now=now)

    def disengage_global(self, *, approval_authorized: bool, actor: str,
                         now: float | None = None) -> None:
        if not approval_authorized:
            raise PermissionError("disengaging the global kill switch requires "
                                  "a fresh two-person approval")
        self._global = False
        self.chain.append("KILL_SWITCH_DISENGAGED",
                          {"level": KillLevel.GLOBAL.value, "actor": actor}, now=now)

    def disengage_scope(self, scope: str, *, approval_authorized: bool,
                        actor: str, now: float | None = None) -> None:
        if not approval_authorized:
            raise PermissionError(f"disengaging kill switch for {scope!r} requires "
                                  "a fresh two-person approval")
        self._scopes.discard(scope)
        self.chain.append("KILL_SWITCH_DISENGAGED",
                          {"level": KillLevel.SCOPE.value, "scope": scope,
                           "actor": actor}, now=now)

    def halted(self, scope: str) -> bool:
        return self._global or scope in self._scopes

    def guard_flag(self) -> bool:
        """Feeds EffectorGuard.kill_switch_engaged each request."""
        return self._global
