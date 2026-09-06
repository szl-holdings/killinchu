"""Tests for the Defend coordination ledger (killinchu seam 7)."""

import pytest

from app.defend.chain_store import PersistentAuditChain
from app.defend.coordination import (AgentRegistry, ConflictDetector,
                                     coordination_telemetry, reputation)

NOW = 1_760_000_000.0


def _setup():
    chain = PersistentAuditChain()
    reg = AgentRegistry(chain)
    reg.register("perplexity", "Perplexity", now=NOW)
    reg.register("codex", "Codex", now=NOW)
    return chain, reg, ConflictDetector(chain, reg)


def test_registration_is_chained_and_unique():
    chain, reg, _ = _setup()
    count = chain._conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type='AGENT_REGISTERED'").fetchone()[0]
    assert count == 2
    with pytest.raises(ValueError):
        reg.register("perplexity", "dupe", now=NOW)


def test_conflict_inside_window_truces_and_freezes_both():
    chain, _, det = _setup()
    assert det.record_action(agent_id="perplexity", scope="net.segment", now=NOW)
    assert det.record_action(agent_id="perplexity", scope="net.segment", now=NOW + 60)
    assert not det.record_action(agent_id="codex", scope="net.segment", now=NOW + 120)
    assert det.frozen("net.segment")
    assert not det.record_action(agent_id="perplexity", scope="net.segment", now=NOW + 130)
    truces = chain._conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type='TRUCE'").fetchone()[0]
    assert truces == 1


def test_truce_resolution_requires_human_approval():
    _, _, det = _setup()
    det.record_action(agent_id="perplexity", scope="net.segment", now=NOW)
    det.record_action(agent_id="codex", scope="net.segment", now=NOW + 60)
    with pytest.raises(PermissionError):
        det.resolve_truce("net.segment", approval_authorized=False,
                          actor="stephen", now=NOW + 200)
    det.resolve_truce("net.segment", approval_authorized=True,
                      actor="stephen", now=NOW + 210)
    assert not det.frozen("net.segment")


def test_unregistered_agent_cannot_act():
    _, _, det = _setup()
    with pytest.raises(ValueError):
        det.record_action(agent_id="rogue", scope="logs.pull", now=NOW)


def test_outside_window_is_not_a_conflict():
    _, _, det = _setup()
    det.record_action(agent_id="perplexity", scope="host.quarantine", now=NOW)
    assert det.record_action(agent_id="codex", scope="host.quarantine",
                             now=NOW + 400)


def test_reputation_derives_from_chain():
    chain, _, _ = _setup()
    chain.append("EFFECTOR_ALLOWED", {"principal": "perplexity"}, now=NOW)
    chain.append("EFFECTOR_ALLOWED", {"principal": "perplexity"}, now=NOW + 1)
    chain.append("EFFECTOR_DENIED",
                 {"principal": "perplexity", "denial": "rate_limit_exceeded"},
                 now=NOW + 2)
    rep = reputation(chain, "perplexity")
    assert rep["allowed"] == 2 and rep["denied"] == 1
    assert abs(rep["allow_rate"] - 2 / 3) < 1e-9


def test_telemetry_computed_and_chained():
    chain, _, _ = _setup()
    tel = coordination_telemetry(chain, prs_proposed=30, prs_merged=24,
                                 files_shared=12, files_total=100, now=NOW)
    assert tel["pr_merge_fraction"] == 0.8
    assert tel["code_share_fraction"] == 0.12
    assert chain.verify()[0]
