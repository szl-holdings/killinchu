# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11 · Perplexity Computer Agent.
"""NOAA / MarineCadastre AIS — August 2024 coastal-US historical dataset connector.

This is the WarHacker "Maritime AIS Data August 2024 (coastal US)" dataset, wired
as a SELECTABLE governed source ALONGSIDE the live AIS feed (live stays default).

REAL SOURCE (schema source-of-truth, do NOT fabricate):
  NOAA / Marine Cadastre AIS vessel transit data — daily zipped CSVs
  AIS_YYYY_MM_DD.zip published at
  https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/
  August 2024 = AIS_2024_08_01.zip ... AIS_2024_08_31.zip

REAL SCHEMA (verbatim CSV header):
  MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, IMO, CallSign,
  VesselType, Status, Length, Width, Draft, Cargo, TransceiverClass

WHAT THIS CONNECTOR SHIPS (honest label — doctrine v11, no overclaim):
  A BOUNDED SAMPLE of REAL rows extracted from the real AIS_2024_08_01.csv:
  US Northeast / Mid-Atlantic coastal bbox, first hour of 2024-08-01, one row per
  vessel — committed at data/ais_noaa_aug2024/AIS_2024_08_01_sample_coastal_ne.csv.
  These are GENUINE NOAA AIS rows (not synthetic), but a SAMPLE of one day, NOT the
  full multi-GB August 2024 month. It is labelled "(sample)" everywhere.

  The parser is written to the REAL NOAA schema, so pointing it at a full
  AIS_2024_08_*.csv (or the live ranged fetch below) ingests the real file as-is.

LIVE FETCH (optional, off by default — keeps the build repo-light & offline-safe):
  With query {"fetch": true} the connector will range-download the head of the real
  AIS_2024_08_01.zip from NOAA and stream-inflate real rows. This is REAL data, but
  network-dependent; the default path reads the committed real-row sample so the demo
  is deterministic and offline.
"""
from __future__ import annotations

import csv
import io
import os
import struct
import zlib
from typing import Any

from ..base import Connector, Records, State
from ..registry import register

# Real NOAA daily AIS zip (Aug 1 2024) — used ONLY when query {"fetch": true}.
NOAA_AIS_AUG01_URL = (
    "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/AIS_2024_08_01.zip"
)

# Verbatim NOAA AIS CSV schema (source of truth).
NOAA_SCHEMA = [
    "MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName",
    "IMO", "CallSign", "VesselType", "Status", "Length", "Width", "Draft",
    "Cargo", "TransceiverClass",
]

# Committed real-row sample (bounded coastal bbox + 1h window of AIS_2024_08_01).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
SAMPLE_CSV = os.path.join(
    _REPO_ROOT, "data", "ais_noaa_aug2024", "AIS_2024_08_01_sample_coastal_ne.csv"
)

# The bounded coastal bbox the committed sample was cut from (US NE / Mid-Atlantic).
SAMPLE_BBOX = {"lat_min": 38.0, "lat_max": 43.0, "lon_min": -75.0, "lon_max": -68.0}
SAMPLE_WINDOW = {"start": "2024-08-01T00:00:00", "end": "2024-08-01T01:00:00"}

PROVENANCE_FULL = "NOAA/MarineCadastre AIS, Aug 2024, coastal US"
# Honest label — this is a SAMPLE of one day, never the full month.
PROVENANCE_SAMPLE = (
    "source: NOAA/MarineCadastre AIS, Aug 2024, coastal US (sample) — "
    "real rows from AIS_2024_08_01.csv, US NE coastal bbox, first hour; "
    "NOT the full month."
)

# NOAA VesselType (AIS ship-and-cargo-type) → coarse killinchu category.
# Per ITU-R M.1371 / NOAA AIS dictionary numeric ranges.
def _vessel_type_label(vt: str) -> str:
    try:
        n = int(float(vt))
    except Exception:
        return "unknown"
    if n in (30,):
        return "fishing"
    if n in (31, 32, 52):
        return "tug_tow"
    if n in (35,):
        return "military"
    if n in (36,):
        return "sailing"
    if n in (37,):
        return "pleasure"
    if 60 <= n <= 69:
        return "passenger"
    if 70 <= n <= 79:
        return "cargo"
    if 80 <= n <= 89:
        return "tanker"
    if n in (40, 41, 42, 43, 44, 45, 46, 47, 48, 49):
        return "high_speed"
    return "other"


