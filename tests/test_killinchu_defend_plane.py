# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for the consolidated Killinchu Defend plane."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import pytest

import killinchu_defend_plane as defend

SESSION = "defend-test-session-token-012345678901234567890"
HEADERS = {"X-SZL-Session": SESSION}


def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv(
        "KILLINCHU_DEFEND_STATE_PATH",
        str(tmp_path / "defend.sqlite3"),
    )
    monkeypatch.setenv(
        "KILLINCHU_DEFEND_SIGNING_KEY",
        "test-only-not-a-production-secret-test-only",
    )
    app = FastAPI()

    @app.get("/existing", response_class=HTMLResponse)
    def existing() -> str:
        return "<!doctype html><html><head><title>Existing</title></head><body>Existing Killinchu surface</body></html>"

    result = defend.register(app)
    assert result["status"] == "ok"
    return TestClient(app)


def event_payload(event_id: str = "evt-provider-001") -> dict:
    return {
        "source_event_id": event_id,
        "event_type": "vulnerability.known_exploited",
        "asset_ref": "asset/demo-gateway",
        "actor_id": "actor/observed-service",
        "severity": "CRITICAL",
        "summary": "Known-exploited vulnerability observed on a public-facing asset.",
        "requested_by": "operator/requester",
        "indicators": {
            "source_authenticated": True,
            "asset_owner_known": True,
            "rollback_available": True,
            "known_exploited": True,
            "public_exposure": True,
            "privilege_escalation": False,
            "agent_tool_policy_violation": False,
            "destructive_capability": False,
            "evidence_count": 3,
        },
    }


