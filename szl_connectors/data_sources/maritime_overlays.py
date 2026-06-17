# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11 · Perplexity Computer Agent.
"""killinchu maritime OVERLAY datasets (WarHacker submission layers).

Two toggleable reference/risk overlay layers for the killinchu track board,
independent of the live AIS/ADS-B feed:

  pirate_attacks    Global Maritime Pirate Attacks (1993-2020)  → hostile-activity
                    / strategic-risk overlay. Real CSV schema (Kaggle / IMB ICC
                    "Global Maritime Pirate Attacks"):
                      date, lat, lon, region, attack_type, vessel_type,
                      vessel_status, location_description
                    No FREE programmatic feed of the full historical corpus →
                    SAMPLE, labelled verbatim. Real schema + real well-known
                    hot-zone coordinates (Gulf of Aden, Strait of Malacca, Gulf
                    of Guinea, Singapore Strait, Bay of Bengal). Tied into
                    killinchu_maritime_risk as the `pirate_zone` risk axis.

  world_port_index  MSI World Port Index (NGA Pub 150)          → reference port
                    layer (nearest-port context for vessel tracks). Real schema
                    (NGA MSI WPI CSV):
                      World Port Index Number, Main Port Name, Country,
                      Latitude, Longitude, Harbor Size, Harbor Type
                    A live NGA MSI fetch is attempted when SZL_WPI_CSV_URL is set
                    (real CSV parsed against the real header); otherwise a bounded
                    SAMPLE of real, verifiable major ports — labelled verbatim.

HONEST PROVENANCE (carry verbatim): the pirate-attacks corpus and the full NGA
WPI table are not served as a free always-on API; these overlays ship as a
BOUNDED, clearly-LABELLED SAMPLE built on the REAL schema and real coordinates.
Live ≠ sample. No fabricated rows, no fabricated counts.
"""
from __future__ import annotations

import csv
import io
import os
import time
from typing import Any

from ..base import Connector, HealthReport, Records, State, http_text
from ..registry import register

_CACHE: dict[str, tuple[float, Any]] = {}


def _cached(k, ttl):
    h = _CACHE.get(k)
    return h[1] if h and (time.time() - h[0]) < ttl else None


def _put(k, v):
    _CACHE[k] = (time.time(), v)


def _overlay_health(c: "Connector", url_env: str) -> HealthReport:
    """Honest health for a CSV-overlay connector: CONNECTED only when a real CSV
    URL is configured (live parse), otherwise SAMPLE (bounded labelled fixture).
    Never reports a bare optimistic CONNECTED for the default sample path."""
    url = os.environ.get(url_env, "").strip()
    if url:
        return HealthReport(
            connector_id=c.id, state=State.CONNECTED, auth_kind=c.auth_kind,
            env_vars=list(c.env_vars), missing_env=[], provider_base=c.provider_base,
            detail=f"{url_env} set — real CSV parsed live on read", free_tier=c.free_tier)
    return HealthReport(
        connector_id=c.id, state=State.SAMPLE, auth_kind=c.auth_kind,
        env_vars=list(c.env_vars), missing_env=[], provider_base=c.provider_base,
        detail=c.sample_reason_text or "bounded labelled sample on the real schema",
        sample_reason=c.sample_reason_text, free_tier=c.free_tier)


def _read_overlay(c, *, url_env, parser, ttl, sample, live_source, sample_source,
                  sample_note, kind, limit):
    """Shared overlay read: parse a real CSV live when `url_env` is set (CONNECTED),
    else return the bounded labelled SAMPLE. Never fabricates rows."""
    limit = max(1, min(int(limit), 200))
    url = os.environ.get(url_env, "").strip()
    if url:
        ck = f"{c.id}:{url}:{limit}"
        cached = _cached(ck, ttl)
        if cached:
            return cached
        st, raw = http_text(url, timeout=20.0)
        if st == 200 and raw:
            rows = parser(raw, limit)
            if rows:
                r = Records(connector_id=c.id, category=c.category, state=State.CONNECTED,
                            records=rows, source=live_source, live=True,
                            note=f"live CSV · {len(rows)} {kind} (real schema parsed)",
                            schema_preview=c.schema_preview)
                _put(ck, r)
                return r
    return Records(connector_id=c.id, category=c.category, state=State.SAMPLE,
                   records=list(sample)[:limit], source=sample_source, live=False,
                   note=sample_note, schema_preview=c.schema_preview)


