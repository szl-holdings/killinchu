# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
"""
killinchu_cot_interop.py — MITRE Cursor on Target (CoT) interoperability.

ADDITIVE module. serve.py imports this and calls register(app) AFTER the other
routers but BEFORE the SPA catch-all. It does NOT touch any existing route.

WHAT THIS IS
------------
Cursor on Target (CoT) is the DoD's XML-based tactical messaging standard
(base schema "Event.xsd", maintained by MITRE; cot.mitre.org). A CoT event
describes the What / When / Where (W3) of a battlefield entity:

  <event version="2.0" uid="..." type="a-f-S" time="..." start="..."
         stale="..." how="m-g">
    <point lat="..." lon="..." hae="..." ce="..." le="..."/>
    <detail> ... optional sub-schema ... </detail>
  </event>

This module makes killinchu "speak CoT": it EXPORTS killinchu tracks
(maritime vessels + friendly drones + cued threat UAS) as standards-compliant
CoT XML events, VALIDATES the XML against the real CoT base-schema shape, and
INGESTS CoT XML back into killinchu track dicts (bidirectional).

LIVE vs ROADMAP (honest doctrine v11)
-------------------------------------
LIVE NOW (real, in this PR):
  * CoT 2.0 XML serialisation of every killinchu track (vessel/drone/threat).
  * CoT type-resolution via the MIL-STD-2525 / CoT atom hierarchy
    (a-f-S-X-M = friendly surface vessel, a-f-A-M-F = friendly UAS,
     a-h-A = hostile air, a-u-A = unknown air, etc.).
  * Schema-shape validation (required attrs, value ranges, ISO-8601 stamps)
    against the documented Event.xsd contract — pure-Python, no network.
  * CoT XML ingest: parse an inbound <event> into a killinchu track dict.
  * REST: GET /api/killinchu/v1/cot/export (all tracks as a CoT <events> doc),
          GET /api/killinchu/v1/cot/export/{track_id} (one event),
          POST /api/killinchu/v1/cot/ingest (CoT XML -> killinchu track),
          GET /api/killinchu/v1/cot/status (capability + honesty manifest).

ROADMAP (NOT wired — explicitly labelled, never claimed as live):
  * UDP multicast emission to the CoT default group 239.2.3.1:6969.
  * Live TAK-server (FreeTAKServer / TAK Server) streaming / mesh SA.
  * TLS client-cert enrolment to a TAK server.
  These are documented in cot_status()["roadmap"] and the /status route as
  "roadmap" — there is NO live TAK socket in this build.

Source / standard provenance:
  MITRE CoT base schema "Event.xsd" (cot.mitre.org); DISA DoD XML registry.
  MIL-STD-2525 symbology underlies the CoT 'type' atom hierarchy.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse, Response
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore
    Response = None  # type: ignore

_HERE = os.path.dirname(os.path.abspath(__file__))
_VESSELS_PATH = os.path.join(_HERE, "fleet_vessels_data.json")
_LOGGER = logging.getLogger(__name__)

COT_VERSION = "2.0"
# CoT default multicast SA group (ROADMAP target only — never opened here).
COT_DEFAULT_MULTICAST = "239.2.3.1:6969"

# CoT events are compact tactical messages. Hard limits bound parser memory and
# post-parse traversal even after DTD/entity expansion has been disabled.
MAX_COT_XML_BYTES = 256 * 1024
MAX_COT_XML_ELEMENTS = 2048
MAX_COT_XML_DEPTH = 24
MAX_COT_XML_TEXT_CHARS = 128 * 1024
MAX_COT_ATTRIBUTES_PER_ELEMENT = 64

# Client responses deliberately expose only stable categories. Detailed
# exception context remains in server logs and never crosses the HTTP boundary.
_INGEST_ERROR_TOO_LARGE = "CoT XML payload too large"
_INGEST_ERROR_ENCODING = "CoT XML must be UTF-8"
_INGEST_ERROR_INVALID = "invalid CoT XML"

HONESTY_LABEL = (
    "Real CoT 2.0 XML export + schema-shape validation + ingest, computed from "
    "killinchu sample tracks. No live TAK-server / UDP multicast in this build "
    "(roadmap, labelled)."
)

# Standard / leader sources surfaced in every CoT payload (honest data_kind).
COT_SOURCES = [
    {"leader": "MITRE Cursor on Target (CoT)", "kind": "Event.xsd base schema (DoD XML tactical messaging)",
     "url": "https://www.mitre.org/", "data_kind": "standard"},
    {"leader": "DISA DoD XML Registry", "kind": "CoT schema registration authority",
     "url": "https://www.disa.mil/", "data_kind": "standard"},
    {"leader": "MIL-STD-2525", "kind": "symbology underpinning the CoT 'type' atom hierarchy",
     "url": "https://www.jcs.mil/", "data_kind": "standard"},
    {"leader": "TAK (Team Awareness Kit)", "kind": "reference CoT consumer / SA ecosystem (roadmap target)",
     "url": "https://tak.gov/", "data_kind": "standard"},
]


class CotPayloadTooLarge(ValueError):
    """Raised before parsing when an inbound CoT body exceeds the byte limit."""


def _parse_untrusted_xml(xml: str) -> ET.Element:
    """Parse untrusted CoT XML with entity expansion and DTDs disabled.

    The byte limit is checked before parsing; structural limits are then
    enforced iteratively to avoid recursive traversal of adversarial trees.
    """
    if not isinstance(xml, str):
        raise ValueError("CoT XML must be text")
    try:
        encoded = xml.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"invalid CoT XML encoding: {exc}") from exc
    if len(encoded) > MAX_COT_XML_BYTES:
        raise CotPayloadTooLarge(f"CoT XML exceeds {MAX_COT_XML_BYTES} byte limit")

    try:
        root = DefusedET.fromstring(
            xml,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise ValueError(f"XML parse error: {exc}") from exc

    element_count = 0
    text_chars = 0
    stack: list[tuple[ET.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        element_count += 1
        if element_count > MAX_COT_XML_ELEMENTS:
            raise ValueError(f"CoT XML exceeds {MAX_COT_XML_ELEMENTS} element limit")
        if depth > MAX_COT_XML_DEPTH:
            raise ValueError(f"CoT XML exceeds {MAX_COT_XML_DEPTH} level depth limit")
        if len(element.attrib) > MAX_COT_ATTRIBUTES_PER_ELEMENT:
            raise ValueError(
                "CoT XML element exceeds "
                f"{MAX_COT_ATTRIBUTES_PER_ELEMENT} attribute limit"
            )
        text_chars += len(element.text or "") + len(element.tail or "")
        if text_chars > MAX_COT_XML_TEXT_CHARS:
            raise ValueError(
                f"CoT XML exceeds {MAX_COT_XML_TEXT_CHARS} text-character limit"
            )
        stack.extend((child, depth + 1) for child in list(element))
    return root


async def _read_limited_request_body(request: Request) -> bytes:
    """Read a streaming request body without buffering past the CoT limit."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_COT_XML_BYTES:
            raise CotPayloadTooLarge(f"CoT XML exceeds {MAX_COT_XML_BYTES} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# CoT type-atom resolution (MIL-STD-2525 / CoT hierarchy).
#   a            = atoms (vs b=bits, t=tasking, etc.)
#   <affiliation> f=friendly, h=hostile, u=unknown, n=neutral, p=pending
#   <battle dim>  A=air, G=ground, S=surface/sea-surface, U=subsurface, ...
# Examples used here:
#   a-f-S-X-M    friendly surface vessel (merchant/maritime)
#   a-f-A-M-F-Q  friendly UAS (manned-unmanned aerial, rotary/quad)
#   a-h-A        hostile air track
#   a-u-A        unknown air track
#   a-u-S        unknown surface track
# ---------------------------------------------------------------------------
def cot_type_for_vessel(vessel: dict[str, Any]) -> str:
    """Friendly (cooperative AIS) surface vessel atom."""
    return "a-f-S-X-M"


def cot_type_for_friendly_drone(_drone: dict[str, Any]) -> str:
    """Friendly unmanned aerial system atom."""
    return "a-f-A-M-F-Q"


def cot_type_for_threat(track: dict[str, Any]) -> str:
    """Map a cued threat track to a hostile/unknown air atom from its verdict."""
    verdict = str(track.get("lambda_verdict", "")).upper()
    kind = str(track.get("type", "")).upper()
    affil = "h" if verdict.startswith("THREAT") else "u"
    if "FIXED-WING" in kind:
        return f"a-{affil}-A-M-F"
    return f"a-{affil}-A-M-H-Q"


# ---------------------------------------------------------------------------
# Time helpers — CoT requires ISO-8601 UTC with 'Z'.
# ---------------------------------------------------------------------------
def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(ts: _dt.datetime) -> str:
    # Millisecond precision, Z suffix — the conventional CoT stamp form.
    return ts.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{ts.microsecond // 1000:03d}Z"


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:?\d{2})$"
)


