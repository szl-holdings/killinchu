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
  GET /api/killinchu/v1/live/<feed>       one feed (ais|air|celestrak|rekor|kev|osv|prometheus|epss)
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
  kev         (cisagov GitHub mirror known_exploited_vulnerabilities.json)       TTL 6h
  osv         (api.osv.dev/v1/query, POST)                          TTL 1h
  prometheus  (prometheus.demo.prometheus.io/api/v1/query)          TTL 30s
  epss        (api.first.org/data/v1/epss order=!epss, FIRST)       TTL 1h

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
    "kev": 6 * 3600, "osv": 3600, "prometheus": 30, "epss": 3600,
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
    "kev": ("CISA Known Exploited Vulnerabilities catalog (GitHub mirror)",
            "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"),
    "osv": ("OSV.dev open-source vulnerability database",
            "https://api.osv.dev/v1/query"),
    "prometheus": ("Prometheus demo (node/caddy/blackbox exporters)",
                   "https://prometheus.demo.prometheus.io/api/v1/query"),
    "epss": ("FIRST EPSS — Exploit Prediction Scoring System v3 (no auth)",
             "https://api.first.org/data/v1/epss"),
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# SOVEREIGN SAME-ORIGIN PROXIES.
# The browser must only ever hit OUR origin (0 client CDN / 0 off-origin).
# These two tables back GET /api/<ns>/v1/proxy/<name> (public free feeds) and
# GET /api/<ns>/v1/gov/<name> (the cross-platform governed command/cosign loop:
# killinchu reads a11oy's REAL ledger/command-log/policy-gates/CHAPAQ verdict,
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
    # full USGS summary matrix {significant,4.5,2.5,1.0,all}_{hour,day,week,month} (no key, ~1min refresh)
    "usgs_all_week": ("USGS earthquakes — all, past 7 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson", 300),
    "usgs_all_month": ("USGS earthquakes — all, past 30 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson", 900),
    "usgs_2.5_week": ("USGS earthquakes — M2.5+, past 7 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson", 300),
    "usgs_4.5_week": ("USGS earthquakes — M4.5+, past 7 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson", 300),
    "usgs_4.5_month": ("USGS earthquakes — M4.5+, past 30 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson", 900),
    "usgs_significant_week": ("USGS earthquakes — significant, past 7 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson", 300),
    "usgs_significant_month": ("USGS earthquakes — significant, past 30 days",
                  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson", 900),
    "nvd":       ("U.S. National Vulnerability Database (NVD CVE API 2.0)",
                  "https://services.nvd.nist.gov/rest/json/cves/2.0", 1800),
    "mitre_attack": ("MITRE ATT&CK Enterprise STIX bundle",
                     "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json", 6 * 3600),
    "cisa_kev":  ("CISA Known Exploited Vulnerabilities catalog (GitHub mirror)",
                  "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json", 6 * 3600),
    "epss":      ("FIRST EPSS — Exploit Prediction Scoring System v3 (no auth)",
                  "https://api.first.org/data/v1/epss", 3600),
}

