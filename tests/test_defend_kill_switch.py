"""Tests for the Defend kill switch + scope registry (#399 §5 / spec #401).

Pins the asymmetric property that must never regress: engaging a halt is
always permitted and audited; disengaging requires a two-person approval.
"""

import pytest

from app.defend.audit_chain import AuditChain
from app.defend.kill_switch import KillSwitch, ScopeRegistry

NOW = 1_760_000_000.0


def _registry() -> ScopeRegistry:
    reg = ScopeRegistry()
    reg.register("net.segment", effector="defend.effectors.net",
                 high_blast_radius=True, now=NOW)
    reg.register("logs.pull", effector="defend.effectors.logs",
                 high_blast_radius=False, now=NOW)
    return reg


def test_registry_allowlist_and_unregistered_default_deny():
    reg = _registry()
    assert reg.allowlist() == {"net.segment", "logs.pull"}
    assert not reg.is_registered("host.reimage")


def test_duplicate_registration_rejected():
    reg = _registry()
    with pytest.raises(ValueError):
        reg.register("net.segment", effector="dup",
                     high_blast_radius=False, now=NOW)


def test_global_engage_halts_everything_and_is_audited():
    chain = AuditChain()
    sw = KillSwitch(chain)
    assert not sw.guard_flag()
    sw.engage_global(actor="oncall", reason="ransomware note seen", now=NOW)
    assert sw.halted("net.segment") and sw.halted("logs.pull")
    assert sw.guard_flag()
    assert chain._events[-1].event_type == "KILL_SWITCH_ENGAGED"


def test_disengage_requires_approval_and_stays_halted_without_it():
    chain = AuditChain()
    sw = KillSwitch(chain)
    sw.engage_global(actor="oncall", reason="x", now=NOW)
    with pytest.raises(PermissionError):
        sw.disengage_global(approval_authorized=False, actor="oncall", now=NOW + 60)
    assert sw.guard_flag()


def test_approved_disengage_clears_and_is_audited():
    chain = AuditChain()
    sw = KillSwitch(chain)
    sw.engage_global(actor="oncall", reason="x", now=NOW)
    sw.disengage_global(approval_authorized=True, actor="oncall", now=NOW + 120)
    assert not sw.guard_flag()
    assert chain._events[-1].event_type == "KILL_SWITCH_DISENGAGED"
    assert chain.verify()[0]


def test_scope_halt_is_surgical():
    chain = AuditChain()
    sw = KillSwitch(chain)
    sw.engage_scope("net.segment", actor="oncall", reason="vlan 7 flap", now=NOW)
    assert sw.halted("net.segment")
    assert not sw.halted("logs.pull")
    sw.disengage_scope("net.segment", approval_authorized=True,
                       actor="oncall", now=NOW + 60)
    assert not sw.halted("net.segment")
    assert chain.verify()[0]