# NOAA Status (AIS navigational status code) → human label (subset).
_STATUS = {
    0: "under_way_engine", 1: "at_anchor", 2: "not_under_command",
    3: "restricted_manoeuvrability", 4: "constrained_by_draught", 5: "moored",
    6: "aground", 7: "engaged_in_fishing", 8: "under_way_sailing",
    15: "undefined",
}


def _status_label(s: str) -> str:
    try:
        return _STATUS.get(int(float(s)), "unknown")
    except Exception:
        return "unknown"


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map one REAL NOAA AIS CSV row to killinchu's vessel/track shape.

    Output keys match the killinchu_fleet_vessels / killinchu_maritime_risk vessel
    model (name, imo, mmsi, flag, vesselType, status, currentLat, currentLon,
    currentSpeed, currentHeading, ...) so score_vessel() consumes it directly.
    Provenance fields are added; the source label is carried honestly.
    """
    name = (row.get("VesselName") or "").strip()
    imo = (row.get("IMO") or "").strip()
    heading = _f(row.get("Heading"))
    # AIS encodes "heading not available" as 511; carry None rather than fake it.
    if heading is not None and heading >= 511:
        heading = None
    cog = _f(row.get("COG"))
    return {
        "mmsi": (row.get("MMSI") or "").strip(),
        "name": name or None,
        "imo": imo or None,
        "callSign": (row.get("CallSign") or "").strip() or None,
        # NOAA AIS carries no flag-state field; do NOT fabricate one.
        "flag": None,
        "vesselType": _vessel_type_label(row.get("VesselType", "")),
        "vesselTypeCode": (row.get("VesselType") or "").strip() or None,
        "status": _status_label(row.get("Status", "")),
        "statusCode": (row.get("Status") or "").strip() or None,
        "currentLat": _f(row.get("LAT")),
        "currentLon": _f(row.get("LON")),
        "currentSpeed": _f(row.get("SOG")),
        "currentHeading": heading if heading is not None else cog,
        "cog": cog,
        "length": _f(row.get("Length")),
        "beam": _f(row.get("Width")),
        "draft": _f(row.get("Draft")),
        "cargo": (row.get("Cargo") or "").strip() or None,
        "transceiverClass": (row.get("TransceiverClass") or "").strip() or None,
        "baseDateTime": (row.get("BaseDateTime") or "").strip() or None,
        "source": PROVENANCE_FULL,
        "data_kind": "noaa_ais_aug2024_sample",
    }


def _in_bbox(row: dict[str, Any], bbox: dict[str, float] | None) -> bool:
    if not bbox:
        return True
    lat = _f(row.get("LAT"))
    lon = _f(row.get("LON"))
    if lat is None or lon is None:
        return False
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]
            and bbox["lon_min"] <= lon <= bbox["lon_max"])


def _in_window(row: dict[str, Any], window: dict[str, str] | None) -> bool:
    if not window:
        return True
    ts = (row.get("BaseDateTime") or "")
    return window["start"] <= ts <= window["end"]


def parse_ais_csv(text: str, *, bbox: dict[str, float] | None = None,
                  window: dict[str, str] | None = None,
                  limit: int | None = None) -> list[dict[str, Any]]:
    """Parse REAL NOAA AIS CSV text → normalized vessel rows (bounded)."""
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict[str, Any]] = []
    for row in reader:
        if not _in_bbox(row, bbox) or not _in_window(row, window):
            continue
        out.append(normalize_row(row))
        if limit is not None and len(out) >= limit:
            break
    return out


def _stream_inflate_zip_head(zip_bytes: bytes) -> str:
    """Inflate the first (only) member of a NOAA AIS daily zip from a partial
    byte prefix. Returns decoded CSV text (last, possibly-truncated line dropped).

    NOAA daily zips contain one stored member AIS_YYYY_MM_DD.csv (deflate). A
    ranged prefix is enough to recover the leading real rows for a bounded sample.
    """
    if zip_bytes[:4] != b"PK\x03\x04":
        raise ValueError("not a zip local file header")
    (_sig, _ver, _flags, method, _mt, _md, _crc, _cs, _us,
     fnlen, eflen) = struct.unpack("<IHHHHHIIIHH", zip_bytes[:30])
    if method != 8:
        raise ValueError(f"unexpected zip method {method} (expected deflate)")
    start = 30 + fnlen + eflen
    d = zlib.decompressobj(-15)
    try:
        raw = d.decompress(zip_bytes[start:])
    except zlib.error:
        raw = b""
    text = raw.decode("latin1", "replace")
    lines = text.splitlines()
    return "\n".join(lines[:-1]) if len(lines) > 1 else text


@register
class NoaaAisAug2024Connector(Connector):
    id = "noaa_ais_aug2024"
    label = "NOAA/MarineCadastre AIS — Aug 2024 coastal US (WarHacker dataset)"
    category = "maritime"
    auth_kind = "none"          # public NOAA dataset, keyless
    free_tier = True
    provider_base = NOAA_AIS_AUG01_URL
    docs_url = "https://marinecadastre.gov/ais/"
    schema_preview = list(NOAA_SCHEMA)
    # Committed real-row sample acts as the fixture (no synthetic rows ever).
    sample_reason_text = (
        "bounded real-row sample of AIS_2024_08_01.csv (full month is multi-GB)"
    )

    def _read_sample_text(self) -> str | None:
        try:
            with open(SAMPLE_CSV, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return None

    def _fetch_real_head(self, nbytes: int = 6_000_000) -> str | None:
        """Range-download the head of the real NOAA zip and inflate real rows."""
        import urllib.request as _ur
        req = _ur.Request(self.provider_base,
                          headers={"User-Agent": "SZL-Connectors/1.0",
                                   "Range": f"bytes=0-{nbytes - 1}"})
        try:
            with _ur.urlopen(req, timeout=30.0) as resp:
                blob = resp.read()
            return _stream_inflate_zip_head(blob)
        except Exception:
            return None

    def read(self, query: dict | None = None) -> Records:
        q = query or {}
        bbox = q.get("bbox", SAMPLE_BBOX)
        window = q.get("window", SAMPLE_WINDOW)
        limit = q.get("limit")
        limit = int(limit) if limit is not None else None

        # Real live ingest path (opt-in): range-fetch + inflate the real NOAA zip.
        if q.get("fetch"):
            text = self._fetch_real_head()
            if text:
                rows = parse_ais_csv(text, bbox=bbox, window=window, limit=limit)
                return Records(
                    connector_id=self.id, category=self.category,
                    state=State.CONNECTED, records=rows,
                    source=f"{PROVENANCE_FULL} (live ranged fetch of AIS_2024_08_01.zip)",
                    live=True,
                    note=("real NOAA AIS rows fetched live (ranged) and bounded to "
                          "the requested coastal bbox + window"),
                    schema_preview=list(NOAA_SCHEMA),
                )
            # fall through to committed sample if the network path is unavailable

        # Default deterministic path: committed REAL-ROW sample (labelled sample).
        text = self._read_sample_text()
        if text is None:
            return self._ready_records(
                "NOAA AIS Aug-2024 sample CSV not found on disk; "
                "set query {'fetch': true} to range-fetch real rows from NOAA")
        rows = parse_ais_csv(text, bbox=bbox, window=window, limit=limit)
        return Records(
            connector_id=self.id, category=self.category, state=State.SAMPLE,
            records=rows, source=PROVENANCE_SAMPLE, live=False,
            note=PROVENANCE_SAMPLE,
            schema_preview=list(NOAA_SCHEMA),
        )


__all__ = [
    "NoaaAisAug2024Connector", "normalize_row", "parse_ais_csv",
    "NOAA_SCHEMA", "SAMPLE_BBOX", "SAMPLE_WINDOW",
    "PROVENANCE_FULL", "PROVENANCE_SAMPLE", "NOAA_AIS_AUG01_URL",
]
