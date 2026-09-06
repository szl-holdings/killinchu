"""Tests for Defend chain persistence (killinchu #399 follow-up 3).

SQLite-file backed tests prove real persistence: the chain survives reopen,
continues from the stored head, and any tampering with or deletion of a
persisted row breaks verification.
"""

import json

from app.defend.chain_store import GENESIS, PersistentAuditChain

NOW = 1_760_000_000.0


def test_empty_chain_verifies_and_backup_age_none():
    chain = PersistentAuditChain()
    assert chain.verify() == (True, None)
    assert chain.latest_backup_age_hours(now=NOW) is None


def test_chain_links_from_genesis_and_verifies():
    chain = PersistentAuditChain()
    e1 = chain.append("EFFECTOR_ALLOWED", {"principal": "stephen"}, now=NOW)
    e2 = chain.append("KILL_SWITCH_ENGAGED", {"level": "global"}, now=NOW + 1)
    assert e1["prior_hash"] == GENESIS
    assert e2["prior_hash"] == e1["event_hash"]
    assert chain.verify()[0]


def test_chain_survives_reopen_and_continues(tmp_path):
    path = str(tmp_path / "audit.db")
    c1 = PersistentAuditChain(path)
    a = c1.append("EFFECTOR_ALLOWED", {"i": 1}, now=NOW)
    c1._conn.close()
    c2 = PersistentAuditChain(path)
    assert len(c2) == 1 and c2.verify()[0]
    b = c2.append("EFFECTOR_ALLOWED", {"i": 2}, now=NOW + 1)
    assert b["prior_hash"] == a["event_hash"]


def test_backup_event_is_chained_and_age_computed():
    chain = PersistentAuditChain()
    rec = chain.record_backup("ab" * 32, now=NOW)
    assert rec["event_type"] == "BACKUP_COMMITTED"
    assert abs(chain.latest_backup_age_hours(now=NOW + 3600) - 1.0) < 0.01
    assert chain.latest_backup_age_hours(now=NOW + 40 * 3600) > 36
    assert chain.verify()[0]


def test_persisted_tamper_and_deletion_are_detected():
    chain = PersistentAuditChain()
    chain.record_backup("ab" * 32, now=NOW)
    chain._conn.execute("UPDATE audit_events SET payload = ? WHERE seq = 1",
                        (json.dumps({"dump_sha256": "ff" * 32}),))
    assert not chain.verify()[0]

    c2 = PersistentAuditChain()
    for i in range(3):
        c2.append("EFFECTOR_ALLOWED", {"i": i}, now=NOW + i)
    c2._conn.execute("DELETE FROM audit_events WHERE seq = 2")
    assert not c2.verify()[0]