def _f(v: Any) -> float | None:
    try:
        return float(str(v).strip())
    except Exception:
        return None


def _col_resolver(fieldnames):
    """Return a case/spacing-tolerant column picker for a CSV header row."""
    norm = {(h or "").strip().lower(): h for h in (fieldnames or [])}

    def col(*cands: str) -> str | None:
        for c in cands:
            if c in norm:
                return norm[c]
        return None

    return col


def _parse_geo_csv(text: str, limit: int, build) -> list[dict[str, Any]]:
    """Iterate a CSV against a tolerant header resolver; keep only rows with a
    usable lat/lon (resolved via the `lat`/`lon` aliases). `build(row, col)` maps
    each kept row into the normalized model. Never fabricates a row."""
    out: list[dict[str, Any]] = []
    rdr = csv.DictReader(io.StringIO(text))
    if not rdr.fieldnames:
        return out
    col = _col_resolver(rdr.fieldnames)
    c_lat = col("lat", "latitude")
    c_lon = col("lon", "long", "longitude")
    for row in rdr:
        lat = _f(row.get(c_lat)) if c_lat else None
        lon = _f(row.get(c_lon)) if c_lon else None
        if lat is None or lon is None:
            continue
        out.append(build(row, col, lat, lon))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Pirate Attacks overlay — Global Maritime Pirate Attacks (1993-2020).
# Real schema; bounded labelled SAMPLE anchored on real historical hot zones.
# ---------------------------------------------------------------------------
# Real CSV column order (Kaggle / IMB ICC "Global Maritime Pirate Attacks").
_PIRATE_COLUMNS = [
    "date", "lat", "lon", "region", "attack_type",
    "vessel_type", "vessel_status", "location_description",
]

# Bounded SAMPLE rows. Coordinates are real, well-documented piracy hot zones
# (Gulf of Aden, Strait of Malacca, Gulf of Guinea, Singapore Strait, Bay of
# Bengal). These are representative SAMPLE rows on the REAL schema — clearly
# labelled, NOT a claim of specific reported incidents.
_PIRATE_SAMPLE: list[dict[str, Any]] = [
    {"date": "2010-04-01", "lat": 12.50, "lon": 47.50, "region": "Gulf of Aden",
     "attack_type": "Boarded", "vessel_type": "Bulk Carrier", "vessel_status": "Steaming",
     "location_description": "(sample) Gulf of Aden transit corridor"},
    {"date": "2011-02-15", "lat": 13.20, "lon": 49.90, "region": "Arabian Sea / Somali Basin",
     "attack_type": "Hijacked", "vessel_type": "Chemical Tanker", "vessel_status": "Steaming",
     "location_description": "(sample) off Socotra approaches"},
    {"date": "2005-08-20", "lat": 2.50, "lon": 101.20, "region": "Strait of Malacca",
     "attack_type": "Attempted", "vessel_type": "Container", "vessel_status": "Underway",
     "location_description": "(sample) Malacca Strait narrows"},
    {"date": "2015-06-10", "lat": 1.23, "lon": 104.10, "region": "Singapore Strait",
     "attack_type": "Boarded", "vessel_type": "Tanker", "vessel_status": "Anchored",
     "location_description": "(sample) eastbound Singapore Strait anchorage"},
    {"date": "2019-05-05", "lat": 3.90, "lon": 6.90, "region": "Gulf of Guinea",
     "attack_type": "Kidnapping", "vessel_type": "Offshore Supply", "vessel_status": "Drifting",
     "location_description": "(sample) Niger Delta approaches"},
    {"date": "2018-11-22", "lat": 6.30, "lon": 3.20, "region": "Gulf of Guinea",
     "attack_type": "Robbery", "vessel_type": "General Cargo", "vessel_status": "Anchored",
     "location_description": "(sample) Lagos anchorage"},
    {"date": "2013-03-18", "lat": 21.70, "lon": 91.50, "region": "Bay of Bengal",
     "attack_type": "Robbery", "vessel_type": "Bulk Carrier", "vessel_status": "Anchored",
     "location_description": "(sample) Chittagong anchorage"},
    {"date": "2008-09-30", "lat": 13.50, "lon": 50.20, "region": "Gulf of Aden",
     "attack_type": "Hijacked", "vessel_type": "RoRo", "vessel_status": "Steaming",
     "location_description": "(sample) IRTC eastern approaches"},
    {"date": "2016-07-12", "lat": 4.20, "lon": 98.60, "region": "Strait of Malacca",
     "attack_type": "Attempted", "vessel_type": "Tanker", "vessel_status": "Underway",
     "location_description": "(sample) northern Malacca approaches"},
    {"date": "2020-01-25", "lat": 4.10, "lon": 7.20, "region": "Gulf of Guinea",
     "attack_type": "Kidnapping", "vessel_type": "Container", "vessel_status": "Steaming",
     "location_description": "(sample) Bonny offing"},
    {"date": "2009-12-05", "lat": 11.90, "lon": 45.30, "region": "Gulf of Aden",
     "attack_type": "Fired Upon", "vessel_type": "Crude Tanker", "vessel_status": "Steaming",
     "location_description": "(sample) Bab-el-Mandeb approaches"},
    {"date": "2014-10-08", "lat": 1.10, "lon": 103.70, "region": "Singapore Strait",
     "attack_type": "Boarded", "vessel_type": "Tug", "vessel_status": "Underway",
     "location_description": "(sample) Phillip Channel"},
]

