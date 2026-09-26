"""mavlink_parse must never report a CRC-rejected frame as a decoded message.

pymavlink's robust_parsing turns a CRC or framing failure into a BAD_DATA
pseudo-message. Before this contract the parser counted it as a frame and
answered ok: true for a corrupted input.
"""
import io
import json

import pytest

mavlink2 = pytest.importorskip("pymavlink.dialects.v20.common")
mavlink1 = pytest.importorskip("pymavlink.dialects.v10.common")

import killinchu_protocols as kp  # noqa: E402


def _heartbeat(wire_version="2.0"):
    dialect = mavlink2 if wire_version == "2.0" else mavlink1
    enc = dialect.MAVLink(io.BytesIO(), srcSystem=1, srcComponent=1)
    frame = bytes(enc.heartbeat_encode(2, 3, 0, 0, 4).pack(enc))
    assert frame[0] == (0xFD if wire_version == "2.0" else 0xFE)
    return frame


def _corrupt_crc(frame, index=-1):
    bad = bytearray(frame)
    bad[index] ^= 0xFF
    return bytes(bad)


def _types(result):
    return [m["type"] for m in result.get("messages", [])]


@pytest.mark.parametrize("wire_version,protocol", [("2.0", "MAVLink v2"), ("1.0", "MAVLink v1")])
def test_valid_frame_decodes_ok(wire_version, protocol):
    result = kp.mavlink_parse(_heartbeat(wire_version).hex())
    assert result["ok"] is True
    assert result["protocol"] == protocol
    assert result["frame_count"] == 1
    assert _types(result) == ["HEARTBEAT"]
    assert "rejected" not in result
    json.dumps(result)


@pytest.mark.parametrize("wire_version,marker", [("2.0", "0xFD"), ("1.0", "0xFE")])
def test_bad_crc_frame_is_rejected_not_decoded(wire_version, marker):
    result = kp.mavlink_parse(_corrupt_crc(_heartbeat(wire_version)).hex())
    assert result["ok"] is False
    assert result["start_marker"] == marker
    assert result["frame_count"] == 0
    assert result["messages"] == []
    assert result["rejected_count"] == 1
    assert "CRC" in result["rejected"][0]["reason"]
    assert "rejected" in result["error"]
    json.dumps(result)


def test_mixed_input_fails_closed_but_keeps_verified_frames():
    frame = _heartbeat()
    result = kp.mavlink_parse((frame + _corrupt_crc(frame)).hex())
    assert result["ok"] is False
    assert result["frame_count"] == 1
    assert _types(result) == ["HEARTBEAT"]
    assert result["rejected_count"] == 1


def test_trailing_garbage_is_rejected():
    result = kp.mavlink_parse(_heartbeat().hex() + "0011")
    assert result["ok"] is False
    assert _types(result) == ["HEARTBEAT"]
    assert result["rejected_count"] == 1


def test_bad_data_never_appears_as_a_message():
    frame = _heartbeat()
    inputs = [
        _corrupt_crc(frame),
        _corrupt_crc(_heartbeat("1.0")),
        frame + _corrupt_crc(frame),
        frame + b"\x00\x11",
    ]
    for raw in inputs:
        assert "BAD_DATA" not in _types(kp.mavlink_parse(raw.hex()))
