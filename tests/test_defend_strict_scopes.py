"""Tests for seam 8: strict scopes, withheld evals, checkpoints."""

import pytest

from app.defend.chain_store import PersistentAuditChain
from app.defend.strict_scopes import (SchemaViolation, ScopeSchemas,
                                      WithheldDrillRegistry, checkpoint,
                                      resume_verified, validate)

NOW = 1_760_000_000.0
SCHEMA = {"type": "object", "required": ["vlan"],
          "properties": {"vlan": {"type": "integer"},
                         "mode": {"type": "string", "enum": ["isolate", "restore"]}},
          "additionalProperties": False}
KEY = b"operator-drill-key-2026"


def _setup():
    chain = PersistentAuditChain()
    schemas = ScopeSchemas(chain)
    schemas.bind("net.segment", SCHEMA, now=NOW)
    return chain, schemas


def test_valid_body_passes_and_binding_is_chained():
    chain, schemas = _setup()
    schemas.check("net.segment", {"vlan": 7, "mode": "isolate"}, now=NOW + 1)
    bound = chain._conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type='SCOPE_SCHEMA_BOUND'").fetchone()[0]
    assert bound == 1


@pytest.mark.parametrize("bad", [
    {"vlan": "7"},                    # wrong type
    {"mode": "isolate"},              # missing required
    {"vlan": 7, "extra": 1},          # additionalProperties
    {"vlan": 7, "mode": "nuke"},      # enum violation
    {"vlan": True},                   # bool is not an integer
])
def test_invalid_bodies_rejected_and_chained(bad):
    chain, schemas = _setup()
    with pytest.raises(SchemaViolation):
        schemas.check("net.segment", bad, now=NOW + 2)
    rejected = chain._conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type='SCHEMA_REJECTED'").fetchone()[0]
    assert rejected == 1


def test_unknown_schema_keys_and_unbound_scope():
    with pytest.raises(SchemaViolation):
        validate({}, {"type": "object", "evil": "eval()"})
    _, schemas = _setup()
    schemas.check("logs.pull", {"anything": "goes"}, now=NOW + 3)


def test_withheld_drill_sealed_opened_and_chained():
    chain, _ = _setup()
    reg = WithheldDrillRegistry(chain)
    reg.register("drill-7", {"scenario": "ransomware in vlan 9"}, KEY, now=NOW + 4)
    assert b"ransomware" not in reg._sealed["drill-7"]
    out = reg.execute("drill-7", KEY, now=NOW + 5)
    assert out["scenario"] == "ransomware in vlan 9"
    with pytest.raises((UnicodeDecodeError, ValueError)):
        reg.execute("drill-7", b"wrong-key", now=NOW + 6)
    events = chain._conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type LIKE 'WITHHELD_DRILL%'").fetchone()[0]
    assert events == 2  # registered + executed; wrong key never chains


def test_checkpoint_and_resume_detect_rewritten_history():
    chain, _ = _setup()
    head_before = chain.head
    events_before = len(chain)
    cp = checkpoint(chain, now=NOW + 7)
    assert cp["payload"]["head"] == head_before
    assert cp["payload"]["events"] == events_before
    ok, msg = resume_verified(chain)
    assert ok and msg == "head matches checkpoint"
    chain.append("EFFECTOR_ALLOWED", {"principal": "perplexity"}, now=NOW + 8)
    ok2, msg2 = resume_verified(chain)
    assert ok2 and "extended" in msg2


def test_resume_fails_when_history_is_rewritten():
    chain, _ = _setup()
    checkpoint(chain, now=NOW + 7)
    chain._conn.execute("DELETE FROM audit_events WHERE seq = 1")
    ok, msg = resume_verified(chain)
    assert not ok