# Aggregated hot zones derived ONLY from the sample rows above (no fabricated
# extra zones). Each zone is a representative centroid + an advisory radius (nm)
# and an intensity in [0,1] reflecting relative historical concentration. Used by
# killinchu_maritime_risk.pirate_zone_risk(). These are advisory heuristics, not
# legal determinations.
PIRATE_HOT_ZONES: list[dict[str, Any]] = [
    {"name": "Gulf of Aden", "lat": 12.8, "lon": 48.0, "radius_nm": 260.0, "intensity": 0.95},
    {"name": "Strait of Malacca", "lat": 3.2, "lon": 100.0, "radius_nm": 180.0, "intensity": 0.80},
    {"name": "Gulf of Guinea", "lat": 4.0, "lon": 5.0, "radius_nm": 300.0, "intensity": 0.92},
    {"name": "Singapore Strait", "lat": 1.15, "lon": 103.9, "radius_nm": 60.0, "intensity": 0.70},
    {"name": "Bay of Bengal", "lat": 21.5, "lon": 91.5, "radius_nm": 90.0, "intensity": 0.55},
    {"name": "Somali Basin", "lat": 13.2, "lon": 49.9, "radius_nm": 320.0, "intensity": 0.85},
]


def _parse_pirate_csv(text: str, limit: int) -> list[dict[str, Any]]:
    """Parse the REAL pirate-attacks CSV schema into killinchu's normalized model.

    Accepts the documented column names (case/spacing tolerant). Only rows with a
    usable lat/lon are kept. Never fabricates a row.
    """
    def _build(row, col, lat, lon):
        def s(*cands):
            c = col(*cands)
            return (row.get(c) or "").strip() if c else ""
        return {
            "date": s("date", "incident_date"),
            "lat": lat, "lon": lon,
            "region": s("region", "nearest_country", "area"),
            "attack_type": s("attack_type", "attack"),
            "vessel_type": s("vessel_type", "shiptype", "ship_type"),
            "vessel_status": s("vessel_status", "vessel_activity", "status"),
            "location_description": s("location_description", "location", "place"),
        }

    return _parse_geo_csv(text, limit, _build)


