"""Defend effector guard — killinchu #399 §2 per spec #401.

Single choke point for every effectful request. Order is fixed and
non-bypassable: kill switch -> approval freshness -> scope allowlist ->
per-principal rate limit -> durable idempotency -> guarded effector call.
The guard never decides policy content itself; it enforces that the
decision path exists, is current, and is recorded. Default posture: deny.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum

from app.defend.durable_state import DurableState

RATE_LIMIT_PER_MINUTE = 60  # spec: 60 req/min/principal default


class Denial(str, Enum):
    KILL_SWITCH = "kill_switch_engaged"
    APPROVAL_STALE = "approval_stale_or_missing"
    SCOPE_DENIED = "scope_not_allowlisted"
    RATE_LIMITED = "rate_limit_exceeded"
    IDEMPOTENCY_REPLAY = "idempotent_replay"


@dataclass
class GuardDecision:
    allowed: bool
    denial: Denial | None = None
    replayed_response: dict | None = None
    effector_response: dict | None = None
    receipt_fragment: dict = field(default_factory=dict)


@dataclass
class Approval:
    approved_at_epoch: float
    ttl_seconds: int = 300  # approval freshness window, 5 min default

    def fresh(self, now: float) -> bool:
        return 0 <= now - self.approved_at_epoch <= self.ttl_seconds


class EffectorGuard:
    def __init__(self, store: DurableState, allowed_scopes: set[str],
                 kill_switch_engaged: bool = False,
                 rate_limit_per_minute: int = RATE_LIMIT_PER_MINUTE):
        self.store = store
        self.allowed_scopes = allowed_scopes
        self.kill_switch_engaged = kill_switch_engaged
        self.rate_limit = rate_limit_per_minute
        self._hits: dict[str, list[float]] = {}

    def _deny(self, denial: Denial, principal: str, scope: str) -> GuardDecision:
        return GuardDecision(allowed=False, denial=denial,
                             receipt_fragment={"principal": principal, "scope": scope,
                                               "denial": denial.value})

    def _rate_limited(self, principal: str, now: float) -> bool:
        window = [t for t in self._hits.get(principal, []) if now - t < 60]
        self._hits[principal] = window
        if len(window) >= self.rate_limit:
            return True
        window.append(now)
        return False

    def execute(self, *, principal: str, scope: str, idempotency_key: str,
                request_body: dict, approval: Approval | None,
                effector, now: float | None = None) -> GuardDecision:
        now = time.time() if now is None else now
        if self.kill_switch_engaged:
            return self._deny(Denial.KILL_SWITCH, principal, scope)
        if approval is None or not approval.fresh(now):
            return self._deny(Denial.APPROVAL_STALE, principal, scope)
        if scope not in self.allowed_scopes:
            return self._deny(Denial.SCOPE_DENIED, principal, scope)
        if self._rate_limited(principal, now):
            return self._deny(Denial.RATE_LIMITED, principal, scope)

        req_hash = hashlib.sha256(
            json.dumps(request_body, sort_keys=True).encode()).hexdigest()
        prior = self.store.idempotent_lookup(idempotency_key, req_hash)
        if prior is not None:
            return GuardDecision(allowed=False, denial=Denial.IDEMPOTENCY_REPLAY,
                                 replayed_response=prior,
                                 receipt_fragment={"principal": principal, "scope": scope,
                                                   "denial": Denial.IDEMPOTENCY_REPLAY.value})

        response = effector(request_body)
        self.store.idempotent_store(idempotency_key, req_hash, response)
        return GuardDecision(allowed=True, effector_response=response,
                             receipt_fragment={"principal": principal, "scope": scope,
                                               "idempotency_key": idempotency_key,
                                               "request_hash": req_hash})
