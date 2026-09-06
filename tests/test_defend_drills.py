"""Tests for the Defend DR + load drills (killinchu #399 follow-up 4).

The DR drill proves a restored chain is byte-identical and verifies; the
load drill proves rate caps hold and the evidence itself lands in the chain.
"""

from app.defend.chain_store import PersistentAuditChain
from app.defend.drills import authz_load_drill, dr_restore_drill

NOW = 1_760_000_000.0


class _Decision:
    def __init__(self, allowed):
        self.allowed = allowed


class _Guard:
    """Minimal stand-in honoring the merged #411 guard contract."""

    def __init__(self, rate):
        self.rate_limit = rate
        self._hits = {}
        self._seen = set()

    def execute(self, *, principal, scope, idempotency_key, request_body,
                approval, effector, now):
        if idempotency_key in self._seen:
            return _Decision(False)
        window = [t for t in self._hits.get(principal, []) if now - t < 60]
        self._hits[principal] = window
        if len(window) >= self.rate_limit:
            return _Decision(False)
        window.append(now)
        self._seen.add(idempotency_key)
        effector(request_body)
        return _Decision(True)


def _populated_chain():
    chain = PersistentAuditChain()
    for i in range(5):
        chain.append("EFFECTOR_ALLOWED", {"i": i}, now=NOW + i)
    chain.record_backup("ab" * 32, now=NOW + 5)
    return chain


def test_dr_restore_is_byte_identical_and_verifies():
    result = dr_restore_drill(_populated_chain())
    assert result["byte_identical"]
    assert result["chain_verifies_after_restore"]
    assert result["events_restored"] == 6
    assert result["backups_restored"] == 1


def test_load_drill_enforces_caps_and_receipts_evidence():
    chain = PersistentAuditChain()
    ev = authz_load_drill(chain, _Guard(rate=3), principals=4,
                          requests_per_principal=5, now=NOW,
                          approval_factory=lambda now: object())
    assert ev["allowed"] == 12          # 4 principals x 3 under cap
    assert ev["denied"] == 8            # 4 principals x 2 above cap
    assert ev["max_decision_latency_ms"] >= 0
    row = chain._conn.execute("SELECT event_type FROM audit_events").fetchone()
    assert row[0] == "LOAD_DRILL_EVIDENCE"
    assert chain.verify()[0]


def test_dr_drill_on_chain_containing_load_evidence():
    chain = PersistentAuditChain()
    authz_load_drill(chain, _Guard(rate=3), principals=2,
                     requests_per_principal=4, now=NOW,
                     approval_factory=lambda now: object())
    result = dr_restore_drill(chain)
    assert result["byte_identical"] and result["chain_verifies_after_restore"]
