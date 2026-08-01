from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from killinchu_track_contract import (
    TRACK_BATCH_SCHEMA,
    TRACK_ENVELOPE_SCHEMA,
    air_feed_batch,
    training_batch,
    unavailable_batch,
)


NOW = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)
REQUIRED_PROVENANCE = {
    "mode",
    "observed_at",
    "received_at",
    "age_s",
    "source",
    "sensor_id",
    "authentication",
    "payload_sha256",
    "trust",
}


def _feed(mode: str = "live") -> dict:
    return {
        "source": "adsb.lol community ADS-B (military + civil aircraft, no auth)",
        "source_url": "https://api.adsb.lol/v2/mil",
        "mode": mode,
        "fetched_at": "2026-08-01T13:59:58Z",
        "data": {
            "endpoint": "https://api.adsb.lol/v2/mil",
            "attribution": "Data: adsb.lol (ODbL)",
            "aircraft": [
                {
                    "hex": "abc123",
                    "flight": "EVID01",
                    "lat": 40.5,
                    "lon": -73.5,
                    "alt_baro": 400,
                    "gs": 100,
                    "track": 90,
                    "type": "H60",
                    "seen_pos": 3.5,
                    "seen": 1.0,
                },
                {"hex": "no-position", "lat": None, "lon": None},
            ],
        },
    }


def test_live_adsb_becomes_claim_envelope_not_confirmed_threat() -> None:
    batch = air_feed_batch(_feed(), now=NOW)

    assert batch["schema"] == TRACK_BATCH_SCHEMA
    assert REQUIRED_PROVENANCE <= batch.keys()
    assert batch["mode"] == "LIVE"
    assert batch["availability"] == "AVAILABLE"
    assert batch["active_threats"] == 0
    assert batch["total_tracks"] == 1
    assert batch["age_s"] == 5.5
    assert batch["tracks"] == batch["threats"]

    track = batch["tracks"][0]
    assert track["schema"] == TRACK_ENVELOPE_SCHEMA
    assert REQUIRED_PROVENANCE <= track.keys()
    assert track["observed_at"] == "2026-08-01T13:59:54.500000Z"
    assert track["received_at"] == "2026-08-01T13:59:58Z"
    assert track["age_s"] == 5.5
    assert track["authentication"] == "UNAUTHENTICATED_BROADCAST"
    assert track["trust"] == "CLAIM"
    assert track["status"] == "LOW_ALTITUDE_ADVISORY"
    assert track["altitude_m"] == 121.9
    assert track["speed_m_s"] == 51.4
    assert track["side"] == "unknown"
    assert len(track["payload_sha256"]) == 64


