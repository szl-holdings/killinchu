"""Defend approval workflow — killinchu #399 §3 per spec #401.

Durable, fail-closed approvals. Two-person rule: high-blast-radius scopes
require two distinct approvers, and no approver may be the requester.
Approvals carry a 5-minute TTL consumed by the effector guard; expired
approvals never authorize. Denials and expirations are terminal — a denied
request must be re-requested, not re-voted.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

APPROVAL_TTL_SECONDS = 300  # consumed by the effector guard freshness check
HIGH_BLAST_RADIUS = {"host.quarantine", "net.segment", "account.disable"}


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
    approvers: list[str] = field(default_factory=list)
    denier: str | None = None
    state: RequestState = RequestState.PENDING

    @property
    def high_blast_radius(self) -> bool:
        return self.scope in HIGH_BLAST_RADIUS

    def required_approvers(self) -> int:
        return 2 if self.high_blast_radius else 1


class ApprovalWorkflow:
    """Fail-closed approval lifecycle: request -> approve/deny -> consume."""

    def __init__(self, ttl_seconds: int = APPROVAL_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._requests: dict[str, ApprovalRequest] = {}

    def request(self, *, requester: str, scope: str, justification: str,
                now: float | None = None) -> ApprovalRequest:
        if not justification.strip():
            raise ValueError("approval requests require a justification")
        req = ApprovalRequest(request_id=str(uuid.uuid4()), requester=requester,
                              scope=scope, justification=justification,
                              created_at_epoch=time.time() if now is None else now)
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
        if approver == req.requester:
            raise ValueError("requester cannot approve their own request")
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
        """Emit the guard-consumable approval, or None when not authorized.

        Fail-closed: anything other than a fresh APPROVED request yields None,
        and the guard denies on None.
        """
        from app.defend.effector_guard import Approval

        now = time.time() if now is None else now
        req = self._requests[request_id]
        self._expire_if_stale(req, now)
        if req.state != RequestState.APPROVED:
            return None
        return Approval(approved_at_epoch=req.created_at_epoch, ttl_seconds=self.ttl)
