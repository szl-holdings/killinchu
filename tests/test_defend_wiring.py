"""Tests for the Defend composition root (killinchu #399 §6 / spec #401).

Full-drill tests: every path through the plane — denial, approval, kill
switch — must land in the audit chain, and the chain must verify at the end.
"""

from app.defend.effector_guard import Denial
from app.defend.wiring import assemble, handle_effector_request, readyz

NOW = 1_760_000_000.0
CALLS = {"n": 0}


def _eff(body):
    CALLS["n"] += 1
    return {"ok": True}


def _plane():
    plane = assemble(demo_mode=True)
    plane.registry.register("net.segment", effector="defend.effectors.net",
                            high_blast_radius=True, now=NOW)
    plane.registry.register("logs.pull", effector="defend.effectors.logs",
                            high_blast_radius=False, now=NOW)
    return plane


def test_readyz_aggregates_all_seams():
    ok, info = readyz(_plane())
    assert ok
    assert info["registry_scopes"] == 2
    assert info["audit_chain"]["intact"]


def test_no_approval_denied_and_audited():
    CALLS["n"] = 0
    plane = _plane()
    d = handle_effector_request(plane, principal="alice", scope="net.segment",
                                idempotency_key="w1", request_body={"vlan": 7},
                                approval_request_id=None, effector=_eff, now=NOW)
    assert d.denial == Denial.APPROVAL_STALE
    assert CALLS["n"] == 0
    assert plane.chain._events[-1].event_type == "EFFECTOR_DENIED"


def test_approved_path_allows_once_and_audits():
    CALLS["n"] = 0
    plane = _plane()
    req = plane.approvals.request(requester="alice", scope="net.segment",
                                  justification="isolate vlan 7", now=NOW)
    plane.approvals.approve(req.request_id, "bob", now=NOW)
    plane.approvals.approve(req.request_id, "carol", now=NOW)
    d = handle_effector_request(plane, principal="alice", scope="net.segment",
                                idempotency_key="w2", request_body={"vlan": 7},
                                approval_request_id=req.request_id, effector=_eff,
                                now=NOW + 30)
    assert d.allowed and CALLS["n"] == 1
    assert plane.chain._events[-1].event_type == "EFFECTOR_ALLOWED"


def test_unregistered_scope_denied_through_plane():
    plane = _plane()
    d = handle_effector_request(plane, principal="alice", scope="host.reimage",
                                idempotency_key="w3", request_body={},
                                approval_request_id=None, effector=_eff, now=NOW)
    assert d.denial == Denial.SCOPE_DENIED


def test_global_and_scope_kill_through_plane():
    CALLS["n"] = 0
    plane = _plane()
    plane.kill_switch.engage_global(actor="oncall", reason="drill", now=NOW)
    d = handle_effector_request(plane, principal="alice", scope="logs.pull",
                                idempotency_key="w4", request_body={},
                                approval_request_id=None, effector=_eff, now=NOW + 10)
    assert d.denial == Denial.KILL_SWITCH and CALLS["n"] == 0
    plane.kill_switch.disengage_global(approval_authorized=True, actor="oncall",
                                       now=NOW + 20)
    plane.kill_switch.engage_scope("net.segment", actor="oncall",
                                   reason="vlan flap", now=NOW + 30)
    req = plane.approvals.request(requester="alice", scope="logs.pull",
                                  justification="triage", now=NOW + 35)
    plane.approvals.approve(req.request_id, "bob", now=NOW + 40)
    d5 = handle_effector_request(plane, principal="alice", scope="net.segment",
                                 idempotency_key="w5", request_body={"vlan": 8},
                                 approval_request_id=None, effector=_eff, now=NOW + 45)
    d6 = handle_effector_request(plane, principal="alice", scope="logs.pull",
                                 idempotency_key="w6", request_body={"q": "x"},
                                 approval_request_id=req.request_id, effector=_eff,
                                 now=NOW + 45)
    assert d5.denial == Denial.KILL_SWITCH
    assert d6.allowed and CALLS["n"] == 1
    assert plane.chain.verify()[0]