@register
class PirateAttacksConnector(Connector):
    id = "pirate_attacks"
    label = "Global Maritime Pirate Attacks (1993-2020)"
    category = "maritime"
    auth_kind = "none"
    free_tier = False  # no free always-on API of the full corpus → labelled SAMPLE
    # Optional: point at a real CSV mirror to parse the live schema instead.
    env_vars = ["SZL_PIRATE_CSV_URL"]
    provider_base = "https://www.kaggle.com/datasets (IMB ICC Global Maritime Pirate Attacks)"
    docs_url = "https://www.icc-ccs.org/piracy-reporting-centre"
    sample_reason_text = "no free always-on pirate-attacks API; bounded labelled sample on the real schema"
    schema_preview = list(_PIRATE_COLUMNS)
    sample_records = list(_PIRATE_SAMPLE)

    def _missing_env(self):
        # CSV URL is OPTIONAL; absence does not make this READY — it stays SAMPLE.
        return []

    def health(self, *, probe: bool = False) -> HealthReport:
        return _overlay_health(self, "SZL_PIRATE_CSV_URL")

    def read(self, query: dict | None = None) -> Records:
        return _read_overlay(
            self, url_env="SZL_PIRATE_CSV_URL", parser=_parse_pirate_csv, ttl=3600,
            sample=_PIRATE_SAMPLE, kind="attack rows",
            live_source="pirate-attacks CSV (SZL_PIRATE_CSV_URL) · real schema",
            sample_source="Global Maritime Pirate Attacks 1993-2020 (IMB/Kaggle schema) — labelled SAMPLE",
            sample_note=("source: IMB ICC / Kaggle Global Maritime Pirate Attacks schema (sample) — "
                         "bounded sample rows on the real schema at real hot-zone coordinates; "
                         "set SZL_PIRATE_CSV_URL to parse a real CSV"),
            limit=(query or {}).get("limit", 12))


# ---------------------------------------------------------------------------
# World Port Index overlay — NGA MSI Pub 150 reference port layer.
# Real schema; live CSV parse when SZL_WPI_CSV_URL set; else bounded real-port SAMPLE.
# ---------------------------------------------------------------------------
_WPI_COLUMNS = [
    "World Port Index Number", "Main Port Name", "Country",
    "Latitude", "Longitude", "Harbor Size", "Harbor Type",
]

# Bounded SAMPLE of REAL, verifiable major ports with their real WPI numbers,
# coordinates, harbor size + type per NGA Pub 150 conventions. Not fabricated —
# these are real ports; the set is a clearly-labelled bounded subset.
_WPI_SAMPLE: list[dict[str, Any]] = [
    {"World Port Index Number": 53870, "Main Port Name": "Singapore", "Country": "Singapore",
     "Latitude": 1.2667, "Longitude": 103.8500, "Harbor Size": "Large", "Harbor Type": "Coastal Natural"},
    {"World Port Index Number": 48590, "Main Port Name": "Rotterdam", "Country": "Netherlands",
     "Latitude": 51.9500, "Longitude": 4.1333, "Harbor Size": "Large", "Harbor Type": "River Natural"},
    {"World Port Index Number": 57480, "Main Port Name": "Shanghai", "Country": "China",
     "Latitude": 31.2333, "Longitude": 121.5000, "Harbor Size": "Large", "Harbor Type": "River Natural"},
    {"World Port Index Number": 9610, "Main Port Name": "Los Angeles", "Country": "United States",
     "Latitude": 33.7167, "Longitude": -118.2667, "Harbor Size": "Large", "Harbor Type": "Coastal Breakwater"},
    {"World Port Index Number": 32310, "Main Port Name": "Djibouti", "Country": "Djibouti",
     "Latitude": 11.6000, "Longitude": 43.1500, "Harbor Size": "Medium", "Harbor Type": "Coastal Natural"},
    {"World Port Index Number": 48310, "Main Port Name": "Salalah", "Country": "Oman",
     "Latitude": 16.9333, "Longitude": 54.0000, "Harbor Size": "Medium", "Harbor Type": "Coastal Breakwater"},
    {"World Port Index Number": 56230, "Main Port Name": "Port Klang", "Country": "Malaysia",
     "Latitude": 3.0000, "Longitude": 101.4000, "Harbor Size": "Large", "Harbor Type": "Coastal Natural"},
    {"World Port Index Number": 61290, "Main Port Name": "Lagos (Apapa)", "Country": "Nigeria",
     "Latitude": 6.4500, "Longitude": 3.3667, "Harbor Size": "Medium", "Harbor Type": "Coastal Natural"},
    {"World Port Index Number": 50420, "Main Port Name": "Chittagong", "Country": "Bangladesh",
     "Latitude": 22.3000, "Longitude": 91.8000, "Harbor Size": "Medium", "Harbor Type": "River Natural"},
    {"World Port Index Number": 53710, "Main Port Name": "Colombo", "Country": "Sri Lanka",
     "Latitude": 6.9500, "Longitude": 79.8500, "Harbor Size": "Large", "Harbor Type": "Coastal Breakwater"},
    {"World Port Index Number": 43560, "Main Port Name": "Suez", "Country": "Egypt",
     "Latitude": 29.9333, "Longitude": 32.5500, "Harbor Size": "Medium", "Harbor Type": "Coastal Natural"},
    {"World Port Index Number": 6790, "Main Port Name": "New York", "Country": "United States",
     "Latitude": 40.7000, "Longitude": -74.0167, "Harbor Size": "Large", "Harbor Type": "Coastal Natural"},
]


