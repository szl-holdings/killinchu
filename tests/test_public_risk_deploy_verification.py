"""Offline tests for dated, source-bound public-risk deployment refusals."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_risk_verify", ROOT / "scripts/verify_public_risk_unavailable.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)
SHA = "1d6bf84c454a75d209f825c276bac3a546ca5ee1"


class PublicRiskDeployVerificationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / "public-risk-transition.json").read_text())
        self.payload = {
            "schema": "szl.killinchu-public-risk-transition-status/v1",
            "state": "UNAVAILABLE", "reason_code": "OPTION_A_REVIEW_EXPIRED",
            "runtime_observation": {"source": {"state": "OBSERVED", "revision": SHA}},
        }

    def check(self, *, payload=None, status="503", sha=SHA, today=date(2026, 11, 1), contract=None):
        return verify.verify(self.payload if payload is None else payload,
                             http_status=status, source_sha=sha, today=today,
                             contract=self.contract if contract is None else contract)

    def test_expired_refusal_is_verified_without_renewing_approval(self):
        self.assertEqual(self.check(), "OPTION_A_REVIEW_EXPIRED")
        self.assertEqual(self.contract["decision"]["review_due"], "2026-10-23")

    def test_reason_changes_at_review_date_not_before(self):
        self.payload["reason_code"] = "CI_ATTESTATION_EVIDENCE_UNPROVED"
        self.assertEqual(self.check(today=date(2026, 10, 22)), self.payload["reason_code"])
        with self.assertRaises(ValueError):
            self.check(today=date(2026, 10, 23))
        self.payload["reason_code"] = "OPTION_A_REVIEW_EXPIRED"
        self.assertEqual(self.check(today=date(2026, 10, 23)), self.payload["reason_code"])
        with self.assertRaises(ValueError):
            self.check(today=date(2026, 10, 22))

    def test_neither_transport_success_nor_unrelated_errors_are_refusals(self):
        for status in ("200", "500", "404", "000", "503503"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.check(status=status)

    def test_unknown_reason_and_divergence_remain_failures(self):
        for state, reason in (("UNAVAILABLE", "PUBLIC_CONTRACT_UNAVAILABLE"),
                              ("UNAVAILABLE", "PUBLIC_SCHEMA_INVALID"),
                              ("UNAVAILABLE", "OPTION_A_CAPABILITY_MIGRATED"),
                              ("DIVERGENT", "OPTION_A_REVIEW_EXPIRED"),
                              ("READY", "OPTION_A_REVIEW_EXPIRED")):
            with self.subTest(state=state, reason=reason), self.assertRaises(ValueError):
                self.check(payload={**self.payload, "state": state, "reason_code": reason})

    def test_wrong_or_absent_live_revision_is_rejected(self):
        for source in ({}, {"state": "UNAVAILABLE", "revision": SHA},
                       {"state": "OBSERVED", "revision": "b" * 40}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.check(payload={**self.payload, "runtime_observation": {"source": source}})

    def test_invalid_source_parameter_is_rejected(self):
        for sha in ("main", "0" * 40, "A" * 40, "a" * 39):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                self.check(sha=sha)

    def test_expiry_cannot_mask_a_corrupt_checked_in_contract(self):
        contract = deepcopy(self.contract)
        contract["controls"][0]["state"] = "VERIFIED"
        with self.assertRaises(ValueError):
            self.check(contract=contract)

    def test_changed_review_deadline_or_migration_is_not_admitted(self):
        for field, value in (("review_due", "2099-01-01"), ("migration_state", "MIGRATED")):
            contract = deepcopy(self.contract)
            contract["decision"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(contract=contract)

    def test_malformed_payloads_fail_closed(self):
        for payload in ([], {}, {**self.payload, "schema": "wrong"},
                        {**self.payload, "runtime_observation": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.check(payload=payload)

    def test_json_parser_rejects_duplicates_nonfinite_and_oversize(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "body.json"
            for raw in ('{"state":"READY","state":"UNAVAILABLE"}',
                        '{"value":NaN}', '{"value":1e400}', ' ' * 65537):
                path.write_text(raw)
                with self.subTest(raw=raw[:70]), self.assertRaises(ValueError):
                    verify.read_json(path)

    def test_deployment_invokes_source_bound_verifier(self):
        workflow = (ROOT / ".github/workflows/hf-sync.yml").read_text()
        job = workflow.split("  verify-risk-status-fails-closed:", 1)[1].split("  release-receipt:", 1)[0]
        self.assertIn("scripts/verify_public_risk_unavailable.py", job)
        self.assertIn('--source-sha "$SOURCE_SHA"', job)
        self.assertIn('--http-status "$code"', job)
        self.assertIn("ref: ${{ github.sha }}", job)
        self.assertNotIn("continue-on-error", job)
        self.assertIn('payload["production_ready"] is False', job)
        self.assertIn('payload["production_receipts_ready"] is False', job)


if __name__ == "__main__":
    unittest.main()
