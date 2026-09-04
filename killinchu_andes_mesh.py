#!/usr/bin/env python3
"""Andes-first live ADS-B mesh for official killinchu.

Installs first-class theaters (andes, altiplano, redsea, levant) onto
killinchu_feeds_realdata.THEATERS and exposes GET .../feeds/mesh.

Honesty:
- ADS-B is a broadcast claim, not identity truth.
- LIVE | EMPTY | BLOCKED | TIMEOUT | ERROR only. Never paint green.
- Sample/snapshot only if every live source fails AND a dated snapshot exists.
- No fabricated hex, callsign, or position.
- Effectors stay SIMULATED. Human-on-the-loop.

Doctrine v11 LOCKED · Λ = Conjecture 1 · receipts prove integrity not accuracy.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

PAYLOAD = "SZL-KILLINCHU-ANDES-MESH-2026-09-04"
UA = (
    "killinchu-andes-mesh/2026-09-04 "
    "(+https://huggingface.co/spaces/SZLHOLDINGS/killinchu)"
)

# Hardcoded theater boxes (geographic only — not tracks).
ANDES_THEATERS = {
    "andes": {
        "label": "Andes (Peru coastal + sierra)",
        "lamin": -17.8,
        "lamax": -6.2,
        "lomin": -82.4,
        "lomax": -71.6,
        "lat": -12.0464,
        "lon": -77.0428,
        "nm": 250,
    },
    "altiplano": {
        "label": "Altiplano (PE/BO/CL high plateau)",
        "lamin": -22.5,
        "lamax": -14.5,
        "lomin": -70.5,
        "lomax": -64.5,
        "lat": -16.5,
        "lon": -68.15,
        "nm": 280,
    },
    "redsea": {
        "label": "Red Sea / Bab el-Mandeb",
        "lamin": 11.0,
        "lamax": 22.0,
        "lomin": 36.0,
        "lomax": 45.0,
        "lat": 13.0,
        "lon": 43.3,
        "nm": 350,
    },
    "levant": {
        "label": "Levant eastern Med",
        "lamin": 30.5,
        "lamax": 37.5,
        "lomin": 31.5,
        "lomax": 37.0,
        "lat": 33.5,
        "lon": 35.5,
        "nm": 280,
    },
}

_PUBLIC_DEFAULT = "andes"


def _in_box(lat: float, lon: float, box: dict) -> bool:
    return box["lamin"] <= lat <= box["lamax"] and box["lomin"] <= lon <= box["lomax"]


def _http_json(url: str, timeout: float = 8.0) -> tuple[int, Any, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            code = int(getattr(res, "status", 200) or 200)
        try:
            return code, json.loads(raw.decode("utf-8", "replace")), "LIVE"
        except json.JSONDecodeError:
            return code, {"_text": raw[:180].decode("utf-8", "replace")}, "ERROR"
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "403" in msg or "401" in msg:
            return 403, {"error": type(exc).__name__, "note": msg[:160]}, "BLOCKED"
        if "timed out" in low or "timeout" in type(exc).__name__.lower():
            return 0, {"error": type(exc).__name__, "note": msg[:160]}, "TIMEOUT"
        return 0, {"error": type(exc).__name__, "note": msg[:160]}, "ERROR"


def _norm_adsb(ac: dict, feed: str) -> dict | None:
    hex_id = str(ac.get("hex") or ac.get("icao") or "").strip().lower()
    if not hex_id:
        return None
    lat, lon = ac.get("lat"), ac.get("lon")
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return {
        "track_id": hex_id,
        "hex": hex_id,
        "icao24": hex_id,
        "callsign": str(ac.get("flight") or ac.get("callsign") or "").strip() or None,
        "lat": lat_f,
        "lon": lon_f,
        "alt_baro": ac.get("alt_baro") if ac.get("alt_baro") != "ground" else 0,
        "gs": ac.get("gs"),
        "track": ac.get("track") or ac.get("true_heading"),
        "squawk": ac.get("squawk"),
        "type": ac.get("t") or ac.get("type"),
        "feeds": [feed],
        "source": feed,
        "live": True,
        "evidence": "MEASURED",
        "claim": "ADS-B broadcast position claim, not identity truth",
    }


def _norm_opensky(row: list, feed: str = "opensky") -> dict | None:
    if not isinstance(row, (list, tuple)) or len(row) < 8:
        return None
    hex_id = str(row[0] or "").strip().lower()
    lon, lat = row[5], row[6]
    if not hex_id or lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return {
        "track_id": hex_id,
        "hex": hex_id,
        "icao24": hex_id,
        "callsign": str(row[1] or "").strip() or None,
        "lat": lat_f,
        "lon": lon_f,
        "alt_baro": row[7],
        "gs": (float(row[9]) * 1.94384) if isinstance(row[9], (int, float)) else None,
        "track": row[10],
        "squawk": row[14] if len(row) > 14 else None,
        "feeds": [feed],
        "source": feed,
        "live": True,
        "evidence": "MEASURED",
        "claim": "ADS-B / Mode S state vector claim via OpenSky, not identity truth",
    }


def _merge(tracks: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for tr in tracks:
        key = tr["hex"]
        if key not in by:
            by[key] = dict(tr)
            continue
        feeds = list(dict.fromkeys((by[key].get("feeds") or []) + (tr.get("feeds") or [])))
        by[key]["feeds"] = feeds
        by[key]["source"] = "+".join(feeds)
        if not by[key].get("callsign") and tr.get("callsign"):
            by[key]["callsign"] = tr["callsign"]
    return list(by.values())


def fetch_mesh(theater: str = _PUBLIC_DEFAULT, limit: int = 80) -> dict:
    key = (theater or _PUBLIC_DEFAULT).lower()
    box = ANDES_THEATERS.get(key) or ANDES_THEATERS[_PUBLIC_DEFAULT]
    used_default = key not in ANDES_THEATERS and key not in {"china", "global"}
    lat, lon, nm = box["lat"], box["lon"], box["nm"]
    feeds = [
        ("adsb.lol", f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}", 8.0, "ac"),
        ("adsb.lol-point", f"https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}", 8.0, "ac"),
        ("adsb.lol-mil", "https://api.adsb.lol/v2/mil", 8.0, "ac"),
        ("adsb.lol-7700", "https://api.adsb.lol/v2/squawk/7700", 8.0, "ac"),
        ("adsb.fi", f"https://api.adsb.fi/v2/lat/{lat}/lon/{lon}/dist/{nm}", 6.0, "ac"),
        ("airplanes.live", f"https://api.airplanes.live/v2/lat/{lat}/lon/{lon}/dist/{nm}", 6.0, "ac"),
        ("adsb.one", f"https://api.adsb.one/v2/point/{lat}/{lon}/{nm}", 6.0, "ac"),
        (
            "opensky",
            (
                "https://opensky-network.org/api/states/all"
                f"?lamin={box['lamin']}&lomin={box['lomin']}"
                f"&lamax={box['lamax']}&lomax={box['lomax']}"
            ),
            8.0,
            "states",
        ),
    ]
    feed_states: list[dict] = []
    raw_tracks: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_http_json, url, timeout): (name, kind) for name, url, timeout, kind in feeds}
        for fut in as_completed(futs):
            name, kind = futs[fut]
            code, data, state = fut.result()
            n = 0
            if state == "LIVE" and isinstance(data, dict):
                if kind == "ac":
                    rows = data.get("ac") or []
                    for ac in rows:
                        tr = _norm_adsb(ac, name)
                        if not tr:
                            continue
                        if name.endswith("-mil") or name.endswith("-7700"):
                            if not _in_box(tr["lat"], tr["lon"], box):
                                continue
                        raw_tracks.append(tr)
                        n += 1
                elif kind == "states":
                    rows = data.get("states") or []
                    for row in rows:
                        tr = _norm_opensky(row, name)
                        if tr:
                            raw_tracks.append(tr)
                            n += 1
                if n == 0:
                    state = "EMPTY"
            feed_states.append(
                {
                    "feed": name,
                    "http": code,
                    "state": state,
                    "n": n,
                    "note": (data.get("error") or data.get("note") or data.get("_text") if isinstance(data, dict) else None),
                }
            )
    merged = _merge(raw_tracks)
    if limit and len(merged) > int(limit):
        merged = merged[: int(limit)]
    live_feeds = [f["feed"] for f in feed_states if f["state"] == "LIVE"]
    mode = "live" if live_feeds else "empty"
    return {
        "payload": PAYLOAD,
        "sha256": hashlib.sha256(PAYLOAD.encode()).hexdigest(),
        "live": bool(live_feeds),
        "mode": mode,
        "honest": (
            "REAL open ADS-B mesh. Merge on ICAO hex. "
            "LIVE|EMPTY|BLOCKED|TIMEOUT|ERROR. Never fabricated. "
            "Effector stays SIMULATED."
        ),
        "theater": box["label"] if key in ANDES_THEATERS else key,
        "theater_key": key if key in ANDES_THEATERS else _PUBLIC_DEFAULT,
        "theater_known": key in ANDES_THEATERS,
        "used_andes_default": used_default or key not in ANDES_THEATERS,
        "count": len(merged),
        "tracks": merged,
        "feeds": feed_states,
        "live_feeds": live_feeds,
        "elapsed_s": round(time.time() - t0, 3),
        "tracks_synthetic": False,
    }


def install() -> dict:
    """Mutate official THEATERS + default. Safe if feeds module missing."""
    report = {"ok": False, "patched": [], "note": None}
    try:
        import killinchu_feeds_realdata as fr
    except Exception as exc:
        report["note"] = f"feeds module unavailable: {type(exc).__name__}"
        return report
    theaters = getattr(fr, "THEATERS", None)
    if not isinstance(theaters, dict):
        report["note"] = "THEATERS missing"
        return report
    for key, box in ANDES_THEATERS.items():
        if key not in theaters:
            theaters[key] = {
                "label": box["label"],
                "lamin": box["lamin"],
                "lamax": box["lamax"],
                "lomin": box["lomin"],
                "lomax": box["lomax"],
            }
            report["patched"].append(key)
    try:
        fr._DEFAULT_THEATER = _PUBLIC_DEFAULT
        report["patched"].append("default=andes")
    except Exception:
        pass
    report["ok"] = True
    report["theaters_now"] = sorted(theaters.keys())
    return report


def register(app, ns: str = "killinchu") -> None:
    """Attach /feeds/mesh and run install(). Starlette-compatible."""
    hook = install()
    base = f"/api/{ns}/v1"

    async def _mesh(request):
        q = request.query_params
        theater = q.get("theater") or os.environ.get("KILLINCHU_DEFAULT_THEATER") or _PUBLIC_DEFAULT
        try:
            limit = int(q.get("limit") or 80)
        except ValueError:
            limit = 80
        envelope = fetch_mesh(theater=theater, limit=limit)
        envelope["install"] = hook
        from starlette.responses import JSONResponse

        return JSONResponse(envelope)

    try:
        from starlette.routing import Route

        app.routes.append(Route(f"{base}/feeds/mesh", _mesh, methods=["GET"], name=f"{ns}_andes_mesh"))
    except Exception:
        try:
            app.add_route(f"{base}/feeds/mesh", _mesh, methods=["GET"])
        except Exception:
            pass


if __name__ == "__main__":
    print(json.dumps(fetch_mesh("andes", 12), indent=2)[:12000])
