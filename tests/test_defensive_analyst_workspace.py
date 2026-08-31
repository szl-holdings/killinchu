# SPDX-License-Identifier: Apache-2.0

from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "static" / "analyst.html"
CSS = ROOT / "static" / "analyst.css"
JS = ROOT / "static" / "analyst.js"
HF_SYNC = ROOT / ".github" / "workflows" / "hf-sync.yml"


class _Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _parsed_document():
    source = HTML.read_text(encoding="utf-8")
    parser = _Document()
    parser.feed(source)
    return source, parser.tags


def _run_contract(function_name, fixture):
    script = f"""
const contract = require({json.dumps(str(JS))});
const fixture = {json.dumps(fixture)};
process.stdout.write(JSON.stringify(contract[{json.dumps(function_name)}](fixture)));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_workspace_is_semantic_read_only_and_accessible():
    source, tags = _parsed_document()
    mains = [attrs for tag, attrs in tags if tag == "main"]
    assert mains == [{"id": "workspace", "class": "shell", "tabindex": "-1", "aria-busy": "true"}]
    assert any(tag == "a" and attrs.get("class") == "skip-link" and attrs.get("href") == "#workspace" for tag, attrs in tags)
    assert any(tag == "nav" and attrs.get("aria-label") == "Primary navigation" for tag, attrs in tags)
    assert any(tag == "table" for tag, _ in tags)
    assert any(tag == "caption" and attrs.get("id") == "observation-caption" for tag, attrs in tags)
    assert any(tag == "p" and attrs.get("role") == "status" and attrs.get("aria-live") == "polite" for tag, attrs in tags)
    assert {attrs.get("for") for tag, attrs in tags if tag == "label"} >= {"observation-search", "mode-filter"}
    assert not any(tag == "form" for tag, _ in tags)
    assert "never dispatches, targets, jams, spoofs, or actuates anything" in source
    assert "An observation is not a confirmed threat" in source
    assert "An HTTP 200 is not proof of a valid signature" in source


def test_client_reads_only_the_four_bounded_evidence_endpoints():
    source = JS.read_text(encoding="utf-8")
    endpoints = {
        "/api/killinchu/v1/threats/active",
        "/api/killinchu/v1/feeds/status",
        "/api/killinchu/v1/honest",
        "/api/killinchu/v1/receipt/export",
    }
    assert all(endpoint in source for endpoint in endpoints)
    assert 'method: "GET"' in source
    assert "method: \"POST\"" not in source
    assert ".innerHTML" not in source
    assert "credentials: \"same-origin\"" in source
    assert "cache: \"no-store\"" in source
    assert "body.signed === true && verification.verified === true" in source


def test_workspace_exposes_the_inert_defensive_intake_registry_without_calling_it():
    html = HTML.read_text(encoding="utf-8")
    javascript = JS.read_text(encoding="utf-8")
    registry = "/api/killinchu/v1/defensive-intake/tools"

    assert f'href="{registry}"' in html
    assert registry not in javascript


def test_live_threats_array_is_consumed_without_inventing_provenance():
    normalized = _run_contract(
        "normalizeObservationResult",
        {
            "ok": True,
            "status": 200,
            "body": {
                "ok": True,
                "total_tracks": 1,
                "threats": [{"track_id": "TRK-0001", "model": "broadcast label"}],
                "honesty": "Positions are illustrative; not a live sensor feed.",
            },
        },
    )
    assert normalized["sourceField"] == "threats"
    assert normalized["mode"] == "UNLABELLED"
    assert normalized["authentication"] == "UNAVAILABLE"
    assert normalized["tracks"] == [{"track_id": "TRK-0001", "model": "broadcast label"}]
    assert "illustrative" in normalized["honesty"]


def test_tracks_compatibility_requires_the_canonical_schema_and_non_2xx_fails_closed():
    typed = _run_contract(
        "normalizeObservationResult",
        {
            "ok": True,
            "status": 200,
            "body": {
                "schema": "killinchu.track-batch.v1",
                "mode": "LIVE",
                "tracks": [{"track_id": "ADSB-abc", "authentication": "UNAUTHENTICATED_BROADCAST"}],
            },
        },
    )
    assert typed["sourceField"] == "tracks:killinchu.track-batch.v1"
    assert typed["mode"] == "LIVE"
    assert len(typed["tracks"]) == 1

    untyped = _run_contract(
        "normalizeObservationResult",
        {"ok": True, "status": 200, "body": {"tracks": [{"track_id": "shape-coincidence"}]}},
    )
    assert untyped["sourceField"] is None
    assert untyped["tracks"] == []

    rejected = _run_contract(
        "normalizeObservationResult",
        {"ok": False, "status": 503, "body": {"threats": [{"track_id": "not-accepted"}]}},
    )
    assert rejected["healthy"] is False
    assert rejected["tracks"] == []
    assert rejected["sourceLabel"].startswith("HTTP 503")


def test_live_honest_labels_doctrine_and_revision_are_renderable():
    normalized = _run_contract(
        "normalizeHonestyResult",
        {
            "ok": True,
            "status": 200,
            "body": {
                "git_sha": "a" * 40,
                "doctrine_lock": {
                    "doctrine": "v11",
                    "state": "LOCKED",
                    "declarations": 749,
                    "axioms": 14,
                    "sorries": 163,
                    "commit": "c7c0ba17",
                },
                "honest_labels": {
                    "principle": "HONESTY OVER CHECKLIST.",
                    "lambda": "Conjecture 1 — NOT a theorem.",
                },
            },
        },
    )
    assert normalized["summary"] == "HONESTY OVER CHECKLIST."
    assert any(item.startswith("Lambda:") for item in normalized["disclosures"])
    assert "Doctrine lock: v11 LOCKED · 749/14/163 · commit c7c0ba17" in normalized["disclosures"]
    assert "Deployed git SHA: " + "a" * 40 in normalized["disclosures"]

    rejected = _run_contract(
        "normalizeHonestyResult",
        {"ok": False, "status": 429, "body": {"honest_labels": {"principle": "do not trust"}}},
    )
    assert rejected == {
        "healthy": False,
        "httpStatus": 429,
        "summary": "HTTP 429 · disclosure response rejected.",
        "disclosures": [],
    }


def test_responsive_and_assistive_display_contracts_are_present():
    source = CSS.read_text(encoding="utf-8")
    assert ":focus-visible" in source
    assert "prefers-reduced-motion: reduce" in source
    assert "forced-colors: active" in source
    assert "@media (max-width: 680px)" in source
    assert "min-height: 44px" in source
    assert "content: attr(data-label)" in source


def test_public_front_doors_link_to_the_workspace():
    for path in (ROOT / "static" / "landing.html", ROOT / "static" / "index.html"):
        assert 'href="/static/analyst.html"' in path.read_text(encoding="utf-8")


def test_hf_release_smokes_the_workspace_and_inert_registry():
    workflow = HF_SYNC.read_text(encoding="utf-8")
    smoke_paths = next(
        line for line in workflow.splitlines() if "smoke-paths:" in line
    )

    assert '"/static/analyst.html"' in smoke_paths
    assert '"/api/killinchu/v1/defensive-intake/tools"' in smoke_paths
