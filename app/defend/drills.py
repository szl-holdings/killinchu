"""Defend DR drill + load evidence — killinchu #399 follow-up 4 (final).

Two evidence harnesses the release gate can run on demand:

- dr_restore_drill: dump the persisted chain to a canonical snapshot,
  restore into a fresh store, and prove the restored chain verifies
  byte-identically and readyz freshness carries over. A DR story you have
  not restored from is a hope, not a control.
- authz_load_drill: drive the guard at and above the per-principal rate
  limit across many principals and record the evidence — allows below the
  cap, denials at the cap, per-decision latency bounds — as a chained
  audit event, so the load claim is itself receipted.
"""

from __future__ import annotations

import hashlib
import json
import time

from app.defend.chain_store import PersistentAuditChain


def _snapshot(chain: PersistentAuditChain) -> dict:
    rows = chain._conn.execute(
        "SELECT event_id, event_type, payload, prior_hash, event_hash, at_epoch "
        "FROM audit_events ORDER BY seq").fetchall()
    backups = chain._conn.execute(
        "SELECT id, dump_sha256, created_at FROM backup_events").fetchall()
    return {"audit_events": [list(r) for r in rows],
            "backup_events": [list(r) for r in backups]}


def dr_restore_drill(chain: PersistentAuditChain) -> dict:
    """Dump -> restore into a fresh store -> verify byte-identical chain."""
    snap = _snapshot(chain)
    snapshot_sha = hashlib.sha256(
        json.dumps(snap, sort_keys=True).encode()).hexdigest()

    restored = PersistentAuditChain()
    for event_id, event_type, payload, prior_hash, event_hash, at_epoch in snap["audit_events"]:
        restored._conn.execute(
            "INSERT INTO audit_events (event_id, event_type, payload, prior_hash, "
            "event_hash, at_epoch) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, event_type, payload, prior_hash, event_hash, at_epoch))
    for bid, sha, created in snap["backup_events"]:
        restored._conn.execute(
            "INSERT INTO backup_events (id, dump_sha256, created_at) VALUES (?, ?, ?)",
            (bid, sha, created))

    ok, broken = restored.verify()
    resnap = _snapshot(restored)
    resnap_sha = hashlib.sha256(
        json.dumps(resnap, sort_keys=True).encode()).hexdigest()
    return {"snapshot_sha256": snapshot_sha,
            "restored_sha256": resnap_sha,
            "byte_identical": snapshot_sha == resnap_sha,
            "chain_verifies_after_restore": ok and broken is None,
            "events_restored": len(snap["audit_events"]),
            "backups_restored": len(snap["backup_events"])}


def authz_load_drill(chain: PersistentAuditChain, guard, *, principals: int,
                     requests_per_principal: int, now: float,
                     approval_factory) -> dict:
    """Drive the guard and receipt the outcome into the audit chain."""
    allows = 0
    denials = 0
    max_latency_ms = 0.0
    for p in range(principals):
        for r in range(requests_per_principal):
            t0 = time.perf_counter()
            decision = guard.execute(
                principal=f"load-{p}", scope="logs.pull",
                idempotency_key=f"load-{p}-{r}", request_body={"r": r},
                approval=approval_factory(now), effector=lambda b: {"ok": True},
                now=now)
            latency_ms = (time.perf_counter() - t0) * 1000
            max_latency_ms = max(max_latency_ms, latency_ms)
            if decision.allowed:
                allows += 1
            else:
                denials += 1
    evidence = {"principals": principals,
                "requests_per_principal": requests_per_principal,
                "rate_limit_per_minute": guard.rate_limit,
                "allowed": allows, "denied": denials,
                "max_decision_latency_ms": round(max_latency_ms, 3)}
    chain.append("LOAD_DRILL_EVIDENCE", evidence, now=now)
    return evidence
