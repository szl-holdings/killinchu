#!/usr/bin/env python3
"""Offline contracts for Killinchu's public-intelligence source mesh."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_research_sources as sources


def test_registry_is_fixed_public_and_official() -> None:
    required = {
        "cisa-kev",
        "nvd-recent",
        "ofac-sdn",
        "un-dprk-1718",
        "cia-world-leaders",
        "nsa-advisories",
        "cert-ua",
        "ukraine-open-data",
        "china-mfa",
        "china-state-council",
    }
    assert required <= set(sources._PUBLIC_FEEDS)
    assert sources._PUBLIC_POLICY["arbitrary_url_input"] is False
    assert sources._PUBLIC_POLICY["authentication"] == "NONE"
    assert sources._PUBLIC_POLICY["active_scanning"] is False
    assert sources._PUBLIC_POLICY["protected_resources"] is False
    for source in sources._PUBLIC_FEEDS.values():
        assert source["url"].startswith("https://")
        assert source["hosts"]
        assert source["max_bytes"] <= 30_000_000
        assert "token" not in source
        assert "password" not in source


def test_target_validation_rejects_unsafe_transport(monkeypatch) -> None:
    monkeypatch.setattr(
        sources._socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    assert sources._validate_target(
        "https://example.com/a", ("example.com",)
    ) == "example.com"
    for url in (
        "http://example.com/a",
        "https://user:pass@example.com/a",
        "https://evil.example/a",
        "https://example.com:8443/a",
    ):
        try:
            sources._validate_target(url, ("example.com",))
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe target accepted: %s" % url)

    monkeypatch.setattr(
        sources._socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    try:
        sources._validate_target("https://example.com/a", ("example.com",))
    except ValueError as error:
        assert str(error) == "NON_PUBLIC_ADDRESS"
    else:
        raise AssertionError("loopback target accepted")


def test_cisa_parser_preserves_reported_claim_boundary() -> None:
    payload = json.dumps(
        {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-0001",
                    "vulnerabilityName": "Example flaw",
                    "shortDescription": "Reported description",
                    "dateAdded": "2026-09-01",
                    "vendorProject": "Vendor",
                    "product": "Product",
                    "requiredAction": "Patch",
                    "dueDate": "2026-09-20",
                    "knownRansomwareCampaignUse": "Unknown",
                }
            ]
        }
    ).encode()
    rows = sources._parse_cisa("cisa-kev", payload)
    assert rows[0]["id"] == "CVE-2026-0001"
    assert rows[0]["claim_state"] == "REPORTED"
    assert rows[0]["evidence_state"] == "MEASURED"
    assert len(rows[0]["content_sha256"]) == 64


def test_nvd_parser_reads_english_description() -> None:
    payload = json.dumps(
        {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2026-0002",
                        "published": "2026-09-02T00:00:00Z",
                        "lastModified": "2026-09-03T00:00:00Z",
                        "sourceIdentifier": "nvd@nist.gov",
                        "descriptions": [
                            {"lang": "en", "value": "English description"}
                        ],
                    }
                }
            ]
        }
    ).encode()
    rows = sources._parse_nvd("nvd-recent", payload)
    assert rows[0]["title"] == "CVE-2026-0002"
    assert rows[0]["summary"] == "English description"


def test_ofac_parser_is_namespace_tolerant() -> None:
    payload = b"""<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"><sdnEntry><uid>123</uid><firstName>Jane</firstName><lastName>Example</lastName><sdnType>Individual</sdnType><programList><program>DPRK</program></programList><remarks>Public remarks</remarks></sdnEntry></sdnList>"""
    rows = sources._parse_ofac("ofac-sdn", payload)
    assert rows[0]["id"] == "123"
    assert rows[0]["title"] == "Jane Example"
    assert rows[0]["attributes"]["programs"] == ["DPRK"]


