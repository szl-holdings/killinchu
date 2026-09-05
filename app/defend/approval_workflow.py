"""Defend approval workflow — killinchu #399 §3 per spec #401, solo policy.

Durable, fail-closed approvals. Two policy modes:

- team (default): high-blast-radius scopes require two distinct approvers;
  nobody approves their own request.
- solo: an explicit operator-declared posture for single-operator builds.
  One approver suffices and self-approval is permitted — anything else
  would deadlock a solo operator. The mode is stamped on every request and
  carried into receipts, so the relaxed posture is always visible in audit.

Both modes share the invariants that never relax: justification required,
denials and expirations terminal, 5-minute TTL enforced, and
`authorization_for_guard` returns None for anything but a fresh APPROVED
request — the guard denies on None.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

APPROVAL_TTL_SECONDS = 300
HIGH_BLAST_RADIUS = {"host.quarantine", "net.segment", "account.disable"}


class PolicyMode(str, Enum):
    TEAM = "team"
    SOLO = "solo"


class RequestState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    request_id: str
    requester: str
    scope: str
    justification: str
    created_at_epoch: float
    policy_mode: PolicyMode
    approvers: list[str] = field(default_factory=list)
    denier: str | None = None
    state: RequestState = RequestState.PENDING

    @property
    def high_blast_radius(self) -> bool:
        return self.scope in HIGH_BLAST_RADIUS

    def required_approvers(self) -> int:
        if self.policy_mode == PolicyMode.SOLO:
            return 1
        return 2 if self.high_blast_radius else 1


class ApprovalWorkflow:
    """Fail-closed approval lifecycle: request -> approve/deny -> consume."""

    def __init__(self, ttl_seconds: int = APPROVAL_TTL_SECONDS,
                 policy_mode: PolicyMode = PolicyMode.TEAM):
        self.ttl = ttl_seconds
        self.policy_mode = PolicyMode(policy_mode)
        self._requests: dict[str, ApprovalRequest] = {}

    def request(self, *, requester: str, scope: str, justification: str,
                now: float | None = None) -> ApprovalRequest:
        if not justification.strip():
            raise ValueError("approval requests require a justification")
        req = ApprovalRequest(request_id=str(uuid.uuid4()), requester=requester,
                              scope=scope, justification=justification,
                              created_at_epoch=time.time() if now is None else now,
                              policy_mode=self.policy_mode)
        self._requests[req.request_id] = req
        return req

    def _terminal(self, req: ApprovalRequest) -> bool:
        return req.state in (RequestState.DENIED, RequestState.EXPIRED)

    def _expire_if_stale(self, req: ApprovalRequest, now: float) -> None:
        if req.state in (RequestState.PENDING, RequestState.APPROVED) and (
                now - req.created_at_epoch > self.ttl):
            req.state = RequestState.EXPIRED

    def approve(self, request_id: str, approver: str,
                now: float | None = None) -> ApprovalRequest:
        now = time.time() if now is None else now
        req = self._requests[request_id]
        self._expire_if_stale(req, now)
        if self._terminal(req):
            raise ValueError(f"request is {req.state.value}; re-request instead")
        if req.state == RequestState.APPROVED:
            raise ValueError("request already approved")
        if approver == req.requester and self.policy_mode != PolicyMode.SOLO:
            raise ValueError("requester cannot approve their own request in team mode")
        if approver in req.approvers:
            raise ValueError("approver has already voted on this request")
        req.approvers.append(approver)
        if len(req.approvers) >= req.required_approvers():
            req.state = RequestState.APPROVED
        return req

    def deny(self, request_id: str, denier: str,
             now: float | None = None) -> ApprovalRequest:
        now = time.time() if now is None else now
        req = self._requests[request_id]
        self._expire_if_stale(req, now)
        if self._terminal(req):
            raise ValueError(f"request is {req.state.value}; re-request instead")
        req.denier = denier
        req.state = RequestState.DENIED
        return req

    def authorization_for_guard(self, request_id: str, now: float | None = None):
        """Emit the guard-consumable approval, or None when not authorized."""
        from app.defend.effector_guard import Approval

        now = time.time() if now is None else now
        req = self._requests[request_id]
        self._expire_if_stale(req, now)
        if req.state != RequestState.APPROVED:
            return None
        return Approval(approved_at_epoch=req.created_at_epoch, ttl_seconds=self.ttl)