def test_payload_digest_is_canonical_and_input_sensitive() -> None:
    first = air_feed_batch(_feed(), now=NOW)["tracks"][0]["payload_sha256"]
    second = air_feed_batch(_feed(), now=NOW)["tracks"][0]["payload_sha256"]
    changed_feed = _feed()
    changed_feed["data"]["aircraft"][0]["lat"] = 41.0
    changed = air_feed_batch(changed_feed, now=NOW)["tracks"][0]["payload_sha256"]

    assert first == second
    assert first != changed
    assert first == hashlib.sha256(
        json.dumps(
            _feed()["data"]["aircraft"][0],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def test_live_feed_adapter_retains_upstream_observation_age(monkeypatch) -> None:
    import killinchu_live_feeds

    monkeypatch.setattr(
        killinchu_live_feeds,
        "_http_get",
        lambda *_args, **_kwargs: {
            "ac": [
                {
                    "hex": "abc123",
                    "lat": 40.5,
                    "lon": -73.5,
                    "seen_pos": 2.25,
                    "seen": 0.5,
                }
            ]
        },
    )

    aircraft = killinchu_live_feeds._fetch_air()["aircraft"][0]
    assert aircraft["seen_pos"] == 2.25
    assert aircraft["seen"] == 0.5


def test_cached_feed_is_never_labelled_live() -> None:
    batch = air_feed_batch(_feed("cached"), now=NOW)

    assert batch["mode"] == "CACHED"
    assert batch["availability"] == "STALE"
    assert batch["trust"] == "STALE_CLAIM"
    assert batch["tracks"][0]["mode"] == "CACHED"
    assert batch["tracks"][0]["trust"] == "STALE_CLAIM"
    assert "never LIVE" in batch["honesty"]


def test_missing_feed_fails_closed_without_tracks() -> None:
    batch = air_feed_batch(
        {
            "mode": "cached",
            "source": "adsb.lol community ADS-B",
            "source_url": "https://api.adsb.lol/v2/mil",
            "data": None,
        },
        now=NOW,
    )

    assert batch == unavailable_batch(
        source="adsb.lol community ADS-B",
        source_url="https://api.adsb.lol/v2/mil",
        now=NOW,
    )
    assert batch["mode"] == "UNAVAILABLE"
    assert batch["tracks"] == []
    assert batch["threats"] == []
    assert batch["payload_sha256"] is None


def test_training_fixtures_are_explicit_fixed_and_distinct() -> None:
    batch = training_batch(
        [{"id": "shahed136", "model": "Shahed-136", "side": "adversary"}], now=NOW
    )

    assert batch["mode"] == "TRAINING"
    assert batch["availability"] == "TRAINING"
    assert batch["authentication"] == "SYNTHETIC_FIXTURE"
    assert batch["observed_at"] == "2026-01-01T00:00:00Z"
    assert all(track["mode"] == "TRAINING" for track in batch["tracks"])
    assert all(track["trust"] == "TRAINING_ONLY" for track in batch["tracks"])
    assert all(track["track_id"].startswith("TRAINING-") for track in batch["tracks"])
    assert "no live claim" in batch["honesty"]


def test_frontend_surfaces_consume_truth_contract_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "static" / "truth-cop.js").read_text(encoding="utf-8")
    landing = (root / "static" / "landing.html").read_text(encoding="utf-8")
    app_shell = (root / "static" / "index.html").read_text(encoding="utf-8")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert 'var ENDPOINT = "/api/killinchu/v1/threats/active"' in script
    assert '"LIVE", "CACHED", "TRAINING", "UNAVAILABLE"' in script
    assert "no tracks fabricated" in script
    assert "not confirmed threats" in script
    assert 'src="/static/truth-cop.js"' in landing
    assert 'src="/static/truth-cop.js"' in app_shell
    assert "killinchu_track_contract.py" in dockerfile


def test_production_route_defaults_real_and_requires_explicit_training(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("KILLINCHU_ROOT", str(root))
    import serve

    class AirFeed:
        @staticmethod
        def get_feed(name: str) -> dict:
            assert name == "air"
            return _feed()

    monkeypatch.setattr(serve, "_killinchu_live_feeds", AirFeed())
    client = TestClient(serve.app)

    live = client.get("/api/killinchu/v1/threats/active")
    training = client.get("/api/killinchu/v1/threats/active?mode=training")
    invalid = client.get("/api/killinchu/v1/threats/active?mode=demo")

    assert live.status_code == 200
    assert live.headers["cache-control"] == "no-store"
    assert live.json()["mode"] == "LIVE"
    assert live.json()["active_threats"] == 0
    assert training.status_code == 200
    assert training.json()["mode"] == "TRAINING"
    assert invalid.status_code == 422
    assert invalid.json()["availability"] == "UNAVAILABLE"
    assert REQUIRED_PROVENANCE <= invalid.json().keys()


def test_production_route_returns_typed_503_when_feed_is_absent(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import serve

    monkeypatch.setattr(serve, "_killinchu_live_feeds", None)
    response = TestClient(serve.app).get("/api/killinchu/v1/threats/active")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["mode"] == "UNAVAILABLE"
    assert response.json()["tracks"] == []
