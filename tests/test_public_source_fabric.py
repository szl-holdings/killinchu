"""Hermetic tests for the Killinchu Public Source Fabric.

No test performs network access.  Fixtures model only the fields retained by the
bounded parsers.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import killinchu_public_source_fabric as psf  # noqa: E402


CISA_FIXTURE = {
    "title": "CISA Known Exploited Vulnerabilities Catalog",
    "catalogVersion": "fixture",
    "vulnerabilities": [
        {
            "cveID": "CVE-2026-12345",
            "vendorProject": "Example Vendor",
            "product": "Example Product",
            "vulnerabilityName": "Example Product Memory Safety Vulnerability",
            "dateAdded": "2026-09-01",
            "shortDescription": "A memory-safety issue is known to be exploited.",
            "requiredAction": "Apply vendor mitigations or discontinue use.",
            "dueDate": "2026-09-22",
            "knownRansomwareCampaignUse": "Unknown",
            "notes": "https://example.invalid/advisory",
            "cwes": ["CWE-416"],
        }
    ],
}

OFAC_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML">
  <sdnEntry>
    <uid>42</uid><firstName>Example</firstName><lastName>Shipping LLC</lastName>
    <sdnType>Entity</sdnType>
    <programList><program>DPRK3</program></programList>
    <akaList><aka><uid>43</uid><firstName>Example</firstName><lastName>Maritime</lastName></aka></akaList>
    <idList><id><idType>Vessel Registration Identification</idType><idNumber>IMO 1234567</idNumber></id></idList>
  </sdnEntry>
</sdnList>"""

UN_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<CONSOLIDATED_LIST>
  <INDIVIDUALS>
    <INDIVIDUAL>
      <REFERENCE_NUMBER>KPi.001</REFERENCE_NUMBER>
      <LISTED_ON>2009-07-16</LISTED_ON>
      <FIRST_NAME>Example</FIRST_NAME><SECOND_NAME>Person</SECOND_NAME>
      <UN_LIST_TYPE>DPRK</UN_LIST_TYPE>
      <INDIVIDUAL_ALIAS><ALIAS_NAME>Example Alias</ALIAS_NAME></INDIVIDUAL_ALIAS>
    </INDIVIDUAL>
  </INDIVIDUALS>
  <ENTITIES>
    <ENTITY>
      <REFERENCE_NUMBER>KPe.001</REFERENCE_NUMBER>
      <FIRST_NAME>Example Entity</FIRST_NAME>
      <ENTITY_ALIAS><ALIAS_NAME>Example Trading</ALIAS_NAME></ENTITY_ALIAS>
    </ENTITY>
  </ENTITIES>
