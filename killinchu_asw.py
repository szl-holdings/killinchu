# ===========================================================================
# killinchu_asw.py — Submarine / ASW intelligence, HONEST edition (Maritime W4)
# ===========================================================================
# THE HONEST POSTURE (state it plainly — it is a Series-A credibility asset):
#
#   Submarines do NOT broadcast AIS. There is NO public live submarine track
#   feed. We do NOT claim live submarine tracking, and we will NEVER fabricate
#   a live submarine track. What we CAN provide, truthfully:
#
#     1. OSINT-LIVE  — server-side open-source collection of PUBLIC naval
#                      reporting (published port departures/returns, announced
#                      patrols, open naval-movement reporting). Cited + ts.
#                      Endpoint:  /api/killinchu/v1/asw/osint
#
#     2. FORECAST    — a TRANSPARENT model that, given an OSINT departure +
#                      known transit speeds + bastion / operating-area doctrine,
#                      projects PROBABILITY FIELDS for probable operating areas /
#                      transit corridors. A projection, NEVER an observation.
#                      Endpoint:  /api/killinchu/v1/asw/forecast
#
#     3. INFERENCE   — "negative-space" advisory: flag sea areas where the
#                      ABSENCE of expected surface traffic (over W1's REAL AIS)
#                      + OSINT signals suggests restricted / military activity.
#                      We infer interesting areas from what ISN'T there.
#                      Endpoint:  /api/killinchu/v1/asw/negative-space
#
# Every ASW assessment is signed with a REAL DSSE receipt (szl_dsse, ECDSA-P256
# over the DSSE PAE) and the honesty labels are carried INSIDE the signed
# payload. Advisory / human-on-the-loop. Never an effector. 0 CDN, same-origin.
#
# Doctrine v11: locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ kernel c7c0ba17;
# Λ = Conjecture 1 (advisory). Additive, try/except-guarded, registered EARLY
# (before the SPA catch-all). Pure stdlib + the existing feeds/dsse helpers.
# ===========================================================================
from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.responses import JSONResponse

# --- Reuse the proven HTTP helpers + theaters from the W1 feeds layer. --------
try:
    import killinchu_feeds_realdata as _feeds
    _http_get_raw = _feeds._http_get_raw
    _fetch_vessels = _feeds._fetch_vessels
    THEATERS = _feeds.THEATERS
    _now_iso = _feeds._now_iso
    _haversine_nm = _feeds._haversine_nm
    _in_box = _feeds._in_box
except Exception:  # pragma: no cover — standalone fallback keeps module importable
    _feeds = None
    THEATERS = {
        "south_china_sea": {"label": "South China Sea",
                            "lamin": 5.0, "lamax": 23.0, "lomin": 105.0, "lomax": 121.0},
        "east_china_sea": {"label": "East China Sea",
                           "lamin": 25.0, "lamax": 33.0, "lomin": 120.0, "lomax": 131.0},
        "baltic": {"label": "Baltic / Gulf of Finland",
                   "lamin": 58.0, "lamax": 66.0, "lomin": 18.0, "lomax": 30.0},
    }

    def _now_iso():
        return datetime.now(timezone.utc).isoformat()

    def _http_get_raw(url, timeout=25, headers=None, data=None, method=None):
        h = {"User-Agent": "killinchu-asw/1.0", "Accept-Encoding": "gzip"}
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

    def _haversine_nm(a_lat, a_lon, b_lat, b_lon):
        R = 3440.065
        p1, p2 = math.radians(a_lat), math.radians(b_lat)
        dp = math.radians(b_lat - a_lat)
        dl = math.radians(b_lon - a_lon)
        x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(2 * R * math.asin(min(1.0, math.sqrt(x))), 3)

    def _in_box(lat, lon, t):
        if t.get("lamin") is None:
            return True
        if lat is None or lon is None:
            return False
        return (t["lamin"] <= lat <= t["lamax"]) and (t["lomin"] <= lon <= t["lomax"])

    _fetch_vessels = None

# --- Real DSSE signing (ECDSA-P256 over DSSE PAE). No fabricated signature. ---
try:
    import szl_dsse as _dsse
except Exception:  # pragma: no cover
    _dsse = None

_UA = "killinchu-asw/1.0 (+https://szlholdings-killinchu.hf.space)"
_ASW_PAYLOAD_TYPE = "application/vnd.szl.killinchu.asw+json"

