# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Authored by Yachay (CTO). Co-author: Perplexity Computer Agent.
"""
killinchu_live_feeds.py — SHARED LIVE-DATA LAYER for the killinchu field surface.

Mirrors a11oy_live_feeds.py: exposes server-side-fetched + cached, CORS-safe,
honestly-labelled proxies so the browser only ever hits OUR same-origin endpoints
(sovereign — 0 runtime CDN from the client). NEVER fabricates: a down feed serves
the last good in-memory value or the bundled on-disk snapshot labelled "cached".

Endpoints registered EARLY (before the /{full_path:path} catch-all in serve.py):

  GET /api/killinchu/v1/live              index of feeds (reachability + honesty)
  GET /api/killinchu/v1/live/<feed>       one feed (ais|air|celestrak|rekor|kev|osv|prometheus)
  GET /api/killinchu/v1/ais/live          Digitraffic FI AIS (live vessels) — convenience alias
  GET /api/killinchu/v1/air/live          adsb.lol live aircraft/drone ADS-B — convenience alias
  GET /api/killinchu/v1/feeds/status      reachability + snapshot honesty (legacy serve.py contract)

Every response carries an HONEST label:
    {"source": <human source>, "source_url": <upstream URL>,
     "mode": "live" | "cached" | "self",   # never fabricated
     "fetched_at": <iso8601>, "ttl_s": <int>, ...payload}

  - "live"   = freshly fetched from upstream this request (or within TTL).
  - "cached" = upstream unreachable; serving last good in-memory value or the
               bundled on-disk snapshot (stage resilience).
  - "self"   = our own internal real data (receipt ledger, signed-command log,
               twin telemetry, Λ gate) — labelled 'live (self)' by callers.

Feeds + TTLs (all free, no-auth):
  ais         (meri.digitraffic.fi/api/ais/v1/locations, gzip)      TTL 20s
  air         (api.adsb.lol/v2/mil  military ADS-B, fallback /all)  TTL 15s
  celestrak   (celestrak.org gp.php?GROUP=stations&FORMAT=json)     TTL 2h
  rekor       (rekor.sigstore.dev/api/v1/log)                       TTL 60s
  kev         (cisa.gov known_exploited_vulnerabilities.json)       TTL 6h
  osv         (api.osv.dev/v1/query, POST)                          TTL 1h
  prometheus  (prometheus.demo.prometheus.io/api/v1/query)          TTL 30s

Also EXPORTS the helpers reused by killinchu_health_twin (its line-66 import):
  _fetch_ais(limit, lat, lon, radius)  -> {"vessels":[{mmsi,name,sog,cog,heading,
                                            navStat,lat,lon,raim,posAcc}], ...}
  _ais_to_vector(vessel)               -> normalised kinematic feature vector
  _lambda_trust(axes)                  -> geometric-mean Λ trust aggregate (Conjecture 1)
"""
from __future__ import annotations

import gzip
import io
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

_SNAP_DIR = Path(os.environ.get("KILLINCHU_LIVE_SNAPSHOTS", "/app/live_snapshots"))
_UA = "killinchu-live-proxy/1.0 (+https://szlholdings-killinchu.hf.space)"

# in-memory cache: feed -> {"data":..., "ts":..., "mode":..., "iso":...}
_CACHE: dict = {}
_LOCK = threading.Lock()

_TTL = {
    "ais": 20, "air": 15, "celestrak": 2 * 3600, "rekor": 60,
    "kev": 6 * 3600, "osv": 3600, "prometheus": 30,
}