def test_un_parser_filters_only_dprk_1718_records() -> None:
    payload = b"""<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL><REFERENCE_NUMBER>KPi.001</REFERENCE_NUMBER><FIRST_NAME>Kim</FIRST_NAME><SECOND_NAME>Example</SECOND_NAME><LISTED_ON>2026-01-01</LISTED_ON><COMMENTS1>Public listing</COMMENTS1></INDIVIDUAL><INDIVIDUAL><REFERENCE_NUMBER>QDi.999</REFERENCE_NUMBER><FIRST_NAME>Other</FIRST_NAME></INDIVIDUAL></INDIVIDUALS><ENTITIES><ENTITY><REFERENCE_NUMBER>KPe.002</REFERENCE_NUMBER><FIRST_NAME>Entity Example</FIRST_NAME></ENTITY></ENTITIES></CONSOLIDATED_LIST>"""
    rows = sources._parse_un_dprk("un-dprk-1718", payload)
    assert [row["id"] for row in rows] == ["KPi.001", "KPe.002"]


def test_ukraine_ckan_parser_reads_public_dataset_metadata() -> None:
    payload = json.dumps(
        {
            "success": True,
            "result": [
                {
                    "id": "activity-1",
                    "activity_type": "changed package",
                    "timestamp": "2026-09-03T00:00:00Z",
                    "data": {
                        "package": {
                            "name": "dataset-one",
                            "title": "Dataset One",
                        }
                    },
                }
            ],
        }
    ).encode()
    rows = sources._parse_ukraine_ckan("ukraine-open-data", payload)
    assert rows[0]["title"] == "Dataset One"
    assert rows[0]["attributes"]["dataset_name"] == "dataset-one"


def test_html_parser_rejects_off_host_and_off_path_links() -> None:
    payload = b"""<a href="/resources/world-leaders/foreign-governments/china/">China government</a><a href="https://evil.example/x">Bad host</a><a href="/unrelated">Unrelated link</a>"""
    rows = sources._parse_html_index("cia-world-leaders", payload)
    assert len(rows) == 1
    assert rows[0]["title"] == "China government"


def test_result_cache_and_failure_are_explicit(monkeypatch) -> None:
    sources._PUBLIC_CACHE.clear()
    calls = []

    def fake_fetch(source):
        calls.append(source["url"])
        return json.dumps({"vulnerabilities": []}).encode(), {
            "http_status": 200,
            "final_url": source["url"],
            "content_type": "application/json",
            "etag": "fixture",
            "last_modified": None,
        }

    monkeypatch.setattr(sources, "_fetch_bytes", fake_fetch)
    first = sources._public_result("cisa-kev")
    second = sources._public_result("cisa-kev")
    assert first["state"] == "MEASURED"
    assert second["cache"] == "HIT"
    assert len(calls) == 1

    sources._PUBLIC_CACHE.clear()

    def fail(_source):
        raise TimeoutError

    monkeypatch.setattr(sources, "_fetch_bytes", fail)
    failed = sources._public_result("cisa-kev")
    assert failed["state"] == "UNAVAILABLE"
    assert failed["items"] == []
    assert failed["item_count"] is None


def test_routes_are_bounded_and_do_not_accept_a_url(monkeypatch) -> None:
    app = FastAPI()
    sources.register(app)
    monkeypatch.setattr(
        sources,
        "_public_result",
        lambda source_id: {
            "state": "MEASURED",
            "source_id": source_id,
            "item_count": 1,
            "items": [{"id": "fixture", "title": "Fixture", "published": None}],
        },
    )
    client = TestClient(app)
    source_response = client.get("/api/killinchu/v1/public-intel/sources")
    assert source_response.status_code == 200
    assert source_response.json()["policy"]["arbitrary_url_input"] is False
    assert client.get("/api/killinchu/v1/public-intel/status").status_code == 200
    assert client.get("/api/killinchu/v1/public-intel/cisa-kev?limit=1").status_code == 200
    assert client.get("/api/killinchu/v1/public-intel/not-real").status_code == 404
    assert client.get("/api/killinchu/v1/research/sanctions").status_code == 200
    assert sources.sources_for("totally_unknown_key_42")
    paths = {route.path for route in app.routes}
    assert not any("{url" in path or "target_url" in path for path in paths)