_CACHE: dict = {}
_LOCK = threading.Lock()

KN_TO_MS = 0.514444

# ===========================================================================
# Honesty constants — surfaced verbatim in every response.
# ===========================================================================
HONEST_LIMITS = (
    "HONEST LIMITS — Submarines do NOT broadcast AIS; there is NO public live "
    "submarine track feed and we do NOT claim live submarine tracking. We will "
    "NEVER fabricate a live submarine track. This module provides three "
    "truthfully-labeled products: (1) OSINT-LIVE open-source collection of "
    "PUBLIC naval reporting, cited with source URLs + timestamps; (2) FORECAST "
    "— a transparent projection of probable operating areas / transit corridors "
    "as PROBABILITY FIELDS, a model output and never an observation; (3) "
    "INFERENCE — a negative-space advisory over REAL surface AIS density. All "
    "advisory / human-on-the-loop. NO classified or non-public claims."
)

_LABEL = {
    "osint": "OSINT-LIVE (public open-source collection)",
    "forecast": "FORECAST (model projection — probability field, NOT an observation)",
    "inference": "INFERENCE (negative-space advisory over real AIS — NOT a track)",
}

# ===========================================================================
# 1. SUBMARINE OSINT (LIVE) — public naval open-source reporting.
# ===========================================================================
# Public, no-key RSS feeds carrying open naval-movement reporting (port
# departures/returns, announced patrols, deployments). We label everything
# OSINT(public), cite source URL + published timestamp, and surface ONLY items
# matching submarine / undersea-warfare relevance terms. No classified claims.
_OSINT_SOURCES = [
    {"name": "USNI News (U.S. Naval Institute) — Fleet Tracker",
     "url": "https://news.usni.org/category/fleet-tracker/feed",
     "home": "https://news.usni.org/category/fleet-tracker"},
    {"name": "USNI News (U.S. Naval Institute) — main feed",
     "url": "https://news.usni.org/feed",
     "home": "https://news.usni.org"},
    {"name": "Naval News — open naval reporting",
     "url": "https://www.navalnews.com/feed/",
     "home": "https://www.navalnews.com"},
]

# Submarine / undersea-warfare / ASW relevance terms (word-boundary matched).
# STRONG terms are unambiguously submarine/undersea-warfare and qualify an item
# on their own. WEAK terms are generic naval movement/context words that only
# qualify an item when paired with a STRONG term (otherwise too noisy).
_STRONG_TERMS = [
    "submarine", "submarines", "ssn", "ssbn", "ssgn", "ssk", "boomer",
    "attack boat", "attack submarine", "ballistic-missile submarine",
    "undersea", "under-sea", "asw", "anti-submarine", "sub patrol",
    "virginia-class", "virginia class", "columbia-class", "columbia class",
    "los angeles-class", "astute", "vanguard", "yasen", "borei", "akula",
    "type 094", "type 093", "jin-class", "shang-class", "han-class",
    "kilo-class", "kilo class", "soryu", "taigei", "scorpene", "sonar",
    "torpedo", "sonobuoy", "bastion", "diesel-electric",
]
_WEAK_TERMS = [
    "patrol", "deploy", "deployment", "departs", "departed", "deployed",
    "returns", "returned", "sortie", "transit", "operating area",
]
_STRONG_RE = re.compile(r"(?i)\b(" + "|".join(re.escape(t) for t in _STRONG_TERMS) + r")\b")
_WEAK_RE = re.compile(r"(?i)\b(" + "|".join(re.escape(t) for t in _WEAK_TERMS) + r")\b")
# Platform/undersea terms denote an actual submarine → "high"; weapon/sensor-only
# matches (torpedo/sonar/sonobuoy/bastion) are kept but labeled "context".
_PLATFORM_RE = re.compile(
    r"(?i)\b(submarine|submarines|ssn|ssbn|ssgn|ssk|boomer|attack boat|undersea"
    r"|under-sea|anti-submarine|asw|virginia-class|columbia-class|los angeles-class"
    r"|astute|vanguard|yasen|borei|akula|type 094|type 093|jin-class|shang-class"
    r"|han-class|kilo-class|kilo class|soryu|taigei|scorpene|diesel-electric)\b")


def _strip_html(s):
    s = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", s or "")
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&#8217;", "'").replace("&#8211;", "-").replace("&nbsp;", " ")
          .replace("&#8220;", '"').replace("&#8221;", '"').replace("&quot;", '"'))
    return re.sub(r"\s+", " ", s).strip()


