# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""tests/test_roe_decisions_api.py — the evidence-first API additions:

  * POST /roe/evaluate PERSISTS the gate evaluation with its receipt and
    GET /roe/decisions serves it back (paginated, filterable) — the ROE audit
    view's data feed;
  * POST /engagements/record closes under the SIMULATED 3-of-4 witness quorum
    (genuine MeshHarness(4) votes) or honestly reports UNAVAILABLE — never a
    fabricated certificate;
  * GET /engagements/after-action exports the bundle for a track and the
    /{record_id}/after-action pins one closure; empty tracks 404 with an
    audited empty_state (Zero-Bandaid — never a blank 200).

Lightweight: a fresh FastAPI app + in-test ledger (serve.py is not imported —
these tests pin the MODULE contracts, and the serve wiring is try/except-
guarded ADDITIVE).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import killinchu_after_action as aar  # noqa: E402
import killinchu_parity as parity  # noqa: E402


# ---------------------------------------------------------------------------
# In-test ledger (mirrors serve.py _emit_receipt construction; UNSIGNED-honest
# — the module contract under test is evidence bookkeeping, not signing).
# ---------------------------------------------------------------------------

class _Ledger:
    def __init__(self):
        self.nodes = []

    def emit(self, kind, payload):
        parents = [self.nodes[-1]["digest"]] if self.nodes else []
        receipt = {"schema": "szl.killinchu.receipt/v1", "kind": kind,
                   "payload": payload, "doctrine": "v11",
                   "ts_utc": "2026-09-30T00:00:00+00:00"}
        h = hashlib.sha256()
        h.update(json.dumps(receipt, sort_keys=True).encode())
        for p in parents:
            h.update(p.encode())
        node = {"index": len(self.nodes), "receipt": receipt, "parents": parents,
                "dsse": {"payloadType": "application/vnd.szl.receipt+json",
                         "signatures": [], "signed": False, "keyid": None},
                "signed": False, "ts_utc": receipt["ts_utc"],
                "digest": h.hexdigest()}
        self.nodes.append(node)
        return node


@pytest.fixture()
def client():
    ledger = _Ledger()
    # reset module rings so each test sees a clean runtime
    parity._ROE_DECISIONS.clear()
    parity._AUDIT_LOG.clear()
    parity._TRACK_HISTORY.clear()

    app = FastAPI()
    parity.register(app, emit_receipt=ledger.emit, ns="killinchu")
    aar.register(
        app, emit_receipt=ledger.emit, ns="killinchu",
        ledger_readiness=lambda: {"ready": True, "durability_state": "IN_MEMORY",
                                  "production_ready": False},
        ledger_snapshot=lambda: list(ledger.nodes),
    )
    return TestClient(app), ledger


def _evaluate(c, track_id="TRK-0001", speed=120.0):
    return c.post("/api/killinchu/v1/roe/evaluate", json={
        "telemetry": {"track_id": track_id, "speed_m_s": speed, "altitude_m": 80,
                      "latitude": -13.53, "longitude": -71.97,
                      "classification": "HOSTILE"},
    })


# ---------------------------------------------------------------------------
# ROE gate-decision persistence + feed
# ---------------------------------------------------------------------------

def test_evaluate_persists_decision_with_receipt(client):
    c, ledger = client
    r = _evaluate(c)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["decision_id"].startswith("ROE-")
    assert body["verdict"] in {"REVIEW", "ENGAGE", "SUSPECT", "ALLOW"}

    feed = c.get("/api/killinchu/v1/roe/decisions").json()
    assert feed["ok"] is True
    assert feed["total"] == 1
    d = feed["decisions"][0]
    assert d["decision_id"] == body["decision_id"]
    assert d["verdict"] == body["verdict"]
    # receipt coordinates bind the decision into the chain
    assert d["receipt"]["digest"] == body["roe_receipt"]["digest"]
    assert d["receipt"]["signed"] is False  # unsigned-honest test ledger
    assert d["policy_hash"] and len(d["policy_hash"]) == 64
    # the receipt really is the ledger node at that index
    node = ledger.nodes[d["receipt"]["index"]]
    assert node["digest"] == d["receipt"]["digest"]
    assert node["receipt"]["kind"] == "roe_decision"


