# SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for Killinchu Defensive Fusion Wave 4."""
from __future__ import annotations

from unittest import mock

from szl_connectors.base import Records, State
from szl_connectors import REGISTRY
from szl_connectors import bindings
from szl_connectors.data_sources import security


CVE = "CVE-2026-12345"


def cisa_records(*, connected: bool = True, hit: bool = True) -> Records:
    rows = []
    if hit:
        rows.append(
            {
                "cveID": CVE,
                "vendorProject": "Example Vendor",
                "product": "Example Product",
                "vulnerabilityName": "Example memory safety vulnerability",
                "dateAdded": "2026-09-01",
                "knownRansomwareCampaignUse": "Known",
                "requiredAction": "Apply vendor mitigations.",
            }
        )
    return Records(
        connector_id="cisa_kev",
        category="vuln",
        state=State.CONNECTED if connected else State.READY,
        records=rows,
        source="fixture",
        live=connected,
    )


def nvd_payload() -> dict:
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": CVE,
                    "published": "2026-08-30T00:00:00.000",
                    "lastModified": "2026-09-03T00:00:00.000",
                    "vulnStatus": "Analyzed",
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseScore": 9.8,
                                    "baseSeverity": "CRITICAL",
                                    "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                }
                            }
                        ]
                    },
                    "weaknesses": [
                        {"description": [{"lang": "en", "value": "CWE-416"}]}
                    ],
                }
            }
        ]
    }


def epss_payload() -> dict:
    return {
        "data": [
            {
                "cve": CVE,
                "epss": "0.910000",
                "percentile": "0.998000",
                "date": "2026-09-04",
            }
        ]
    }


def fake_http(url: str, *args, **kwargs):
    if "services.nvd.nist.gov" in url:
        assert "cveId=CVE-2026-12345" in url
        return 200, nvd_payload()
    if "api.first.org" in url:
        assert "cve=CVE-2026-12345" in url
        return 200, epss_payload()
    raise AssertionError(url)


def test_connector_is_registered_and_bound_without_replacing_live_feeds():
    assert "defensive_fusion" in REGISTRY
    assert bindings.TAB_BINDINGS["vuln"] == [
        "nvd_cve",
        "cisa_kev",
        "epss",
        "defensive_fusion",
    ]


def test_exact_cve_full_coverage_is_deterministic_and_defensive_only():
    security._CACHE.clear()
    with mock.patch.object(security.CisaKevConnector, "read", return_value=cisa_records()), mock.patch.object(
        security, "http_json", side_effect=fake_http
    ):
        result = security.DefensiveFusionConnector().read({"q": CVE})
    assert result.state == State.CONNECTED
    assert result.live is True
    assert len(result.records) == 1
    row = result.records[0]
    assert row["cve"] == CVE
    assert row["coverage"] == "FULL"
    assert row["priority"] == "IMMEDIATE"
    assert 0.0 <= row["priority_score"] <= 0.99
    assert row["known_exploited"] is True
    assert row["known_ransomware_use"] is True
    assert row["cvss"] == 9.8
    assert row["epss"] == 0.91
    assert row["action_authority"] == "DEFENSIVE_PRIORITIZATION_ONLY"
    assert row["human_approval_required"] is True
    assert row["exploit_content_included"] is False
    assert row["asset_scanning_performed"] is False
    assert row["formula"]["missing_evidence_is_zero"] is False
    assert len(row["normalized_evidence_sha256"]) == 64
    assert "mitigation" in row["recommended_action"].casefold()


def test_missing_source_is_partial_not_silently_scored_as_zero():
    security._CACHE.clear()

    def partial_http(url: str, *args, **kwargs):
        if "services.nvd.nist.gov" in url:
            return 503, {}
        if "api.first.org" in url:
            return 200, epss_payload()
        raise AssertionError(url)

    with mock.patch.object(
        security.CisaKevConnector, "read", return_value=cisa_records(hit=False)
    ), mock.patch.object(security, "http_json", side_effect=partial_http):
        result = security.DefensiveFusionConnector().read({"cve": CVE})
    row = result.records[0]
    assert row["coverage"] == "PARTIAL"
    assert row["source_states"]["nvd_cve"] == "UNAVAILABLE"
    assert "cvss" not in row["formula"]["observed_components"]
    assert row["priority_score"] is not None


def test_invalid_query_returns_no_record_and_no_network_call():
    security._CACHE.clear()
    with mock.patch.object(security, "http_json") as request:
        result = security.DefensiveFusionConnector().read(
            {"q": "https://example.invalid/CVE-2026-12345"}
        )
    assert result.state == State.READY
    assert result.records == []
    assert result.live is False
    assert "exact CVE" in result.note
    request.assert_not_called()


def test_all_sources_unavailable_fails_closed_without_priority():
    security._CACHE.clear()
    with mock.patch.object(
        security.CisaKevConnector,
        "read",
        return_value=cisa_records(connected=False, hit=False),
    ), mock.patch.object(security, "http_json", return_value=(503, {})):
        result = security.DefensiveFusionConnector().read({"q": CVE})
    assert result.state == State.ERROR
    assert result.records == []
    assert result.live is False
    assert "no priority fabricated" in result.note


def test_source_contains_no_scanner_command_or_exploit_channel():
    source = __import__("pathlib").Path(security.__file__).read_text(encoding="utf-8")
    fusion = source.split("class DefensiveFusionConnector", 1)[1]
    for forbidden in (
        "subprocess.",
        "os.system(",
        "socket.create_connection",
        "paramiko",
        "nmap",
        'method="POST"',
        'method="PUT"',
        'method="DELETE"',
        "exploit_payload",
    ):
        assert forbidden not in fusion


def test_measured_transports_without_exact_cve_do_not_create_a_priority():
    security._CACHE.clear()

    def empty_http(url: str, *args, **kwargs):
        if "services.nvd.nist.gov" in url:
            return 200, {"vulnerabilities": []}
        if "api.first.org" in url:
            return 200, {"data": []}
        raise AssertionError(url)

    with mock.patch.object(
        security.CisaKevConnector, "read", return_value=cisa_records(hit=False)
    ), mock.patch.object(security, "http_json", side_effect=empty_http):
        result = security.DefensiveFusionConnector().read({"q": CVE})
    assert result.state == State.READY
    assert result.records == []
    assert result.live is False
    assert "exact CVE was not present" in result.note
    assert "no priority fabricated" in result.note