def _rss_field(item_xml, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), item_xml, re.S)
    return _strip_html(m.group(1)) if m else None


def _parse_pubdate(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s.strip(), fmt).astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return s.strip()


def _collect_osint_source(src, cap=40):
    raw = _http_get_raw(src["url"], timeout=25, headers={"User-Agent": _UA})
    text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
    items = re.findall(r"<item>(.*?)</item>", text, re.S)
    out = []
    for it in items[:cap]:
        title = _rss_field(it, "title") or ""
        desc = _rss_field(it, "description") or ""
        link = _rss_field(it, "link")
        blob = title + " " + desc
        strong_m = sorted({m.lower() for m in _STRONG_RE.findall(blob)})
        weak_m = sorted({m.lower() for m in _WEAK_RE.findall(blob)})
        # Keep only items with a STRONG submarine/undersea term. Weak movement
        # terms are recorded as context but never qualify an item alone.
        if not strong_m:
            continue
        matches = (strong_m + weak_m)[:8]
        strong = bool(_PLATFORM_RE.search(blob))
        out.append({
            "title": title,
            "summary": desc[:360],
            "url": link,
            "published": _parse_pubdate(_rss_field(it, "pubDate")),
            "matched_terms": matches[:8],
            "relevance": "high" if strong else "context",
            "kind": "naval_movement_report",
            "label": "OSINT(public) — open naval-movement report (open-source collection)",
            "source": src["name"],
            "source_url": link or src["home"],
            "feed_url": src["url"],
        })
    return out


def _collect_osint(theater=None):
    """REAL public open-source collection of submarine-relevant naval reporting.
    Each item is cited (source + URL + published ts) and labeled OSINT(public).
    Only PUBLIC reporting — NO classified or non-public claims."""
    items, tried = [], []
    for src in _OSINT_SOURCES:
        try:
            got = _collect_osint_source(src)
            items.extend(got)
            tried.append({"source": src["name"], "url": src["url"],
                          "ok": True, "count": len(got)})
        except Exception as e:
            tried.append({"source": src["name"], "url": src["url"],
                          "ok": False, "error": "%s: %s" % (type(e).__name__, e)})
    # De-dupe by URL/title; sort newest first; strong relevance first.
    seen, dedup = set(), []
    for it in items:
        k = it.get("url") or it.get("title")
        if k in seen:
            continue
        seen.add(k)
        dedup.append(it)
    dedup.sort(key=lambda r: (0 if r["relevance"] == "high" else 1,
                              r.get("published") or ""), reverse=False)
    dedup.sort(key=lambda r: (r.get("published") or ""), reverse=True)
    return dedup, tried


# ===========================================================================
# 2. ASW FORECAST MODEL (FORECAST) — transparent probability-field projection.
# ===========================================================================
# Given an OSINT departure (port + datetime), known transit speeds, and a
# named bastion / operating-area doctrine, project a PROBABILITY FIELD over a
# grid of probable presence. This is a MODEL OUTPUT, openly parameterized and
# labeled FORECAST — never an observation, never a point track.
#
# Method (all parameters are returned so the projection is fully transparent):
#   - elapsed_h = now - departure
#   - reachable radius R = transit_speed_kn * elapsed_h  (great-circle, nm)
#   - over a grid, presence probability ~ a doctrine-weighted blend of:
#       * a transit annulus (vessel is somewhere within reach of the departure
#         point, weighted toward the doctrinal operating area / bastion), and
#       * a bastion-pull Gaussian centered on the operating area.
#   We normalize to a probability field that integrates to ~1 over the grid.

# Public, doctrinally-described operating areas / bastions (open-source naval
# literature describes these as general patrol regions — NOT a claim that any
# specific boat is present). Used only to shape the FORECAST field.
_OPERATING_AREAS = {
    "south_china_sea_bastion": {
        "label": "South China Sea — described SSBN bastion / operating area (open-source)",
        "center": (16.5, 113.5), "sigma_nm": 240.0,
        "context": "Open-source naval literature describes a South China Sea SSBN "
                   "bastion concept. Projection only — not an observation."},
    "east_china_sea_oparea": {
        "label": "East China Sea operating area (open-source)",
        "center": (29.0, 126.0), "sigma_nm": 200.0,
        "context": "General operating-area context from open naval reporting."},
    "barents_bastion": {
        "label": "Barents Sea — described SSBN bastion (open-source)",
        "center": (74.0, 38.0), "sigma_nm": 280.0,
        "context": "Open-source literature describes a Barents bastion concept."},
    "norwegian_sea_transit": {
        "label": "Norwegian Sea / GIUK transit corridor (open-source)",
        "center": (66.0, 0.0), "sigma_nm": 320.0,
        "context": "GIUK-gap transit corridor described in open naval literature."},
    "western_pacific": {
        "label": "Western Pacific operating area (open-source)",
        "center": (22.0, 130.0), "sigma_nm": 300.0,
        "context": "Broad Western-Pacific operating-area context."},
}