def test_decisions_feed_filters_and_empty_state(client):
    c, _ = client
    _evaluate(c, track_id="TRK-0001", speed=120.0)
    _evaluate(c, track_id="TRK-0002", speed=5.0)  # slow → likely ALLOW
    feed = c.get("/api/killinchu/v1/roe/decisions", params={"track_id": "TRK-0002"}).json()
    assert feed["total"] == 1
    assert feed["decisions"][0]["track_id"] == "TRK-0002"
    # a never-evaluated track reports an audited 0 — never a blank
    empty = c.get("/api/killinchu/v1/roe/decisions", params={"track_id": "NOPE"}).json()
    assert empty["total"] == 0 and empty["decisions"] == []
    assert "in-memory" in empty["honesty"]


# ---------------------------------------------------------------------------
# Witness-quorum engagement closure (SIMULATED, honestly labelled)
# ---------------------------------------------------------------------------

def test_engagement_record_closes_under_witness_quorum(client):
    c, _ = client
    r = c.post("/api/killinchu/v1/engagements/record", json={
        "track_id": "TRK-0001", "verdict": "HOLD", "effector": "EW_JAM",
        "operator_id": "OP-DEMO", "lambda_at_decision": 0.88,
    })
    assert r.status_code == 200
    record = r.json()["record"]
    wq = record.get("witness_quorum")
    assert wq is not None, "closure must carry a witness_quorum block"
    assert wq["state"] in {"CANONICAL", "REJECTED", "UNAVAILABLE"}
    assert wq["record_hash"] and len(wq["record_hash"]) == 64
    if wq["state"] == "CANONICAL":
        # genuine quorum: real per-vote ECDSA material, honestly labelled
        assert wq["quorum_mode"] == "SIMULATED_IN_PROCESS"
        assert wq["allow_count"] >= wq["threshold"] == 3
        signed = [v for v in wq["votes"] if v.get("signed")]
        assert len(signed) >= 3
        for v in signed:
            assert v.get("pub_pem") and v.get("sig") and v.get("payload")
        assert "SIMULATED" in wq["honesty"]
    else:
        # honest degrade: state explains itself, nothing fabricated
        assert "honesty" in wq
    # the closure outcome is bound into the Khipu receipt payload
    payload = record["receipt"]
    assert payload["digest"]


# ---------------------------------------------------------------------------
# After-action export routes
# ---------------------------------------------------------------------------

def test_after_action_export_for_track(client):
    c, ledger = client
    _evaluate(c, track_id="TRK-0001")
    c.post("/api/killinchu/v1/engagements/record", json={
        "track_id": "TRK-0001", "verdict": "HOLD", "effector": "EW_JAM",
        "operator_id": "OP-DEMO",
    })
    before_nodes = list(ledger.nodes)
    r = c.get("/api/killinchu/v1/engagements/after-action",
              params={"track_id": "TRK-0001"})
    assert r.status_code == 200
    b = r.json()
    assert b["schema"] == aar.SCHEMA
    assert b["truth_states"]["effectors"] == "SIMULATED"
    assert b["sections"]["closure"]["records"], "closure evidence present"
    assert b["sections"]["roe_chain"]["decisions"], "ROE evidence present"
    # Existing decision/closure receipts remain embedded for offline checks.
    assert b["sections"]["ledger_chain"]["node_count"] >= 2
    assert b["export_receipt"] == {"index": None, "digest": None, "signed": False,
                                    "state": "UNSIGNED_READ_ONLY"}
    assert b["receipt_minted"] is False
    assert b["export_read_only"] is True
    assert ledger.nodes == before_nodes


def test_after_action_export_pinned_record_and_404(client):
    c, ledger = client
    r = c.post("/api/killinchu/v1/engagements/record", json={
        "track_id": "TRK-0007", "verdict": "HOLD", "effector": "EW_JAM",
    })
    rid = r.json()["record"]["record_id"]
    before_nodes = list(ledger.nodes)
    pinned = c.get(f"/api/killinchu/v1/engagements/{rid}/after-action")
    assert pinned.status_code == 200
    b = pinned.json()
    assert b["engagement"]["latest_record_id"] == rid
    assert len(b["sections"]["closure"]["records"]) == 1
    # unknown record → 404 with an audited error (never a blank)
    missing = c.get("/api/killinchu/v1/engagements/ENG-NOPE/after-action")
    assert missing.status_code == 404
    assert "not found" in missing.json()["error"]
    # unknown track → 404 with an explicit empty_state (Zero-Bandaid)
    none = c.get("/api/killinchu/v1/engagements/after-action",
                 params={"track_id": "TRK-GHOST"})
    assert none.status_code == 404
    assert none.json()["empty_state"]
    assert ledger.nodes == before_nodes
