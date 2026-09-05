"""Tests for the Defend effector guard (killinchu #399 §2 / spec #401).

The guard is the single choke point; every test here pins an ordering or
default-deny property that must never regress.
"""

from app.defend.durable_state import DurableState
from app.defend.effector_guard import Approval, Denial, EffectorGuard

NOW = 1_760_000_000.0
CALLS = {"n": 0}


def fake_effector(body):
    CALLS["n"] += 1
    return {"effected": True, "body": body}


def fresh_guard(**kw):
    return EffectorGuard(DurableState(demo_mode=True),
                         allowed_scopes={"net.segment", "host.quarantine"}, **kw)


def test_happy_path_allows_and_calls_effector_once():
    CALLS["n"] = 0
    r = fresh_guard().execute(principal="op", scope="net.segment", idempotency_key="k1",
                              request_body={"a": 1}, approval=Approval(NOW - 10),
                              effector=fake_effector, now=NOW)
    assert r.allowed and CALLS["n"] == 1


def test_replay_serves_stored_response_without_recalling_effector():
    CALLS["n"] = 0
    g = fresh_guard()
    appr = Approval(NOW - 10)
    g.execute(principal="op", scope="net.segment", idempotency_key="k1",
              request_body={"a": 1}, approval=appr, effector=fake_effector, now=NOW)
    r = g.execute(principal="op", scope="net.segment", idempotency_key="k1",
                  request_body={"a": 1}, approval=appr, effector=fake_effector, now=NOW + 1)
    assert r.denial == Denial.IDEMPOTENCY_REPLAY
    assert r.replayed_response == {"effected": True, "body": {"a": 1}}
    assert CALLS["n"] == 1


def test_kill_switch_denies_before_anything_else():
    r = fresh_guard(kill_switch_engaged=True).execute(
        principal="op", scope="net.segment", idempotency_key="k2", request_body={},
        approval=Approval(NOW - 10), effector=fake_effector, now=NOW)
    assert r.denial == Denial.KILL_SWITCH


def test_stale_and_missing_approval_both_deny():
    g = fresh_guard()
    stale = g.execute(principal="op", scope="net.segment", idempotency_key="k3",
                      request_body={}, approval=Approval(NOW - 999),
                      effector=fake_effector, now=NOW)
    missing = g.execute(principal="op", scope="net.segment", idempotency_key="k3b",
                        request_body={}, approval=None, effector=fake_effector, now=NOW)
    assert stale.denial == Denial.APPROVAL_STALE
    assert missing.denial == Denial.APPROVAL_STALE


def test_non_allowlisted_scope_denies():
    r = fresh_guard().execute(principal="op", scope="host.reimage", idempotency_key="k4",
                              request_body={}, approval=Approval(NOW - 10),
                              effector=fake_effector, now=NOW)
    assert r.denial == Denial.SCOPE_DENIED


def test_rate_limit_denies_after_cap():
    g = fresh_guard(rate_limit_per_minute=2)
    res = [g.execute(principal="op", scope="net.segment", idempotency_key=f"rl{i}",
                     request_body={"i": i}, approval=Approval(NOW - 10),
                     effector=fake_effector, now=NOW) for i in range(3)]
    assert all(x.allowed for x in res[:2])
    assert res[2].denial == Denial.RATE_LIMITED


def test_order_fixed_approval_checked_before_scope_and_rate():
    g = fresh_guard(rate_limit_per_minute=1)
    r = g.execute(principal="attacker", scope="not.a.scope", idempotency_key="z",
                  request_body={}, approval=None, effector=fake_effector, now=NOW)
    assert r.denial == Denial.APPROVAL_STALE


def test_receipt_fragment_always_present():
    g = fresh_guard()
    allow = g.execute(principal="op", scope="net.segment", idempotency_key="k9",
                      request_body={"a": 1}, approval=Approval(NOW - 10),
                      effector=fake_effector, now=NOW)
    deny = g.execute(principal="op", scope="host.reimage", idempotency_key="k9b",
                     request_body={}, approval=Approval(NOW - 10),
                     effector=fake_effector, now=NOW)
    assert allow.receipt_fragment and deny.receipt_fragment
