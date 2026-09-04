# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""Network-free contract tests for Killinchu Asset Exposure Wave 5."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from szl_connectors.asset_exposure import (
    ExposureInputError,
    compose_report,
    contract,
    loads_strict,
    prepare_payload,
)


def cyclonedx_payload() -> dict:
    return {
        "asset": {
            "asset_id": "asset:prod:payments-01",
            "name": "Payments API",
            "owner": "Platform Security",
            "environment": "production",
            "criticality": 5,
            "exposure": "internet",
        },
        "sbom": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": "urn:uuid:wave5-test",
            "metadata": {"component": {"name": "payments-api"}},
            "components": [
                {
                    "type": "library",
                    "bom-ref": "pkg:maven/log4j-core@2.14.1",
                    "name": "log4j-core",
                    "version": "2.14.1",
                    "purl": "pkg:maven/log4j-core@2.14.1",
                },
                {
                    "type": "library",
                    "bom-ref": "pkg:pypi/fastapi@0.116.1",
                    "name": "fastapi",
                    "version": "0.116.1",
                    "purl": "pkg:pypi/fastapi@0.116.1",
                },
            ],
        },
        "findings": [
            {
                "component_ref": "pkg:maven/log4j-core@2.14.1",
                "cve": "cve-2021-44228",
                "status": "affected",
                "evidence_ref": "operator-vex:2026-09-04:1",
            }
        ],
    }


def spdx_payload() -> dict:
    return {
        "asset": {
            "asset_id": "asset:lab:gateway",
            "criticality": 3,
            "exposure": "internal",
        },
        "sbom": {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "gateway",
            "documentNamespace": "urn:uuid:spdx-wave5-test",
            "packages": [
                {
                    "SPDXID": "SPDXRef-Package-openssl",
                    "name": "openssl",
                    "versionInfo": "3.0.0",
                    "externalRefs": [
                        {
                            "referenceType": "purl",
                            "referenceLocator": "pkg:generic/openssl@3.0.0",
                        }
                    ],
                }
            ],
        },
        "findings": [
            {
                "component_ref": "SPDXRef-Package-openssl",
                "cve": "CVE-2023-0286",
                "status": "under_investigation",
            }
        ],
    }


def fusion(
    *,
    cve: str,
    priority: str = "IMMEDIATE",
    score: float = 0.95,
    coverage: str = "FULL",
    state: str = "connected",
) -> dict:
    return {
        "connector_id": "defensive_fusion",
        "state": state,
        "records": [
            {
                "cve": cve,
                "priority": priority,
                "priority_score": score,
                "coverage": coverage,
                "known_exploited": priority == "IMMEDIATE",
                "known_ransomware_use": False,
                "cvss": 10.0,
                "epss": 0.94,
                "recommended_action": "Apply the approved vendor mitigation.",
                "normalized_evidence_sha256": "a" * 64,
            }
        ]
        if state.casefold() == "connected"
        else [],
        "source": "CISA KEV + NIST NVD CVE 2.0 + FIRST EPSS",
        "live": state.casefold() == "connected",
        "note": "test evidence",
    }


