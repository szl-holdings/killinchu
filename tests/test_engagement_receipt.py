# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# T104 — proof-carrying engagement receipt: a REAL killinchu counter-UAS
# decision output (the edge verdict over caller-submitted telemetry) is emitted
# as a single signed szl-receipt. These tests prove the receipt:
#   * binds the RIGHT input + output digests + governing policy id;
#   * is cryptographically verifiable, and tamper is detected;
#   * reports energy as the honest UNAVAILABLE sentinel (never fabricated);
#   * is byte-identical whether produced by the installed szl-receipt lib or
#     the vendored byte-identical fallback;
#   * NEVER overclaims: an UNSIGNED-honest receipt never reports a fake pass.
#
# NO MOCKS: real ECDSA-P256 DSSE signatures over real canonical JSON.
import base64
import copy
import hashlib
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, "/app"):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import killinchu_edge_formulas as ef
import killinchu_engagement_receipt as er


# A real, deterministic telemetry frame: 4 sensors agree @100.0, 1 spoofed
# @150.0 (byzantine), plus a noisy-but-consistent track. This is exactly the
# shape killinchu_edge_formulas.edge_verdict consumes.
def _telemetry():
    return {
        "sensors": {"s0": 100.0, "s1": 100.0, "s2": 100.0, "s3": 100.0,
                    "s4": 150.0},
        "track": [100.0, 100.5, 99.8, 100.2, 100.1, 99.9, 100.3, 100.0],
        "lambda_floor": 0.5,
        "f": 1,
    }


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha(obj):
    return hashlib.sha256(_canon(obj)).hexdigest()


def test_receipt_binds_input_and_output_digests():
    tel = _telemetry()
    verdict = ef.edge_verdict(tel)
    priv, _pub = er._SR.generate_keypair()
    bundle = er.emit_engagement_receipt(
        tel, policy_id="killinchu-cuas/test-policy", private_key_pem=priv,
        verdict=verdict, ts="2026-01-01T00:00:00+00:00")

    # The bound input digest is exactly sha256 over the canonical telemetry.
    assert bundle["input_digest"] == _sha(tel)
    # The bound output digest is exactly sha256 over the STABLE decision output.
    expected_out = _sha(er.decision_output(verdict))
    assert bundle["output_digest"] == expected_out

    # Those digests are physically present inside the signed receipt body.
    body = json.loads(base64.b64decode(bundle["receipt"]["payload"]))
    assert body["input_digest"] == bundle["input_digest"]
    assert body["output_digest"] == bundle["output_digest"]
    assert body["governing_policy_id"] == "killinchu-cuas/test-policy"
    assert body["decision"] == verdict["decision"]

    # The in-toto statement's subject is the receipt digest (the binding anchor).
    subj = bundle["statement"]["subject"][0]["digest"]["sha256"]
    assert subj == bundle["subject_digest"] == bundle["receipt"]["digest"]


def test_receipt_is_signed_and_verifies_and_tamper_is_detected():
    tel = _telemetry()
    priv, pub = er._SR.generate_keypair()
    bundle = er.emit_engagement_receipt(tel, private_key_pem=priv,
                                        ts="2026-01-01T00:00:00+00:00")

    assert bundle["receipt"]["signed"] is True
    res = er.verify_engagement_receipt(bundle, public_key_pem=pub, telemetry=tel)
    assert res["verified"] is True
    assert res["statement_binds_receipt"] is True
    assert res["signature_verified"] is True
    assert res["digests_match"] is True
    assert res["energy_honest_unavailable"] is True

    # Tamper: flip the recorded decision inside the signed payload → the real
    # ECDSA signature must FAIL (crypto binds the exact payload bytes).
    tampered = copy.deepcopy(bundle)
    env = tampered["receipt"]
    body = json.loads(base64.b64decode(env["payload"]))
    body["decision"] = "ALLOW" if body["decision"] != "ALLOW" else "HALT"
    env["payload"] = base64.b64encode(_canon(body)).decode("ascii")
    res_t = er.verify_engagement_receipt(tampered, public_key_pem=pub)
    assert res_t["signature_verified"] is False
    assert res_t["verified"] is False


def test_energy_is_honest_unavailable_never_fabricated():
    tel = _telemetry()
    priv, _pub = er._SR.generate_keypair()
    bundle = er.emit_engagement_receipt(tel, private_key_pem=priv,
                                        ts="2026-01-01T00:00:00+00:00")

    assert bundle["energy_joules"] == er.UNAVAILABLE
    body = json.loads(base64.b64decode(bundle["receipt"]["payload"]))
    assert body["energy_joules"] == "UNAVAILABLE"
    # The predicate energy field is the same honest sentinel — not a number.
    energy = bundle["statement"]["predicate"]["energy"]["joules"]
    assert energy == "UNAVAILABLE"
    assert not isinstance(energy, (int, float))


def test_wrong_public_key_does_not_verify():
    tel = _telemetry()
    priv, _pub = er._SR.generate_keypair()
    _priv2, pub2 = er._SR.generate_keypair()
    bundle = er.emit_engagement_receipt(tel, private_key_pem=priv,
                                        ts="2026-01-01T00:00:00+00:00")
    res = er.verify_engagement_receipt(bundle, public_key_pem=pub2, telemetry=tel)
    assert res["signature_verified"] is False
    assert res["verified"] is False