</CONSOLIDATED_LIST>"""

NSA_FIXTURE = b"""<!doctype html><html><body>
<table><tr><td><a href="https://media.defense.gov/2026/Aug/26/example.pdf">Joint CSA: Defensive Guidance</a></td><td>8/26/2026</td></tr></table>
<a href="https://evil.example/steal">Do not keep</a>
<a href="https://cyber.mil/protected">Protected guidance</a>
</body></html>"""

CIA_FIXTURE = b"""<!doctype html><html><body>
<a href="/stories/story/public-source-intelligence-history/">Public Source Intelligence History</a>
<a href="/the-world-factbook/">World Factbook Archive</a>
<a href="https://evil.example/private">Private collection</a>
</body></html>"""

CERT_UA_FIXTURE = """<!doctype html><html><body>
<a href="/article/6280063">CERT-UA publishes defensive recommendations</a>
<a href="/article/6280064">Live troop coordinates and deployment report</a>
<a href="/contact-us">Report an incident</a>
</body></html>""".encode("utf-8")

CAC_FIXTURE = """<!doctype html><html><body>
<table><tr><td><a href="/2026-07/03/c_1784822399677167.htm">Public consultation on internet information services</a></td><td>2026-07-03</td></tr></table>
<a href="https://evil.example/not-a-notice">Untrusted notice</a>
</body></html>""".encode("utf-8")

CKAN_FIXTURE = {
    "success": True,
    "result": {
        "count": 2,
        "results": [
            {
                "id": "safe-1",
                "name": "public-cyber-procurement",
                "title": "Public cybersecurity procurement notices",
                "notes": "Metadata for published procurement notices.",
                "metadata_modified": "2026-09-01T12:00:00",
                "organization": {"title": "Public Authority"},
                "tags": [{"name": "кібербезпека"}, {"name": "закупівлі"}],
                "resources": [
                    {"format": "CSV", "url": "https://data.gov.ua/private-resource-not-retained"}
                ],
            },
            {
                "id": "unsafe-1",
                "name": "active-unit-map",
                "title": "Географічні координати та місця дислокації підрозділу",
                "notes": "Live troop coordinates",
                "organization": {"title": "Example"},
                "tags": [],
                "resources": [],
            },
        ],
    },
}


class PublicSourceFabricContract(unittest.TestCase):
    def test_registry_is_fixed_https_and_contains_no_protected_nsa_host(self) -> None:
        self.assertGreaterEqual(len(psf.SOURCES), 8)
        for source_id, spec in psf.SOURCES.items():
            self.assertEqual(source_id, spec.source_id)
            self.assertTrue(spec.url.startswith("https://"), source_id)
            self.assertNotIn("cyber.mil", spec.url)
            self.assertFalse("token=" in spec.url.casefold())
            self.assertFalse("password=" in spec.url.casefold())
            psf._validate_url(spec.url, spec)
        self.assertEqual(psf.POLICY["authority"]["action_authority"], "NONE")
        self.assertEqual(psf.POLICY["content"]["active_force_geolocation"], "PROHIBITED")

    def test_redirect_policy_accepts_only_the_declared_ofac_distribution_host(self) -> None:
        spec = psf.SOURCES["ofac-sdn"]
        allowed = (
            "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/"
            "Published/example/SDN.XML?X-Amz-Signature=redacted"
        )
        self.assertEqual(
            psf._validate_url(allowed, spec, redirect=True),
            "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
        )
        for bad in (
            "http://sanctionslistservice.ofac.treas.gov/SDN.XML",
            "https://evil.example/SDN.XML",
            "https://user:pass@sanctionslistservice.ofac.treas.gov/SDN.XML",
            "https://127.0.0.1/SDN.XML",
        ):
            with self.assertRaises(ValueError, msg=bad):
                psf._validate_url(bad, spec, redirect=True)

    def test_cisa_parser_retains_defensive_metadata_not_payloads(self) -> None:
        spec = psf.SOURCES["cisa-kev"]
        rows = psf._parse_cisa_kev(json.dumps(CISA_FIXTURE).encode(), spec)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["cve"], "CVE-2026-12345")
        self.assertEqual(row["action_authority"], "DEFENSIVE_PRIORITIZATION_ONLY")
        self.assertIn("Apply vendor mitigations", row["required_defensive_action"])
        self.assertNotIn("payload", json.dumps(row).casefold())

    def test_html_index_keeps_public_nsa_advisory_and_drops_other_hosts(self) -> None:
        spec = psf.SOURCES["nsa-advisories"]
        rows = psf._parse_html_index(NSA_FIXTURE, spec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Joint CSA: Defensive Guidance")
        self.assertEqual(rows[0]["published_at"], "2026-08-26")
        self.assertTrue(rows[0]["url"].startswith("https://media.defense.gov/"))

    def test_cia_parser_keeps_only_public_story_records(self) -> None:
        spec = psf.SOURCES["cia-public-stories"]
        parsed = psf._parse_html_index(CIA_FIXTURE, spec)
        safe, excluded = psf._finalize_records(parsed, spec)
        self.assertEqual(len(safe), 1)
        self.assertEqual(safe[0]["title"], "Public Source Intelligence History")
        self.assertTrue(safe[0]["url"].startswith("https://www.cia.gov/stories/story/"))
        self.assertEqual(excluded, [])
        self.assertNotIn("world-factbook", json.dumps(safe).casefold())

    def test_cert_ua_parser_excludes_contact_and_active_force_content(self) -> None:
        spec = psf.SOURCES["cert-ua-advisories"]
        parsed = psf._parse_html_index(CERT_UA_FIXTURE, spec)
        safe, excluded = psf._finalize_records(parsed, spec)
        self.assertEqual(len(safe), 1)
        self.assertEqual(safe[0]["title"], "CERT-UA publishes defensive recommendations")
        self.assertEqual(safe[0]["retrieval_scope"], "INDEX_METADATA_ONLY")
        self.assertEqual(len(excluded), 1)
        serialized = json.dumps(safe).casefold()
        self.assertNotIn("contact-us", serialized)
        self.assertNotIn("troop coordinates", serialized)

    def test_cac_parser_keeps_only_official_public_notice_metadata(self) -> None:
        spec = psf.SOURCES["china-cac-notices"]
        rows = psf._parse_html_index(CAC_FIXTURE, spec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-07-03")
        self.assertTrue(rows[0]["url"].startswith("https://www.cac.gov.cn/2026-07/03/"))
        self.assertEqual(rows[0]["retrieval_scope"], "INDEX_METADATA_ONLY")

    def test_ofac_parser_extracts_names_programs_and_maritime_identifier(self) -> None:
        spec = psf.SOURCES["ofac-sdn"]
        rows = psf._parse_ofac_sdn(OFAC_FIXTURE, spec)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Example Shipping LLC")
        self.assertIn("Example Maritime", row["names"])
        self.assertEqual(row["programs"], ["DPRK3"])
        self.assertEqual(row["identifiers"][0]["value"], "IMO 1234567")
        self.assertEqual(row["action_authority"], "NONE")

    def test_un_parser_extracts_entities_without_addresses_or_dossiers(self) -> None:
        spec = psf.SOURCES["un-dprk-1718"]
        rows = psf._parse_un_sanctions(UN_FIXTURE, spec)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["reference_number"], "KPi.001")
        self.assertIn("Example Alias", rows[0]["names"])
        serialized = json.dumps(rows).casefold()
        self.assertNotIn("address", serialized)
        self.assertNotIn("passport", serialized)

    def test_ckan_parser_never_retains_resource_urls_and_filters_force_locations(self) -> None:
        spec = psf.SOURCES["ukraine-open-data-metadata"]
        parsed = psf._parse_ckan_metadata(json.dumps(CKAN_FIXTURE).encode(), spec)
        safe, excluded = psf._finalize_records(parsed, spec)
        self.assertEqual(len(safe), 1)
        self.assertEqual(safe[0]["title"], "Public cybersecurity procurement notices")
        serialized = json.dumps(safe)
        self.assertNotIn("private-resource-not-retained", serialized)
        self.assertEqual(safe[0]["retrieval_scope"], "CATALOG_METADATA_ONLY_NO_RESOURCE_DOWNLOAD")
        self.assertEqual(len(excluded), 1)

    def test_xml_dtd_and_entities_are_rejected(self) -> None:
        hostile = b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
        with self.assertRaises(ValueError):
            psf._parse_un_sanctions(hostile, psf.SOURCES["un-dprk-1718"])

    def test_live_cache_and_fail_closed_stale_fallback(self) -> None:
        original_root = psf.CACHE_ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                psf.CACHE_ROOT = Path(directory)
                fetched = psf.FetchBytes(
                    body=json.dumps(CISA_FIXTURE).encode(),
                    status=200,
                    final_url=psf.SOURCES["cisa-kev"].url,
                    content_type="application/json",
                    etag='"fixture"',
                    last_modified="Thu, 03 Sep 2026 00:00:00 GMT",
                )
                with mock.patch.object(psf, "_fetch_bytes", return_value=fetched):
                    first = psf.fetch_source("cisa-kev", force=True)
                self.assertEqual(first["mode"], "LIVE")
                self.assertEqual(first["item_count"], 1)

                second = psf.fetch_source("cisa-kev")
                self.assertEqual(second["mode"], "CACHED")
                self.assertEqual(second["content_sha256"], first["content_sha256"])

                cache_path = psf._cache_path("cisa-kev")
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                cache["fetched_epoch"] = time.time() - 99_999
                cache_path.write_text(json.dumps(cache), encoding="utf-8")
                with mock.patch.object(psf, "_fetch_bytes", side_effect=OSError("offline")):
                    stale = psf.fetch_source("cisa-kev")
                self.assertEqual(stale["mode"], "CACHED")
                self.assertIn("OSError", stale["fetch_error"])
        finally:
            psf.CACHE_ROOT = original_root

    def test_sanctions_screen_is_exact_manual_review_and_never_clear(self) -> None:
        fixtures = {
            "ofac-sdn": {
                "source_id": "ofac-sdn",
                "mode": "LIVE",
                "content_sha256": "a" * 64,
                "items": [
                    {
                        "names": ["Example Shipping LLC", "Example Maritime"],
                        "record_sha256": "b" * 64,
                        "entry_uid": "42",
                        "entity_type": "Entity",
                        "programs": ["DPRK3"],
                    }
                ],
            },
            "un-dprk-1718": {
                "source_id": "un-dprk-1718",
                "mode": "LIVE",
                "content_sha256": "c" * 64,
                "items": [],
            },
        }
        with mock.patch.object(psf, "fetch_source", side_effect=lambda source_id: fixtures[source_id]):
            hit = psf.screen_sanctions("  EXAMPLE   MARITIME ")
            miss = psf.screen_sanctions("Unlisted Example")
        self.assertEqual(hit["verdict"], "POSSIBLE_MATCH")
        self.assertEqual(hit["coverage"], "FULL")
        self.assertTrue(hit["manual_review_required"])
        self.assertEqual(hit["action_authority"], "NONE")
        self.assertEqual(miss["verdict"], "NO_EXACT_MATCH")
        self.assertNotEqual(miss["verdict"], "CLEAR")

    def test_fastapi_routes_are_get_only_and_have_no_arbitrary_url_route(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        installed = psf.register(app, ns="killinchu")
        self.assertEqual(len(installed), 5)
        public_routes = [route for route in app.routes if route.path in installed]
        self.assertEqual(len(public_routes), 5)
        for route in public_routes:
            self.assertEqual(route.methods, {"GET"})
            self.assertNotIn("{url}", route.path)
        self.assertIn(
            "/api/killinchu/v1/osint/public/source/{source_id}",
            installed,
        )

    def test_source_contains_no_offensive_network_client_or_shell_execution(self) -> None:
        source = (ROOT / "killinchu_public_source_fabric.py").read_text(encoding="utf-8")
        for prohibited in (
            "subprocess.",
            "os.system(",
            "paramiko",
            "ftplib",
            "socket.create_connection",
            'method="POST"',
            'method="PUT"',
            'method="PATCH"',
            'method="DELETE"',
            "Authorization\": USER",
        ):
            self.assertNotIn(prohibited, source)
        self.assertIn('method="GET"', source)
        self.assertIn("active_force_geolocation", source)
        self.assertIn("action_authority", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
