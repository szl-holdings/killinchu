"""Tests for the solo-operator approval policy (killinchu #399 follow-up).

Solo mode exists because a single-operator build cannot produce two distinct
approvers — without it the two-person rule deadlocks the only operator. The
mode is explicit and stamped on every request; team mode stays the default
and is unchanged.
"""

import pytest

from app.defend.approval_workflow import (ApprovalWorkflow, PolicyMode,
                                          RequestState)

NOW = 1_760_000_000.0


def test_solo_mode_needs_one_approver_even_for_high_blast_radius():
    w = ApprovalWorkflow(policy_mode="solo")
    r = w.request(requester="stephen", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    assert r.required_approvers() == 1


def test_solo_mode_permits_self_approval_and_stamps_mode():
    w = ApprovalWorkflow(policy_mode="solo")
    r = w.request(requester="stephen", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    w.approve(r.request_id, "stephen", now=NOW)
    assert r.state == RequestState.APPROVED
    assert r.policy_mode == PolicyMode.SOLO
    authz = w.authorization_for_guard(r.request_id, now=NOW + 30)
    assert authz is not None and authz.fresh(NOW + 30)


def test_solo_mode_still_fail_closed_on_expiry_and_denial():
    w = ApprovalWorkflow(policy_mode="solo")
    r = w.request(requester="stephen", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    w.approve(r.request_id, "stephen", now=NOW)
    assert w.authorization_for_guard(r.request_id, now=NOW + 400) is None
    r2 = w.request(requester="stephen", scope="logs.pull",
                   justification="triage", now=NOW)
    w.deny(r2.request_id, "stephen", now=NOW)
    with pytest.raises(ValueError):
        w.approve(r2.request_id, "stephen", now=NOW)
    assert w.authorization_for_guard(r2.request_id, now=NOW) is None


def test_team_mode_is_default_and_unchanged():
    w = ApprovalWorkflow()
    assert w.policy_mode == PolicyMode.TEAM
    r = w.request(requester="alice", scope="net.segment",
                  justification="isolate vlan 7", now=NOW)
    assert r.required_approvers() == 2
    with pytest.raises(ValueError):
        w.approve(r.request_id, "alice", now=NOW)
