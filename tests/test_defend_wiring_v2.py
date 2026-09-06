"""Tests for the v2 composition root (killinchu seam 9).

Full-stack order is pinned: identity -> schema -> conflict -> kill ->
approval -> allowlist -> rate -> idempotency -> effector. Every outcome
is chained. Includes the truce-resolution slate regression.
"""

from app.defend.effector_guard import Approval
from app.defend.wiring_v2 import (assemble_v2, handle_effector_request, readyz)

NOW = 1_760_000_000.0
CALLS = {"n": 0}


def _eff(body):
    CALLS["n"] += 1
    return {"ok": True}


def _plane():
    p = assemble_v2(demo_mode=True)
    p.registry.register("net.segment", effector="defend.effectors.net",
                        high_blast_radius=True, now=NOW)
    p.registry.register("logs.pull", effector="defend.effectors.logs",
                        high_blast_radius=False, now=NOW)
    p.agents.register("perplexity", "Perplexity", now=NOW)
    p.agents.register("codex", "Codex", now=NOW)
    return p


APPR = Approval(approved_at_epoch=NOW - 10)


def test_unregistered_agent_denied_before_anything():
    CALLS["n"] = 0
    d = handle_effector_request(_plane(), agent_id="rogue", scope="net.segment",
                                idempotency_key="a", request_body={}, approval=APPR,
                                effector=_eff, now=NOW)
    assert d.receipt_fragment["denial"] == "unregistered_agent"
    assert CALLS["n"] == 0


def test_schema_rejection_precedes_hashing_and_effector():
    CALLS["n"] = 0
    p = _plane()
    p.schemas.bind("net.segment", {"type": "object", "required": ["vlan"],
                                   "properties": {"vlan": {"type": "integer"}},
                                   "additionalProperties": False}, now=NOW)
    d = handle_effector_request(p, agent_id="perplexity", scope="net.segment",
                                idempotency_key="b", request_body={"vlan": "7"},
                                approval=APPR, effector=_eff, now=NOW)
    assert d.receipt_fragment["denial"] == "schema_rejected"
    assert CALLS["n"] == 0
    ok = handle_effector_request(p, agent_id="perplexity", scope="net.segment",
                                 idempotency_key="c", request_body={"vlan": 7},
                                 approval=APPR, effector=_eff, now=NOW + 5)
    assert ok.allowed and CALLS["n"] == 1


def test_truce_freezes_both_and_human_resolution_clears_slate():
    p = _plane()
    handle_effector_request(p, agent_id="perplexity", scope="logs.pull",
                            idempotency_key="d1", request_body={}, approval=APPR,
                            effector=_eff, now=NOW)
    d2 = handle_effector_request(p, agent_id="codex", scope="logs.pull",
                                 idempotency_key="d2", request_body={}, approval=APPR,
                                 effector=_eff, now=NOW + 60)
    assert d2.receipt_fragment["denial"] == "truce_frozen"
    d3 = handle_effector_request(p, agent_id="perplexity", scope="logs.pull",
                                 idempotency_key="d3", request_body={}, approval=APPR,
                                 effector=_eff, now=NOW + 70)
    assert d3.receipt_fragment["denial"] == "truce_frozen"
    p.conflicts.resolve_truce("logs.pull", approval_authorized=True,
                              actor="stephen", now=NOW + 80)
    d4 = handle_effector_request(p, agent_id="codex", scope="logs.pull",
                                 idempotency_key="d4", request_body={}, approval=APPR,
                                 effector=_eff, now=NOW + 90)
    assert d4.allowed  # resolution cleared the slate; no instant re-freeze


def test_kill_switch_denies_within_full_stack():
    p = _plane()
    p.kill_switch.engage_scope("net.segment", actor="oncall", reason="flap", now=NOW)
    d = handle_effector_request(p, agent_id="perplexity", scope="net.segment",
                                idempotency_key="e", request_body={}, approval=APPR,
                                effector=_eff, now=NOW + 1)
    assert d.receipt_fragment["denial"] == "kill_switch_engaged"


def test_readyz_aggregates_and_chain_verifies_after_drill():
    p = _plane()
    handle_effector_request(p, agent_id="perplexity", scope="logs.pull",
                            idempotency_key="f", request_body={}, approval=APPR,
                            effector=_eff, now=NOW)
    ok, info = readyz(p)
    assert ok and info["registry_scopes"] == 2 and info["audit_chain"]["intact"]
    assert p.chain.verify()[0]