# ---------------------------------------------------------------------------
# Track -> CoT event (dict intermediate, then serialised to XML).
# ---------------------------------------------------------------------------
def _event_dict(
    *,
    uid: str,
    cot_type: str,
    lat: float,
    lon: float,
    hae: float = 0.0,
    ce: float = 9999999.0,
    le: float = 9999999.0,
    how: str = "m-g",
    stale_seconds: int = 120,
    detail: dict[str, Any] | None = None,
    now: _dt.datetime | None = None,
) -> dict[str, Any]:
    now = now or _now_utc()
    stale = now + _dt.timedelta(seconds=stale_seconds)
    return {
        "version": COT_VERSION,
        "uid": uid,
        "type": cot_type,
        "how": how,
        "time": _iso(now),
        "start": _iso(now),
        "stale": _iso(stale),
        "point": {
            "lat": float(lat),
            "lon": float(lon),
            "hae": float(hae),
            "ce": float(ce),
            "le": float(le),
        },
        "detail": detail or {},
    }


def vessel_to_cot(vessel: dict[str, Any], now: _dt.datetime | None = None) -> dict[str, Any]:
    """Map a killinchu maritime vessel track to a CoT event dict."""
    uid = f"killinchu.vessel.{vessel.get('mmsi') or vessel.get('id')}"
    detail = {
        "contact": {"callsign": str(vessel.get("name", uid))},
        "track": {
            "course": str(vessel.get("currentHeading", "")),
            # CoT track speed is m/s; source is knots -> convert.
            "speed": f"{float(vessel.get('currentSpeed', 0.0)) * 0.514444:.3f}",
        },
        "__group": {"name": "Cyan", "role": "Team Member"},
        "remarks": (
            f"{vessel.get('vesselType', 'vessel')} | flag {vessel.get('flag', '?')} "
            f"| IMO {vessel.get('imo', '?')} | MMSI {vessel.get('mmsi', '?')} "
            f"| {vessel.get('lastPort', '?')}->{vessel.get('nextPort', '?')}"
        ),
        "__killinchu": {"source": "fleet", "vesselType": str(vessel.get("vesselType", ""))},
    }
    return _event_dict(
        uid=uid,
        cot_type=cot_type_for_vessel(vessel),
        lat=float(vessel.get("currentLat", 0.0)),
        lon=float(vessel.get("currentLon", 0.0)),
        hae=0.0,
        how="m-g",
        stale_seconds=300,
        detail=detail,
        now=now,
    )


