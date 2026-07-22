# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_ais_aug2024.py — REAL, committed guard for the NOAA/MarineCadastre AIS
# (Aug 2024 coastal US, WarHacker dataset) selectable governed source. NO MOCKS.
#
# Proves:
#   * the committed sample is REAL NOAA AIS rows in the REAL schema (verbatim header)
#   * the connector normalizes rows into killinchu's vessel/track shape
#   * the dataset is honestly labelled a SAMPLE — never "the full month"
#   * the live feed remains the DEFAULT selectable source
#   * the governed Λ risk board scores real rows and (when signed) carries a receipt
#   * register() is additive — adds exactly its routes, clobbers nothing
from __future__ import annotations

import csv
import os

from szl_connectors.data_sources import ais_noaa_aug2024 as noaa
import killinchu_ais_aug2024 as m


REAL_HEADER = [
    "MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName",
    "IMO", "CallSign", "VesselType", "Status", "Length", "Width", "Draft",
    "Cargo", "TransceiverClass",
]


def test_sample_csv_is_real_noaa_schema():
    assert os.path.exists(noaa.SAMPLE_CSV), "committed real-row sample CSV missing"
    with open(noaa.SAMPLE_CSV, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    assert header == REAL_HEADER, f"sample header is not the real NOAA schema: {header}"
    assert len(rows) >= 50, "sample should carry a meaningful number of real rows"
    # Real Aug-1-2024 timestamps (the day the sample was cut from).
    for r in rows[:20]:
        assert r[1].startswith("2024-08-01"), f"unexpected BaseDateTime {r[1]!r}"


def test_normalize_maps_to_vessel_shape():
    row = {
        "MMSI": "367597470", "BaseDateTime": "2024-08-01T00:00:00",
        "LAT": "38.94872", "LON": "-74.90901", "SOG": "0.0", "COG": "295.7",
        "Heading": "511.0", "VesselName": "BULLDOG SALLY", "IMO": "",
        "CallSign": "WDJ2058", "VesselType": "30", "Status": "0",
        "Length": "17", "Width": "7", "Draft": "0.0", "Cargo": "30",
        "TransceiverClass": "A",
    }
    v = noaa.normalize_row(row)
    assert v["mmsi"] == "367597470"
    assert v["name"] == "BULLDOG SALLY"
    assert v["currentLat"] == 38.94872 and v["currentLon"] == -74.90901
    assert v["currentSpeed"] == 0.0
    # Heading 511 = "not available" in AIS -> must NOT be fabricated; fall back to COG.
    assert v["currentHeading"] == 295.7
    # NOAA AIS has no flag field -> honest None, never fabricated.
    assert v["flag"] is None
    assert v["vesselType"] == "fishing"
    assert v["status"] == "under_way_engine"


def test_connector_default_is_labelled_sample():
    rec = noaa.NoaaAisAug2024Connector().read()
    assert rec.state.value == "sample", "default path must serve the labelled SAMPLE"
    assert rec.live is False
    assert "(sample)" in rec.source.lower()
    assert "not the full month" in rec.source.lower()
    assert len(rec.records) >= 50


def test_no_overclaim_full_month():
    # Doctrine v11: never label a sample as the full month.
    label = noaa.PROVENANCE_SAMPLE.lower()
    assert "sample" in label
    assert "not the full month" in label


def test_live_feed_is_default_source():
    sm = m.sources_manifest("killinchu")
    assert sm["default"] == "live"
    ids = [s["id"] for s in sm["sources"]]
    assert "live" in ids and "noaa_ais_aug2024" in ids
    live = next(s for s in sm["sources"] if s["id"] == "live")
    assert live["live"] is True and live["is_sample"] is False
    noaa_src = next(s for s in sm["sources"] if s["id"] == "noaa_ais_aug2024")
    assert noaa_src["is_sample"] is True


def test_risk_board_scores_real_rows():
    rb = m.risk_board(limit=10, sign=False)
    assert rb["count"] >= 1
    assert rb["is_sample"] is True
    for row in rb["board"]:
        assert 0.0 <= row["risk_score"] <= 1.0
        assert row["traffic_light"] in {"GREEN", "AMBER", "RED"}
    # sorted by risk descending
    scores = [r["risk_score"] for r in rb["board"]]
    assert scores == sorted(scores, reverse=True)


def test_risk_board_signed_carries_receipt():
    rb = m.risk_board(limit=2, sign=True)
    assert rb["signed"] is True
    for row in rb["board"]:
        assert "receipt" in row
        assert "receipt_digest_sha256" in row["receipt"]


def test_register_is_additive():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()

    @app.get("/api/killinchu/v1/live/ais")
    async def _pre_existing():  # the live feed must NOT be clobbered
        return {"ok": True, "live": True}

    info = m.register(app, ns="killinchu")
    assert info["registered_count"] == 6
    expected = {
        "/api/killinchu/v1/ais/sources",
        "/api/killinchu/v1/ais/aug2024/tracks",
        "/api/killinchu/v1/ais/aug2024/risk-board",
        "/api/killinchu/v1/ais/tracks",
        "/api/killinchu/v1/overlays/pirate",
        "/api/killinchu/v1/overlays/wpi",
    }
    assert {r.removeprefix("GET ") for r in info["routes"]} == expected

    # Exercise the actual ASGI router. Recent FastAPI releases may represent an
    # included router as a lazy wrapper with no public path, so app.routes
    # inspection is not sufficient proof that the endpoints are reachable.
    client = TestClient(app)
    for path in sorted(expected):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code, response.text)

    # The pre-existing live feed still answers and is not clobbered.
    assert client.get("/api/killinchu/v1/live/ais").json() == {"ok": True, "live": True}


if __name__ == "__main__":
    test_sample_csv_is_real_noaa_schema()
    test_normalize_maps_to_vessel_shape()
    test_connector_default_is_labelled_sample()
    test_no_overclaim_full_month()
    test_live_feed_is_default_source()
    test_risk_board_scores_real_rows()
    test_risk_board_signed_carries_receipt()
    test_register_is_additive()
    print("OK — all NOAA AIS Aug-2024 self-tests passed")