def test_unsigned_honest_receipt_never_reports_fake_pass():
    """Keyless emission must be UNSIGNED-honest: signed=False and verification
    NEVER reports authenticity — honesty doctrine (no fake pass)."""
    tel = _telemetry()
    bundle = er.emit_engagement_receipt(tel, private_key_pem=None,
                                        ts="2026-01-01T00:00:00+00:00")
    assert bundle["receipt"]["signed"] is False
    res = er.verify_engagement_receipt(bundle, public_key_pem=None, telemetry=tel)
    assert res["signature_verified"] is False
    assert res["verified"] is False
    # But the statement still honestly binds the receipt digest.
    assert res["statement_binds_receipt"] is True


def test_receipt_binds_the_right_decision_only():
    """A receipt minted for telemetry A must NOT validate its digests against a
    DIFFERENT telemetry B — the receipt binds the decision it was made for."""
    tel_a = _telemetry()
    tel_b = _telemetry()
    tel_b["sensors"]["s4"] = 100.0  # remove the byzantine sensor → different Λ
    priv, pub = er._SR.generate_keypair()
    bundle = er.emit_engagement_receipt(tel_a, private_key_pem=priv,
                                        ts="2026-01-01T00:00:00+00:00")

    # Against the correct telemetry: digests match.
    ok = er.verify_engagement_receipt(bundle, public_key_pem=pub, telemetry=tel_a)
    assert ok["digests_match"] is True
    # Against different telemetry: input digest re-derivation must NOT match.
    bad = er.verify_engagement_receipt(bundle, public_key_pem=pub, telemetry=tel_b)
    assert bad["digests_match"] is False
    assert bad["verified"] is False


def test_bft_witnesses_are_recorded():
    tel = _telemetry()
    priv, _pub = er._SR.generate_keypair()
    witnesses = ["khipu-node-a", "khipu-node-b"]
    bundle = er.emit_engagement_receipt(
        tel, private_key_pem=priv, bft_witnesses=witnesses,
        ts="2026-01-01T00:00:00+00:00")
    body = json.loads(base64.b64decode(bundle["receipt"]["payload"]))
    assert body["bft_witnesses"] == witnesses
    assert bundle["statement"]["predicate"]["bftWitnesses"] == witnesses


def test_vendored_fallback_is_byte_identical_to_installed():
    """The vendored fallback (used when the szl-receipt install is blocked) must
    produce a BYTE-IDENTICAL unsigned envelope + statement to the real library,
    and cross-verify signatures — proving it is a genuine drop-in, not a fork."""
    szl_receipt = pytest.importorskip("szl_receipt")

    body = {"organ": "killinchu", "decision": "HALT", "lambda": 0.42,
            "input_digest": "a" * 64, "output_digest": "b" * 64,
            "energy_joules": "UNAVAILABLE", "nested": {"b": 2, "a": [3, 2, 1]}}

    r_inst = szl_receipt.Receipt(kind="counter-uas-engagement", body=body)
    r_vend = er._VendorReceipt(kind="counter-uas-engagement", body=body)
    assert r_inst.digest() == r_vend.digest()

    env_inst = szl_receipt.sign_receipt(r_inst, None, organ="killinchu")
    env_vend = er._v_sign_receipt(r_vend, None, organ="killinchu")
    assert env_inst == env_vend  # byte-identical unsigned envelope

    st_inst = szl_receipt.build_statement(
        subject_name="killinchu-engagement-receipt",
        subject_digest=r_inst.digest(), predicate={"p": 1},
        predicate_type=er.PREDICATE_TYPE)
    st_vend = er._v_build_statement(
        subject_name="killinchu-engagement-receipt",
        subject_digest=r_vend.digest(), predicate={"p": 1},
        predicate_type=er.PREDICATE_TYPE)
    assert _canon(st_inst) == _canon(st_vend)

    # Cross-verify: installed-signed verifies under vendored verify and vice-versa.
    priv, pub = szl_receipt.generate_keypair()
    env_s = szl_receipt.sign_receipt(r_inst, priv, organ="killinchu")
    assert er._v_verify_receipt(env_s, pub) == (True, "ok")
    env_s2 = er._v_sign_receipt(r_vend, priv, organ="killinchu")
    assert szl_receipt.verify_receipt(env_s2, pub) == (True, "ok")


def test_digests_are_deterministic_across_calls():
    """Same telemetry → same input/output/subject digests every time (the
    signature differs since ECDSA is randomised, but the bound digests do not)."""
    tel = _telemetry()
    priv, _pub = er._SR.generate_keypair()
    b1 = er.emit_engagement_receipt(tel, private_key_pem=priv,
                                    ts="2026-01-01T00:00:00+00:00")
    b2 = er.emit_engagement_receipt(tel, private_key_pem=priv,
                                    ts="2026-01-01T00:00:00+00:00")
    assert b1["input_digest"] == b2["input_digest"]
    assert b1["output_digest"] == b2["output_digest"]
    assert b1["subject_digest"] == b2["subject_digest"]