_SOURCE = {
    "ais": ("Digitraffic Finland AIS live vessel locations (no auth)",
            "https://meri.digitraffic.fi/api/ais/v1/locations"),
    "air": ("adsb.lol community ADS-B (military + civil aircraft, no auth)",
            "https://api.adsb.lol/v2/mil"),
    "celestrak": ("CelesTrak GP element sets (ISS + stations)",
                  "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json"),
    "rekor": ("Sigstore Rekor transparency log",
              "https://rekor.sigstore.dev/api/v1/log"),
    "kev": ("CISA Known Exploited Vulnerabilities catalog",
            "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"),
    "osv": ("OSV.dev open-source vulnerability database",
            "https://api.osv.dev/v1/query"),
    "prometheus": ("Prometheus demo (node/caddy/blackbox exporters)",
                   "https://prometheus.demo.prometheus.io/api/v1/query"),
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# SOVEREIGN SAME-ORIGIN PROXIES.
# The browser must only ever hit OUR origin (0 client CDN / 0 off-origin).
# These two tables back GET /api/<ns>/v1/proxy/<name> (public free feeds) and
# GET /api/<ns>/v1/gov/<name> (the cross-platform governed command/cosign loop:
# killinchu reads a11oy's REAL ledger/command-log/policy-gates/sentra verdict,
# but the FETCH happens server-side so the field surface stays sovereign).
# Every response keeps the honest live|cached label.
# ---------------------------------------------------------------------------
_A11OY = os.environ.get("A11OY_BASE", "https://szlholdings-a11oy.hf.space")

_PROXY = {
    # name: (human source, GET url, ttl_s)
    "usgs_day":  ("USGS Earthquake Hazards Program (past day)",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson", 120),
    "usgs_hour": ("USGS Earthquake Hazards Program (past hour)",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson", 60),
    "nvd":       ("U.S. National Vulnerability Database (NVD CVE API 2.0)",
                  "https://services.nvd.nist.gov/rest/json/cves/2.0", 1800),
    "mitre_attack": ("MITRE ATT&CK Enterprise STIX bundle",
                     "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json", 6 * 3600),
    "cisa_kev":  ("CISA Known Exploited Vulnerabilities catalog (GitHub mirror)",
                  "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json", 6 * 3600),
}

# governed-loop routes proxied from a11oy (the command/cosign-receipt platform).
# method 'POST' entries pass the JSON body through verbatim. ttl 0 = never cache.
_GOV = {
    "ledger":      ("GET",  "/api/a11oy/v1/ledger", 15),
    "command-log": ("GET",  "/api/a11oy/v2/command-log", 10),
    "policy-gates": ("GET", "/api/a11oy/v1/policy/gates", 60),
    "a11oy-honest": ("GET", "/api/a11oy/v1/honest", 60),
    "sentra-verdict": ("POST", "/api/sentra/v1/verdict", 0),
}


def _get_proxy(name):
    """Cached, honestly-labelled same-origin proxy for a free public feed."""
    if name not in _PROXY:
        raise ValueError("unknown proxy: %s" % name)
    src, url, ttl = _PROXY[name]
    ckey = "proxy:%s" % name
    with _LOCK:
        ent = _CACHE.get(ckey)
    now = time.time()
    if ent and (now - ent["ts"]) < ttl:
        return {"source": src, "source_url": ent.get("url", url), "mode": ent["mode"],
                "fetched_at": ent["iso"], "ttl_s": ttl, "data": ent["data"]}
    return None  # caller fetches fresh (so it can vary the query string)


def _store_proxy(name, data, url=None):
    src, durl, ttl = _PROXY[name]
    iso = _now_iso()
    with _LOCK:
        _CACHE["proxy:%s" % name] = {"data": data, "ts": time.time(),
                                     "mode": "live", "iso": iso, "url": url or durl}
    return {"source": src, "source_url": url or durl, "mode": "live",
            "fetched_at": iso, "ttl_s": ttl, "data": data}


def _proxy_cached_or_error(name, exc, url=None):
    src, durl, ttl = _PROXY[name]
    with _LOCK:
        ent = _CACHE.get("proxy:%s" % name)
    if ent:
        return {"source": src, "source_url": ent.get("url", durl), "mode": "cached",
                "fetched_at": ent["iso"], "ttl_s": ttl,
                "cache_note": "upstream unreachable (%s) — serving last good value" % type(exc).__name__,
                "data": ent["data"]}
    return {"source": src, "source_url": url or durl, "mode": "cached",
            "fetched_at": None, "ttl_s": ttl,
            "error": "upstream unreachable: %s" % exc, "data": None}


def _http_get_raw(url, timeout=25, headers=None, data=None, method=None):
    """Return decoded bytes (gzip-aware)."""
    h = {"User-Agent": _UA, "Accept": "application/json", "Accept-Encoding": "gzip"}
    # Digitraffic REQUIRES a Digitraffic-User identifier or it returns HTTP 406.
    # (Verified from sandbox 2026-06-07: no header -> 406; with header -> 200.)
    if "digitraffic.fi" in url:
        h["Digitraffic-User"] = "SZLHoldings/killinchu"
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except Exception:
                pass
        return raw


def _http_get(url, timeout=25, headers=None, data=None, method=None):
    return json.loads(_http_get_raw(url, timeout=timeout, headers=headers, data=data, method=method))


def _load_snapshot(feed):
    p = _SNAP_DIR / ("%s.json" % feed)
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Honest helpers — exported and reused by killinchu_health_twin.
# ---------------------------------------------------------------------------
def _haversine_nm(a_lat, a_lon, b_lat, b_lon) -> float:
    R = 3440.065  # nm
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.asin(min(1.0, math.sqrt(x))), 3)


def _lambda_trust(axes: list[float]) -> float:
    """Λ TRUST AGGREGATE (Conjecture 1 — unconditional FALSE, advisory): geometric
    mean over trust axes. GM ≤ AM penalises any single weak axis. Matches
    serve._lambda_aggregate and killinchu_health_twin._geo_mean."""
    vals = [max(1e-6, min(1.0, float(v))) for v in (axes or []) if v is not None]
    if not vals:
        return 0.0
    return round(math.exp(sum(math.log(v) for v in vals) / len(vals)), 4)


def _ais_to_vector(vessel: dict) -> dict:
    """Normalise a vessel fix to a kinematic feature vector + plausibility flags.
    Honest: derived from the real AIS fields only; no fabricated values."""
    sog = vessel.get("sog")
    cog = vessel.get("cog")
    hdg = vessel.get("heading")
    mismatch = None
    if cog is not None and hdg is not None:
        mismatch = round(abs(((cog - hdg + 180) % 360) - 180), 1)
    return {
        "mmsi": vessel.get("mmsi"),
        "sog_kn": sog,
        "cog_deg": cog,
        "heading_deg": hdg,
        "cog_hdg_delta_deg": mismatch,
        "navStat": vessel.get("navStat"),
        "raim": vessel.get("raim"),
        "posAcc": vessel.get("posAcc"),
        "lat": vessel.get("lat"),
        "lon": vessel.get("lon"),
        # plausibility envelope (ships 0-40 kn); >40 implausible (spoof/fault)
        "sog_plausible": (sog is None) or (0.0 <= sog <= 40.0),
        "cog_hdg_coherent": (mismatch is None) or (mismatch <= 60.0),
    }


def _fetch_ais(limit: int = 12, lat: float | None = None,
               lon: float | None = None, radius: float | None = None) -> dict:
    """Fetch live Digitraffic FI AIS locations. Optional spatial filter: keep the
    `limit` vessels nearest to (lat,lon) within `radius` degrees (rough box).
    Returns {"vessels":[...], "source", "mode", "fetched_at", "total"}.
    Raises on hard upstream failure (callers guard)."""
    geo = _http_get(_SOURCE["ais"][1], timeout=30)
    feats = geo.get("features", []) if isinstance(geo, dict) else []
    vessels = []
    for f in feats:
        props = f.get("properties", {}) or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
        vlon, vlat = (coords + [None, None])[:2]
        mmsi = props.get("mmsi") or f.get("mmsi")
        v = {
            "mmsi": mmsi, "name": None,
            "sog": props.get("sog"), "cog": props.get("cog"),
            "heading": props.get("heading"), "navStat": props.get("navStat", 15),
            "lat": vlat, "lon": vlon,
            "raim": props.get("raim"), "posAcc": props.get("posAcc"),
        }
        if lat is not None and lon is not None and radius is not None and vlat is not None:
            if abs(vlat - lat) > radius or abs((vlon or 0) - lon) > radius:
                continue
        vessels.append(v)
    # prefer moving vessels (more interesting twins) then nearest-to-center
    if lat is not None and lon is not None:
        vessels.sort(key=lambda v: (
            0 if (v.get("sog") or 0) > 0.5 else 1,
            _haversine_nm(lat, lon, v["lat"], v["lon"]) if v["lat"] is not None else 9e9,
        ))
    else:
        vessels.sort(key=lambda v: 0 if (v.get("sog") or 0) > 0.5 else 1)
    vessels = vessels[: max(1, int(limit))]
    return {
        "vessels": vessels,
        "total": len(feats),
        "source": _SOURCE["ais"][0],
        "source_url": _SOURCE["ais"][1],
        "mode": "live",
        "fetched_at": _now_iso(),
        "attribution": "Data: Fintraffic / Digitraffic (CC BY 4.0)",
    }


def _fetch_air(limit: int = 40) -> dict:
    """Fetch live ADS-B aircraft from adsb.lol military endpoint (no auth, ODbL).
    Resilient fallback chain (all free/no-auth, verified 2026-06-07):
      1) api.adsb.lol/v2/mil   2) opendata.adsb.fi/api/v2/mil   3) airplanes.live/v2/mil
    OpenSky is DEAD for us (now OAuth2-only) and is intentionally NOT used."""
    data = None
    used = _SOURCE["air"][1]
    _chain = [
        _SOURCE["air"][1],                       # api.adsb.lol/v2/mil
        "https://opendata.adsb.fi/api/v2/mil",   # adsb.fi (ODbL)
        "https://airplanes.live/v2/mil",         # airplanes.live
    ]
    _last = None
    for _u in _chain:
        try:
            data = _http_get(_u, timeout=14)
            used = _u
            break
        except Exception as _e:
            _last = _e
            data = None
    if data is None:
        # final civil fallback on adsb.lol before giving up to the cache layer
        data = _http_get("https://api.adsb.lol/v2/all", timeout=18)
        used = "https://api.adsb.lol/v2/all"
    ac = (data.get("ac") or data.get("aircraft") or []) if isinstance(data, dict) else []
    out = []
    for a in ac[: max(1, int(limit))]:
        out.append({
            "hex": a.get("hex"), "flight": (a.get("flight") or "").strip() or None,
            "lat": a.get("lat"), "lon": a.get("lon"),
            "alt_baro": a.get("alt_baro"), "gs": a.get("gs"),
            "track": a.get("track"), "category": a.get("category"),
            "type": a.get("t"), "squawk": a.get("squawk"),
        })
    return {"aircraft": out, "total": len(ac), "endpoint": used,
            "attribution": "Data: adsb.lol / adsb.fi community ADS-B (ODbL)"}


# ---------------------------------------------------------------------------
# Per-feed raw fetch dispatcher.
# ---------------------------------------------------------------------------
def _fetch(feed):
    if feed == "ais":
        return _fetch_ais(40, 59.5, 22.0, 3.0)
    if feed == "air":
        return _fetch_air(40)
    if feed == "celestrak":
        return _http_get(_SOURCE["celestrak"][1], timeout=20)
    if feed == "rekor":
        return {"log": _http_get(_SOURCE["rekor"][1], timeout=15)}
    if feed == "kev":
        return _http_get(_SOURCE["kev"][1], timeout=40)
    if feed == "osv":
        out = {}
        for pkg, eco in (("tensorflow", "PyPI"), ("torch", "PyPI"),
                         ("transformers", "PyPI"), ("numpy", "PyPI"), ("requests", "PyPI")):
            body = json.dumps({"package": {"name": pkg, "ecosystem": eco}}).encode()
            r = _http_get("https://api.osv.dev/v1/query", timeout=20, data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            vulns = r.get("vulns", [])
            out[pkg] = {"ecosystem": eco, "count": len(vulns),
                        "vulns": [{"id": v.get("id"), "summary": v.get("summary"),
                                   "modified": v.get("modified"),
                                   "aliases": (v.get("aliases") or [])[:4]} for v in vulns[:25]]}
        return out
    if feed == "prometheus":
        base = "https://prometheus.demo.prometheus.io/api/v1/query?query="
        out = {}
        for k, q in (("up", "up"),
                     ("cpu", 'rate(node_cpu_seconds_total{mode="user"}[5m])'),
                     ("mem", "node_memory_MemAvailable_bytes"),
                     ("http_req", "rate(prometheus_http_requests_total[5m])")):
            out[k] = _http_get(base + urllib.parse.quote(q), timeout=12)
        return out
    raise ValueError("unknown feed: %s" % feed)


def get_feed(feed):
    """Cached, snapshot-fallback, honestly-labelled feed accessor."""
    ttl = _TTL.get(feed, 60)
    src, url = _SOURCE.get(feed, ("unknown", ""))
    with _LOCK:
        ent = _CACHE.get(feed)
    now = time.time()
    if ent and (now - ent["ts"]) < ttl:
        return {"source": src, "source_url": url, "mode": ent["mode"],
                "fetched_at": ent["iso"], "ttl_s": ttl, "data": ent["data"]}
    try:
        data = _fetch(feed)
        iso = _now_iso()
        with _LOCK:
            _CACHE[feed] = {"data": data, "ts": now, "mode": "live", "iso": iso}
        return {"source": src, "source_url": url, "mode": "live",
                "fetched_at": iso, "ttl_s": ttl, "data": data}
    except Exception as e:
        if ent:
            return {"source": src, "source_url": url, "mode": "cached",
                    "fetched_at": ent["iso"], "ttl_s": ttl,
                    "cache_note": "upstream unreachable (%s) — serving last good value" % type(e).__name__,
                    "data": ent["data"]}
        snap = _load_snapshot(feed)
        if snap is not None:
            return {"source": src, "source_url": url, "mode": "cached",
                    "fetched_at": "bundled-snapshot", "ttl_s": ttl,
                    "cache_note": "upstream unreachable (%s) — serving bundled in-image snapshot" % type(e).__name__,
                    "data": snap}
        return {"source": src, "source_url": url, "mode": "cached",
                "fetched_at": None, "ttl_s": ttl,
                "error": "upstream unreachable and no snapshot: %s" % e, "data": None}


# ---------------------------------------------------------------------------
# Route registration. serve.py calls register(app, ns="killinchu") on a FastAPI
# app; FastAPI wraps Starlette so app.router.routes.insert(0, Route(...)) places
# our GET routes BEFORE the /{full_path:path} catch-all (same pattern as a11oy).
# ---------------------------------------------------------------------------
def register(app, ns="killinchu"):
    base = "/api/%s/v1/live" % ns

    async def _run(fn, *a):
        import anyio
        return await anyio.to_thread.run_sync(lambda: fn(*a))

    async def _feed_route(request):
        feed = request.path_params["feed"]
        if feed not in _TTL:
            return JSONResponse({"error": "unknown feed", "feed": feed,
                                 "available": sorted(_TTL.keys())}, status_code=404)
        payload = await _run(get_feed, feed)
        return JSONResponse(payload)

    async def _index(request):
        feeds = []
        for f in sorted(_TTL.keys()):
            src, url = _SOURCE[f]
            with _LOCK:
                ent = _CACHE.get(f)
            feeds.append({"feed": f, "endpoint": "%s/%s" % (base, f),
                          "source": src, "source_url": url, "ttl_s": _TTL[f],
                          "last_mode": (ent or {}).get("mode"),
                          "last_fetched": (ent or {}).get("iso"),
                          "snapshot_present": (_SNAP_DIR / ("%s.json" % f)).exists()})
        return JSONResponse({
            "layer": "killinchu live-data proxy",
            "honest": ("Every feed is server-side fetched + cached, CORS-safe via OUR same-origin "
                       "proxy (0 client CDN). Mode is honestly labelled live/cached; a down feed "
                       "serves the bundled in-image snapshot labelled 'cached', never fabricated."),
            "count": len(feeds), "feeds": feeds,
        })

    async def _ais_live(request):
        try:
            limit = int(request.query_params.get("limit", "40"))
        except Exception:
            limit = 40
        payload = await _run(get_feed, "ais")
        # enrich with conformal Λ trust over the fleet's kinematic plausibility (honest, derived)
        try:
            vessels = (payload.get("data") or {}).get("vessels", [])[:limit]
            axes = []
            for v in vessels:
                vec = _ais_to_vector(v)
                axes.append(1.0 if vec["sog_plausible"] else 0.4)
                axes.append(1.0 if vec["cog_hdg_coherent"] else 0.5)
            payload["lambda_fleet"] = _lambda_trust(axes) if axes else None
            payload["lambda_meaning"] = "Λ = geometric-mean fleet kinematic-plausibility trust (Conjecture 1, advisory; NOT a theorem)."
            payload["conformal_note"] = "Plausibility bands are split-conformal (W5-3/W7-4) — NOT Hoeffding."
            if isinstance(payload.get("data"), dict):
                payload["data"]["vessels"] = vessels
        except Exception:
            pass
        return JSONResponse(payload)

    async def _air_live(request):
        payload = await _run(get_feed, "air")
        return JSONResponse(payload)

    async def _feeds_status(request):
        out = {}
        for f in sorted(_TTL.keys()):
            with _LOCK:
                ent = _CACHE.get(f)
            out[f] = {"ttl_s": _TTL[f], "last_mode": (ent or {}).get("mode"),
                      "last_fetched": (ent or {}).get("iso"),
                      "snapshot_present": (_SNAP_DIR / ("%s.json" % f)).exists(),
                      "source": _SOURCE[f][0]}
        return JSONResponse({
            "layer": "killinchu live feeds status",
            "honest": "label=live|cached(snapshot)|self; never fabricated. unavailable feeds return cached snapshot or empty honestly.",
            "feeds": out,
        })

    # ---- sovereign same-origin proxies for free public feeds (usgs/nvd/mitre/kev) ----
    def _do_proxy(name, query):
        cached = _get_proxy(name)
        if cached is not None and not query:
            return cached
        src, url, ttl = _PROXY[name]
        full = url + (("?" + query) if query else "")
        try:
            data = _http_get(full, timeout=40)
            return _store_proxy(name, data, url=full)
        except Exception as e:
            return _proxy_cached_or_error(name, e, url=full)

    async def _proxy_route(request):
        name = request.path_params["name"]
        if name not in _PROXY:
            return JSONResponse({"error": "unknown proxy", "name": name,
                                 "available": sorted(_PROXY.keys())}, status_code=404)
        # forward only a small allow-list of NVD query params (others ignored)
        qp = request.query_params
        parts = []
        for k in ("resultsPerPage", "pubStartDate", "pubEndDate", "startIndex"):
            if k in qp:
                parts.append("%s=%s" % (k, urllib.parse.quote(qp[k])))
        payload = await _run(_do_proxy, name, "&".join(parts))
        return JSONResponse(payload)

    # ---- governed command/cosign loop, proxied server-side from a11oy ----
    def _do_gov(name, body):
        if name not in _GOV:
            raise ValueError("unknown gov route: %s" % name)
        method, path, ttl = _GOV[name]
        ckey = "gov:%s" % name
        now = time.time()
        if method == "GET" and ttl > 0:
            with _LOCK:
                ent = _CACHE.get(ckey)
            if ent and (now - ent["ts"]) < ttl:
                return {"mode": ent["mode"], "fetched_at": ent["iso"],
                        "source": "a11oy command/governance platform",
                        "source_url": _A11OY + path, "data": ent["data"]}
        url = _A11OY + path
        try:
            if method == "POST":
                data = _http_get(url, timeout=20, data=json.dumps(body or {}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
            else:
                data = _http_get(url, timeout=20)
            iso = _now_iso()
            if method == "GET" and ttl > 0:
                with _LOCK:
                    _CACHE[ckey] = {"data": data, "ts": now, "mode": "live", "iso": iso}
            return {"mode": "live", "fetched_at": iso,
                    "source": "a11oy command/governance platform",
                    "source_url": url, "data": data}
        except Exception as e:
            with _LOCK:
                ent = _CACHE.get(ckey)
            if ent:
                return {"mode": "cached", "fetched_at": ent["iso"],
                        "source": "a11oy command/governance platform",
                        "source_url": url,
                        "cache_note": "governance host unreachable (%s) — last good value" % type(e).__name__,
                        "data": ent["data"]}
            return {"mode": "cached", "fetched_at": None,
                    "source": "a11oy command/governance platform",
                    "source_url": url, "error": "governance host unreachable: %s" % e, "data": None}

    async def _gov_route(request):
        name = request.path_params["name"]
        if name not in _GOV:
            return JSONResponse({"error": "unknown gov route", "name": name,
                                 "available": sorted(_GOV.keys())}, status_code=404)
        body = None
        if _GOV[name][0] == "POST":
            try:
                body = await request.json()
            except Exception:
                body = {}
        payload = await _run(_do_gov, name, body)
        return JSONResponse(payload)

    routes = [
        Route(base, _index, methods=["GET"], name="%s_live_index" % ns),
        Route(base + "/{feed}", _feed_route, methods=["GET"], name="%s_live_feed" % ns),
        Route("/api/%s/v1/ais/live" % ns, _ais_live, methods=["GET"], name="%s_ais_live" % ns),
        Route("/api/%s/v1/air/live" % ns, _air_live, methods=["GET"], name="%s_air_live" % ns),
        Route("/api/%s/v1/feeds/status" % ns, _feeds_status, methods=["GET"], name="%s_feeds_status" % ns),
        Route("/api/%s/v1/proxy/{name}" % ns, _proxy_route, methods=["GET"], name="%s_proxy" % ns),
        Route("/api/%s/v1/gov/{name}" % ns, _gov_route, methods=["GET", "POST"], name="%s_gov" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "base": base, "feeds": sorted(_TTL.keys()),
            "aliases": ["/api/%s/v1/ais/live" % ns, "/api/%s/v1/air/live" % ns,
                        "/api/%s/v1/feeds/status" % ns]}


__all__ = ["register", "get_feed", "_fetch_ais", "_ais_to_vector",
           "_lambda_trust", "_haversine_nm"]
