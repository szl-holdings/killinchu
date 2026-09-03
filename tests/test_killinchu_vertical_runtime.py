from __future__ import annotations

import math

import killinchu_fleet_vessels as fleet


def _formula_runner(name, args):
    values = [float(value) for value in args[0]]
    if name == "lambda_aggregate":
        result = math.exp(sum(math.log(max(value, 1e-12)) for value in values) / len(values))
    elif name == "lambda_bounded":
        result = True
    else:
        raise AssertionError(f"unexpected formula {name}")
    return {
        "ok": True,
        "formula": name,
        "result": result,
        "proof_status": "TEST_DOUBLE",
        "lambda_receipt": "test-receipt",
    }


def _live_track(name="SEA STAR"):
    return {
        "track_id": "ais:123456789",
        "domain": "sea",
        "label": name,
        "country": "Panama",
        "kind": "under way using engine",
        "live": True,
        "source": "Digitraffic Finland AIS",
        "source_url": "https://example.test/ais",
        "provenance": "real test fixture",
        "ts": "2026-09-03T00:00:00Z",
        "raw": {"mmsi": 123456789},
        "dark_fleet": {
            "flag": False,
            "reasons": [],
            "label": "advisory",
        },
    }


def test_current_runtime_consumes_live_evidence_and_requires_human_review():
    def vessels(_theater, _limit):
        return [_live_track()], [{"source": "Digitraffic", "ok": True}], "live"

    def sanctions():
        return {
            "live": True,
            "mode": "live",
            "fetched_at": "2026-09-03T00:00:00Z",
            "source": "UN 1718",
            "source_url": "https://example.test/sanctions",
            "count": 1,
            "items": [
                {
                    "name": "Sea Star",
                    "aliases": [],
                    "identifiers": "",
                    "program": "UN1718",
                }
            ],
        }

    def brain(_query, _k):
        return {
            "state": "GROUNDED_HANDLES_READY",
            "ready": True,
            "handles": [{"nodeId": "vessels-1"}],
            "evidence": [{"node_id": "vessels-1"}],
            "content_access": "HANDLES_ONLY",
        }

    out = fleet.build_current_voyage_risk(
        vessel_fetcher=vessels,
        sanctions_fetcher=sanctions,
        brain_fetcher=brain,
        formula_runner=_formula_runner,
    )

    assert out["current_data"]["state"] == "LIVE"
    assert out["risk_level"] == "CRITICAL_REVIEW"
    assert out["sanctions"]["potential_matches"][0]["screen"]["clearance"] is False
    assert out["recommendation"]["requires_human_approval"] is True
    assert out["recommendation"]["automation_authority"] == "NONE"
    assert out["formula"]["state"] == "COMPUTED_PARTIAL"
    assert out["formula"]["full_yuyay13"] is None
    assert out["formula"]["measured_axis_count"] < out["formula"]["axis_count"]
    assert out["second_brain"]["content_access"] == "HANDLES_ONLY"
    assert out["anatomy"]["state"] == "OPERATIONAL"
    assert len(out["evidence_digest"]) == 64


def test_sample_fallback_never_becomes_live_or_operational():
    sample = _live_track("Replay Vessel")
    sample["live"] = False
    sample["source"] = "bundled in-image snapshot (sample)"
    sample["provenance"] = "SAMPLE/replay"

    out = fleet.build_current_voyage_risk(
        vessel_fetcher=lambda _theater, _limit: (
            [sample],
            [{"source": "all live sources", "ok": False}],
            "sample",
        ),
        sanctions_fetcher=lambda: {
            "live": False,
            "mode": "unreachable",
            "items": [],
            "count": 0,
        },
        brain_fetcher=lambda _query, _k: {
            "state": "UNAVAILABLE",
            "ready": False,
            "handles": [],
            "evidence": [],
            "content_access": "HANDLES_ONLY",
        },
        formula_runner=_formula_runner,
    )

    assert out["current_data"]["state"] == "SAMPLE"
    assert out["current_data"]["live_track_count"] == 0
    assert out["risk_level"] == "DEMONSTRATION"
    assert out["sanctions"]["state"] == "UNAVAILABLE"
    assert out["anatomy"]["state"] == "DEGRADED"
    assert out["recommendation"]["automation_authority"] == "NONE"


def test_sanctions_unavailable_never_returns_clearance():
    result = fleet.screen_track_against_sanctions(
        _live_track(),
        {"live": False, "items": []},
    )
    assert result["state"] == "UNAVAILABLE"
    assert result["potential_match"] is False
    assert result["clearance"] is False


def test_second_brain_rejects_unapproved_remote_host(monkeypatch):
    monkeypatch.setenv("SZL_SECOND_BRAIN_URL", "https://untrusted.example")
    result = fleet.second_brain_context("vessel risk")
    assert result["state"] == "UNAVAILABLE"
    assert result["mode"] == "REMOTE_BLOCKED"
    assert result["handles"] == []


def test_vertical_contract_makes_killinchu_canonical_and_gaps_explicit():
    contract = fleet.vertical_contract()
    assert contract["vertical"]["id"] == "killinchu"
    assert contract["vertical"]["vessels_consolidated"] is True
    assert contract["vertical"]["standalone_vessels_product"] is False
    assert contract["doctrine"]["lambda_uniqueness"] == "Conjecture 1 — OPEN"
    assert contract["second_brain"]["content_access"] == "HANDLES_ONLY"
