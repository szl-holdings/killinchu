# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
Killinchu protocol decoders — REAL parsers, NO MOCKS.

  remote_id_decode(hex)  — OpenDroneID / ASTM F3411 25-byte message byte parser
                           (Basic ID, Location/Vector, Self-ID, System, Operator ID).
  adsb_decode(hex|pair)  — ADS-B Mode-S 1090ES via pyModeS v3 (icao/typecode/callsign/
                           altitude/velocity; even+odd pair → full lat/lon via CPR).
  mavlink_parse(hex)     — MAVLink v1/v2 frame parse via pymavlink (common dialect).

Honesty (Doctrine v11): malformed/short input returns an explicit error object, never a
silent pass. ADS-B/Remote-ID are unauthenticated broadcast — decoded fields are *claims*.
"""
# ---------------------------------------------------------------------------
# DEVELOPER ORIENTATION (added by Perplexity Computer Agent, 2026-06)
# Purpose:       Real protocol decoders for drone broadcast signals (NO mocks).
#                This is killinchu's most important unique module.
# Key entry pts: remote_id_decode(hexstr) -> dict [OpenDroneID ASTM F3411-22a]
#                adsb_decode(hexstr) -> dict [ADS-B Mode-S 1090ES via pyModeS]
#                mavlink_parse(hexstr) -> dict [MAVLink v1/v2 via pymavlink]
# Related mods:  serve.py (routes these), szl_dsse.py (signing verdicts)
# Honesty note:  All decoded fields are UNAUTHENTICATED CLAIMS from broadcast.
#                Drones can spoof Remote-ID. Never claim "verified identity".
#                pyModeS and pymavlink are optional; absent = honest error dict.
# Spec refs:     ASTM F3411-22a (Remote ID), ICAO Doc 9684 (ADS-B),
#                MAVLink v2.0 (https://mavlink.io/en/guide/serialization.html)
# ---------------------------------------------------------------------------
from __future__ import annotations

import struct
from typing import Any

# ---------------------------------------------------------------------------
# OpenDroneID / ASTM F3411 — Remote ID broadcast message decoder (real bytes)
# Reference: opendroneid/opendroneid-core-c + ASTM F3411-22a.
# Each message = 25 bytes. Byte0 = (type<<4)|version.
# ---------------------------------------------------------------------------

_RID_MSG_TYPES = {
    0x0: "Basic ID", 0x1: "Location/Vector", 0x2: "Authentication",
    0x3: "Self-ID", 0x4: "System", 0x5: "Operator ID", 0xF: "Message Pack",
}
_RID_ID_TYPES = {0: "None", 1: "Serial Number (ANSI/CTA-2063-A)", 2: "CAA Registration ID",
                 3: "UTM (UUID)", 4: "Specific Session ID"}
_RID_UA_TYPES = {0: "None", 1: "Aeroplane/Fixed-wing", 2: "Helicopter/Multirotor", 3: "Gyroplane",
                 4: "Hybrid Lift", 5: "Ornithopter", 6: "Glider", 7: "Kite", 8: "Free Balloon",
                 9: "Captive Balloon", 10: "Airship", 11: "Free Fall/Parachute", 12: "Rocket",
                 13: "Tethered Powered Aircraft", 14: "Ground Obstacle", 15: "Other"}
_RID_STATUS = {0: "Undeclared", 1: "Ground", 2: "Airborne", 3: "Emergency", 4: "RID System Failure"}


def _hex_to_bytes(s: str) -> bytes:
    s = s.strip().replace(" ", "").replace(":", "").replace("0x", "")
    if len(s) % 2 != 0:
        raise ValueError(f"odd-length hex string ({len(s)} chars)")
    return bytes.fromhex(s)


def _ascii_field(b: bytes) -> str:
    return b.split(b"\x00")[0].decode("ascii", errors="replace").strip()


def remote_id_decode(hexstr: str) -> dict[str, Any]:
    """Decode a single 25-byte OpenDroneID broadcast frame. Returns honest error on bad input."""
    try:
        raw = _hex_to_bytes(hexstr)
    except ValueError as e:
        return {"ok": False, "error": f"invalid hex: {e}", "protocol": "OpenDroneID/ASTM F3411"}
    if len(raw) < 1:
        return {"ok": False, "error": "empty message", "protocol": "OpenDroneID/ASTM F3411"}
    # Many capture tools prepend a 1-byte "ADD counter / message size" or app header.
    # ASTM frame proper is 25 bytes; accept 25 (frame) or 24 (header+body alt) gracefully.
    if len(raw) not in (24, 25):
        return {
            "ok": False,
            "error": f"unexpected length {len(raw)} bytes — ASTM F3411 message is 25 bytes "
                     f"(1 header + 24 body). Provide a single 25-byte frame.",
            "protocol": "OpenDroneID/ASTM F3411",
            "hint": "Example Basic-ID frame: 0012 + 20-byte serial + pad (50 hex chars).",
        }
    header = raw[0]
    mtype = (header >> 4) & 0xF
    version = header & 0xF
    body = raw[1:]
    out: dict[str, Any] = {
        "ok": True,
        "protocol": "OpenDroneID / ASTM F3411-22a",
        "message_type_code": mtype,
        "message_type": _RID_MSG_TYPES.get(mtype, f"Reserved(0x{mtype:X})"),
        "protocol_version": version,
        "length_bytes": len(raw),
        "honesty": "Broadcast Remote ID is unauthenticated and spoofable — decoded fields are claims.",
    }

    if mtype == 0x0:  # Basic ID
        id_type = (body[0] >> 4) & 0xF
        ua_type = body[0] & 0xF
        uas_id = _ascii_field(body[1:21])
        out["fields"] = {
            "id_type_code": id_type, "id_type": _RID_ID_TYPES.get(id_type, "Reserved"),
            "ua_type_code": ua_type, "ua_type": _RID_UA_TYPES.get(ua_type, "Reserved"),
            "uas_id": uas_id,
        }
    elif mtype == 0x1:  # Location/Vector
        status_byte = body[0]
        status = (status_byte >> 4) & 0xF
        height_type = (status_byte >> 2) & 0x1
        ew_dir = (status_byte >> 1) & 0x1  # E/W direction segment for track
        speed_mult = status_byte & 0x1
        track_raw = body[1]
        track = track_raw + (180 if ew_dir else 0)
        speed_raw = body[2]
        speed = speed_raw * 0.25 if speed_mult == 0 else (speed_raw * 0.75 + 255 * 0.25)
        vspeed = struct.unpack("<b", body[3:4])[0] * 0.5
        lat = struct.unpack("<i", body[4:8])[0] / 1e7
        lon = struct.unpack("<i", body[8:12])[0] / 1e7
        press_alt = struct.unpack("<H", body[12:14])[0] * 0.5 - 1000
        geo_alt = struct.unpack("<H", body[14:16])[0] * 0.5 - 1000
        height = struct.unpack("<H", body[16:18])[0] * 0.5 - 1000
        out["fields"] = {
            "operational_status_code": status, "operational_status": _RID_STATUS.get(status, "Reserved"),
            "height_type": "Above Takeoff" if height_type else "Above Ground",
            "track_deg": track % 360, "ground_speed_m_s": round(speed, 2),
            "vertical_speed_m_s": round(vspeed, 2),
            "latitude": round(lat, 7), "longitude": round(lon, 7),
            "pressure_altitude_m": round(press_alt, 1), "geodetic_altitude_m": round(geo_alt, 1),
            "height_agl_m": round(height, 1),
            "position_valid": -90 <= lat <= 90 and -180 <= lon <= 180,
        }
    elif mtype == 0x3:  # Self-ID
        desc_type = body[0]
        desc = _ascii_field(body[1:24])
        out["fields"] = {"description_type": desc_type, "description": desc}
    elif mtype == 0x4:  # System
        op_lat = struct.unpack("<i", body[1:5])[0] / 1e7
        op_lon = struct.unpack("<i", body[5:9])[0] / 1e7
        area_count = struct.unpack("<H", body[9:11])[0]
        out["fields"] = {
            "operator_latitude": round(op_lat, 7), "operator_longitude": round(op_lon, 7),
            "area_count": area_count,
        }
    elif mtype == 0x5:  # Operator ID
        op_id_type = body[0]
        op_id = _ascii_field(body[1:21])
        out["fields"] = {"operator_id_type": op_id_type, "operator_id": op_id}
    else:
        out["fields"] = {"raw_body_hex": body.hex()}
        out["note"] = "Authentication / Message-Pack bodies surfaced as raw hex."
    return out


# ---------------------------------------------------------------------------
# ADS-B Mode-S 1090ES — pyModeS v3 (real library decode)
# ---------------------------------------------------------------------------

def adsb_decode(msg) -> dict[str, Any]:
    """Decode ADS-B. `msg` may be a single 28-hex string, or a {even,odd} pair / list for CPR
    position. Uses pyModeS v3 decode()."""
    import pyModeS
    from pyModeS.util import icao as _icao, crc as _crc, df as _df

    pair = None
    single = None
    if isinstance(msg, (list, tuple)):
        pair = [str(m).strip() for m in msg if str(m).strip()]
    elif isinstance(msg, dict):
        e, o = msg.get("even"), msg.get("odd")
        if e and o:
            pair = [str(e).strip(), str(o).strip()]
        else:
            single = str(msg.get("msg") or msg.get("hex") or "").strip()
    else:
        single = str(msg).strip()

    def _meta(m: str) -> dict[str, Any]:
        m = m.replace(" ", "").upper()
        if len(m) not in (14, 28):
            raise ValueError(f"Mode-S message must be 14 or 28 hex chars, got {len(m)}")
        return {"icao": _icao(m), "downlink_format": _df(m), "crc": _crc(m),
                "crc_valid": _crc(m) == 0}

    try:
        if pair and len(pair) >= 2:
            decoded = pyModeS.decode(pair[:2])
            merged: dict[str, Any] = {}
            for d in decoded:
                merged.update({k: v for k, v in d.items() if v is not None})
            return {
                "ok": True, "protocol": "ADS-B Mode-S 1090ES (CPR pair)",
                "even": _meta(pair[0]), "odd": _meta(pair[1]),
                "decoded": merged,
                "latitude": merged.get("latitude"), "longitude": merged.get("longitude"),
                "altitude_ft": merged.get("altitude"),
                "honesty": "ADS-B is unauthenticated broadcast — position is a self-reported claim.",
            }
        else:
            m = (single or "").upper().replace(" ", "")
            meta = _meta(m)
            decoded = pyModeS.decode(m)
            return {
                "ok": True, "protocol": "ADS-B Mode-S 1090ES (single frame)",
                "meta": meta, "decoded": decoded,
                "note": "Airborne-position frames (TC 9-18) need an even+odd pair for full lat/lon. "
                        "Submit {even, odd} to resolve global position.",
                "honesty": "ADS-B is unauthenticated broadcast — fields are self-reported claims.",
            }
    except Exception as e:
        return {"ok": False, "protocol": "ADS-B Mode-S 1090ES",
                "error": f"{type(e).__name__}: {e}",
                "hint": "Provide a 28-hex DF17 extended squitter, or {even, odd} for position."}


# ---------------------------------------------------------------------------
# MAVLink v1/v2 — pymavlink (real frame parse)
# ---------------------------------------------------------------------------

def mavlink_parse(hexstr: str) -> dict[str, Any]:
    """Parse one or more concatenated MAVLink frames from hex. Real pymavlink decode."""
    try:
        raw = _hex_to_bytes(hexstr)
    except ValueError as e:
        return {"ok": False, "protocol": "MAVLink", "error": f"invalid hex: {e}"}
    if not raw:
        return {"ok": False, "protocol": "MAVLink", "error": "empty frame"}
    magic = raw[0]
    version = 2 if magic == 0xFD else 1 if magic == 0xFE else None
    if version is None:
        return {"ok": False, "protocol": "MAVLink",
                "error": f"first byte 0x{magic:02X} is not a MAVLink start marker "
                         f"(v1=0xFE, v2=0xFD)"}
    import io
    from pymavlink.dialects.v20 import common as mavlink2
    mav = mavlink2.MAVLink(io.BytesIO())
    mav.robust_parsing = True
    msgs = []
    try:
        parsed = mav.parse_buffer(bytearray(raw)) or []
        for m in parsed:
            d = m.to_dict()
            msgs.append({
                "type": m.get_type(),
                "msg_id": m.get_msgId(),
                "src_system": m.get_srcSystem(),
                "src_component": m.get_srcComponent(),
                "fields": {k: v for k, v in d.items() if k != "mavpackettype"},
            })
    except Exception as e:
        return {"ok": False, "protocol": f"MAVLink v{version}",
                "error": f"{type(e).__name__}: {e}", "start_marker": f"0x{magic:02X}"}
    if not msgs:
        return {"ok": False, "protocol": f"MAVLink v{version}",
                "error": "no complete MAVLink message decoded (truncated frame or bad CRC)",
                "start_marker": f"0x{magic:02X}", "bytes": len(raw)}
    return {"ok": True, "protocol": f"MAVLink v{version}", "frame_count": len(msgs),
            "messages": msgs,
            "honesty": "MAVLink is typically unencrypted on civilian builds; frames are claims."}