def test_status_is_source_bound_and_no_effector_exists(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    response = c.get("/api/defend/status")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "READY"
    assert body["workflow_operational"] is True
    assert body["production_receipts_ready"] is True
    assert body["source"]["revision"] == defend.SOURCE_REVISION
    assert body["source"]["repository"] == "szl-holdings/szl-defensive-control-plane"
    assert body["taxonomy"] == {
        "public_product": "Killinchu",
        "portfolio_name": "Aegis",
        "internal_engine": "Sentra",
        "separate_public_space_required": False,
    }
    assert body["external_effectors_enabled"] is False
    assert body["arbitrary_commands_allowed"] is False
    assert body["arbitrary_urls_allowed"] is False


def test_product_tabs_are_visible_and_legacy_names_redirect(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    page = c.get("/defend")
    assert page.status_code == 200
    assert 'data-killinchu-plane-tabs="v1"' in page.text
    assert "Killinchu / Defend" in page.text
    assert "Aegis" in page.text
    assert "Sentra" in page.text
    assert "/elite/maritime" in page.text
    assert "@media(prefers-reduced-motion:reduce)" in page.text

    existing = c.get("/existing")
    assert existing.status_code == 200
    assert existing.text.count('data-killinchu-plane-tabs="v1"') == 1

    for alias in ("/aegis", "/sentra"):
        response = c.get(alias, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/defend"


class PlaneTabsParser(HTMLParser):
    """Inspect only this module's navigation, not links inside other pages."""

    def __init__(self):
        super().__init__()
        self.in_tabs = False
        self.links = []
        self.unavailable = {}
        self.pending_route = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "nav" and attributes.get("data-killinchu-plane-tabs") == "v1":
            self.in_tabs = True
        if not self.in_tabs:
            return
        if tag == "a":
            self.links.append(attributes.get("href"))
        if "data-unavailable-route" in attributes:
            assert tag == "span"
            assert not any(name in attributes for name in ("href", "onclick", "tabindex"))
            assert attributes.get("role") not in {"button", "link"}
            self.pending_route = attributes["data-unavailable-route"]
            self.unavailable[self.pending_route] = ""

    def handle_data(self, data):
        if self.pending_route:
            self.unavailable[self.pending_route] += data

    def handle_endtag(self, tag):
        if tag == "span":
            self.pending_route = None
        if tag == "nav":
            self.in_tabs = False


@pytest.mark.parametrize("page_path", ("/defend", "/resilience", "/existing"))
def test_navigation_exposes_only_existing_page_destinations(
    tmp_path, monkeypatch, page_path,
):
    # Register the actual page owners. GETs below render HTML only; they neither
    # execute browser JavaScript nor call detection, signing or external APIs.
    import killinchu_elite_console
    import killinchu_maritime_view

    c = client(tmp_path, monkeypatch)
    killinchu_elite_console.register(c.app)
    killinchu_maritime_view.register(c.app)
    response = c.get(page_path)
    assert response.status_code == 200
    tabs = PlaneTabsParser()
    tabs.feed(response.text)
    assert tabs.links == ["/resilience", "/defend", "/elite/maritime", "/elite#cuas_lab"]
    assert tabs.unavailable == {
        "/immune": "Immune · migration pending",
        "/khipu": "Evidence page · unavailable",
    }
    for destination in tabs.links:
        target = c.get(urlsplit(destination).path, follow_redirects=False)
        assert target.status_code == 200, destination
        assert target.headers["content-type"].startswith("text/html"), destination


@pytest.mark.parametrize("missing_path", ("/immune", "/khipu"))
def test_navigation_repair_does_not_fabricate_missing_routes(
    tmp_path, monkeypatch, missing_path,
):
    c = client(tmp_path, monkeypatch)
    response = c.get(missing_path, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers
    assert missing_path not in {route.path for route in defend._routes("killinchu")}


def test_complete_detection_approval_rehearsal_and_verification_loop(
    tmp_path,
    monkeypatch,
):
    c = client(tmp_path, monkeypatch)
    detected = c.post(
        "/api/defend/analyze",
        headers=HEADERS,
        json=event_payload(),
    )
    assert detected.status_code == 200
    first = detected.json()
    assert first["decision"] == "PROPOSED"
    assert first["proposal"]["action_type"] == "isolate_asset"
    assert first["proposal"]["can_execute"] is False
    assert first["external_effectors_enabled"] is False
    assert first["receipt"]["signature_state"].startswith("HMAC_SHA256:")
    proposal_id = first["proposal"]["id"]

    replay = c.post(
        "/api/defend/analyze",
        headers=HEADERS,
        json=event_payload(),
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["proposal"]["id"] == proposal_id

    same_actor = c.post(
        "/api/defend/approve",
        headers=HEADERS,
        json={"proposal_id": proposal_id, "approver": "operator/requester"},
    )
    assert same_actor.status_code == 409
    assert same_actor.json()["error"] == "INDEPENDENCE_REQUIRED"

    approved = c.post(
        "/api/defend/approve",
        headers=HEADERS,
        json={"proposal_id": proposal_id, "approver": "operator/independent-reviewer"},
    )
    assert approved.status_code == 200
    assert approved.json()["proposal_state"] == "APPROVED_FOR_REHEARSAL"
    assert approved.json()["can_execute_external_action"] is False

    rehearsed = c.post(
        "/api/defend/rehearse",
        headers=HEADERS,
        json={"proposal_id": proposal_id},
    )
    assert rehearsed.status_code == 200
    simulation = rehearsed.json()
    assert simulation["proposal_state"] == "REHEARSED"
    assert simulation["rehearsal"]["external_calls"] == 0
    assert simulation["rehearsal"]["external_effectors"] is False
    assert simulation["rehearsal"]["truth_label"] == "MODELED"
    receipt_id = simulation["receipt"]["id"]

    verified = c.post(
        "/api/defend/verify",
        headers=HEADERS,
        json={"receipt_id": receipt_id},
    )
    assert verified.status_code == 200
    proof = verified.json()
    assert proof["integrity_verified"] is True
    assert proof["predecessor_verified"] is True
    assert proof["signature_verified"] is True

    cases = c.get("/api/defend/cases?limit=25", headers=HEADERS)
    assert cases.status_code == 200
    assert cases.json()["count"] == 1
    assert cases.json()["cases"][0]["state"] == "REHEARSED_AND_VERIFIED"

    receipt = c.get(f"/api/defend/receipts/{receipt_id}", headers=HEADERS)
    assert receipt.status_code == 200
    assert receipt.json()["receipt"]["id"] == receipt_id
    assert receipt.json()["receipt"]["signature_present"] is True


def test_event_id_collision_is_quarantined_and_receipted(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    first = c.post(
        "/api/defend/analyze",
        headers=HEADERS,
        json=event_payload("evt-collision-001"),
    )
    assert first.status_code == 200

    changed = event_payload("evt-collision-001")
    changed["summary"] = "Different payload presented under the same provider event identifier."
    collision = c.post(
        "/api/defend/analyze",
        headers=HEADERS,
        json=changed,
    )
    assert collision.status_code == 409
    body = collision.json()
    assert body["decision"] == "QUARANTINE"
    assert body["reason"] == "SOURCE_EVENT_ID_COLLISION"
    assert body["receipt"]["kind"] == "EVENT_ID_COLLISION"


def test_requests_fail_closed_on_missing_scope_or_unbounded_fields(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    no_scope = c.post("/api/defend/analyze", json=event_payload())
    assert no_scope.status_code == 422
    assert no_scope.json()["error"] == "INVALID_REQUEST"

    invalid = event_payload("evt-invalid-001")
    invalid["command"] = "not accepted"
    rejected = c.post("/api/defend/analyze", headers=HEADERS, json=invalid)
    assert rejected.status_code == 422
    assert "unsupported fields" in rejected.json()["detail"]

    invalid_action_shape = c.post(
        "/api/defend/approve",
        headers=HEADERS,
        json={"proposal_id": "prop_not-valid", "approver": "operator/reviewer"},
    )
    assert invalid_action_shape.status_code == 422