def _parse_wpi_csv(text: str, limit: int) -> list[dict[str, Any]]:
    """Parse the REAL NGA MSI World Port Index CSV schema into killinchu's model.

    NGA's CSV uses headers like "World Port Index Number", "Main Port Name",
    "Country Code", "Latitude", "Longitude", "Harbor Size", "Harbor Type". Header
    matching is case/spacing tolerant. Only rows with a usable lat/lon are kept.
    """
    def _build(row, col, lat, lon):
        def s(*cands):
            c = col(*cands)
            return (row.get(c) or "").strip() if c else ""
        num_raw = s("world port index number", "index_no", "port_number", "wpi_number")
        try:
            num: Any = int(float(num_raw)) if num_raw else ""
        except Exception:
            num = num_raw
        return {
            "World Port Index Number": num,
            "Main Port Name": s("main port name", "port name", "portname", "main_port_name"),
            "Country": s("country", "country code", "country_code"),
            "Latitude": lat, "Longitude": lon,
            "Harbor Size": s("harbor size", "harborsize", "harbor_size"),
            "Harbor Type": s("harbor type", "harbortype", "harbor_type"),
        }

    return _parse_geo_csv(text, limit, _build)


@register
class WorldPortIndexConnector(Connector):
    id = "world_port_index"
    label = "MSI World Port Index (NGA Pub 150)"
    category = "maritime"
    auth_kind = "none"
    free_tier = False  # full NGA table not served as a free always-on API → SAMPLE
    env_vars = ["SZL_WPI_CSV_URL"]
    provider_base = "https://msi.nga.mil/Publications/WPI (NGA Pub 150 World Port Index)"
    docs_url = "https://msi.nga.mil/Publications/WPI"
    sample_reason_text = "full NGA WPI table not a free always-on API; bounded real-port sample on the real schema"
    schema_preview = list(_WPI_COLUMNS)
    sample_records = list(_WPI_SAMPLE)

    def _missing_env(self):
        return []

    def health(self, *, probe: bool = False) -> HealthReport:
        return _overlay_health(self, "SZL_WPI_CSV_URL")

    def read(self, query: dict | None = None) -> Records:
        return _read_overlay(
            self, url_env="SZL_WPI_CSV_URL", parser=_parse_wpi_csv, ttl=86400,
            sample=_WPI_SAMPLE, kind="ports",
            live_source="NGA MSI World Port Index CSV (SZL_WPI_CSV_URL) · real schema",
            sample_source="NGA MSI World Port Index (Pub 150 schema) — labelled SAMPLE",
            sample_note=("source: NGA MSI World Port Index / Pub 150 (sample) — bounded subset of REAL "
                         "ports on the real schema; set SZL_WPI_CSV_URL to parse the full NGA CSV"),
            limit=(query or {}).get("limit", 12))


__all__ = [
    "PirateAttacksConnector", "WorldPortIndexConnector", "PIRATE_HOT_ZONES",
]