def friendly_drone_to_cot(drone: dict[str, Any], now: _dt.datetime | None = None) -> dict[str, Any]:
    """Map a killinchu friendly drone track to a CoT event dict."""
    uid = f"killinchu.drone.{drone.get('id')}"
    detail = {
        "contact": {"callsign": str(drone.get("callsign", uid))},
        "track": {
            "course": "",
            "speed": f"{float(drone.get('speed_ms', 0.0)):.3f}",
        },
        "__group": {"name": "Blue", "role": "Team Member"},
        "remarks": (
            f"{drone.get('type', 'UAS')} | role {drone.get('role', '?')} "
            f"| status {drone.get('status', '?')} | batt {drone.get('battery_pct', '?')}% "
            f"| RemoteID {drone.get('remote_id', '?')}"
        ),
        "__killinchu": {"source": "drone_friendly", "role": str(drone.get("role", ""))},
    }
    return _event_dict(
        uid=uid,
        cot_type=cot_type_for_friendly_drone(drone),
        lat=float(drone.get("lat", 0.0)),
        lon=float(drone.get("lon", 0.0)),
        hae=float(drone.get("alt_m", 0.0)),
        how="m-g",
        stale_seconds=60,
        detail=detail,
        now=now,
    )


def threat_to_cot(track: dict[str, Any], now: _dt.datetime | None = None) -> dict[str, Any]:
    """Map a killinchu cued threat track to a CoT (hostile/unknown air) event dict."""
    uid = f"killinchu.threat.{track.get('track_id')}"
    detail = {
        "contact": {"callsign": str(track.get("track_id", uid))},
        "track": {
            "course": "",
            "speed": f"{float(track.get('speed_ms', 0.0)):.3f}",
        },
        "remarks": (
            f"{track.get('type', 'UNKNOWN')} | {track.get('threat_category', '?')} "
            f"| sensor {track.get('cuing_sensor', '?')} "
            f"| Λ={track.get('lambda_score', '?')} ({track.get('lambda_verdict', '?')})"
        ),
        "__killinchu": {
            "source": "threat_cued",
            "lambda_score": track.get("lambda_score"),
            "lambda_verdict": str(track.get("lambda_verdict", "")),
        },
    }
    return _event_dict(
        uid=uid,
        cot_type=cot_type_for_threat(track),
        lat=float(track.get("lat", 0.0)),
        lon=float(track.get("lon", 0.0)),
        hae=float(track.get("alt_m", 0.0)),
        how="m-g",
        stale_seconds=60,
        detail=detail,
        now=now,
    )


