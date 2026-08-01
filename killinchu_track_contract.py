# SPDX-License-Identifier: Apache-2.0
"""Truth-preserving operational-picture contracts for Killinchu tracks.

The public ADS-B feed is an unauthenticated broadcast. These helpers keep
that boundary explicit: a track is an observation claim, never a confirmed
threat, and cached or unavailable upstream state can never be shown as LIVE.
Training fixtures use a separate, opt-in mode.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

TRACK_BATCH_SCHEMA = "killinchu.track-batch.v1"
TRACK_ENVELOPE_SCHEMA = "killinchu.track-envelope.v1"


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or value in {"", "bundled-snapshot"}:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sensor_id(source_url: str | None) -> str:
    parsed = urlparse(source_url or "")
    host = (parsed.hostname or "unknown-source").lower()
    path = parsed.path.strip("/").replace("/", ":") or "feed"
    return f"{host}:{path}"


def _observed_at(received_at: datetime | None, aircraft: dict[str, Any]) -> datetime | None:
    """Derive observation time from upstream ``seen_pos``/``seen`` seconds."""
    if received_at is None:
        return None
    seconds = _number(aircraft.get("seen_pos"))
    if seconds is None:
        seconds = _number(aircraft.get("seen"))
    if seconds is None or seconds < 0:
        return None
    return received_at - timedelta(seconds=seconds)


def _altitude_metres(value: Any) -> float | None:
    if value == "ground":
        return 0.0
    feet = _number(value)
    return round(feet * 0.3048, 1) if feet is not None else None


def _speed_metres_per_second(value: Any) -> float | None:
    knots = _number(value)
    return round(knots * 0.514444, 1) if knots is not None else None


def _track_envelope(
    aircraft: dict[str, Any],
    *,
    mode: str,
    source: str,
    source_url: str | None,
    received_at: datetime | None,
    now: datetime,
) -> dict[str, Any] | None:
    latitude = _number(aircraft.get("lat"))
    longitude = _number(aircraft.get("lon"))
    if latitude is None or longitude is None:
        return None

    observed_at = _observed_at(received_at, aircraft)
    age_s = max(0.0, (now - observed_at).total_seconds()) if observed_at else None
    altitude_m = _altitude_metres(aircraft.get("alt_baro"))
    speed_m_s = _speed_metres_per_second(aircraft.get("gs"))
    low_altitude = altitude_m is not None and altitude_m < 150.0
    identity = str(aircraft.get("hex") or _sha256(aircraft)[:12]).strip().lower()

    return {
        "schema": TRACK_ENVELOPE_SCHEMA,
        "mode": mode,
        "observed_at": _iso(observed_at),
        "received_at": _iso(received_at),
        "age_s": round(age_s, 3) if age_s is not None else None,
        "source": source,
        "source_url": source_url,
        "sensor_id": _sensor_id(source_url),
        "authentication": "UNAUTHENTICATED_BROADCAST",
        "payload_sha256": _sha256(aircraft),
        "trust": "CLAIM" if mode == "LIVE" else "STALE_CLAIM",
        "track_id": f"ADSB-{identity}",
        "model": aircraft.get("type") or aircraft.get("flight") or "ADS-B aircraft",
        "side": "unknown",
        "role": "cooperative-air-observation",
        "group": "ADS-B",
        "country": "",
        "latitude": latitude,
        "longitude": longitude,
        "altitude_m": altitude_m,
        "heading_deg": _number(aircraft.get("track")),
        "speed_m_s": speed_m_s,
        "status": "LOW_ALTITUDE_ADVISORY" if low_altitude else "OBSERVED",
        "first_seen": _iso(observed_at),
        "last_update": _iso(received_at),
        "telemetry_source": source,
    }


def air_feed_batch(feed: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Normalize an honestly labelled ``killinchu_live_feeds`` air result."""
    current = _utc(now)
    data = feed.get("data") if isinstance(feed, dict) else None
    raw_mode = str(feed.get("mode") or "").lower() if isinstance(feed, dict) else ""
    mode = "LIVE" if raw_mode == "live" else "CACHED"
    availability = "AVAILABLE" if mode == "LIVE" else "STALE"
    received_at = _parse_iso(feed.get("fetched_at")) if isinstance(feed, dict) else None
    source = str(feed.get("source") or "adsb.lol community ADS-B") if isinstance(feed, dict) else "adsb.lol community ADS-B"
    source_url = feed.get("source_url") if isinstance(feed, dict) else None

    if not isinstance(data, dict):
        return unavailable_batch(source=source, source_url=source_url, now=current)

    endpoint = data.get("endpoint") or source_url
    tracks = []
    for aircraft in data.get("aircraft") or []:
        if not isinstance(aircraft, dict):
            continue
        envelope = _track_envelope(
            aircraft,
            mode=mode,
            source=source,
            source_url=endpoint,
            received_at=received_at,
            now=current,
        )
        if envelope:
            tracks.append(envelope)

    return {
        "schema": TRACK_BATCH_SCHEMA,
        "ok": True,
        "mode": mode,
        "availability": availability,
        "observed_at": min((t["observed_at"] for t in tracks if t["observed_at"]), default=None),
        "received_at": _iso(received_at),
        "age_s": max((t["age_s"] for t in tracks if t["age_s"] is not None), default=None),
        "source": source,
        "source_url": endpoint,
        "sensor_id": _sensor_id(endpoint),
        "authentication": "UNAUTHENTICATED_BROADCAST",
        "payload_sha256": _sha256(data),
        "trust": "CLAIM" if mode == "LIVE" else "STALE_CLAIM",
        "total_tracks": len(tracks),
        "active_threats": 0,
        "tracks": tracks,
        # Compatibility for the existing Overview, Live Threats, and globe UI.
        "threats": tracks,
        "attribution": data.get("attribution"),
        "doctrine": "v11",
        "honesty": (
            "Real ADS-B observations from the named upstream. Broadcast identity and position "
            "are unauthenticated claims; no observation is classified as a confirmed threat."
            if mode == "LIVE"
            else "Cached ADS-B observations. They are stale unauthenticated claims, never LIVE."
        ),
    }


