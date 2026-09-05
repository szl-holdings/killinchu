"""Tests for the Defend audit chain + incident receipts (#399 §4 / spec #401).

Every test pins an append-only or tamper-evidence property that must never
regress.
"""

from app.defend.audit_chain import GENESIS, AuditChain, seal_incident_receipt

NOW = 1_760_000_000.0


def test_empty_chain_verifies():
    assert AuditChain().verify() == (True, None)


def test_chain_links_from_genesis():
    chain = AuditChain()
    e1 = chain.append("EFFECTOR_ALLOWED", {"principal": "alice"}, now=NOW)
    e2 = chain.append("BACKUP_COMMITTED", {"dump_sha256": "ab" * 32}, now=NOW + 1)
    assert e1.prior_hash == GENESIS
    assert e2.prior_hash == e1.event_hash
    assert chain.head == e2.event_hash
    assert chain.verify()[0]


def test_tamper_is_detected_and_names_broken_link():
    chain = AuditChain()
    e1 = chain.append("EFFECTOR_ALLOWED", {"principal": "alice"}, now=NOW)
    chain.append("BACKUP_COMMITTED", {"dump_sha256": "ab" * 32}, now=NOW + 1)
    chain._events[0].payload["principal"] = "mallory"
    ok, broken = chain.verify()
    assert not ok and broken == e1.event_id


def test_deletion_breaks_chain():
    chain = AuditChain()
    for i in range(3):
        chain.append("EFFECTOR_ALLOWED", {"i": i}, now=NOW + i)
    del chain._events[1]
    assert not chain.verify()[0]


def test_seal_incident_receipt_fields_and_anchor():
    chain = AuditChain()
    trig = chain.append("INCIDENT_TRIGGERED", {"signal": "edr:x"}, now=NOW)
    receipt = seal_incident_receipt(
        chain, trigger_event_hash=trig.event_hash,
        environment_snapshot={"hosts": 42},
        timeline=[{"t": NOW, "action": "net.segment"}],
        blast_radius={"isolated_hosts": 12},
        backup_dump_sha256="cd" * 32, now=NOW + 5)
    assert receipt.trigger_event_hash == trig.event_hash
    assert receipt.environment_snapshot["hosts"] == 42
    assert receipt.blast_radius["isolated_hosts"] == 12
    assert receipt.backup_dump_sha256 == "cd" * 32
    assert len(receipt.timeline_hash) == 64
    assert len(receipt.receipt_hash) == 64
    assert len(chain) == 3  # trigger + BACKUP_COMMITTED + RECEIPT_SEALED
    assert chain.verify()[0]
    sealed = chain._events[-1]
    assert sealed.event_type == "RECEIPT_SEALED"
    assert sealed.payload["receipt_hash"] == receipt.receipt_hash


def test_no_update_or_delete_api():
    chain = AuditChain()
    assert not hasattr(chain, "update")
    assert not hasattr(chain, "delete")