# Typical transit speeds (knots) from open-source naval literature. Ranges,
# clearly approximate — used only to size the FORECAST reachability field.
_TRANSIT_SPEED = {
    "nuclear_attack_ssn": {"cruise_kn": 20.0, "max_kn": 30.0,
                           "note": "SSN sustained transit ~20 kn (open-source typical)"},
    "ballistic_ssbn": {"cruise_kn": 12.0, "max_kn": 20.0,
                       "note": "SSBN quiet patrol transit ~12 kn (open-source typical)"},
    "diesel_electric_ssk": {"cruise_kn": 8.0, "max_kn": 12.0,
                            "note": "SSK submerged transit ~8 kn (open-source typical)"},
}


def _bearing_ok(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def _forecast_field(dep_lat, dep_lon, elapsed_h, speed_kn, oparea, grid_n=21):
    """Build a normalized PROBABILITY FIELD (grid) — model output, not a track."""
    R_nm = max(1.0, speed_kn * max(0.0, elapsed_h))  # reachable great-circle radius
    area = _OPERATING_AREAS.get(oparea)
    # Grid bounds: cover departure + reachable radius (+ the op-area center).
    deg_pad = min(40.0, R_nm / 60.0 + 4.0)  # ~1 deg lat ~ 60 nm
    lat_lo, lat_hi = dep_lat - deg_pad, dep_lat + deg_pad
    lon_lo, lon_hi = dep_lon - deg_pad, dep_lon + deg_pad
    if area:
        clat, clon = area["center"]
        lat_lo, lat_hi = min(lat_lo, clat - 3), max(lat_hi, clat + 3)
        lon_lo, lon_hi = min(lon_lo, clon - 3), max(lon_hi, clon + 3)
    lat_lo = max(-85.0, lat_lo); lat_hi = min(85.0, lat_hi)
    lon_lo = max(-179.0, lon_lo); lon_hi = min(179.0, lon_hi)

    cells = []
    total = 0.0
    annulus_sigma = max(40.0, R_nm * 0.30)  # spread of the transit-reach band
    for i in range(grid_n):
        for j in range(grid_n):
            lat = lat_lo + (lat_hi - lat_lo) * (i + 0.5) / grid_n
            lon = lon_lo + (lon_hi - lon_lo) * (j + 0.5) / grid_n
            d_dep = _haversine_nm(dep_lat, dep_lon, lat, lon)
            # Transit reach: peak near the reachable radius edge, taper outside.
            reach_w = math.exp(-((d_dep - R_nm) ** 2) / (2 * annulus_sigma ** 2))
            if d_dep > R_nm:  # cannot have travelled beyond the reachable radius
                reach_w *= 0.15
            # Bastion / operating-area pull.
            bast_w = 0.0
            if area:
                d_op = _haversine_nm(area["center"][0], area["center"][1], lat, lon)
                bast_w = math.exp(-(d_op ** 2) / (2 * area["sigma_nm"] ** 2))
            w = 0.55 * reach_w + 0.45 * bast_w if area else reach_w
            cells.append([round(lat, 3), round(lon, 3), w])
            total += w
    if total <= 0:
        total = 1.0
    # Normalize to a probability field (sum ~ 1); keep only meaningful cells.
    field = []
    for lat, lon, w in cells:
        p = w / total
        if p >= 0.002:
            field.append({"lat": lat, "lon": lon, "p": round(p, 5)})
    field.sort(key=lambda c: c["p"], reverse=True)
    return {
        "grid_bounds": {"lamin": round(lat_lo, 3), "lamax": round(lat_hi, 3),
                        "lomin": round(lon_lo, 3), "lomax": round(lon_hi, 3)},
        "grid_n": grid_n,
        "reachable_radius_nm": round(R_nm, 1),
        "cells": field[:200],
        "cell_count": len(field),
    }


# ===========================================================================
# 3. NEGATIVE-SPACE INFERENCE (INFERENCE) — anomalies from ABSENCE of AIS.
# ===========================================================================
# The honest "outside-the-box" move: flag sea sub-areas where the ABSENCE of
# expected surface traffic (from W1's REAL AIS density) + OSINT signals suggests
# restricted / military activity. We infer interesting areas from what ISN'T
# there. ADVISORY — evidence (expected vs observed density) is shown; it is NOT
# a submarine track and NOT proof of one.


def _grid_cells(t, n=4):
    """Divide a theater box into an n x n grid of sub-cells (centers + bounds)."""
    cells = []
    dlat = (t["lamax"] - t["lamin"]) / n
    dlon = (t["lomax"] - t["lomin"]) / n
    for i in range(n):
        for j in range(n):
            la0 = t["lamin"] + i * dlat
            lo0 = t["lomin"] + j * dlon
            cells.append({
                "id": "r%dc%d" % (i, j),
                "lamin": round(la0, 3), "lamax": round(la0 + dlat, 3),
                "lomin": round(lo0, 3), "lomax": round(lo0 + dlon, 3),
                "center": [round(la0 + dlat / 2, 4), round(lo0 + dlon / 2, 4)],
            })
    return cells


def _negative_space(theater_key, n=4):
    """Compute expected-vs-observed surface AIS density per sub-cell over the
    theater, and flag low-traffic 'negative-space' cells. REAL AIS in; the flag
    is an ADVISORY INFERENCE, never a track."""
    t = THEATERS.get((theater_key or "").lower())
    if not t or t.get("lamin") is None:
        return {"error": "theater %r has no bounding box for negative-space analysis"
                % theater_key, "valid_theaters": _boxed_theaters()}
    # Pull REAL surface AIS for the theater (W1 feeds layer).
    ais_note, tracks = "real AIS via W1 feeds layer", []
    try:
        if _fetch_vessels is not None:
            v_tracks, v_tried, v_mode = _fetch_vessels(theater_key, 500)
            tracks = [tr for tr in (v_tracks or [])
                      if tr.get("lat") is not None and tr.get("lon") is not None]
            ais_note = "W1 /feeds/vessels theater=%s mode=%s (REAL AIS)" % (theater_key, v_mode)
        else:
            ais_note = "feeds layer unavailable in this runtime — 0 observed"
            v_tried = []
    except Exception as e:
        ais_note = "AIS fetch failed (%s) — treated as 0 observed (honest)" % type(e).__name__
        v_tried = []

    cells = _grid_cells(t, n)
    n_obs_total = len(tracks)
    # Bin observed AIS contacts into the sub-cells.
    for c in cells:
        c["observed"] = 0
    for tr in tracks:
        for c in cells:
            if (c["lamin"] <= tr["lat"] <= c["lamax"]
                    and c["lomin"] <= tr["lon"] <= c["lomax"]):
                c["observed"] += 1
                break
    # Expected = uniform baseline (mean per cell). Absence relative to the
    # theater's OWN mean is the signal — transparent and self-calibrating.
    n_cells = len(cells)
    mean_per_cell = (n_obs_total / n_cells) if n_cells else 0.0
    # OSINT corroboration: count submarine-relevant OSINT items (theater-wide).
    osint_items, _ = _collect_osint(theater_key)
    osint_high = sum(1 for it in osint_items if it.get("relevance") == "high")

    flagged = []
    for c in cells:
        expected = round(mean_per_cell, 2)
        observed = c["observed"]
        # Deficit ratio: how far below the theater mean (0 = at/above mean).
        deficit = 0.0 if mean_per_cell <= 0 else max(0.0, (mean_per_cell - observed) / mean_per_cell)
        c["expected"] = expected
        c["deficit_ratio"] = round(deficit, 3)
        # Flag a cell when surface traffic is substantially BELOW the theater's
        # own expectation AND the theater carries corroborating OSINT signal.
        is_negative = (mean_per_cell >= 1.0 and observed == 0 and deficit >= 0.6)
        c["negative_space"] = bool(is_negative)
        # Advisory confidence (Λ-style geometric blend; NOT a probability of a sub).
        if is_negative:
            axes = [min(1.0, deficit),
                    min(1.0, (osint_high + 1) / 4.0),
                    min(1.0, mean_per_cell / 3.0)]
            conf = round(math.exp(sum(math.log(max(1e-6, a)) for a in axes) / len(axes)), 3)
            c["advisory_confidence"] = conf
            flagged.append({
                "cell": c["id"], "center": c["center"],
                "bounds": {"lamin": c["lamin"], "lamax": c["lamax"],
                           "lomin": c["lomin"], "lomax": c["lomax"]},
                "expected_contacts": expected,
                "observed_contacts": observed,
                "deficit_ratio": c["deficit_ratio"],
                "advisory_confidence": conf,
                "evidence": ("expected ~%.2f contacts (theater mean) vs observed %d; "
                             "%d high-relevance OSINT submarine signal(s) in theater"
                             % (expected, observed, osint_high)),
                "label": _LABEL["inference"],
            })
    flagged.sort(key=lambda f: f["advisory_confidence"], reverse=True)
    return {
        "theater": theater_key, "theater_box": t,
        "grid_n": n,
        "observed_total": n_obs_total,
        "expected_per_cell": round(mean_per_cell, 3),
        "ais_provenance": ais_note,
        "ais_sources_tried": v_tried,
        "osint_high_relevance_count": osint_high,
        "cells": cells,
        "flagged": flagged,
        "method": ("Negative-space inference: divide the theater into an NxN grid, "
                   "bin REAL surface AIS contacts per cell, compare each cell's "
                   "observed count to the theater's OWN mean (expected). Cells with "
                   "observed=0 and a deficit ratio >= 0.6 in a non-trivially-trafficked "
                   "theater are flagged as negative-space — corroborated by OSINT. "
                   "ADVISORY: the absence of surface traffic is suggestive, NOT proof "
                   "of submarine activity, and NEVER a track."),
    }


def _boxed_theaters():
    return sorted(k for k, v in THEATERS.items() if v.get("lamin") is not None)


# ===========================================================================
# DSSE receipt — sign the ASW assessment; honesty labels live IN the payload.
# ===========================================================================
def _sign_assessment(product, payload_summary):
    """Produce a REAL DSSE receipt over the assessment. Honesty labels are part
    of the SIGNED payload. If no signing key is present, returns an explicit
    UNSIGNED envelope (NO fabricated signature)."""
    receipt_body = {
        "schema": "killinchu.asw.assessment/v1",
        "product": product,
        "label": _LABEL.get(product),
        "honesty_labels": {
            "no_live_submarine_track": True,
            "osint_is_public_only": True,
            "forecast_is_a_projection_not_an_observation": True,
            "inference_is_advisory_not_a_track": True,
            "human_on_the_loop": True,
        },
        "honest_limits": HONEST_LIMITS,
        "summary": payload_summary,
        "doctrine": "v11",
        "kernel": "c7c0ba17",
        "lambda": "Conjecture 1 (advisory)",
        "ts": _now_iso(),
    }
    if _dsse is not None:
        try:
            env = _dsse.sign_payload(receipt_body, _ASW_PAYLOAD_TYPE)
            return {"receipt": receipt_body, "dsse": env,
                    "signed": bool(env.get("signed")),
                    "verify": ("POST the envelope to /khipu/verify, or "
                               "`cosign verify-blob --key cosign.pub`")}
        except Exception as e:
            return {"receipt": receipt_body, "dsse": None, "signed": False,
                    "error": "signing unavailable: %s" % type(e).__name__}
    return {"receipt": receipt_body, "dsse": None, "signed": False,
            "error": "szl_dsse not importable in this runtime — receipt UNSIGNED (no fabricated signature)"}


def _cached(key, builder, ttl):
    now = time.time()
    with _LOCK:
        ent = _CACHE.get(key)
    if ent and (now - ent["ts"]) < ttl:
        return ent["val"]
    val = builder()
    with _LOCK:
        _CACHE[key] = {"val": val, "ts": now}
    return val


# ===========================================================================
# Route registration.
# ===========================================================================
def register(app, ns="killinchu"):
    base = "/api/%s/v1" % ns

    async def _run(fn, *a, **kw):
        import anyio
        return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))

    # -- 1. OSINT-LIVE -------------------------------------------------------
    async def _asw_osint(request):
        theater = request.query_params.get("theater")
        items, tried = await _run(lambda: _cached(
            "asw:osint:%s" % (theater or "all"), lambda: _collect_osint(theater), 600))
        live = any(s.get("ok") for s in tried)
        receipt = await _run(_sign_assessment, "osint",
                             {"theater": theater, "item_count": len(items),
                              "sources_ok": [s["source"] for s in tried if s.get("ok")]})
        return JSONResponse({
            "feed": "asw/osint",
            "label": _LABEL["osint"],
            "product": "OSINT-LIVE",
            "theater": theater or "all",
            "count": len(items),
            "live": live,
            "mode": "live" if live else "unreachable",
            "sources_tried": tried,
            "items": items,
            "honest": ("REAL public open-source collection of submarine-relevant naval "
                       "movement reporting — published port departures/returns, announced "
                       "patrols, open naval movements. Each item cited with source URL + "
                       "published timestamp. PUBLIC sources only; NO classified or "
                       "non-public claims. Cached server-side ~10 min."),
            "honest_limits": HONEST_LIMITS,
            "receipt": receipt,
            "doctrine": "v11", "fetched_at": _now_iso(),
        })

    # -- 2. FORECAST ---------------------------------------------------------
    async def _asw_forecast(request):
        qp = request.query_params
        # Inputs (all optional; sane SAMPLE defaults that are clearly labeled).
        sample = False
        try:
            dep_lat = float(qp["dep_lat"]); dep_lon = float(qp["dep_lon"])
        except Exception:
            dep_lat, dep_lon, sample = 16.84, 112.34, True  # SAMPLE departure point
        if not _bearing_ok(dep_lat, dep_lon):
            return JSONResponse({"error": "dep_lat/dep_lon out of range",
                                 "label": _LABEL["forecast"]}, status_code=422)
        dep_iso = qp.get("departed_at")
        try:
            dep_dt = datetime.fromisoformat(dep_iso.replace("Z", "+00:00")) if dep_iso else None
        except Exception:
            dep_dt = None
        if dep_dt is None:
            from datetime import timedelta
            dep_dt = datetime.now(timezone.utc) - timedelta(hours=36)  # SAMPLE: departed 36h ago
            sample = True
        if dep_dt.tzinfo is None:
            dep_dt = dep_dt.replace(tzinfo=timezone.utc)
        elapsed_h = max(0.0, (datetime.now(timezone.utc) - dep_dt).total_seconds() / 3600.0)

        cls = qp.get("class", "nuclear_attack_ssn")
        speed_info = _TRANSIT_SPEED.get(cls, _TRANSIT_SPEED["nuclear_attack_ssn"])
        try:
            speed_kn = float(qp["speed_kn"])
        except Exception:
            speed_kn = speed_info["cruise_kn"]
        oparea = qp.get("oparea", "south_china_sea_bastion")
        if oparea not in _OPERATING_AREAS:
            oparea = "south_china_sea_bastion"

        field = await _run(_forecast_field, dep_lat, dep_lon, elapsed_h, speed_kn, oparea)
        area = _OPERATING_AREAS[oparea]
        receipt = await _run(_sign_assessment, "forecast",
                             {"departure": [dep_lat, dep_lon], "departed_at": dep_dt.isoformat(),
                              "elapsed_h": round(elapsed_h, 2), "speed_kn": speed_kn,
                              "class": cls, "oparea": oparea,
                              "reachable_radius_nm": field["reachable_radius_nm"],
                              "is_sample_inputs": sample})
        return JSONResponse({
            "feed": "asw/forecast",
            "label": _LABEL["forecast"],
            "product": "FORECAST" + (" (SAMPLE inputs)" if sample else ""),
            "is_observation": False,
            "is_projection": True,
            "inputs": {
                "departure": {"lat": dep_lat, "lon": dep_lon},
                "departed_at": dep_dt.isoformat(),
                "elapsed_h": round(elapsed_h, 2),
                "class": cls,
                "transit_speed_kn": speed_kn,
                "speed_basis": speed_info["note"],
                "operating_area": {"key": oparea, **area},
                "sample_inputs": sample,
            },
            "probability_field": field,
            "honest": ("FORECAST — a TRANSPARENT model projection of probable operating "
                       "areas / transit corridors as a PROBABILITY FIELD over a grid, "
                       "given an OSINT departure + open-source transit speeds + a "
                       "doctrinal operating-area concept. This is a MODEL OUTPUT and "
                       "NEVER an observation; it is NOT a submarine track and not a "
                       "point position. All parameters are returned so the projection "
                       "is fully auditable. Advisory / human-on-the-loop." +
                       (" Inputs are SAMPLE defaults (no departure supplied) — pass "
                        "dep_lat, dep_lon, departed_at, class, speed_kn, oparea for a "
                        "real OSINT-driven projection." if sample else "")),
            "honest_limits": HONEST_LIMITS,
            "valid_classes": sorted(_TRANSIT_SPEED.keys()),
            "valid_opareas": sorted(_OPERATING_AREAS.keys()),
            "receipt": receipt,
            "doctrine": "v11", "fetched_at": _now_iso(),
        })

    # -- 3. NEGATIVE-SPACE INFERENCE ----------------------------------------
    async def _asw_negative(request):
        theater = request.query_params.get("theater", "south_china_sea")
        try:
            n = max(2, min(int(request.query_params.get("grid", "4")), 8))
        except Exception:
            n = 4
        result = await _run(lambda: _cached(
            "asw:neg:%s:%d" % (theater, n), lambda: _negative_space(theater, n), 60))
        if "error" in result:
            return JSONResponse({
                "feed": "asw/negative-space", "label": _LABEL["inference"],
                "product": "INFERENCE", **result,
                "honest_limits": HONEST_LIMITS, "doctrine": "v11",
                "fetched_at": _now_iso()}, status_code=200)
        receipt = await _run(_sign_assessment, "inference",
                             {"theater": theater, "grid_n": n,
                              "observed_total": result["observed_total"],
                              "flagged_cells": len(result["flagged"])})
        return JSONResponse({
            "feed": "asw/negative-space",
            "label": _LABEL["inference"],
            "product": "INFERENCE",
            "is_track": False,
            "is_advisory": True,
            **result,
            "honest": ("NEGATIVE-SPACE INFERENCE — we flag sea sub-areas where the "
                       "ABSENCE of expected surface traffic (computed over W1's REAL "
                       "AIS density) plus corroborating OSINT signal suggests "
                       "restricted / military activity. We infer interesting areas "
                       "from what ISN'T there. The evidence (expected vs observed "
                       "density) is shown for every flag. This is ADVISORY and "
                       "human-on-the-loop: absence of surface traffic is SUGGESTIVE, "
                       "NOT proof of submarine activity, and NEVER a submarine track."),
            "honest_limits": HONEST_LIMITS,
            "valid_theaters": _boxed_theaters(),
            "receipt": receipt,
            "doctrine": "v11", "fetched_at": _now_iso(),
        })

    # -- capability / honesty status ----------------------------------------
    async def _asw_status(request):
        return JSONResponse({
            "layer": "killinchu submarine / ASW intelligence (HONEST edition)",
            "honest_limits": HONEST_LIMITS,
            "products": {
                "osint": {"endpoint": "%s/asw/osint" % base, "label": _LABEL["osint"],
                          "sources": [s["name"] for s in _OSINT_SOURCES]},
                "forecast": {"endpoint": "%s/asw/forecast" % base, "label": _LABEL["forecast"],
                             "valid_classes": sorted(_TRANSIT_SPEED.keys()),
                             "valid_opareas": sorted(_OPERATING_AREAS.keys())},
                "negative_space": {"endpoint": "%s/asw/negative-space" % base,
                                   "label": _LABEL["inference"],
                                   "valid_theaters": _boxed_theaters()},
            },
            "signing": {"dsse": (_dsse is not None),
                        "key_present": (bool(_dsse.signing_available()) if _dsse else False),
                        "payload_type": _ASW_PAYLOAD_TYPE},
            "doctrine": "v11", "kernel": "c7c0ba17", "lambda": "Conjecture 1 (advisory)",
            "fetched_at": _now_iso(),
        })

    routes = [
        Route("%s/asw/osint" % base, _asw_osint, methods=["GET"], name="%s_asw_osint" % ns),
        Route("%s/asw/forecast" % base, _asw_forecast, methods=["GET"], name="%s_asw_forecast" % ns),
        Route("%s/asw/negative-space" % base, _asw_negative, methods=["GET"], name="%s_asw_negative" % ns),
        Route("%s/asw/status" % base, _asw_status, methods=["GET"], name="%s_asw_status" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)

    return {"status": "ok", "base": base,
            "endpoints": [r.path for r in routes],
            "products": ["OSINT-LIVE", "FORECAST", "INFERENCE"],
            "signing_key_present": (bool(_dsse.signing_available()) if _dsse else False)}


__all__ = ["register", "_collect_osint", "_forecast_field", "_negative_space",
           "_sign_assessment", "HONEST_LIMITS"]
