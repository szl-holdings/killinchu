import json
import unittest

from dsse_verify.dsse import (
    INVALID,
    POLICY_REJECTED,
    SIGNATURE_MISMATCH,
    VERIFICATION_UNAVAILABLE,
    VERIFIED,
    Verdict,
    pae,
    verify_envelope,
)


def make_envelope(payload_type="application/vnd.in-toto+json", payload='{"k": "v"}',
                  sigs=("aabb",)):
    return json.dumps({
        "payloadType": payload_type,
        "payload": payload,
        "signatures": [{"keyid": "k0", "sig": s} for s in sigs],
    })


class PaeTests(unittest.TestCase):
    def test_pae_prefix_and_lengths(self):
        blob = pae("application/vnd.in-toto+json", '{"k":"v"}',
                   [{"keyid": "k0", "sig": "aa"}])
        self.assertTrue(blob.startswith(b"DSSEv1 "))
        parts = blob.split(b" ")
        self.assertEqual(parts[0], b"DSSEv1")
        self.assertEqual(int(parts[1]), len(b"application/vnd.in-toto+json"))
        expected_sig = json.dumps([{"keyid": "k0", "sig": "aa"}],
                                  separators=(",", ":")).encode("utf-8")
        self.assertTrue(blob.endswith(expected_sig))

    def test_pae_deterministic(self):
        a = pae("t", "p", [{"sig": "s"}])
        b = pae("t", "p", [{"sig": "s"}])
        self.assertEqual(a, b)

    def test_pae_rejects_wrong_types(self):
        with self.assertRaises(TypeError):
            pae(12, "p", [{"sig": "s"}])


class VerifyTests(unittest.TestCase):
    def test_verifier_true_is_verified(self):
        v = verify_envelope(make_envelope(), verifier=lambda pae_bytes, sigs: True)
        self.assertEqual(v.result, VERIFIED)
        self.assertEqual(v.signature_count, 1)
        self.assertEqual(v.payload_type, "application/vnd.in-toto+json")

    def test_verifier_false_is_signature_mismatch(self):
        v = verify_envelope(make_envelope(), verifier=lambda pae_bytes, sigs: False)
        self.assertEqual(v.result, SIGNATURE_MISMATCH)

    def test_no_verifier_is_unavailable_never_pass(self):
        v = verify_envelope(make_envelope(), verifier=None)
        self.assertEqual(v.result, VERIFICATION_UNAVAILABLE)
        self.assertIn("fails closed", v.reason)

    def test_policy_rejection(self):
        v = verify_envelope(make_envelope(payload_type="text/plain"),
                            verifier=lambda p, s: True,
                            policy=lambda pt: pt.startswith("application/"))
        self.assertEqual(v.result, POLICY_REJECTED)

    def test_bad_json_is_invalid(self):
        self.assertEqual(verify_envelope("not json{").result, INVALID)

    def test_non_object_is_invalid(self):
        self.assertEqual(verify_envelope("[1,2]").result, INVALID)

    def test_missing_fields_are_invalid(self):
        cases = (
            {},
            {"payloadType": "t"},
            {"payloadType": "t", "payload": "p"},
            {"payloadType": "t", "payload": "p", "signatures": []},
            {"payloadType": "t", "payload": "p", "signatures": [{"keyid": "k"}]},
            {"payloadType": "t", "payload": "p", "signatures": "nope"},
        )
        for env in cases:
            self.assertEqual(verify_envelope(json.dumps(env)).result, INVALID, env)

    def test_verifier_exception_is_invalid_not_pass(self):
        def boom(pae_bytes, sigs):
            raise RuntimeError("crypto backend down")
        v = verify_envelope(make_envelope(), verifier=boom)
        self.assertEqual(v.result, INVALID)
        self.assertIn("crypto backend down", v.reason)

    def test_verdict_as_dict(self):
        d = verify_envelope(make_envelope(), verifier=lambda p, s: True).as_dict()
        self.assertEqual(d["result"], VERIFIED)
        self.assertEqual(d["signature_count"], 1)


if __name__ == "__main__":
    unittest.main()