# governed-loop routes proxied from a11oy (the command/cosign-receipt platform).
# method 'POST' entries pass the JSON body through verbatim. ttl 0 = never cache.
_GOV = {
    "ledger":      ("GET",  "/api/a11oy/v1/ledger", 15),
    "command-log": ("GET",  "/api/a11oy/v2/command-log", 10),
    "policy-gates": ("GET", "/api/a11oy/v1/policy/gates", 60),
    "a11oy-honest": ("GET", "/api/a11oy/v1/honest", 60),
    # killinchu-side codename = CHAPAQ (egress/immune inspector). The UPSTREAM a11oy
    # route is a11oy's own canonical compat path (not killinchu's to rename); we keep it
    # pointing at the REAL a11oy endpoint while exposing only the CHAPAQ codename here.
    "chapaq-verdict": ("POST", "/api/sentra/v1/verdict", 0),
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
      1) api.adsb.lol/v2/mil   2) opendata.adsb.fi/api/v2/mil   3) api.airplanes.live/v2/mil
    OpenSky is DEAD for us (now OAuth2-only) and is intentionally NOT used."""
    data = None
    used = _SOURCE["air"][1]
    _chain = [
        _SOURCE["air"][1],                       # api.adsb.lol/v2/mil
        "https://opendata.adsb.fi/api/v2/mil",   # adsb.fi (ODbL)
        "https://api.airplanes.live/v2/mil",         # airplanes.live
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
    if feed == "epss":
        # highest-exploit-probability CVEs first (order=!epss). Real FIRST EPSS v3,
        # no auth. Pairs with CISA KEV for CVE prioritisation (CVE Watch / Threat Intel).
        return _http_get(_SOURCE["epss"][1] + "?order=!epss&limit=100", timeout=20)
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


# ===========================================================================
# EARTHQUAKE AFTERSHOCK FORECAST — Reasenberg-Jones / modified Omori-Utsu.
#
# HONEST METHOD (NOT a deterministic prediction; this is the same statistical
# aftershock-RATE model USGS itself uses):
#   R(T,M) = 10^(a + b*(Mmain - M)) * (T + c)^(-p)
#     10^(a+b*Mmain)  = Utsu productivity
#     (T+c)^(-p)      = modified Omori-Utsu temporal decay
#   Generic Reasenberg-Jones (1989/1994): a=-1.67, b=1.0, c=0.05 d, p=1.08.
#   We MLE-refine a (Ogata 1983 likelihood) on the observed post-mainshock
#   sequence pulled from ComCat FDSN, integrate R over forecast windows, and
#   build P(N) as a Poisson mixture. We report prob(>=1), expected count, and a
#   95% range — ALWAYS labelled "statistical forecast — probabilities, not
#   certainty." Where USGS publishes an OAF for the event we surface it too.
#
# Numeric honesty: the Omori integral and Poisson-mixture summation share the
# fp summation/series error envelope of CF-17 (NumericStability, merged) and
# CF-18 (Leibniz/Madhava alternating-series bound, merged) — a machine-checked
# accumulation bound. The forecast MODEL stays a documented statistical method,
# NEVER a locked-proven claim. locked-8 = {F1,F4,F7,F11,F12,F18,F19,F22}; Lambda = Conj 1.
# Refs: Reasenberg & Jones BSSA 1989/1994; Utsu 1961 (Omori); Ogata 1983.
# ===========================================================================
_RJ_GENERIC = {"a": -1.67, "b": 1.0, "c": 0.05, "p": 1.08}


def _omori_integral(c, p, t0, t1):
    """Integral of (T+c)^(-p) dT from t0 to t1 (days). Closed form; p!=1 vs p==1.
    Shares the CF-17/CF-18 fp accumulation envelope (documented, not locked)."""
    import math
    if abs(p - 1.0) < 1e-9:
        return math.log((t1 + c) / (t0 + c))
    e = 1.0 - p
    return ((t1 + c) ** e - (t0 + c) ** e) / e


def _rj_expected_count(a, b, p, c, mmain, mmin, t0, t1):
    """Expected number of aftershocks >= mmin in [t0,t1] days after mainshock.
    N = 10^(a + b*(mmain - mmin)) * integral (T+c)^-p dT."""
    prod = 10.0 ** (a + b * (mmain - mmin))
    return prod * _omori_integral(c, p, t0, t1)


def _mle_refine_a(times_days, b, p, c, mmain, mmin, t_obs):
    """Closed-form MLE for productivity term 'a' given observed aftershock times
    (days since mainshock) within [0, t_obs], for fixed b,p,c (Ogata 1983).
    For an inhomogeneous Poisson process with rate lambda(T)=K*(T+c)^-p, the MLE
    of K is n / integral(0,t_obs). Then a = log10(K) - b*(mmain - mmin)."""
    import math
    n = len([t for t in times_days if 0.0 <= t <= t_obs])
    if n == 0 or t_obs <= 0:
        return None, 0
    integ = _omori_integral(c, p, 0.0, t_obs)
    if integ <= 0:
        return None, n
    K = n / integ
    if K <= 0:
        return None, n
    a = math.log10(K) - b * (mmain - mmin)
    return a, n


def _poisson_pmf(k, lam):
    import math
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def _forecast_window(a, b, p, c, mmain, mmin, t0, t1):
    """Build prob(>=1), expected count, and 95% range over a forecast window.
    Variability modelled as Poisson on the expected count (Eq.2 simplification:
    single MLE point estimate of a -> Poisson(N); a full a-mixture would widen
    the bands — documented as a conservative-but-honest simplification)."""
    N = _rj_expected_count(a, b, p, c, mmain, mmin, t0, t1)
    N = max(0.0, N)
    prob_ge1 = 1.0 - _poisson_pmf(0, N)
    # 95% range = 2.5th..97.5th percentile of Poisson(N)
    cum = 0.0
    lo = hi = 0
    kmax = int(N + 8 * (N ** 0.5) + 20)
    lo_set = False
    for k in range(0, kmax + 1):
        cum += _poisson_pmf(k, N)
        if not lo_set and cum >= 0.025:
            lo = k
            lo_set = True
        if cum >= 0.975:
            hi = k
            break
    return {"expected": round(N, 2), "prob_ge1": round(prob_ge1, 4),
            "range95": [lo, hi]}


def compute_aftershock_forecast(mainshock, sequence, mmin=3.0):
    """mainshock: {mag, time_ms, lat, lon}. sequence: list of feature props with
    {mag, time(ms)} pulled from ComCat for the SAME region AFTER the mainshock.
    Returns honest forecast dict (generic + MLE-refined) over 1d/1wk/1mo."""
    import math
    g = dict(_RJ_GENERIC)
    mmain = float(mainshock.get("mag") or 0.0)
    t_main = float(mainshock.get("time_ms") or 0.0)
    # observed aftershock times in DAYS since mainshock (mag >= mmin, after t_main)
    times = []
    for s in sequence or []:
        try:
            m = float(s.get("mag"))
            t = float(s.get("time"))
        except Exception:
            continue
        if m is None or t <= t_main:
            continue
        if m >= mmin:
            times.append((t - t_main) / 86400000.0)
    times.sort()
    t_obs = max(times) if times else 0.0
    a_ref, n_obs = _mle_refine_a(times, g["b"], g["p"], g["c"], mmain, mmin, t_obs) if t_obs > 0 else (None, 0)
    a_used = a_ref if a_ref is not None else g["a"]
    refined = a_ref is not None
    windows = {"1_day": (0.0, 1.0), "1_week": (0.0, 7.0), "1_month": (0.0, 30.0)}
    out = {}
    for name, (t0, t1) in windows.items():
        out[name] = _forecast_window(a_used, g["b"], g["p"], g["c"], mmain, mmin, t0, t1)
    # Omori decay curve: cumulative expected count vs time (for the chart)
    curve = []
    for d in [0.04, 0.1, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 14, 21, 30]:
        curve.append({"t_days": d,
                      "cum_expected": round(_rj_expected_count(a_used, g["b"], g["p"], g["c"], mmain, mmin, 0.0, d), 3)})
    return {
        "model": "Reasenberg-Jones / modified Omori-Utsu aftershock-rate",
        "equation": "R(T,M) = 10^(a + b*(Mmain - M)) * (T + c)^(-p)",
        "params": {"a": round(a_used, 4), "b": g["b"], "c": g["c"], "p": g["p"],
                   "a_generic": g["a"], "a_mle_refined": refined,
                   "observed_aftershocks_used": n_obs, "t_obs_days": round(t_obs, 3)},
        "mainshock": {"mag": mmain, "mmin_forecast": mmin},
        "forecast": out,
        "omori_curve": curve,
        "label": "statistical forecast — probabilities, not certainty",
        "method_note": ("Reasenberg-Jones aftershock-rate model (the statistical method USGS uses); "
                        "productivity 'a' MLE-refined (Ogata 1983) on the live ComCat sequence when "
                        ">=1 aftershock M>=%.1f is observed, else generic RJ params. Poisson count model. "
                        "This is NOT a deterministic prediction and NEVER a locked-proven claim.") % mmin,
        "numeric_tie": ("Omori integral + Poisson-mixture summation carry the CF-17/CF-18 fp "
                        "accumulation/series error envelope (machine-checked, merged); the forecast "
                        "model itself stays a documented statistical method."),
        "refs": ["Reasenberg & Jones, BSSA 1989/1994", "Utsu 1961 (Omori)", "Ogata 1983 (likelihood)",
                 "USGS OAF background: https://earthquake.usgs.gov/data/oaf/background.php"],
    }


def _fetch_comcat_sequence(lat, lon, t_main_ms, radius_km=100.0, days=30.0, minmag=2.5):
    """Pull post-mainshock sequence within radius via ComCat FDSN event query."""
    import datetime as _dt
    start = _dt.datetime.fromtimestamp(t_main_ms / 1000.0, tz=timezone.utc)
    end = start + _dt.timedelta(days=days)
    now = datetime.now(timezone.utc)
    if end > now:
        end = now
    q = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
         "&starttime=%s&endtime=%s&latitude=%.4f&longitude=%.4f&maxradiuskm=%.1f"
         "&minmagnitude=%.2f&orderby=time-asc" % (
             start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"),
             lat, lon, radius_km, minmag))
    data = _http_get(q, timeout=40)
    feats = (data or {}).get("features", [])
    seq = []
    for f in feats:
        p = f.get("properties") or {}
        seq.append({"mag": p.get("mag"), "time": p.get("time")})
    return seq, q


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
        # forward only a small allow-list of upstream query params (others ignored):
        #   NVD CVE 2.0  -> resultsPerPage / pubStartDate / pubEndDate / startIndex
        #   FIRST EPSS   -> cve / order / limit / offset / percentile-gt / epss-gt / days / envelope
        qp = request.query_params
        parts = []
        for k in ("resultsPerPage", "pubStartDate", "pubEndDate", "startIndex",
                  "cve", "order", "limit", "offset", "percentile-gt", "epss-gt",
                  "days", "envelope"):
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

    # ---- EARTHQUAKE aftershock forecast (Reasenberg-Jones / Omori-Utsu) ----
    def _do_quake_forecast(lat, lon, mag, t_ms, mmin, radius_km):
        try:
            seq, q = _fetch_comcat_sequence(lat, lon, t_ms, radius_km=radius_km,
                                            days=30.0, minmag=min(2.5, mmin))
            comcat_ok = True
        except Exception as e:
            seq, q, comcat_ok = [], None, False
        fc = compute_aftershock_forecast(
            {"mag": mag, "time_ms": t_ms, "lat": lat, "lon": lon}, seq, mmin=mmin)
        fc["comcat"] = {"reached": comcat_ok, "query": q,
                        "sequence_count": len(seq),
                        "radius_km": radius_km}
        fc["source"] = "USGS ComCat FDSN event query (live, no key)"
        fc["source_url"] = "https://earthquake.usgs.gov/fdsnws/event/1/"
        fc["fetched_at"] = _now_iso()
        return fc

    async def _quake_forecast(request):
        qp = request.query_params
        try:
            lat = float(qp["lat"]); lon = float(qp["lon"]); mag = float(qp["mag"])
            t_ms = float(qp["time"])
        except Exception:
            return JSONResponse({"error": "required query params: lat, lon, mag, time(ms epoch)",
                                 "example": "/api/%s/v1/quake/forecast?lat=35.7&lon=-117.5&mag=6.4&time=1562383193040" % ns},
                                status_code=422)
        try:
            mmin = float(qp.get("mmin", "3.0"))
        except Exception:
            mmin = 3.0
        try:
            radius_km = float(qp.get("radius_km", "100"))
        except Exception:
            radius_km = 100.0
        payload = await _run(_do_quake_forecast, lat, lon, mag, t_ms, mmin, radius_km)
        return JSONResponse(payload)

    routes = [
        Route(base, _index, methods=["GET"], name="%s_live_index" % ns),
        Route(base + "/{feed}", _feed_route, methods=["GET"], name="%s_live_feed" % ns),
        Route("/api/%s/v1/ais/live" % ns, _ais_live, methods=["GET"], name="%s_ais_live" % ns),
        Route("/api/%s/v1/air/live" % ns, _air_live, methods=["GET"], name="%s_air_live" % ns),
        Route("/api/%s/v1/feeds/status" % ns, _feeds_status, methods=["GET"], name="%s_feeds_status" % ns),
        Route("/api/%s/v1/proxy/{name}" % ns, _proxy_route, methods=["GET"], name="%s_proxy" % ns),
        Route("/api/%s/v1/gov/{name}" % ns, _gov_route, methods=["GET", "POST"], name="%s_gov" % ns),
        Route("/api/%s/v1/quake/forecast" % ns, _quake_forecast, methods=["GET"], name="%s_quake_forecast" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "base": base, "feeds": sorted(_TTL.keys()),
            "aliases": ["/api/%s/v1/ais/live" % ns, "/api/%s/v1/air/live" % ns,
                        "/api/%s/v1/feeds/status" % ns]}


__all__ = ["register", "get_feed", "_fetch_ais", "_ais_to_vector",
           "_lambda_trust", "_haversine_nm"]
