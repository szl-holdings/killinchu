# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# Real edge test: feed a REAL OTLP telemetry fixture, assert Λ ∈ [0,1] and that
# the DSSE signature verifies + the Khipu chain stays intact.  NO MOCKS.
import json
import os

from src.killinchu.edge import EdgeNode, Telemetry
from src.killinchu.dsse import verify_envelope, public_key_pem
from src.killinchu.lambda_calc import (
    compute_lambda, lambda_aggregate, pac_bayes_penalty, kl_inverse_upper,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "telemetry_otlp_sample.json")


def _otlp_attrs(record):
    out = {}
    for kv in record["attributes"]:
        v = kv["value"]
        out[kv["key"]] = next(iter(v.values()))
    return out


def _load_fixture_frames():
    data = json.load(open(FIXTURE, encoding="utf-8"))
    frames = []
    for rl in data["resourceLogs"]:
        for sl in rl["scopeLogs"]:
            for rec in sl["logRecords"]:
                frames.append(Telemetry.from_otlp_attributes(_otlp_attrs(rec)))
    return frames


def test_lambda_in_unit_interval_from_real_telemetry():
    node = EdgeNode()
    frames = _load_fixture_frames()
    assert len(frames) == 2
    for frame in frames:
        result = node.evaluate(frame)
        lam = result["verdict"]["lambda_value"]
        assert 0.0 <= lam <= 1.0, f"Λ out of [0,1]: {lam}"
        assert result["verdict"]["decision"] in {"ALLOW", "REVIEW", "DENY"}


def test_signature_verifies_real_ecdsa():
    node = EdgeNode()
    frame = _load_fixture_frames()[0]
    result = node.evaluate(frame)
    env = result["dsse"]
    assert env["signed"] is True
    assert env["signatures"], "no signature emitted"
    v = verify_envelope(env, pub_pem=public_key_pem())
    assert v["verified"] is True, f"DSSE signature failed to verify: {v}"


def test_clean_frame_is_not_denied():
    """The authenticated, no-breach OpenDroneID frame (moderate -58 dBm link,
    n=1024) must clear DENY into the REVIEW/ALLOW band — honest reflection of a
    decent-but-not-perfect signal."""
    node = EdgeNode()
    clean = _load_fixture_frames()[0]
    result = node.evaluate(clean)
    assert result["verdict"]["decision"] in {"REVIEW", "ALLOW"}
    assert result["verdict"]["lambda_value"] >= 0.70


def test_allow_is_reachable_with_strong_signal():
    """A strong-link (-45 dBm), authenticated, no-breach frame fused over a real
    window must reach ALLOW — proving the full ALLOW/REVIEW/DENY spectrum is
    reachable from real input, not hard-coded."""
    node = EdgeNode()
    strong = Telemetry(
        source="OpenDroneID", track_id="ODID-STRONG", lat=-13.1, lon=-72.5,
        alt_m=100.0, speed_mps=10.0, rssi_dbm=-45.0, id_authenticated=True,
        geofence_violation=False, timestamp_skew_s=0.1, n_observations=1024)
    result = node.evaluate(strong)
    assert result["verdict"]["decision"] == "ALLOW"
    assert result["verdict"]["lambda_value"] >= 0.90


def test_single_frame_is_honestly_uncertain():
    """A single raw broadcast (n=1) must NOT ALLOW even when clean: one frame
    carries too little statistical evidence. Honesty over checklist."""
    node = EdgeNode()
    clean = _load_fixture_frames()[0]
    clean.n_observations = 1
    result = node.evaluate(clean)
    assert result["verdict"]["decision"] != "ALLOW"


def test_geofence_violation_drives_low_lambda():
    """The ADS-B frame has a geofence violation → containment axis ~0.10 →
    geometric mean must pull Λ well below the ALLOW floor."""
    node = EdgeNode()
    frames = _load_fixture_frames()
    breach = frames[1]  # ADS-B, geofence_violation=True, unauthenticated
    result = node.evaluate(breach)
    assert result["verdict"]["decision"] != "ALLOW"
    assert result["verdict"]["lambda_value"] < 0.70


def test_khipu_chain_intact_after_loop():
    node = EdgeNode()
    node.run_loop(_load_fixture_frames())
    chk = node.khipu.verify_chain()
    assert chk["intact"] is True
    assert chk["length"] == 2
    assert chk["root"] == node.khipu.root


def test_pac_bayes_penalty_decreases_with_n():
    p_small = pac_bayes_penalty(n=1, kl_qp=0.5)
    p_large = pac_bayes_penalty(n=10_000, kl_qp=0.5)
    assert p_large < p_small  # more observations => tighter bound


def test_lambda_aggregate_geometric_zero_collapse():
    # one zero axis collapses the geometric mean to 0 (hard-fail semantics)
    assert lambda_aggregate([0.0, 0.99, 0.99]) == 0.0
    # homogeneity sanity: scaling within bounds is monotone
    assert lambda_aggregate([0.9, 0.9]) > lambda_aggregate([0.8, 0.9])


def test_kl_inverse_monotone():
    # larger bound => larger (looser) upper risk
    assert kl_inverse_upper(0.1, 0.5) >= kl_inverse_upper(0.1, 0.1)
