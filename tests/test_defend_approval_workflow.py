"""Tests for the Defend approval workflow (killinchu #399 §3 / spec #401).

Every test pins a fail-closed or two-person property that must never regress.
The end-to-end test proves approvals flow through the merged effector guard.
"""

import pytest

from app.defend.approval_workflow import ApprovalWorkflow, RequestState
from app.defend.durable_state import DurableState
from app.defend.effector_guard import EffectorGuard

NOW = 1_760_000_000.0


def test_high_blast_radius_requires_two_approvers():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    assert r.required_approvers() == 2


def test_requester_cannot_self_approve():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    with pytest.raises(ValueError):
        w.approve(r.request_id, "alice", now=NOW)


def test_two_person_flow_and_guard_integration():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    w.approve(r.request_id, "bob", now=NOW)
    assert r.state == RequestState.PENDING
    assert w.authorization_for_guard(r.request_id, now=NOW) is None
    with pytest.raises(ValueError):
        w.approve(r.request_id, "bob", now=NOW)  # double vote
    w.approve(r.request_id, "carol", now=NOW)
    assert r.state == RequestState.APPROVED
    authz = w.authorization_for_guard(r.request_id, now=NOW + 60)
    assert authz is not None and authz.fresh(NOW + 60)


def test_expired_approval_never_authorizes():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    w.approve(r.request_id, "bob", now=NOW)
    w.approve(r.request_id, "carol", now=NOW)
    assert w.authorization_for_guard(r.request_id, now=NOW + 400) is None
    assert r.state == RequestState.EXPIRED


def test_normal_scope_needs_one_approver():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="logs.pull",
                  justification="triage", now=NOW)
    assert r.required_approvers() == 1


def test_denial_is_terminal_and_never_authorizes():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="logs.pull",
                  justification="triage", now=NOW)
    w.deny(r.request_id, "bob", now=NOW)
    assert r.state == RequestState.DENIED
    with pytest.raises(ValueError):
        w.approve(r.request_id, "carol", now=NOW)
    assert w.authorization_for_guard(r.request_id, now=NOW) is None


def test_empty_justification_rejected():
    with pytest.raises(ValueError):
        ApprovalWorkflow().request(requester="alice", scope="logs.pull",
                                   justification="   ", now=NOW)


def test_end_to_end_approval_flows_through_guard():
    w = ApprovalWorkflow()
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    w.approve(r.request_id, "bob", now=NOW)
    w.approve(r.request_id, "carol", now=NOW)
    authz = w.authorization_for_guard(r.request_id, now=NOW + 30)
    guard = EffectorGuard(DurableState(demo_mode=True),
                          allowed_scopes={"net.segment", "logs.pull"})
    dec = guard.execute(principal="alice", scope="net.segment",
                        idempotency_key="e2e1", request_body={"vlan": 7},
                        approval=authz, effector=lambda b: {"ok": True}, now=NOW + 30)
    assert dec.allowed