def unavailable_batch(
    *, source: str = "adsb.lol community ADS-B", source_url: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    current = _utc(now)
    return {
        "schema": TRACK_BATCH_SCHEMA,
        "ok": False,
        "mode": "UNAVAILABLE",
        "availability": "UNAVAILABLE",
        "observed_at": None,
        "received_at": _iso(current),
        "age_s": None,
        "source": source,
        "source_url": source_url,
        "sensor_id": _sensor_id(source_url),
        "authentication": "UNAVAILABLE",
        "payload_sha256": None,
        "trust": "UNAVAILABLE",
        "total_tracks": 0,
        "active_threats": 0,
        "tracks": [],
        "threats": [],
        "doctrine": "v11",
        "honesty": "Upstream ADS-B is unavailable and no usable cached observation exists. No tracks were fabricated.",
    }


def training_batch(catalog: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Return the legacy scenario only behind explicit ``mode=training`` opt-in."""
    current = _utc(now)
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fixtures = [
        ("shahed136", 47.85, 35.10, 1500, 270, 51.4, "INBOUND"),
        ("lancet3", 47.40, 36.20, 800, 95, 30.5, "LOITERING"),
        ("orlan10", 48.10, 37.50, 3000, 180, 41.6, "ISR"),
    ]
    signatures = {str(item.get("id")): item for item in catalog}
    tracks = []
    fixture_payloads = []
    for index, (drone_id, lat, lon, altitude, heading, speed, status) in enumerate(fixtures, 1):
        signature = signatures.get(drone_id, {})
        raw = {
            "fixture_id": drone_id,
            "latitude": lat,
            "longitude": lon,
            "altitude_m": altitude,
            "heading_deg": heading,
            "speed_m_s": speed,
            "status": status,
        }
        fixture_payloads.append(raw)
        tracks.append(
            {
                "schema": TRACK_ENVELOPE_SCHEMA,
                "mode": "TRAINING",
                "observed_at": _iso(observed),
                "received_at": _iso(current),
                "age_s": round((current - observed).total_seconds(), 3),
                "source": "killinchu.curated-drone-training-fixture",
                "source_url": None,
                "sensor_id": "training-fixture",
                "authentication": "SYNTHETIC_FIXTURE",
                "payload_sha256": _sha256(raw),
                "trust": "TRAINING_ONLY",
                "track_id": f"TRAINING-{index:04d}",
                "model": signature.get("model", drone_id),
                "side": signature.get("side", "unknown"),
                "role": signature.get("role", ""),
                "group": signature.get("group", ""),
                "country": signature.get("country", ""),
                "latitude": lat,
                "longitude": lon,
                "altitude_m": altitude,
                "heading_deg": heading,
                "speed_m_s": speed,
                "status": status,
                "first_seen": _iso(observed),
                "last_update": _iso(current),
                "telemetry_source": "TRAINING fixture; never a live sensor feed",
            }
        )

    return {
        "schema": TRACK_BATCH_SCHEMA,
        "ok": True,
        "mode": "TRAINING",
        "availability": "TRAINING",
        "observed_at": _iso(observed),
        "received_at": _iso(current),
        "age_s": round((current - observed).total_seconds(), 3),
        "source": "killinchu.curated-drone-training-fixture",
        "source_url": None,
        "sensor_id": "training-fixture",
        "authentication": "SYNTHETIC_FIXTURE",
        "payload_sha256": _sha256({"fixtures": fixture_payloads}),
        "trust": "TRAINING_ONLY",
        "total_tracks": len(tracks),
        "active_threats": sum(1 for track in tracks if track["side"] == "adversary"),
        "tracks": tracks,
        "threats": tracks,
        "doctrine": "v11",
        "honesty": "Explicit TRAINING mode. Positions are fixed fixtures over curated signatures; no live claim is made.",
    }
