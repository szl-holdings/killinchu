import base64
import hashlib
import hmac
import json
import unittest

from killinchu_receipt_export import SCHEMA, build_receipt_export


class _TestDSSE:
    """Deterministic verifier used to test the route contract without secrets."""

    secret = b"test-only-key"

    @staticmethod
    def canonical_json(obj):
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def pae(payload_type, body):
        t = payload_type.encode("utf-8")
        return b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" " + str(len(body)).encode() + b" " + body

    @classmethod
    def signature(cls, payload_type, receipt):
        body = cls.canonical_json(receipt)
        return base64.b64encode(hmac.new(cls.secret, cls.pae(payload_type, body), hashlib.sha256).digest()).decode()

    @classmethod
    def verify_envelope(cls, env):
        body = base64.b64decode(env["payload"])
        expected = hmac.new(cls.secret, cls.pae(env["payloadType"], body), hashlib.sha256).digest()
        actual = base64.b64decode(env["signatures"][0]["sig"])
        verified = hmac.compare_digest(actual, expected)
        return {
            "verified": verified,
            "reason": "test signature mismatch" if not verified else "verified",
            "pae_sha256": hashlib.sha256(cls.pae(env["payloadType"], body)).hexdigest(),
        }


def _node(signature):
    receipt = {
        "schema": "szl.killinchu.receipt/v1",
        "kind": "contract-test",
        "payload": {"bounded": True},
        "doctrine": "v11",
        "ts_utc": "2026-07-11T00:00:00Z",
    }
    return receipt, {
        "index": 0,
        "digest": "a" * 64,
        "receipt": receipt,
        "dsse": {
            "payloadType": "application/vnd.szl.receipt+json",
            "signatures": [{"keyid": "test-key", "sig": signature}],
        },
    }


class ReceiptExportContractTests(unittest.TestCase):
    def test_empty_ledger_is_typed_200_with_explicit_limit(self):
        body, status = build_receipt_export([], dsse_module=_TestDSSE)
        self.assertEqual(status, 200)
        self.assertEqual(body["schema"], SCHEMA)
        self.assertEqual(body["export_state"], "EMPTY")
        self.assertFalse(body["receipt_available"])
        self.assertFalse(body["signed"])
        self.assertIsNone(body["dsse"])
        self.assertEqual(body["verification"]["state"], "NOT_APPLICABLE")
        self.assertIn("NO_RECEIPTS", {item["code"] for item in body["limits"]})

    def test_valid_signature_is_exported_only_after_verification(self):
        receipt, _ = _node("")
        sig = _TestDSSE.signature("application/vnd.szl.receipt+json", receipt)
        _, node = _node(sig)
        body, status = build_receipt_export([node], dsse_module=_TestDSSE, khipu_root=node["digest"])
        self.assertEqual(status, 200)
        self.assertEqual(body["export_state"], "SIGNED_VERIFIED")
        self.assertTrue(body["signed"])
        self.assertEqual(body["verification"]["state"], "VERIFIED")
        self.assertTrue(body["dsse"]["payload"])
        self.assertTrue(body["verify_offline"])

    def test_invalid_signature_never_becomes_signed(self):
        _, node = _node(base64.b64encode(b"not-a-valid-signature").decode())
        body, status = build_receipt_export([node], dsse_module=_TestDSSE)
        self.assertEqual(status, 200)
        self.assertEqual(body["export_state"], "SIGNATURE_UNVERIFIED")
        self.assertFalse(body["signed"])
        self.assertEqual(body["verification"]["state"], "FAILED")
        self.assertEqual(body["verify_offline"], [])
        self.assertIn("NO_VERIFIED_SIGNATURE", {item["code"] for item in body["limits"]})

    def test_placeholder_is_not_exposed_as_a_signature(self):
        _, node = _node("PLACEHOLDER - not a signature")
        node["dsse"]["signatures"][0]["keyid"] = "PENDING"
        body, status = build_receipt_export([node], dsse_module=_TestDSSE)
        self.assertEqual(status, 200)
        self.assertEqual(body["export_state"], "UNSIGNED")
        self.assertFalse(body["signed"])
        self.assertEqual(body["dsse"]["signatures"], [])
        self.assertEqual(body["verification"]["state"], "UNSIGNED")

    def test_out_of_range_index_is_rejected_without_fallback(self):
        _, node = _node(base64.b64encode(b"x").decode())
        body, status = build_receipt_export([node], index=3, dsse_module=_TestDSSE)
        self.assertEqual(status, 422)
        self.assertFalse(body["ok"])
        self.assertEqual(body["export_state"], "INDEX_OUT_OF_RANGE")
        self.assertEqual(body["requested_index"], 3)


if __name__ == "__main__":
    unittest.main()