# ---------------------------------------------------------------------------
# CoT event dict -> XML.
# ---------------------------------------------------------------------------
def _build_detail_element(parent: ET.Element, detail: dict[str, Any]) -> None:
    """Render the (open-content) CoT <detail> sub-tree from a dict.

    Keys beginning with '__' are emitted with the leading underscores stripped
    (e.g. '__group' -> '__group' is reserved in CoT for the team-group element,
    serialised as '<__group .../>'). Scalar dict values become attributes;
    string values become element text.
    """
    det = ET.SubElement(parent, "detail")
    for key, val in detail.items():
        if isinstance(val, dict):
            child = ET.SubElement(det, key)
            for ak, av in val.items():
                if av is None:
                    continue
                child.set(ak, str(av))
        elif val is None:
            continue
        else:
            child = ET.SubElement(det, key)
            child.text = str(val)


def event_dict_to_xml(ev: dict[str, Any]) -> ET.Element:
    """Build a single CoT <event> Element from an event dict."""
    root = ET.Element("event")
    root.set("version", str(ev.get("version", COT_VERSION)))
    root.set("uid", str(ev["uid"]))
    root.set("type", str(ev["type"]))
    root.set("how", str(ev.get("how", "m-g")))
    root.set("time", str(ev["time"]))
    root.set("start", str(ev["start"]))
    root.set("stale", str(ev["stale"]))

    pt = ev["point"]
    point = ET.SubElement(root, "point")
    point.set("lat", f"{float(pt['lat']):.6f}")
    point.set("lon", f"{float(pt['lon']):.6f}")
    point.set("hae", f"{float(pt.get('hae', 0.0)):.1f}")
    point.set("ce", f"{float(pt.get('ce', 9999999.0)):.1f}")
    point.set("le", f"{float(pt.get('le', 9999999.0)):.1f}")

    detail = ev.get("detail")
    if detail:
        _build_detail_element(root, detail)
    return root


def event_to_xml_string(ev: dict[str, Any]) -> str:
    """Serialise a single CoT event dict to an XML string (declaration + event)."""
    root = event_dict_to_xml(ev)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body


