# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests for the civilian inspection rehearsal inside Defend.

Network-free.  Every fixture is synthetic; findings are scripted; identities
are simulated roster labels; the ticket is modeled and never created.
"""
from __future__ import annotations

from datetime import timedelta
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import killinchu_defend_inspection as inspection
import killinchu_defend_plane as defend

HEADERS = {"X-SZL-Session": "inspection-test-session-0123456789012345678"}
OTHER = {"X-SZL-Session": "inspection-other-session-012345678901234567"}
APPROVER = "simulated/approver-cruz"


def _app(path) -> TestClient:
    app = FastAPI()
    result = defend.register(app)
    assert result["status"] == "ok"
    assert result["inspection_scenario"] == "REGISTERED"
    return TestClient(app)


def _forget(path) -> None:
    defend._STORES.pop(str(path), None)
    inspection._STORES.pop(str(path), None)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    path = tmp_path / "defend.sqlite3"
    monkeypatch.setenv("KILLINCHU_DEFEND_STATE_PATH", str(path))
    monkeypatch.setenv("KILLINCHU_DEFEND_SIGNING_KEY", "synthetic-inspection-test-key-not-production")
    yield _app(path), path
    _forget(path)


def _assess(c, fixture="happy_displaced_shingles", headers=HEADERS, **overrides):
    body = inspection.fixture_request(fixture)
    body.update(overrides)
    return c.post("/api/defend/inspection/assess", headers=headers, json=body), body


def _verify(c, receipt_id, headers=HEADERS):
    return c.post("/api/defend/verify", headers=headers, json={"receipt_id": receipt_id})


def _db(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


# 1. Happy path -------------------------------------------------------------
def test_happy_path_binds_evidence_cites_checklist_and_rehearses_only(runtime):
    c, _ = runtime
    response, body = _assess(c)
    assert response.status_code == 200
    first = response.json()
    assert first["decision"] == "RECOMMEND_REVIEW"
    assert first["truth_label"] == "SCRIPTED"
    labels = first["labels"]
    assert labels["data_class"] == "SYNTHETIC_FIXTURE"
    assert labels["inference"] == "SCRIPTED_RULES_NO_MODEL_CALL"
    assert labels["identities"].startswith("SIMULATED")
    assert labels["physical_actuation"] is False
    assert labels["real_ticket_created"] is False
    assert labels["dsse_signed"] is False
    assert labels["production_ready"] is False

    proposal = first["proposal"]
    assert proposal["action_type"] == "maintenance_review_ticket"
    assert proposal["action_type"] not in defend.ALLOWED_ACTIONS
    assert proposal["can_execute"] is False
    binding = proposal["binding"]
    assert binding["model"]["model_id"] == "killinchu/inspection-scripted-rules"
    assert len(binding["model"]["model_revision"]) == 64
    assert len(binding["model"]["prompt_revision"]) == 64
    assert binding["model"]["output_label"] == "SCRIPTED"
    assert binding["checklist_revision"] == inspection.CHECKLIST_REVISION
    assert {(e["observation_id"], e["sha256"], e["captured_at"], e["source_ref"]) for e in binding["evidence"]} == {
        (o["observation_id"], o["sha256"], o["captured_at"], o["source_ref"]) for o in body["observations"]
    }
    claim = proposal["parameters"]["claims"][0]
    assert claim["finding_code"] == "ROOF_COVERING_DISPLACED"
    assert 0.0 < claim["confidence"] < 1.0
    assert claim["interval"][0] <= claim["confidence"] <= claim["interval"][1]
    assert claim["citations"][0]["item_id"] == "SYN-RF-01"
    assert claim["citations"][0]["synthetic"] is True
    assert first["assessment"]["uncertainty_method"] == "HEURISTIC_UNCALIBRATED"

    approved = c.post(
        "/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal["id"], "approver": APPROVER}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval"]["identity"]["authenticated"] is False
    assert approved.json()["can_execute_external_action"] is False

    rehearsed = c.post("/api/defend/inspection/rehearse", headers=HEADERS, json={"proposal_id": proposal["id"]})
    assert rehearsed.status_code == 200, rehearsed.text
    result = rehearsed.json()["rehearsal"]
    assert result["ticket_created"] is False
    assert result["ticket_system"] == "NONE"
    assert result["physical_actuation"] is False
    assert result["external_calls"] == 0
    assert result["modeled_ticket"]["ticket_ref"].startswith("MODELED-ONLY-")
    assert result["truth_label"] == "MODELED"

    again = c.post("/api/defend/inspection/rehearse", headers=HEADERS, json={"proposal_id": proposal["id"]})
    assert again.status_code == 409

    for receipt in (first["receipt"], approved.json()["receipt"], rehearsed.json()["receipt"]):
        proof = _verify(c, receipt["id"])
        assert proof.status_code == 200
        assert proof.json()["integrity_verified"] is True
        assert proof.json()["signature_verified"] is True

    bundle = c.get(f"/api/defend/inspection/bundle/{proposal['id']}", headers=HEADERS).json()
    assert bundle["binding_verified"] is True
    assert bundle["proposal"]["state"] == "REHEARSED"
    assert [r["kind"] for r in bundle["receipts"]] == [
        "INSPECTION_ASSESSMENT",
        "INSPECTION_SIMULATED_APPROVAL",
        "INSPECTION_REHEARSAL_RESULT",
    ]
    status = c.get("/api/defend/status").json()
    assert status["production_ready"] is False
    assert status["external_effectors_enabled"] is False


# 2. Weak / conflicting / missing evidence ----------------------------------
@pytest.mark.parametrize(
    ("fixture", "reason"),
    (
        ("weak_single_blurry_photo", "INSUFFICIENT_EVIDENCE"),
        ("weak_possible_wording", "INSUFFICIENT_EVIDENCE"),
        ("conflicting_photo_vs_note", "CONFLICTING_EVIDENCE"),
        ("missing_evidence", "MISSING_EVIDENCE"),
    ),
)
def test_weak_conflicting_or_missing_evidence_abstains_without_proposal(runtime, fixture, reason):
    c, _ = runtime
    response, _ = _assess(c, fixture)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ABSTAIN"
    assert body["assessment"]["abstain_reasons"] == [reason]
    assert body["proposal"] is None
    assert body["assessment"]["recommendation"] is None
    assert _verify(c, body["receipt"]["id"]).json()["integrity_verified"] is True


def test_intact_roof_is_no_referral_not_a_ticket(runtime):
    c, _ = runtime
    body = _assess(c, "intact_roof")[0].json()
    assert body["decision"] == "NO_REFERRAL"
    assert body["proposal"] is None


# 3. Stale inputs ------------------------------------------------------------
@pytest.mark.parametrize("fixture", ("stale_photos", "future_dated_capture"))
def test_stale_or_future_dated_inputs_abstain(runtime, fixture):
    c, _ = runtime
    body = _assess(c, fixture)[0].json()
    assert body["decision"] == "ABSTAIN"
    assert body["assessment"]["abstain_reasons"] == ["STALE_EVIDENCE"]
    assert body["assessment"]["stale_observations"]
    assert body["proposal"] is None


# 4. Unauthorized and self approval -----------------------------------------
@pytest.mark.parametrize("approver", ("simulated/requester-ben", "simulated/auditor-eli", "operator/unknown"))
def test_unauthorized_approver_is_refused(runtime, approver):
    c, _ = runtime
    proposal_id = _assess(c)[0].json()["proposal"]["id"]
    response = c.post(
        "/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": approver}
    )
    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_APPROVER"


def test_self_approval_is_refused_even_for_dual_role_label(runtime):
    c, _ = runtime
    proposal_id = _assess(c, requested_by="simulated/approver-dee")[0].json()["proposal"]["id"]
    response = c.post(
        "/api/defend/inspection/approve",
        headers=HEADERS,
        json={"proposal_id": proposal_id, "approver": "simulated/approver-dee"},
    )
    assert response.status_code == 409
    assert response.json()["error"] == "INDEPENDENCE_REQUIRED"
    ok = c.post("/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert ok.status_code == 200
    twice = c.post("/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert twice.status_code == 409


def test_rehearsal_requires_approval_and_other_sessions_cannot_see_proposal(runtime):
    c, _ = runtime
    proposal_id = _assess(c)[0].json()["proposal"]["id"]
    early = c.post("/api/defend/inspection/rehearse", headers=HEADERS, json={"proposal_id": proposal_id})
    assert early.status_code == 409
    foreign = c.post("/api/defend/inspection/approve", headers=OTHER, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert foreign.status_code == 404


# 5. Expired proposal --------------------------------------------------------
def test_expired_proposal_cannot_be_approved_and_is_receipted(runtime, monkeypatch):
    c, _ = runtime
    first = _assess(c)[0].json()
    proposal_id = first["proposal"]["id"]
    later = defend._utcnow() + inspection.PROPOSAL_TTL + timedelta(seconds=1)
    monkeypatch.setattr(inspection, "_now", lambda: later)
    response = c.post("/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]
    bundle = c.get(f"/api/defend/inspection/bundle/{proposal_id}", headers=HEADERS).json()
    assert bundle["proposal"]["state"] == "EXPIRED"
    retry = c.post("/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert retry.status_code == 409


# 6. Replay and collision ----------------------------------------------------
def test_replay_is_idempotent_and_collision_is_quarantined(runtime):
    c, _ = runtime
    response, body = _assess(c)
    first = response.json()
    replay = c.post("/api/defend/inspection/assess", headers=HEADERS, json=body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["proposal"]["id"] == first["proposal"]["id"]

    changed = dict(body)
    changed["observations"] = [dict(o) for o in body["observations"]]
    changed["observations"][0]["content"] += " extra"
    changed["observations"][0]["sha256"] = defend._sha256(changed["observations"][0]["content"].encode("utf-8"))
    collision = c.post("/api/defend/inspection/assess", headers=HEADERS, json=changed)
    assert collision.status_code == 409
    assert collision.json()["decision"] == "QUARANTINE"
    assert collision.json()["receipt"]["kind"] == "INSPECTION_ID_COLLISION"


# 7. Modified evidence -------------------------------------------------------
def test_evidence_modified_before_submission_abstains(runtime):
    c, _ = runtime
    body = _assess(c, "modified_evidence")[0].json()
    assert body["decision"] == "ABSTAIN"
    assert body["assessment"]["abstain_reasons"] == ["EVIDENCE_INTEGRITY_FAILED"]
    assert body["assessment"]["modified_observations"] == ["obs-1"]


def test_evidence_modified_in_store_quarantines_before_approval(runtime):
    c, path = runtime
    first = _assess(c)[0].json()
    proposal_id = first["proposal"]["id"]
    with _db(path) as connection:
        connection.execute(
            "UPDATE inspection_evidence SET content = content || ' (altered)' WHERE observation_id='obs-1'"
        )
    connection.close()
    response = c.post("/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER})
    assert response.status_code == 409
    assert "EVIDENCE_MODIFIED:obs-1" in response.json()["detail"]
    bundle = c.get(f"/api/defend/inspection/bundle/{proposal_id}", headers=HEADERS).json()
    assert bundle["proposal"]["state"] == "QUARANTINED"
    assert bundle["binding_verified"] is False
    assert bundle["receipts"][-1]["kind"] == "INSPECTION_BINDING_MISMATCH"


def test_evidence_modified_after_approval_blocks_rehearsal(runtime):
    c, path = runtime
    proposal_id = _assess(c)[0].json()["proposal"]["id"]
    assert c.post(
        "/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER}
    ).status_code == 200
    with _db(path) as connection:
        connection.execute("UPDATE inspection_evidence SET captured_at='2026-01-01T00:00:00.000Z' WHERE observation_id='obs-2'")
    connection.close()
    response = c.post("/api/defend/inspection/rehearse", headers=HEADERS, json={"proposal_id": proposal_id})
    assert response.status_code == 409
    assert "EVIDENCE_METADATA_MODIFIED:obs-2" in response.json()["detail"]


# 8. Receipt tampering -------------------------------------------------------
def test_receipt_tampering_fails_verification(runtime):
    c, path = runtime
    first = _assess(c)[0].json()
    receipt_id = first["receipt"]["id"]
    assert _verify(c, receipt_id).status_code == 200
    with _db(path) as connection:
        connection.execute("DROP TRIGGER defend_receipt_no_update")
        connection.execute(
            "UPDATE receipts SET payload_json = replace(payload_json, 'RECOMMEND_REVIEW', 'NO_REFERRAL') WHERE id=?",
            (receipt_id,),
        )
    connection.close()
    tampered = _verify(c, receipt_id)
    assert tampered.status_code == 409
    assert tampered.json()["integrity_verified"] is False


def test_receipt_signature_tampering_is_detected(runtime):
    c, path = runtime
    receipt_id = _assess(c)[0].json()["receipt"]["id"]
    with _db(path) as connection:
        connection.execute("DROP TRIGGER defend_receipt_no_update")
        connection.execute("UPDATE receipts SET signature = ? WHERE id=?", ("0" * 64, receipt_id))
    connection.close()
    proof = _verify(c, receipt_id).json()
    assert proof["signature_verified"] is False


# 9. Service failure ---------------------------------------------------------
class _FailingAdapter(inspection.ScriptedInspectionAdapter):
    def infer(self, observation):
        raise TimeoutError("synthetic adapter outage")


def test_model_service_failure_fails_closed_and_retry_recovers(runtime, monkeypatch):
    c, path = runtime
    monkeypatch.setattr(inspection, "_ADAPTER_FACTORY", _FailingAdapter)
    response, body = _assess(c)
    assert response.status_code == 503
    failed = response.json()
    assert failed["error"] == "MODEL_SERVICE_UNAVAILABLE"
    assert failed["decision"] == "ABSTAIN"
    assert failed["receipt"]["kind"] == "INSPECTION_SERVICE_FAILURE"
    with _db(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM inspection_assessments").fetchone()[0] == 0
    connection.close()
    monkeypatch.setattr(inspection, "_ADAPTER_FACTORY", inspection.ScriptedInspectionAdapter)
    retry = c.post("/api/defend/inspection/assess", headers=HEADERS, json=body)
    assert retry.status_code == 200
    assert retry.json()["replayed"] is False
    assert retry.json()["decision"] == "RECOMMEND_REVIEW"


def test_unsupported_adapter_output_fails_closed(runtime, monkeypatch):
    class Rogue(inspection.ScriptedInspectionAdapter):
        def infer(self, observation):
            return [{"finding_code": "OPEN_ALL_VALVES", "confidence": 1.0, "observation_id": observation["observation_id"]}]

    c, _ = runtime
    monkeypatch.setattr(inspection, "_ADAPTER_FACTORY", Rogue)
    assert _assess(c)[0].status_code == 503


def test_store_failure_fails_closed(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x")
    path = blocker / "defend.sqlite3"
    monkeypatch.setenv("KILLINCHU_DEFEND_STATE_PATH", str(path))
    c = _app(path)
    try:
        response, _ = _assess(c)
        assert response.status_code in (500, 503)
        assert "error" in response.json()
        bundle = c.get("/api/defend/inspection/bundle/insa_" + "0" * 32, headers=HEADERS)
        assert bundle.status_code == 503
    finally:
        _forget(path)


# 10. Restart / reopen -------------------------------------------------------
def test_restart_reopens_state_and_continues_the_workflow(runtime):
    c, path = runtime
    first = _assess(c)[0].json()
    proposal_id = first["proposal"]["id"]
    c.close()
    _forget(path)

    reopened = _app(path)
    replay = reopened.post("/api/defend/inspection/assess", headers=HEADERS, json=inspection.fixture_request("happy_displaced_shingles"))
    # Captured_at values differ from the first call, so this is a distinct request: collision, not replay.
    assert replay.status_code == 409
    approved = reopened.post(
        "/api/defend/inspection/approve", headers=HEADERS, json={"proposal_id": proposal_id, "approver": APPROVER}
    )
    assert approved.status_code == 200, approved.text
    rehearsed = reopened.post("/api/defend/inspection/rehearse", headers=HEADERS, json={"proposal_id": proposal_id})
    assert rehearsed.status_code == 200
    assert _verify(reopened, first["receipt"]["id"]).json()["integrity_verified"] is True
    assert _verify(reopened, rehearsed.json()["receipt"]["id"]).json()["predecessor_verified"] is True
    bundle = reopened.get(f"/api/defend/inspection/bundle/{proposal_id}", headers=HEADERS).json()
    assert bundle["binding_verified"] is True
    assert bundle["proposal"]["state"] == "REHEARSED"


# 11. Measured comparison against a trivial baseline -------------------------
def test_measured_comparison_against_trivial_baseline(runtime):
    report = inspection.compare_with_baseline(repeats=3)
    governed = report["systems"]["governed"]
    baseline = report["systems"]["baseline"]
    assert report["truth_label"] == "MEASURED_ON_SYNTHETIC_FIXTURES"
    assert report["fixture_count"] == len(inspection.FIXTURE_SPECS) >= 10
    assert governed["unsafe_recommendations"] == 0
    assert governed["grounding_errors"] == 0
    assert governed["decision_match_rate"] == 1.0
    assert baseline["abstention_rate"] == 0.0
    assert governed["abstention_rate"] > baseline["abstention_rate"]
    assert baseline["unsafe_recommendations"] > 0
    assert baseline["grounding_errors"] > 0
    for system in (governed, baseline):
        assert 0.0 <= system["latency_ms_p50"] <= system["latency_ms_max"]
    assert any("not real-world accuracy" in item for item in report["limits"])

    c, _ = runtime
    served = c.get("/api/defend/inspection/comparison?repeats=2")
    assert served.status_code == 200
    assert served.json()["systems"]["governed"]["unsafe_recommendations"] == 0
    assert c.get("/api/defend/inspection/comparison?repeats=0").status_code == 422


def test_grounding_check_rejects_miscited_or_unverified_claims():
    now = inspection._now()
    observations = inspection.fixture_request("flashing_with_moisture", now)["observations"]
    result = inspection.assess(observations, now, inspection.ScriptedInspectionAdapter())
    assert result["decision"] == "RECOMMEND_REVIEW"
    assert [c["finding_code"] for c in result["recommendation"]["claims"]] == ["FLASHING_SEPARATED"]
    assert result["recommendation"]["unconfirmed"][0]["finding_code"] == "MOISTURE_ELEVATED"
    bad = {
        "claims": [
            {**result["recommendation"]["claims"][0], "citations": [{**result["recommendation"]["claims"][0]["citations"][0], "item_id": "SYN-RF-01"}]}
        ]
    }
    assert inspection.grounding_errors(bad, result["evidence"])
    unverified = [dict(e, sha256_verified=False) for e in result["evidence"]]
    assert inspection.grounding_errors(result["recommendation"], unverified)


# 12. Boundaries and presentation -------------------------------------------
def test_requests_must_be_synthetic_and_bounded(runtime):
    c, _ = runtime
    response, _ = _assess(c, data_class="FIELD_CAPTURE")
    assert response.status_code == 422
    body = inspection.fixture_request("happy_displaced_shingles")
    body["target_url"] = "https://example.invalid"
    assert c.post("/api/defend/inspection/assess", headers=HEADERS, json=body).status_code == 422
    assert c.post("/api/defend/inspection/assess", json=inspection.fixture_request("intact_roof")).status_code == 422
    extra = inspection.fixture_request("happy_displaced_shingles")
    extra["observations"][0]["command"] = "anything"
    assert c.post("/api/defend/inspection/assess", headers=HEADERS, json=extra).status_code == 422


def test_scenario_page_and_declared_labels(runtime):
    c, _ = runtime
    scenario = c.get("/api/defend/inspection/scenario").json()
    assert scenario["checklist"]["synthetic"] is True
    assert scenario["checklist"]["label"].startswith("SYNTHETIC")
    assert scenario["model"]["inference_mode"] == "SCRIPTED_RULES_NO_MODEL_CALL"
    assert scenario["model"]["prompt_applied"] is False
    assert scenario["allowed_actions"] == ["maintenance_review_ticket"]
    assert all(name.startswith("simulated/") for name in scenario["simulated_roster"])
    page = c.get("/defend/inspection")
    assert page.status_code == 200
    assert 'data-killinchu-plane-tabs="v1"' in page.text
    for label in ("synthetic evidence", "scripted findings", "simulated identities", "rehearsal only", "not production ready"):
        assert label in page.text
    assert "/defend/inspection" in c.get("/defend").text
    assert c.get("/api/defend/inspection/fixtures/no_such_fixture").status_code == 404


def test_bundle_read_does_not_initialize_state(tmp_path, monkeypatch):
    path = tmp_path / "fresh" / "defend.sqlite3"
    monkeypatch.setenv("KILLINCHU_DEFEND_STATE_PATH", str(path))
    c = TestClient(FastAPI())
    defend.register(c.app)
    response = c.get("/api/defend/inspection/bundle/insa_" + "0" * 32, headers=HEADERS)
    assert response.status_code == 503
    assert not path.exists()
    assert c.get("/api/defend/inspection/scenario").status_code == 200
    assert not path.exists()
    _forget(path)