class InputContractTests(unittest.TestCase):
    def test_cyclonedx_is_normalized_before_resolution(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        self.assertEqual(prepared["sbom"]["format"], "CycloneDX")
        self.assertEqual(prepared["sbom"]["component_count"], 2)
        self.assertEqual(prepared["active_cves"], ["CVE-2021-44228"])
        self.assertEqual(
            prepared["findings"][0]["component_ref"],
            "pkg:maven/log4j-core@2.14.1",
        )
        self.assertRegex(prepared["sbom_input_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(
            prepared["normalized_input_sha256"],
            r"^[0-9a-f]{64}$",
        )

    def test_spdx_2x_is_supported(self) -> None:
        prepared = prepare_payload(spdx_payload())
        self.assertEqual(prepared["sbom"]["format"], "SPDX")
        self.assertEqual(prepared["sbom"]["version"], "SPDX-2.3")
        component = prepared["component_map"]["SPDXRef-Package-openssl"]
        self.assertEqual(component["purl"], "pkg:generic/openssl@3.0.0")

    def test_cyclonedx_root_component_is_addressable(self) -> None:
        payload = cyclonedx_payload()
        root = {
            "type": "application",
            "bom-ref": "pkg:generic/payments-api@1.0.0",
            "name": "payments-api",
            "version": "1.0.0",
        }
        payload["sbom"]["metadata"]["component"] = root
        payload["sbom"]["components"] = []
        payload["findings"][0]["component_ref"] = root["bom-ref"]
        prepared = prepare_payload(payload)
        self.assertEqual(prepared["sbom"]["component_count"], 1)
        self.assertIn(root["bom-ref"], prepared["component_map"])

    def test_unknown_component_fails_closed(self) -> None:
        payload = cyclonedx_payload()
        payload["findings"][0]["component_ref"] = "missing"
        with self.assertRaises(ExposureInputError) as caught:
            prepare_payload(payload)
        self.assertEqual(caught.exception.code, "UNKNOWN_COMPONENT_REF")

    def test_invalid_cve_fails_closed(self) -> None:
        payload = cyclonedx_payload()
        payload["findings"][0]["cve"] = "log4shell"
        with self.assertRaises(ExposureInputError) as caught:
            prepare_payload(payload)
        self.assertEqual(caught.exception.code, "INVALID_CVE")

    def test_closed_vex_state_requires_justification(self) -> None:
        payload = cyclonedx_payload()
        payload["findings"][0]["status"] = "not_affected"
        with self.assertRaises(ExposureInputError) as caught:
            prepare_payload(payload)
        self.assertEqual(caught.exception.code, "MISSING_JUSTIFICATION")

        payload["findings"][0]["justification"] = (
            "The vulnerable code path is absent from this build."
        )
        prepared = prepare_payload(payload)
        self.assertEqual(prepared["active_cves"], [])

    def test_duplicate_component_cve_is_rejected(self) -> None:
        payload = cyclonedx_payload()
        duplicate = dict(payload["findings"][0])
        duplicate["status"] = "under_investigation"
        payload["findings"].append(duplicate)
        with self.assertRaises(ExposureInputError) as caught:
            prepare_payload(payload)
        self.assertEqual(caught.exception.code, "DUPLICATE_FINDING")

    def test_active_cve_bound_is_enforced(self) -> None:
        payload = cyclonedx_payload()
        component = payload["sbom"]["components"][0]["bom-ref"]
        payload["findings"] = [
            {
                "component_ref": component,
                "cve": f"CVE-2026-{1000 + index}",
                "status": "affected",
            }
            for index in range(11)
        ]
        with self.assertRaises(ExposureInputError) as caught:
            prepare_payload(payload)
        self.assertEqual(caught.exception.code, "TOO_MANY_ACTIVE_CVES")

    def test_strict_json_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(ExposureInputError) as caught:
            loads_strict(b'{"asset":{},"asset":{}}')
        self.assertEqual(caught.exception.code, "INVALID_JSON")

    def test_nonstandard_json_constant_is_rejected(self) -> None:
        with self.assertRaises(ExposureInputError) as caught:
            loads_strict(b'{"asset": NaN}')
        self.assertEqual(caught.exception.code, "INVALID_JSON")

    def test_body_size_is_bounded(self) -> None:
        with self.assertRaises(ExposureInputError) as caught:
            loads_strict(b" " * 2_000_001)
        self.assertEqual(caught.exception.code, "BODY_TOO_LARGE")
        self.assertEqual(caught.exception.status_code, 413)


class ReportTests(unittest.TestCase):
    def test_full_critical_internet_exposure_preserves_source_score(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        report = compose_report(
            prepared,
            {
                "CVE-2021-44228": fusion(
                    cve="CVE-2021-44228",
                    priority="IMMEDIATE",
                    score=0.95,
                )
            },
            observed_at="2026-09-04T00:00:00+00:00",
        )
        row = report["remediation_queue"][0]
        self.assertEqual(report["state"], "MEASURED")
        self.assertEqual(row["remediation_lane"], "P0")
        self.assertEqual(row["asset_priority_score"], 0.95)
        self.assertEqual(
            report["action_authority"],
            "DEFENSIVE_REMEDIATION_PLANNING_ONLY",
        )
        self.assertFalse(report["asset_scanning_performed"])
        self.assertFalse(
            report["component_vulnerability_inference_performed"]
        )

    def test_context_formula_is_bounded_and_not_a_probability(self) -> None:
        prepared = prepare_payload(spdx_payload())
        report = compose_report(
            prepared,
            {
                "CVE-2023-0286": fusion(
                    cve="CVE-2023-0286",
                    priority="ROUTINE",
                    score=0.50,
                )
            },
            observed_at="2026-09-04T00:00:00+00:00",
        )
        formula = report["formula"]
        self.assertFalse(formula["probability_claimed"])
        multiplier = formula["context_multiplier"]["value"]
        self.assertGreaterEqual(multiplier, 0.55)
        self.assertLessEqual(multiplier, 1.0)
        self.assertLess(
            report["remediation_queue"][0]["asset_priority_score"],
            0.50,
        )

    def test_no_active_findings_make_no_resolution_claim(self) -> None:
        payload = cyclonedx_payload()
        payload["findings"][0].update(
            {
                "status": "fixed",
                "justification": "Patched and verified in change CHG-2048.",
            }
        )
        prepared = prepare_payload(payload)
        report = compose_report(
            prepared,
            {},
            observed_at="2026-09-04T00:00:00+00:00",
        )
        self.assertEqual(report["state"], "NO_ACTIVE_FINDINGS")
        self.assertEqual(report["summary"]["active_findings"], 0)
        self.assertEqual(report["remediation_queue"], [])

    def test_missing_official_evidence_remains_unavailable(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        report = compose_report(
            prepared,
            {
                "CVE-2021-44228": {
                    "state": "error",
                    "records": [],
                    "live": False,
                    "note": "all sources unavailable",
                }
            },
            observed_at="2026-09-04T00:00:00+00:00",
        )
        row = report["remediation_queue"][0]
        self.assertEqual(report["state"], "UNAVAILABLE")
        self.assertEqual(row["remediation_lane"], "REVIEW")
        self.assertIsNone(row["asset_priority_score"])

    def test_mismatched_resolver_record_is_rejected(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        wrong = fusion(cve="CVE-2024-0001")
        report = compose_report(
            prepared,
            {"CVE-2021-44228": wrong},
            observed_at="2026-09-04T00:00:00+00:00",
        )
        row = report["remediation_queue"][0]
        self.assertEqual(report["state"], "UNAVAILABLE")
        self.assertEqual(row["source_state"], "ERROR")
        self.assertEqual(row["remediation_lane"], "REVIEW")
        self.assertIsNone(row["asset_priority_score"])

    def test_invalid_priority_records_are_rejected(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        cases = (
            (float("nan"), "IMMEDIATE"),
            (0.50, "URGENT"),
        )
        for score, priority in cases:
            with self.subTest(score=score, priority=priority):
                invalid = fusion(
                    cve="CVE-2021-44228",
                    score=score,
                    priority=priority,
                )
                report = compose_report(
                    prepared,
                    {"CVE-2021-44228": invalid},
                    observed_at="2026-09-04T00:00:00+00:00",
                )
                row = report["remediation_queue"][0]
                self.assertEqual(report["state"], "UNAVAILABLE")
                self.assertEqual(row["source_state"], "ERROR")
                self.assertEqual(row["remediation_lane"], "REVIEW")
                self.assertIsNone(row["asset_priority_score"])

    def test_evidence_digest_excludes_observation_time(self) -> None:
        prepared = prepare_payload(cyclonedx_payload())
        resolved = {"CVE-2021-44228": fusion(cve="CVE-2021-44228")}
        first = compose_report(
            prepared,
            resolved,
            observed_at="2026-09-04T00:00:00+00:00",
        )
        second = compose_report(
            prepared,
            resolved,
            observed_at="2026-09-04T01:00:00+00:00",
        )
        self.assertEqual(
            first["evidence_sha256"],
            second["evidence_sha256"],
        )
        self.assertNotEqual(first["observed_at"], second["observed_at"])

    def test_contract_declares_all_safety_boundaries(self) -> None:
        value = json.dumps(contract(), sort_keys=True)
        for phrase in (
            "asset scanning",
            "user-supplied URL retrieval",
            "package-to-CVE inference",
            "exploit content",
            "command execution",
            "third-party mutation",
        ):
            self.assertIn(phrase, value)

    def test_module_has_no_direct_network_or_command_primitive(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "szl_connectors"
            / "asset_exposure.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "import requests",
            "import httpx",
            "import urllib",
            "import socket",
            "import subprocess",
            "os.system(",
            "Popen(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