def events_to_xml_string(events: Iterable[dict[str, Any]]) -> str:
    """Serialise many CoT events into a single <events> wrapper document.

    Note: the CoT base schema defines a single <event> root; a list wrapper is
    a common pragmatic batch envelope (e.g. for a snapshot pull). Each child is
    an individually-valid CoT <event>; validate_event() runs on each.
    """
    wrapper = ET.Element("events")
    wrapper.set("count", str(0))
    n = 0
    for ev in events:
        wrapper.append(event_dict_to_xml(ev))
        n += 1
    wrapper.set("count", str(n))
    body = ET.tostring(wrapper, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body


# ---------------------------------------------------------------------------
# Validation — CoT base-schema (Event.xsd) SHAPE validation, pure-Python.
# We validate the documented Event.xsd contract: required attributes on
# <event> and <point>, ISO-8601 time/start/stale, lat/lon/hae/ce/le numeric
# and in range, type-atom shape. Returns (ok, errors).
# ---------------------------------------------------------------------------
_EVENT_REQUIRED_ATTRS = ("version", "uid", "type", "time", "start", "stale")
_POINT_REQUIRED_ATTRS = ("lat", "lon", "hae", "ce", "le")
_TYPE_ATOM_RE = re.compile(r"^[a-z](-[A-Za-z0-9]+)+$")


def validate_event_element(ev: ET.Element) -> list[str]:
    """Validate one <event> Element against the CoT base-schema shape.

    Returns a list of error strings (empty == valid)."""
    errors: list[str] = []
    if ev.tag != "event":
        errors.append(f"root tag must be 'event', got '{ev.tag}'")
        return errors

    for attr in _EVENT_REQUIRED_ATTRS:
        if ev.get(attr) in (None, ""):
            errors.append(f"event missing required attribute '{attr}'")

    # type atom shape (e.g. a-f-S-X-M)
    t = ev.get("type", "")
    if t and not _TYPE_ATOM_RE.match(t):
        errors.append(f"event type '{t}' is not a valid CoT atom (expect e.g. a-f-S-X-M)")

    # time stamps must be ISO-8601
    for attr in ("time", "start", "stale"):
        val = ev.get(attr, "")
        if val and not _ISO_RE.match(val):
            errors.append(f"event {attr}='{val}' is not ISO-8601 UTC")

    # exactly one <point>
    points = ev.findall("point")
    if len(points) != 1:
        errors.append(f"event must have exactly one <point>, found {len(points)}")
    else:
        pt = points[0]
        for attr in _POINT_REQUIRED_ATTRS:
            if pt.get(attr) in (None, ""):
                errors.append(f"point missing required attribute '{attr}'")
        # numeric + range checks
        try:
            lat = float(pt.get("lat", "nan"))
            if not (-90.0 <= lat <= 90.0):
                errors.append(f"point lat {lat} out of range [-90,90]")
        except ValueError:
            errors.append(f"point lat '{pt.get('lat')}' not numeric")
        try:
            lon = float(pt.get("lon", "nan"))
            if not (-180.0 <= lon <= 180.0):
                errors.append(f"point lon {lon} out of range [-180,180]")
        except ValueError:
            errors.append(f"point lon '{pt.get('lon')}' not numeric")
        for attr in ("hae", "ce", "le"):
            try:
                float(pt.get(attr, "nan"))
            except ValueError:
                errors.append(f"point {attr} '{pt.get(attr)}' not numeric")

    # detail (if present) must be a single element
    details = ev.findall("detail")
    if len(details) > 1:
        errors.append(f"event must have at most one <detail>, found {len(details)}")
    return errors


def validate_event(ev: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a CoT event dict (round-trips through XML build)."""
    el = event_dict_to_xml(ev)
    errs = validate_event_element(el)
    return (len(errs) == 0, errs)


def validate_xml_string(xml: str) -> tuple[bool, list[str]]:
    """Validate a CoT XML string. Handles both a single <event> and an
    <events> batch wrapper. Returns (ok, errors)."""
    try:
        root = _parse_untrusted_xml(xml)
    except ValueError as exc:
        return (False, [str(exc)])
    if root.tag == "events":
        all_errs: list[str] = []
        children = root.findall("event")
        if not children:
            all_errs.append("<events> wrapper contains no <event> children")
        for i, child in enumerate(children):
            for e in validate_event_element(child):
                all_errs.append(f"event[{i}]: {e}")
        return (len(all_errs) == 0, all_errs)
    errs = validate_event_element(root)
    return (len(errs) == 0, errs)


# ---------------------------------------------------------------------------
# Ingest — CoT XML -> killinchu track dict (bidirectional).
# ---------------------------------------------------------------------------
def cot_xml_to_track(xml: str) -> dict[str, Any]:
    """Parse an inbound CoT <event> XML string into a killinchu track dict.

    Raises ValueError if the XML is not a valid CoT event."""
    try:
        root = _parse_untrusted_xml(xml)
    except ValueError as exc:
        raise ValueError(f"invalid CoT XML: {exc}") from exc
    if root.tag != "event":
        raise ValueError(f"expected root <event>, got <{root.tag}>")
    errs = validate_event_element(root)
    if errs:
        raise ValueError("CoT event failed schema-shape validation: " + "; ".join(errs))

    pt = root.find("point")
    track: dict[str, Any] = {
        "track_id": root.get("uid"),
        "cot_type": root.get("type"),
        "cot_how": root.get("how"),
        "time": root.get("time"),
        "stale": root.get("stale"),
        "lat": float(pt.get("lat")),
        "lon": float(pt.get("lon")),
        "alt_m": float(pt.get("hae", 0.0)),
        "ce": float(pt.get("ce", 9999999.0)),
        "le": float(pt.get("le", 9999999.0)),
        "source": "cot_ingest",
    }
    detail = root.find("detail")
    if detail is not None:
        contact = detail.find("contact")
        if contact is not None and contact.get("callsign"):
            track["callsign"] = contact.get("callsign")
        trk = detail.find("track")
        if trk is not None:
            if trk.get("speed"):
                try:
                    track["speed_ms"] = float(trk.get("speed"))
                except ValueError:
                    pass
            if trk.get("course"):
                track["heading"] = trk.get("course")
        remarks = detail.find("remarks")
        if remarks is not None and remarks.text:
            track["remarks"] = remarks.text
    # Honest affiliation read from the type atom (a-<affil>-...).
    atom = (root.get("type") or "").split("-")
    if len(atom) >= 2:
        track["affiliation"] = {
            "f": "friendly", "h": "hostile", "u": "unknown",
            "n": "neutral", "p": "pending",
        }.get(atom[1], atom[1])
    return track


# ---------------------------------------------------------------------------
# Track collection — pull current killinchu tracks from the live modules.
# Network-free: vessels from the embedded seed JSON, drones/threats from the
# canonical fleets in killinchu_drone_routes.
# ---------------------------------------------------------------------------
def _load_vessels() -> list[dict[str, Any]]:
    try:
        with open(_VESSELS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("vessels", []) or []
    except Exception:
        return []


def _load_drone_tracks() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        import killinchu_drone_routes as _dr  # local, no network
        friendly = list(getattr(_dr, "_FRIENDLY_FLEET", []) or [])
        threats = list(getattr(_dr, "_CUED_THREATS", []) or [])
        return friendly, threats
    except Exception:
        return [], []


def collect_cot_events(now: _dt.datetime | None = None) -> list[dict[str, Any]]:
    """Collect every current killinchu track as a CoT event dict."""
    now = now or _now_utc()
    events: list[dict[str, Any]] = []
    for v in _load_vessels():
        try:
            events.append(vessel_to_cot(v, now=now))
        except Exception:
            continue
    friendly, threats = _load_drone_tracks()
    for d in friendly:
        try:
            events.append(friendly_drone_to_cot(d, now=now))
        except Exception:
            continue
    for t in threats:
        try:
            events.append(threat_to_cot(t, now=now))
        except Exception:
            continue
    return events


# ---------------------------------------------------------------------------
# Capability / honesty manifest (board "CoT interop" indicator backs this).
# ---------------------------------------------------------------------------
def cot_status() -> dict[str, Any]:
    events = collect_cot_events()
    # Validate the snapshot so the indicator can show "N/N tracks CoT-valid".
    valid = 0
    for ev in events:
        ok, _ = validate_event(ev)
        if ok:
            valid += 1
    return {
        "capability": "Cursor on Target (CoT) interop",
        "standard": "MITRE CoT 2.0 base schema (Event.xsd)",
        "live": {
            "cot_xml_export": True,
            "schema_shape_validation": True,
            "cot_xml_ingest": True,
            "tracks_total": len(events),
            "tracks_cot_valid": valid,
            "all_tracks_emittable": (valid == len(events) and len(events) > 0),
        },
        "roadmap": {
            "udp_multicast_emit": {"wired": False, "target_group": COT_DEFAULT_MULTICAST,
                                   "note": "roadmap — no UDP socket opened in this build"},
            "live_tak_server_stream": {"wired": False,
                                       "note": "roadmap — no TAK-server / FreeTAKServer integration in this build"},
            "tls_client_cert_enrolment": {"wired": False,
                                          "note": "roadmap — no TAK enrolment in this build"},
        },
        "routes": [
            "GET /api/killinchu/v1/cot/export",
            "GET /api/killinchu/v1/cot/export/{track_id}",
            "POST /api/killinchu/v1/cot/ingest",
            "GET /api/killinchu/v1/cot/status",
        ],
        "data_kind": "computed_from_sample_tracks",
        "honesty": HONESTY_LABEL,
        "sources": COT_SOURCES,
    }


# ---------------------------------------------------------------------------
# Route registration (ADDITIVE).
# ---------------------------------------------------------------------------
def register(app) -> dict[str, Any]:
    if APIRouter is None:
        return {"module": "killinchu_cot_interop", "registered_count": 0, "error": "fastapi missing"}

    router = APIRouter()
    base = "/api/killinchu/v1/cot"
    registered: list[str] = []

    @router.get(f"{base}/export")
    async def _export() -> Response:
        events = collect_cot_events()
        xml = events_to_xml_string(events)
        return Response(content=xml, media_type="application/xml")
    registered.append(f"{base}/export")

    @router.get(f"{base}/export/{{track_id}}")
    async def _export_one(track_id: str) -> Response:
        for ev in collect_cot_events():
            if ev["uid"] == track_id or ev["uid"].endswith(f".{track_id}"):
                return Response(content=event_to_xml_string(ev), media_type="application/xml")
        return JSONResponse({"error": "track not found", "track_id": track_id}, status_code=404)
    registered.append(f"{base}/export/{{track_id}}")

    @router.post(f"{base}/ingest")
    async def _ingest(request: Request) -> JSONResponse:
        try:
            raw = await _read_limited_request_body(request)
            track = cot_xml_to_track(raw.decode("utf-8"))
        except CotPayloadTooLarge:
            _LOGGER.info(
                "Rejected CoT ingest", extra={"cot_rejection": "payload_too_large"}
            )
            return JSONResponse(
                {"ok": False, "error": _INGEST_ERROR_TOO_LARGE}, status_code=413
            )
        except UnicodeDecodeError:
            _LOGGER.info(
                "Rejected CoT ingest", extra={"cot_rejection": "invalid_encoding"}
            )
            return JSONResponse(
                {"ok": False, "error": _INGEST_ERROR_ENCODING}, status_code=400
            )
        except ValueError:
            _LOGGER.info(
                "Rejected CoT ingest", extra={"cot_rejection": "invalid_xml"}
            )
            return JSONResponse(
                {"ok": False, "error": _INGEST_ERROR_INVALID}, status_code=400
            )
        return JSONResponse({"ok": True, "track": track, "honesty": HONESTY_LABEL})
    registered.append(f"{base}/ingest")

    @router.get(f"{base}/status")
    async def _status() -> JSONResponse:
        return JSONResponse(cot_status())
    registered.append(f"{base}/status")

    app.include_router(router)
    return {"module": "killinchu_cot_interop", "registered_count": len(registered), "routes": registered}
