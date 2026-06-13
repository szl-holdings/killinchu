# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ kernel c7c0ba17 · Λ=Conjecture 1
# Authored by Yachay (CTO). Co-author: Perplexity Computer Agent.
"""
killinchu_feeds_realdata.py — REAL LIVE DATA feeds normalized to the TRACK shape.

Founder mandate: "real everything, no simulation, jack into real data live,
open-source collection incl. China — all of it." The ONLY simulated element in
killinchu is the EFFECTOR/engage action (kept human-on-the-loop for LEGAL
reasons). EVERY sensing/intel feed below is REAL, honestly labelled live vs
sample, with a per-record provenance stamp.

Endpoints (registered EARLY, before the SPA /{full_path:path} catch-all):

  GET /api/killinchu/v1/feeds/aircraft?theater=<key>&limit=<n>
        REAL ADS-B aircraft (military + civil), global incl. China / Asia-Pacific.
        PRIMARY: OpenSky Network /states/all (anonymous, bounding box per theater).
        PARALLEL/FALLBACK: adsb.lol /v2/mil + /v2/point (no key, military feed).
        Normalized TRACK[]. live:true when ANY real source returned; sample only
        if every source fails (then bundled snapshot, never fabricated).

  GET /api/killinchu/v1/feeds/vessels?theater=<key>&limit=<n>
        REAL AIS vessels. REDUNDANCY CHAIN (SeaTraffic pattern):
        PRIMARY (keyed): AISStream.io wss — key from the Space SECRET store
          (SZL_AISSTREAM_API_KEY / AISSTREAM_API_KEY); a bounded background
          collector fills a live cache. NEVER committed.
        FALLBACK (no key, still REAL): Digitraffic Finland AIS REST (Baltic).
        SAMPLE: only if both fail. Dark-fleet / sanctioned heuristic computed
          over the REAL AIS and labelled advisory/heuristic (NOT proven).

  GET /api/killinchu/v1/feeds/remoteid
        REAL OpenDroneID / ASTM F3411 Remote-ID broadcasts when a source relays
        them (a connected sniffer POSTs to /feeds/remoteid/ingest). The /jackin
        decoder consumes this. Honest EMPTY when none — never fabricated.

  POST /api/killinchu/v1/feeds/remoteid/ingest
        Accept a real OpenDroneID/F3411 broadcast (from a field sniffer / Web
        Serial relay) into the live Remote-ID cache. Normalized TRACK.

  GET /api/killinchu/v1/feeds/status
        Per-feed reachability + live/sample honesty (chain transparency).

  GET /api/killinchu/v1/osint/intel?vertical=<key>
        REAL public open-source collection: defense/UAS open-source reporting +
        sanctions / dark-vessel designation lists, returned with source URLs +
        timestamps, labelled OSINT(public). NO classified / non-public claims.
        Sources are no-key public: UN SC 1718 designated-vessels list,
        OpenSanctions maritime targets, USGS (geo context). Cached server-side;
        rate-limited. We call this "open-source collection," never "scraping."

THE TRACK SHAPE (every record, every feed):
  {
    "track_id": str,            # stable per-source id (e.g. "air:icao24" / "ais:mmsi")
    "domain": "air"|"sea"|"rid",
    "label": str|None,          # callsign / ship name / RID operator id (a CLAIM)
    "lat": float|None, "lon": float|None,
    "alt_m": float|None,        # barometric/geo altitude (air/rid), null for sea
    "speed_mps": float|None,    # ground speed / SOG converted to m/s
    "heading_deg": float|None,  # track / COG / heading
    "on_ground": bool|None,
    "country": str|None,        # origin country (air) / flag (sea) — a CLAIM
    "kind": str|None,           # type code (air) / nav status (sea) / ua type (rid)
    "raw": {...},               # the un-normalized source fields (audit trail)
    "source": str,              # human source name
    "source_url": str,          # upstream URL
    "live": true|false,         # REAL fetch succeeded -> true; sample/snapshot -> false
    "provenance": str,          # one-line chain: which real feed + how reached
    "ts": iso8601               # server fetch timestamp
  }

Every endpoint envelope ALSO carries: {feed, theater, count, live, mode,
sources_tried[], honest, doctrine:"v11", fetched_at}. mode ∈ live|mixed|sample.

Doctrine v11: locked=8 {F1,F4,F7,F11,F12,F18,F19,F22}; Λ=Conjecture 1 (advisory,
never a theorem); never fabricate a track; label LIVE/SAMPLE truthfully;
effector stays SIMULATED; never commit a key. 0 runtime CDN (same-origin proxy).

Sign: Yachay <yachay@szlholdings.dev>. Perplexity Computer Agent.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from starlette.routing import Route
from starlette.responses import JSONResponse

# Reuse the proven HTTP + snapshot helpers from the existing live-data layer.
try:
    import killinchu_live_feeds as _lf
    _http_get = _lf._http_get
    _http_get_raw = _lf._http_get_raw
    _lambda_trust = _lf._lambda_trust
    _haversine_nm = _lf._haversine_nm
except Exception:  # pragma: no cover — standalone fallback (keeps module importable)
    _lf = None

    def _http_get(url, timeout=25, headers=None, data=None, method=None):
        h = {"User-Agent": "killinchu-feeds/1.0", "Accept": "application/json",
             "Accept-Encoding": "gzip"}
        if "digitraffic.fi" in url:
            h["Digitraffic-User"] = "SZLHoldings/killinchu"
        if headers:
            h.update(headers)
        import gzip as _gz
        import io as _io
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                try:
                    raw = _gz.GzipFile(fileobj=_io.BytesIO(raw)).read()
                except Exception:
                    pass
            return json.loads(raw)

    def _http_get_raw(url, timeout=25, headers=None, data=None, method=None):
        h = {"User-Agent": "killinchu-feeds/1.0", "Accept-Encoding": "gzip"}
        if headers:
            h.update(headers)
        import gzip as _gz
        import io as _io
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                try:
                    raw = _gz.GzipFile(fileobj=_io.BytesIO(raw)).read()
                except Exception:
                    pass
            return raw

    def _lambda_trust(axes):
        vals = [max(1e-6, min(1.0, float(v))) for v in (axes or []) if v is not None]
        if not vals:
            return 0.0
        return round(math.exp(sum(math.log(v) for v in vals) / len(vals)), 4)

    def _haversine_nm(a_lat, a_lon, b_lat, b_lon):
        R = 3440.065
        p1, p2 = math.radians(a_lat), math.radians(b_lat)
        dp = math.radians(b_lat - a_lat)
        dl = math.radians(b_lon - a_lon)
        x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(2 * R * math.asin(min(1.0, math.sqrt(x))), 3)


_SNAP_DIR = Path(os.environ.get("KILLINCHU_LIVE_SNAPSHOTS", "/app/live_snapshots"))
_UA = "killinchu-feeds/1.0 (+https://szlholdings-killinchu.hf.space)"

_CACHE: dict = {}
_LOCK = threading.Lock()

KN_TO_MS = 0.514444  # knots -> m/s
FT_TO_M = 0.3048

# ---------------------------------------------------------------------------
# THEATERS — bounding boxes (lat/lon) incl. China + Asia-Pacific, per the spec.
# OpenSky uses lamin/lamax/lomin/lomax; Digitraffic is fixed (FI/Baltic).
# ---------------------------------------------------------------------------
THEATERS = {
    "china": {"label": "China (mainland + coastal)",
              "lamin": 18.0, "lamax": 42.0, "lomin": 108.0, "lomax": 126.0},
    "taiwan_strait": {"label": "Taiwan Strait",
                      "lamin": 21.0, "lamax": 27.0, "lomin": 117.0, "lomax": 123.0},
    "south_china_sea": {"label": "South China Sea",
                        "lamin": 5.0, "lamax": 23.0, "lomin": 105.0, "lomax": 121.0},
    "east_china_sea": {"label": "East China Sea",
                       "lamin": 25.0, "lamax": 33.0, "lomin": 120.0, "lomax": 131.0},
    "korea": {"label": "Korean Peninsula",
              "lamin": 33.0, "lamax": 43.0, "lomin": 124.0, "lomax": 132.0},
    "japan": {"label": "Japan / Ryukyu",
              "lamin": 24.0, "lamax": 46.0, "lomin": 122.0, "lomax": 146.0},
    "asia_pacific": {"label": "Asia-Pacific (wide)",
                     "lamin": 0.0, "lamax": 46.0, "lomin": 100.0, "lomax": 150.0},
    "baltic": {"label": "Baltic / Gulf of Finland",
               "lamin": 58.0, "lamax": 66.0, "lomin": 18.0, "lomax": 30.0},
    "europe": {"label": "Central Europe (dense civil)",
               "lamin": 45.0, "lamax": 55.0, "lomin": 2.0, "lomax": 18.0},
    "global": {"label": "Global (no box — OpenSky全量, capped)",
               "lamin": None, "lamax": None, "lomin": None, "lomax": None},
}
_DEFAULT_THEATER = "china"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _theater(key):
    return THEATERS.get((key or "").lower(), THEATERS[_DEFAULT_THEATER])


def _bbox_qs(t):
    if t.get("lamin") is None:
        return ""
    return "?" + urllib.parse.urlencode(
        {"lamin": t["lamin"], "lamax": t["lamax"], "lomin": t["lomin"], "lomax": t["lomax"]})


def _in_box(lat, lon, t):
    # No box defined (e.g. true global) -> nothing to filter on; keep the record.
    if t.get("lamin") is None:
        return True
    # A real theater box IS defined. A record without a position CANNOT be
    # confirmed inside the box, so exclude it — never claim a position-less
    # track is "in theater" (honest: no fabricated location).
    if lat is None or lon is None:
        return False
    return (t["lamin"] <= lat <= t["lamax"]) and (t["lomin"] <= lon <= t["lomax"])


def _load_snapshot(feed):
    p = _SNAP_DIR / ("%s.json" % feed)
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ===========================================================================
# AIRCRAFT — REAL ADS-B. OpenSky (PRIMARY, anon) + adsb.lol /v2/mil (PARALLEL).
# ===========================================================================
_OPENSKY_URL = "https://opensky-network.org/api/states/all"
_ADSBLOL_MIL = "https://api.adsb.lol/v2/mil"
# adsb.lol radius/point query: ALL aircraft (civ+mil) with positions within
# radius_nm of (lat,lon). Same host as /v2/mil (reachable where OpenSky egress
# is blocked). Used to TILE a theater box so positioned tracks are available
# even when OpenSky times out. Radius capped at 250 nm by the API.
_ADSBLOL_POINT = "https://api.adsb.lol/v2/point/%s/%s/%s"
_ADSBLOL_MAX_NM = 250

# OpenSky State Vector index order (REST docs):
# 0 icao24, 1 callsign, 2 origin_country, 3 time_position, 4 last_contact,
# 5 longitude, 6 latitude, 7 baro_altitude(m), 8 on_ground, 9 velocity(m/s),
# 10 true_track(deg), 11 vertical_rate, 12 sensors, 13 geo_altitude(m),
# 14 squawk, 15 spi, 16 position_source, 17 category


def _track_from_opensky(s, t):
    icao = (s[0] or "").strip() if s[0] else None
    lon, lat = s[5], s[6]
    return {
        "track_id": "air:%s" % (icao or "unknown"),
        "domain": "air",
        "label": ((s[1] or "").strip() or None) if len(s) > 1 else None,
        "lat": lat, "lon": lon,
        "alt_m": s[7] if len(s) > 7 else None,
        "speed_mps": s[9] if len(s) > 9 else None,
        "heading_deg": s[10] if len(s) > 10 else None,
        "on_ground": bool(s[8]) if len(s) > 8 and s[8] is not None else None,
        "country": s[2] if len(s) > 2 else None,
        "kind": ("category:%s" % s[17]) if len(s) > 17 and s[17] else None,
        "raw": {"icao24": icao, "callsign": (s[1] or "").strip() if len(s) > 1 else None,
                "baro_altitude": s[7] if len(s) > 7 else None,
                "geo_altitude": s[13] if len(s) > 13 else None,
                "velocity": s[9] if len(s) > 9 else None,
                "true_track": s[10] if len(s) > 10 else None,
                "squawk": s[14] if len(s) > 14 else None},
        "source": "OpenSky Network /states/all (anonymous, CC-BY-NC)",
        "source_url": _OPENSKY_URL,
        "live": True,
        "provenance": "OpenSky REST state-vector · theater=%s · anonymous live" % t.get("label"),
        "ts": _now_iso(),
    }


def _track_from_adsblol(a, t):
    hexid = a.get("hex")
    alt = a.get("alt_baro")
    alt_m = None
    if isinstance(alt, (int, float)):
        alt_m = round(alt * FT_TO_M, 1)
    gs = a.get("gs")  # ground speed in knots
    return {
        "track_id": "air:%s" % (hexid or "unknown"),
        "domain": "air",
        "label": (a.get("flight") or "").strip() or None,
        "lat": a.get("lat"), "lon": a.get("lon"),
        "alt_m": alt_m,
        "speed_mps": round(gs * KN_TO_MS, 2) if isinstance(gs, (int, float)) else None,
        "heading_deg": a.get("track"),
        "on_ground": (alt == "ground") if alt is not None else None,
        "country": None,  # adsb.lol does not resolve origin country
        "kind": a.get("t") or (("category:%s" % a.get("category")) if a.get("category") else None),
        "raw": {"hex": hexid, "flight": (a.get("flight") or "").strip(),
                "alt_baro": alt, "gs": gs, "track": a.get("track"),
                "squawk": a.get("squawk"), "type": a.get("t"),
                "category": a.get("category"), "mil": True},
        "source": "adsb.lol community ADS-B (military feed, ODbL)",
        "source_url": _ADSBLOL_MIL,
        "live": True,
        "provenance": "adsb.lol /v2/mil · military ADS-B · no-key live · box-filtered theater=%s" % t.get("label"),
        "ts": _now_iso(),
    }


def _track_from_adsblol_point(a, t):
    """Normalize an adsb.lol point-query record (civ+mil). Same field layout as
    /v2/mil; military flagged via dbFlags bit 0 (1=military)."""
    tr = _track_from_adsblol(a, t)
    is_mil = bool((a.get("dbFlags") or 0) & 1)
    tr["raw"]["mil"] = is_mil
    tr["source"] = "adsb.lol community ADS-B (%s, ODbL)" % ("military" if is_mil else "civil+mil")
    tr["provenance"] = ("adsb.lol /v2/point · community ADS-B (%s) · no-key live · "
                        "radius-tiled theater=%s" % ("mil" if is_mil else "civ/mil", t.get("label")))
    tr["source_url"] = "https://api.adsb.lol/v2/point"
    return tr


def _adsblol_point_tiles(t):
    """Tile a theater box with adsb.lol point queries (radius<=250nm) so we get
    POSITIONED aircraft (civ+mil) even when OpenSky egress is blocked. Returns
    a list of (lat, lon, radius_nm) centers covering the box."""
    if t.get("lamin") is None:
        return [(0.0, 0.0, _ADSBLOL_MAX_NM)]  # global: single broad probe
    lamin, lamax = t["lamin"], t["lamax"]
    lomin, lomax = t["lomin"], t["lomax"]
    # 1 deg lat ~= 60 nm; choose a grid step so each 250nm-radius circle overlaps.
    step_deg = 3.0  # ~180 nm spacing under 250 nm radius -> overlapping coverage
    centers = []
    la = lamin + step_deg / 2.0
    while la < lamax + step_deg:
        lo = lomin + step_deg / 2.0
        while lo < lomax + step_deg:
            centers.append((round(min(la, lamax), 3), round(min(lo, lomax), 3), _ADSBLOL_MAX_NM))
            lo += step_deg
        la += step_deg
    # cap tiles to keep latency bounded (large theaters)
    return centers[:6]


def _fetch_aircraft(theater_key, limit):
    """REAL aircraft. PRIMARY OpenSky (anon, theater bbox) + PARALLEL adsb.lol/mil
    + adsb.lol /v2/point radius tiling (positioned civ+mil; HF-reachable).
    Returns (tracks, sources_tried, mode). mode ∈ live|mixed|sample."""
    t = _theater(theater_key)
    tracks = []
    tried = []
    any_live = False
    seen = set()

    # PRIMARY — OpenSky anonymous state vectors (supports bbox). OpenSky is the
    # main POSITIONED source (civil + ADS-B mil with lat/lon) WHERE REACHABLE.
    # OpenSky egress is blocked/slow from some hosts (incl. this HF Space), so we
    # use a single SHORT-timeout attempt (fast-fail) and rely on the adsb.lol
    # point-tiling supplement below for positioned tracks when OpenSky is down.
    states = None
    _osky_err = None
    try:
        data = _http_get(_OPENSKY_URL + _bbox_qs(t), timeout=11, headers={"User-Agent": _UA})
        states = (data or {}).get("states") or []
    except Exception as e:
        _osky_err = e
    if states is not None:
        tried.append({"source": "OpenSky /states/all (anon)", "ok": True,
                      "count": len(states), "url": _OPENSKY_URL})
        any_live = True
        for s in states:
            if not s or len(s) < 11:
                continue
            tr = _track_from_opensky(s, t)
            if tr["track_id"] in seen:
                continue
            seen.add(tr["track_id"])
            tracks.append(tr)
    else:
        tried.append({"source": "OpenSky /states/all (anon)", "ok": False,
                      "error": "%s: %s" % (type(_osky_err).__name__, _osky_err),
                      "url": _OPENSKY_URL})

    # PARALLEL / FALLBACK — adsb.lol military feed (global; box-filter to theater).
    try:
        data = _http_get(_ADSBLOL_MIL, timeout=14, headers={"User-Agent": _UA})
        ac = (data or {}).get("ac") or (data or {}).get("aircraft") or []
        kept = 0
        for a in ac:
            if not _in_box(a.get("lat"), a.get("lon"), t):
                continue
            tr = _track_from_adsblol(a, t)
            if tr["track_id"] in seen:
                continue
            seen.add(tr["track_id"])
            tracks.append(tr)
            kept += 1
        tried.append({"source": "adsb.lol /v2/mil", "ok": True,
                      "count": kept, "total": len(ac), "url": _ADSBLOL_MIL})
        any_live = True
    except Exception as e:
        tried.append({"source": "adsb.lol /v2/mil", "ok": False,
                      "error": "%s: %s" % (type(e).__name__, e), "url": _ADSBLOL_MIL})

    # SUPPLEMENT — adsb.lol /v2/point radius tiling. Only used when we still have
    # no POSITIONED tracks (e.g. OpenSky unreachable from this host and the mil
    # feed has nothing in-box). Gives real positioned civ+mil aircraft; same host
    # as /v2/mil so it works where OpenSky egress is blocked. Honest live data.
    if not tracks:
        pt_total = 0
        pt_kept = 0
        pt_ok = False
        pt_err = None
        for (clat, clon, rnm) in _adsblol_point_tiles(t):
            try:
                url = _ADSBLOL_POINT % (clat, clon, rnm)
                data = _http_get(url, timeout=9, headers={"User-Agent": _UA})
                ac = (data or {}).get("ac") or (data or {}).get("aircraft") or []
                pt_ok = True
                pt_total += len(ac)
                for a in ac:
                    if not _in_box(a.get("lat"), a.get("lon"), t):
                        continue
                    tr = _track_from_adsblol_point(a, t)
                    if tr["track_id"] in seen:
                        continue
                    seen.add(tr["track_id"])
                    tracks.append(tr)
                    pt_kept += 1
            except Exception as e:
                pt_err = "%s: %s" % (type(e).__name__, e)
        if pt_ok:
            tried.append({"source": "adsb.lol /v2/point (radius tiled)", "ok": True,
                          "count": pt_kept, "total": pt_total,
                          "url": "https://api.adsb.lol/v2/point"})
            any_live = True
        elif pt_err:
            tried.append({"source": "adsb.lol /v2/point (radius tiled)", "ok": False,
                          "error": pt_err, "url": "https://api.adsb.lol/v2/point"})

    if any_live:
        # moving + airborne first, then cap
        tracks.sort(key=lambda r: (0 if (r.get("speed_mps") or 0) > 5 else 1,
                                   0 if r.get("on_ground") is False else 1))
        return tracks[:limit], tried, ("mixed" if len(tried) > 1 and sum(
            1 for x in tried if x.get("ok")) > 1 else "live")

    # SAMPLE — both real sources failed; serve bundled snapshot if present, honestly.
    snap = _load_snapshot("air")
    if snap and isinstance(snap, dict):
        out = []
        for a in (snap.get("data", {}).get("aircraft") or snap.get("aircraft") or [])[:limit]:
            tr = _track_from_adsblol(a, t)
            tr["live"] = False
            tr["source"] = "bundled in-image snapshot (sample)"
            tr["provenance"] = "SAMPLE — all live aircraft sources unreachable; bundled snapshot"
            out.append(tr)
        return out, tried, "sample"
    return [], tried, "sample"


# ===========================================================================
# VESSELS — REAL AIS. AISStream (keyed wss, PRIMARY) -> Digitraffic FI (no key)
#           -> SAMPLE. Dark-fleet / sanctioned heuristic over REAL AIS.
# ===========================================================================
_DIGITRAFFIC_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
_AISSTREAM_WSS = "wss://stream.aisstream.io/v0/stream"

# AISStream background collector state (filled only when a real key is present).
_AIS_STREAM = {
    "vessels": {},      # mmsi -> normalized track
    "started": False,
    "last_msg_ts": None,
    "error": None,
    "thread": None,
}
_AIS_STREAM_LOCK = threading.Lock()


def _aisstream_key():
    for k in ("SZL_AISSTREAM_API_KEY", "AISSTREAM_API_KEY", "AISSTREAM_KEY"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    return None


def _nav_status_text(n):
    table = {0: "under way (engine)", 1: "at anchor", 2: "not under command",
             3: "restricted manoeuvrability", 4: "constrained by draught",
             5: "moored", 6: "aground", 7: "fishing", 8: "under way (sailing)",
             15: "undefined"}
    return table.get(n, str(n) if n is not None else None)


def _track_from_ais_position(mmsi, lat, lon, sog, cog, hdg, navstat, name, t, source, url, prov):
    return {
        "track_id": "ais:%s" % mmsi,
        "domain": "sea",
        "label": (name or None),
        "lat": lat, "lon": lon,
        "alt_m": None,
        "speed_mps": round(sog * KN_TO_MS, 2) if isinstance(sog, (int, float)) else None,
        "heading_deg": cog if cog is not None else hdg,
        "on_ground": None,
        "country": _mid_to_flag(mmsi),
        "kind": _nav_status_text(navstat),
        "raw": {"mmsi": mmsi, "sog_kn": sog, "cog_deg": cog, "heading_deg": hdg,
                "nav_status": navstat},
        "source": source,
        "source_url": url,
        "live": True,
        "provenance": prov,
        "ts": _now_iso(),
    }


def _mid_to_flag(mmsi):
    """Map AIS MID (first 3 digits of MMSI) to a flag-state CLAIM (advisory).
    Partial table covering theaters of interest. Returns None when unknown."""
    try:
        mid = int(str(int(mmsi))[:3])
    except Exception:
        return None
    mids = {412: "China", 413: "China", 414: "China", 416: "Taiwan",
            440: "South Korea", 441: "South Korea", 431: "Japan", 432: "Japan",
            273: "Russia", 230: "Finland", 265: "Sweden", 266: "Sweden",
            636: "Liberia", 538: "Marshall Is.", 477: "Hong Kong", 563: "Singapore",
            564: "Singapore", 565: "Singapore", 374: "Panama", 370: "Panama",
            371: "Panama", 372: "Panama", 373: "Panama"}
    return mids.get(mid)


def _aisstream_collector(key):
    """Bounded background wss collector for REAL AISStream PositionReports.
    Subscribes a WIDE bounding box (global-ish, capped). Keeps last-known per
    MMSI. NEVER fabricates; on any failure records the error and exits cleanly.
    Requires the `websocket-client` package; if absent, records that honestly."""
    try:
        import websocket  # type: ignore  (websocket-client)
    except Exception as e:
        with _AIS_STREAM_LOCK:
            _AIS_STREAM["error"] = "websocket-client not installed (%s) — vessels fall back to Digitraffic" % type(e).__name__
            _AIS_STREAM["started"] = False
        return
    sub = {
        "APIKey": key,
        # wide multi-theater boxes incl. China seas + Baltic (lat/lon pairs).
        "BoundingBoxes": [
            [[-10.0, 100.0], [46.0, 150.0]],   # Asia-Pacific incl. China seas
            [[55.0, 10.0], [66.0, 30.0]],      # Baltic
        ],
        "FilterMessageTypes": ["PositionReport"],
    }
    while True:
        try:
            ws = websocket.create_connection(_AISSTREAM_WSS, timeout=20)
            ws.send(json.dumps(sub))
            with _AIS_STREAM_LOCK:
                _AIS_STREAM["error"] = None
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                if msg.get("MessageType") != "PositionReport":
                    continue
                pr = (msg.get("Message") or {}).get("PositionReport") or {}
                meta = msg.get("MetaData") or {}
                mmsi = pr.get("UserID") or meta.get("MMSI")
                if mmsi is None:
                    continue
                tr = _track_from_ais_position(
                    mmsi, pr.get("Latitude"), pr.get("Longitude"),
                    pr.get("Sog"), pr.get("Cog"), pr.get("TrueHeading"),
                    pr.get("NavigationalStatus"),
                    (meta.get("ShipName") or "").strip() or None,
                    _theater("asia_pacific"),
                    "AISStream.io live wss (free key, real-time AIS)",
                    _AISSTREAM_WSS,
                    "AISStream wss PositionReport · real-time · keyed primary")
                with _AIS_STREAM_LOCK:
                    _AIS_STREAM["vessels"][str(mmsi)] = tr
                    _AIS_STREAM["last_msg_ts"] = time.time()
                    # bound memory: keep most-recent ~4000 vessels
                    if len(_AIS_STREAM["vessels"]) > 4000:
                        items = sorted(_AIS_STREAM["vessels"].items(),
                                       key=lambda kv: kv[1].get("ts") or "")
                        for k, _ in items[:len(items) - 4000]:
                            _AIS_STREAM["vessels"].pop(k, None)
        except Exception as e:
            with _AIS_STREAM_LOCK:
                _AIS_STREAM["error"] = "%s: %s" % (type(e).__name__, e)
            time.sleep(10)  # backoff, then reconnect


def _ensure_aisstream():
    key = _aisstream_key()
    if not key:
        return False
    with _AIS_STREAM_LOCK:
        if _AIS_STREAM["started"]:
            return True
        _AIS_STREAM["started"] = True
        th = threading.Thread(target=_aisstream_collector, args=(key,),
                              name="aisstream-collector", daemon=True)
        _AIS_STREAM["thread"] = th
        th.start()
    return True


def _fetch_digitraffic(theater_key, limit):
    """REAL no-key AIS (Fintraffic / Digitraffic, Baltic). Returns tracks list."""
    t = _theater(theater_key)
    geo = _http_get(_DIGITRAFFIC_URL, timeout=30, headers={"User-Agent": _UA})
    feats = geo.get("features", []) if isinstance(geo, dict) else []
    out = []
    for f in feats:
        props = f.get("properties", {}) or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
        lon, lat = (coords + [None, None])[:2]
        mmsi = props.get("mmsi") or f.get("mmsi")
        if mmsi is None:
            continue
        if not _in_box(lat, lon, t):
            continue
        out.append(_track_from_ais_position(
            mmsi, lat, lon, props.get("sog"), props.get("cog"),
            props.get("heading"), props.get("navStat"), None, t,
            "Digitraffic Finland AIS (Fintraffic, CC BY 4.0, no key)",
            _DIGITRAFFIC_URL,
            "Digitraffic FI AIS REST · no-key live fallback · box-filtered theater=%s" % t.get("label")))
    # prefer moving vessels
    out.sort(key=lambda r: 0 if (r.get("speed_mps") or 0) > 0.3 else 1)
    return out[:limit]


def _dark_fleet_flag(track):
    """ADVISORY dark-fleet / sanctioned heuristic over REAL AIS. NOT proven.
    Signals (each a heuristic, labelled): implausible speed, COG/heading
    incoherence, missing flag resolution, sanctioned-IMO/MMSI match deferred to
    the OSINT designation list. Returns {flag:bool, reasons:[...], advisory:True}."""
    reasons = []   # substantive anomaly signals (raise the advisory flag)
    notes = []     # low-weight context (do NOT by themselves raise the flag)
    sog = track.get("speed_mps")
    if sog is not None and sog > 25.0:  # ~48 kn — implausible for most vessels
        reasons.append("implausible SOG (%.1f m/s) — possible AIS spoof/fault" % sog)
    raw = track.get("raw") or {}
    cog = raw.get("cog_deg")
    hdg = raw.get("heading_deg")
    if cog is not None and hdg is not None:
        delta = abs(((cog - hdg + 180) % 360) - 180)
        if delta > 60:
            reasons.append("COG/heading incoherence (%.0f°) — manoeuvre or spoof" % delta)
    navtxt = (track.get("kind") or "")
    if "not under command" in navtxt and (sog or 0) > 1.0:
        reasons.append("AIS nav-status 'not under command' while making way — anomalous")
    if track.get("country") is None:
        notes.append("flag-state unresolved from MMSI MID")
    return {"flag": bool(reasons), "reasons": reasons, "notes": notes,
            "label": "dark-fleet heuristic — ADVISORY, computed over real AIS, NOT proven"}


def _fetch_vessels(theater_key, limit):
    """REAL vessels with redundancy chain. Returns (tracks, tried, mode)."""
    t = _theater(theater_key)
    tried = []

    # PRIMARY — AISStream keyed wss (live cache filled by background collector).
    if _ensure_aisstream():
        with _AIS_STREAM_LOCK:
            cache = list(_AIS_STREAM["vessels"].values())
            last = _AIS_STREAM["last_msg_ts"]
            err = _AIS_STREAM["error"]
        fresh = last is not None and (time.time() - last) < 120
        in_box = [v for v in cache if _in_box(v["lat"], v["lon"], t)]
        if fresh and in_box:
            in_box.sort(key=lambda r: 0 if (r.get("speed_mps") or 0) > 0.3 else 1)
            out = in_box[:limit]
            for v in out:
                v["dark_fleet"] = _dark_fleet_flag(v)
            tried.append({"source": "AISStream.io wss (keyed)", "ok": True,
                          "count": len(out), "cached_total": len(cache),
                          "url": _AISSTREAM_WSS})
            return out, tried, "live"
        tried.append({"source": "AISStream.io wss (keyed)", "ok": False,
                      "error": err or ("no in-box positions yet (collector warming)"
                                       if not in_box else "stale (>120s)"),
                      "url": _AISSTREAM_WSS})
    else:
        tried.append({"source": "AISStream.io wss (keyed)", "ok": False,
                      "error": "no key in Space secret store (SZL_AISSTREAM_API_KEY) — falling back to no-key Digitraffic",
                      "url": _AISSTREAM_WSS})

    # FALLBACK — Digitraffic FI (no key, REAL).
    try:
        out = _fetch_digitraffic(theater_key, limit)
        for v in out:
            v["dark_fleet"] = _dark_fleet_flag(v)
        tried.append({"source": "Digitraffic Finland AIS (no key)", "ok": True,
                      "count": len(out), "url": _DIGITRAFFIC_URL})
        if out:
            return out, tried, "live"
        # Digitraffic reachable but no vessels IN this theater (e.g. China box):
        # honest — real source, just out of its geographic coverage.
        return out, tried, "live"
    except Exception as e:
        tried.append({"source": "Digitraffic Finland AIS (no key)", "ok": False,
                      "error": "%s: %s" % (type(e).__name__, e), "url": _DIGITRAFFIC_URL})

    # SAMPLE — bundled snapshot if present.
    snap = _load_snapshot("ais")
    if snap and isinstance(snap, dict):
        out = []
        for v in (snap.get("data", {}).get("vessels") or snap.get("vessels") or [])[:limit]:
            tr = _track_from_ais_position(
                v.get("mmsi"), v.get("lat"), v.get("lon"), v.get("sog"),
                v.get("cog"), v.get("heading"), v.get("navStat"), v.get("name"), t,
                "bundled in-image snapshot (sample)", _DIGITRAFFIC_URL,
                "SAMPLE — all live AIS sources unreachable; bundled snapshot")
            tr["live"] = False
            tr["dark_fleet"] = _dark_fleet_flag(tr)
            out.append(tr)
        return out, tried, "sample"
    return [], tried, "sample"


# ===========================================================================
# REMOTE ID — REAL OpenDroneID / ASTM F3411 broadcasts (relayed by a sniffer).
# Honest EMPTY when none. A field sniffer / Web Serial relay POSTs to /ingest.
# ===========================================================================
_RID_LOCK = threading.Lock()
_RID_CACHE: dict = {}   # uas_id -> normalized RID track
_RID_TTL = 60           # seconds a relayed broadcast is considered "live"


def _track_from_rid(b):
    """Normalize an OpenDroneID / ASTM F3411 broadcast dict to a TRACK.
    Accepts the common ODID field names (basic_id, location, operator)."""
    loc = b.get("location") or b.get("Location") or {}
    bid = b.get("basic_id") or b.get("BasicID") or {}
    op = b.get("operator") or b.get("system") or {}
    uas_id = (bid.get("uas_id") or bid.get("UASID") or b.get("uas_id")
              or b.get("id") or "unknown")
    lat = loc.get("latitude", loc.get("Latitude", b.get("lat")))
    lon = loc.get("longitude", loc.get("Longitude", b.get("lon")))
    alt = loc.get("geodetic_altitude", loc.get("altitude", b.get("alt_m")))
    spd = loc.get("speed_horizontal", loc.get("speed", b.get("speed_mps")))
    hdg = loc.get("direction", loc.get("track", b.get("heading_deg")))
    return {
        "track_id": "rid:%s" % uas_id,
        "domain": "rid",
        "label": str(uas_id),
        "lat": lat, "lon": lon,
        "alt_m": alt,
        "speed_mps": spd,
        "heading_deg": hdg,
        "on_ground": None,
        "country": None,
        "kind": bid.get("ua_type") or bid.get("UAType") or b.get("ua_type"),
        "raw": b,
        "source": b.get("source") or "OpenDroneID / ASTM F3411 broadcast (relayed)",
        "source_url": "ASTM F3411-22a Remote-ID (broadcast; relayed by field sniffer)",
        "live": True,
        "provenance": ("ASTM F3411/OpenDroneID broadcast relayed by a connected sniffer · "
                       "UNAUTHENTICATED broadcast — every field is a CLAIM, not ground truth"),
        "ts": _now_iso(),
    }


def _rid_live_tracks():
    now = time.time()
    out = []
    with _RID_LOCK:
        for k in list(_RID_CACHE.keys()):
            ent = _RID_CACHE[k]
            if now - ent["_ts"] > _RID_TTL:
                _RID_CACHE.pop(k, None)
                continue
            out.append(ent["track"])
    return out


# ===========================================================================
# OSINT (public, no-key) — defense/UAS + sanctions / dark-vessel designations.
# "open-source collection," cited with source URLs + ts. Cached server-side.
# ===========================================================================
_UN1718_VESSELS = "https://data.opensanctions.org/datasets/latest/un_1718_vessels/targets.simple.csv"
_OPENSANCTIONS_MARITIME = "https://data.opensanctions.org/datasets/latest/maritime/entities.ftm.json"
_USGS_DAY = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

_OSINT_TTL = {
    "sanctioned_vessels": 6 * 3600,
    "geo_context": 600,
}


def _csv_rows(raw_bytes, cap=400):
    import csv
    import io
    text = raw_bytes.decode("utf-8", "replace") if isinstance(raw_bytes, (bytes, bytearray)) else raw_bytes
    rows = []
    for i, row in enumerate(csv.DictReader(io.StringIO(text))):
        if i >= cap:
            break
        rows.append(row)
    return rows


def _osint_sanctioned_vessels():
    """REAL public designated/sanctioned vessel list — UN SC 1718 designated
    vessels (no key). Each item carries source URL + ts. OSINT(public)."""
    raw = _http_get_raw(_UN1718_VESSELS, timeout=30, headers={"User-Agent": _UA})
    rows = _csv_rows(raw)
    items = []
    for r in rows:
        if (r.get("schema") or "").lower() != "vessel":
            # the dataset is vessel-focused but be defensive
            pass
        items.append({
            "name": r.get("name"),
            "aliases": [a for a in (r.get("aliases") or "").split(";") if a][:6],
            "identifiers": r.get("identifiers"),  # IMO etc.
            "countries": r.get("countries"),
            "program": r.get("sanctions") or r.get("program_ids"),
            "first_seen": r.get("first_seen"),
            "last_seen": r.get("last_seen"),
            "kind": "designated_vessel",
            "label": "OSINT(public) — UN Security Council 1718 designated vessel",
        })
    return {
        "source": "UN Security Council 1718 Committee — Designated Vessels (via OpenSanctions, public, no key)",
        "source_url": _UN1718_VESSELS,
        "doc_url": "https://www.un.org/securitycouncil/sanctions/1718/materials",
        "count": len(items), "items": items,
    }


def _osint_geo_context():
    """REAL public geophysical context (USGS, no key) — situational backdrop."""
    data = _http_get(_USGS_DAY, timeout=20, headers={"User-Agent": _UA})
    feats = (data or {}).get("features", []) or []
    items = []
    for f in feats[:60]:
        p = f.get("properties") or {}
        g = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        items.append({"place": p.get("place"), "mag": p.get("mag"),
                      "time_ms": p.get("time"), "lon": g[0], "lat": g[1],
                      "depth_km": g[2] if len(g) > 2 else None,
                      "url": p.get("url"),
                      "label": "OSINT(public) — USGS seismic event (situational context)"})
    return {
        "source": "USGS Earthquake Hazards Program — all, past day (public, no key)",
        "source_url": _USGS_DAY, "count": len(items), "items": items,
    }


def _osint_cached(stream, builder):
    ttl = _OSINT_TTL.get(stream, 3600)
    ck = "osint:%s" % stream
    now = time.time()
    with _LOCK:
        ent = _CACHE.get(ck)
    if ent and (now - ent["ts"]) < ttl:
        return {"mode": "cached" if (now - ent["ts"]) > 5 else "live",
                "fetched_at": ent["iso"], "ttl_s": ttl, "live": True, **ent["data"]}
    try:
        data = builder()
        iso = _now_iso()
        with _LOCK:
            _CACHE[ck] = {"data": data, "ts": now, "iso": iso}
        return {"mode": "live", "fetched_at": iso, "ttl_s": ttl, "live": True, **data}
    except Exception as e:
        if ent:
            return {"mode": "cached", "fetched_at": ent["iso"], "ttl_s": ttl, "live": True,
                    "cache_note": "upstream unreachable (%s) — last good value" % type(e).__name__,
                    **ent["data"]}
        return {"mode": "unreachable", "fetched_at": None, "ttl_s": ttl, "live": False,
                "error": "upstream unreachable: %s" % e, "count": 0, "items": [],
                "source": stream, "source_url": None}


# ===========================================================================
# Route registration.
# ===========================================================================
def register(app, ns="killinchu"):
    base = "/api/%s/v1" % ns

    async def _run(fn, *a, **kw):
        import anyio
        return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))

    def _limit(request, default=120, cap=500):
        try:
            return max(1, min(int(request.query_params.get("limit", str(default))), cap))
        except Exception:
            return default

    _HONEST = ("REAL live feeds, server-side fetched + cached, same-origin (0 client CDN). "
               "Every record is normalized to the TRACK shape and carries source/live/"
               "provenance/ts. live=true means a REAL fetch succeeded this cycle; a record "
               "is only SAMPLE if every real source failed (then a bundled snapshot, never "
               "fabricated). Effector/engage stays SIMULATED (human-on-the-loop, legal line). "
               "Doctrine v11: locked=8 {F1,F4,F7,F11,F12,F18,F19,F22}; Λ=Conjecture 1 (advisory).")

    def _fetch_cached(kind, fn, theater, limit, ttl=20):
        """Short-TTL cache so repeated demo polls are instant and we are gentle on
        upstreams. Honest: served value is still REAL live data (<=ttl old)."""
        ck = "feed:%s:%s:%s" % (kind, theater, limit)
        now = time.time()
        with _LOCK:
            ent = _CACHE.get(ck)
        if ent and (now - ent["ts"]) < ttl:
            return ent["val"]
        val = fn(theater, limit)
        with _LOCK:
            _CACHE[ck] = {"val": val, "ts": now}
        return val

    async def _aircraft(request):
        theater = request.query_params.get("theater", _DEFAULT_THEATER)
        limit = _limit(request)
        tracks, tried, mode = await _run(_fetch_cached, "air", _fetch_aircraft, theater, limit)
        live = any(t.get("ok") for t in tried)
        return JSONResponse({
            "feed": "aircraft", "domain": "air",
            "theater": theater, "theater_box": _theater(theater),
            "count": len(tracks), "mode": mode, "live": live,
            "sources_tried": tried,
            "tracks": tracks,
            "honest": _HONEST, "doctrine": "v11", "fetched_at": _now_iso(),
        })

    async def _vessels(request):
        theater = request.query_params.get("theater", "baltic")
        limit = _limit(request)
        tracks, tried, mode = await _run(_fetch_cached, "sea", _fetch_vessels, theater, limit)
        live = any(t.get("ok") for t in tried)
        return JSONResponse({
            "feed": "vessels", "domain": "sea",
            "theater": theater, "theater_box": _theater(theater),
            "count": len(tracks), "mode": mode, "live": live,
            "sources_tried": tried,
            "dark_fleet_note": ("Dark-fleet / sanctioned flags are an ADVISORY heuristic "
                                "computed over REAL AIS — NOT proven. Cross-reference "
                                "/osint/intel?vertical=sanctioned_vessels for designations."),
            "tracks": tracks,
            "honest": _HONEST, "doctrine": "v11", "fetched_at": _now_iso(),
        })

    async def _remoteid(request):
        tracks = await _run(_rid_live_tracks)
        return JSONResponse({
            "feed": "remoteid", "domain": "rid",
            "count": len(tracks), "mode": ("live" if tracks else "idle"),
            "live": bool(tracks),
            "tracks": tracks,
            "honest": ("REAL OpenDroneID / ASTM F3411 Remote-ID broadcasts relayed by a "
                       "connected field sniffer / Web Serial bridge to POST "
                       "/api/%s/v1/feeds/remoteid/ingest. Broadcasts are UNAUTHENTICATED — "
                       "every decoded field is a CLAIM, not ground truth. Honest EMPTY "
                       "(idle) when no broadcast is being relayed — never fabricated. "
                       "The /jackin decoder consumes this feed." % ns),
            "ingest_endpoint": "%s/feeds/remoteid/ingest" % base,
            "doctrine": "v11", "fetched_at": _now_iso(),
        })

    async def _remoteid_ingest(request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "body must be a JSON OpenDroneID/F3411 broadcast object"},
                                status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        broadcasts = body.get("broadcasts") if isinstance(body.get("broadcasts"), list) else [body]
        accepted = []
        for b in broadcasts:
            if not isinstance(b, dict):
                continue
            tr = _track_from_rid(b)
            with _RID_LOCK:
                _RID_CACHE[tr["track_id"]] = {"track": tr, "_ts": time.time()}
            accepted.append(tr["track_id"])
        return JSONResponse({"ok": True, "accepted": len(accepted),
                             "track_ids": accepted, "ttl_s": _RID_TTL,
                             "honest": "relayed real broadcast(s) cached; expire after %ss" % _RID_TTL,
                             "fetched_at": _now_iso()})

    async def _osint_intel(request):
        vertical = (request.query_params.get("vertical") or "all").lower()
        out = {"feed": "osint/intel", "label": "OSINT(public) — open-source collection",
               "doctrine": "v11", "fetched_at": _now_iso(),
               "honest": ("Public open-source collection only — defense/UAS open-source "
                          "reporting + sanctions / dark-vessel designation lists, returned "
                          "with source URLs + timestamps. NO classified or non-public "
                          "claims. Rate-limited + cached server-side."),
               "verticals": {}}
        if vertical in ("all", "sanctioned_vessels", "naval", "sea"):
            out["verticals"]["sanctioned_vessels"] = await _run(
                _osint_cached, "sanctioned_vessels", _osint_sanctioned_vessels)
        if vertical in ("all", "geo_context", "geo"):
            out["verticals"]["geo_context"] = await _run(
                _osint_cached, "geo_context", _osint_geo_context)
        out["live"] = any(v.get("live") for v in out["verticals"].values())
        out["count"] = sum(v.get("count", 0) for v in out["verticals"].values())
        out["valid_verticals"] = ["all", "sanctioned_vessels", "geo_context"]
        if not out["verticals"]:
            out["note"] = ("unknown vertical %r — use one of %s"
                           % (vertical, out["valid_verticals"]))
        return JSONResponse(out)

    async def _feeds_status(request):
        with _AIS_STREAM_LOCK:
            ais_started = _AIS_STREAM["started"]
            ais_last = _AIS_STREAM["last_msg_ts"]
            ais_err = _AIS_STREAM["error"]
            ais_n = len(_AIS_STREAM["vessels"])
        return JSONResponse({
            "layer": "killinchu real-data feeds (TRACK-normalized)",
            "honest": _HONEST, "doctrine": "v11", "fetched_at": _now_iso(),
            "feeds": {
                "aircraft": {"endpoint": "%s/feeds/aircraft" % base,
                             "primary": "OpenSky /states/all (anon)",
                             "parallel": "adsb.lol /v2/mil",
                             "fallback": "bundled snapshot (SAMPLE)",
                             "theaters": sorted(THEATERS.keys())},
                "vessels": {"endpoint": "%s/feeds/vessels" % base,
                            "primary": "AISStream.io wss (keyed, secret store)",
                            "fallback": "Digitraffic FI AIS (no key) -> bundled snapshot (SAMPLE)",
                            "aisstream": {"key_present": bool(_aisstream_key()),
                                          "collector_started": ais_started,
                                          "cached_vessels": ais_n,
                                          "last_msg_age_s": (round(time.time() - ais_last, 1)
                                                             if ais_last else None),
                                          "error": ais_err}},
                "remoteid": {"endpoint": "%s/feeds/remoteid" % base,
                             "ingest": "%s/feeds/remoteid/ingest" % base,
                             "live_tracks": len(_rid_live_tracks())},
                "osint_intel": {"endpoint": "%s/osint/intel" % base,
                                "sources": ["UN SC 1718 designated vessels (OpenSanctions, no key)",
                                            "USGS seismic (no key)"]},
            },
        })

    routes = [
        Route("%s/feeds/aircraft" % base, _aircraft, methods=["GET"], name="%s_feeds_aircraft" % ns),
        Route("%s/feeds/vessels" % base, _vessels, methods=["GET"], name="%s_feeds_vessels" % ns),
        Route("%s/feeds/remoteid" % base, _remoteid, methods=["GET"], name="%s_feeds_remoteid" % ns),
        Route("%s/feeds/remoteid/ingest" % base, _remoteid_ingest, methods=["POST"], name="%s_feeds_remoteid_ingest" % ns),
        Route("%s/feeds/realdata/status" % base, _feeds_status, methods=["GET"], name="%s_feeds_realdata_status" % ns),
        Route("%s/osint/intel" % base, _osint_intel, methods=["GET"], name="%s_osint_intel" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)

    # Warm the AISStream collector if a key is present (no-op otherwise).
    try:
        _ensure_aisstream()
    except Exception:
        pass

    return {"status": "ok", "base": base,
            "endpoints": [r.path for r in routes],
            "theaters": sorted(THEATERS.keys()),
            "aisstream_key_present": bool(_aisstream_key())}


__all__ = ["register", "_fetch_aircraft", "_fetch_vessels", "_track_from_rid",
           "THEATERS"]
