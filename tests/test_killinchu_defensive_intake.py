# SPDX-License-Identifier: Apache-2.0
"""Offline tests for the fail-closed Killinchu defensive IOC intake."""
from __future__ import annotations

import ast
import asyncio
import copy
import json
from pathlib import Path

import pytest

import killinchu_defensive_intake as intake


class StubRequest:
    def __init__(self, body: bytes, headers=None, chunks=None):
        self._body = body
        self.headers = {
            "content-type": "application/json",
            "content-length": str(len(body)),
        }
        if headers:
            self.headers.update(headers)
        self._chunks = list(chunks) if chunks is not None else [body]
        self.stream_called = False

    async def stream(self):
        self.stream_called = True
        for chunk in self._chunks:
            yield chunk


def _request(payload, **kwargs):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return StubRequest(body, **kwargs)


def _payload(**overrides):
    payload = {
        "authorization_ref": "IR-2026-0042",
        "indicators": [
            {"type": "domain", "value": "Example.COM."},
            {"type": "ipv4", "value": "203.0.113.7"},
            {"type": "ipv6", "value": "2001:0DB8:0:0:0:0:0:1"},
            {"type": "url", "value": "HTTPS://EXAMPLE.COM:443/a?b=2#fragment"},
            {"type": "cve", "value": "cve-2026-12345"},
            {"type": "domain", "value": "example.com"},
        ],
        "adapters": ["network-scan-report-review"],
    }
    payload.update(overrides)
    return payload


def _assert_error(payload, code, status_code=None):
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        intake.build_defensive_plan(payload)
    assert captured.value.code == code
    if status_code is not None:
        assert captured.value.status_code == status_code


def test_normalizes_deduplicates_and_never_resolves_iocs():
    plan = intake.build_defensive_plan(_payload())

    assert plan["external_execution_state"] == "NOT_PERFORMED"
    assert plan["indicators"] == [
        {"type": "cve", "value": "CVE-2026-12345"},
        {"type": "domain", "value": "example.com"},
        {"type": "ipv4", "value": "203.0.113.7"},
        {"type": "ipv6", "value": "2001:db8::1"},
        {"type": "url", "value": "https://example.com/a?b=2"},
    ]
    assert plan["indicator_summary"] == {
        "input_count": 6,
        "unique_count": 5,
        "by_type": {"cve": 1, "domain": 1, "ipv4": 1, "ipv6": 1, "url": 1},
    }
    assert plan["selected_adapters"] == [
        "ioc-normalize",
        "network-scan-report-review",
    ]


def test_inference_is_conservative_and_idna_is_canonical():
    normalized = intake.normalize_indicators(
        [
            "198.51.100.9",
            "CVE-2025-9999",
            "Exämple.COM.",
            "A" * 64,
        ]
    )
    assert normalized == [
        {"type": "cve", "value": "CVE-2025-9999"},
        {"type": "domain", "value": "xn--exmple-cua.com"},
        {"type": "ipv4", "value": "198.51.100.9"},
        {"type": "sha256", "value": "a" * 64},
    ]
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        intake.normalize_indicator("not-an-unambiguous-ioc")
    assert captured.value.code == "UNKNOWN_INDICATOR_TYPE"


@pytest.mark.parametrize(
    "bad_indicator,code",
    [
        ({"type": "domain", "value": "single-label"}, "INVALID_DOMAIN"),
        ({"type": "ipv4", "value": "2001:db8::1"}, "IP_VERSION_MISMATCH"),
        ({"type": "ipv6", "value": "fe80::1%eth0"}, "INVALID_IP"),
        ({"type": "url", "value": "ftp://example.com/a"}, "INVALID_URL"),
        (
            {"type": "url", "value": "https://user:secret@example.com/a"},
            "CREDENTIALS_REJECTED",
        ),
        ({"type": "sha256", "value": "not-a-hash"}, "INVALID_HASH"),
        ({"type": "cve", "value": "CVE-26-1"}, "INVALID_CVE"),
        ({"type": "domain", "value": "example.com", "option": "unsafe"},
         "UNKNOWN_INDICATOR_FIELD"),
    ],
)
def test_malformed_indicators_fail_closed(bad_indicator, code):
    _assert_error(_payload(indicators=[bad_indicator]), code)


def test_unknown_fields_and_command_shaped_input_fail_closed():
    _assert_error(
        _payload(command="scanner --target 203.0.113.7"),
        "UNKNOWN_PAYLOAD_FIELD",
    )
    _assert_error(
        _payload(credentials={"token": "must-not-be-accepted"}),
        "UNKNOWN_PAYLOAD_FIELD",
    )


def test_disallowed_and_duplicate_adapters_fail_closed():
    _assert_error(_payload(adapters=["shell-runner"]), "ADAPTER_NOT_ALLOWLISTED")
    _assert_error(
        _payload(adapters=["ioc-normalize", "ioc-normalize"]),
        "DUPLICATE_ADAPTER",
    )


def test_oversized_inputs_fail_closed_before_a_plan_is_emitted():
    _assert_error(
        _payload(indicators=["example.com"] * (intake.MAX_INDICATORS + 1)),
        "TOO_MANY_INDICATORS",
        413,
    )
    _assert_error(
        _payload(
            indicators=[
                {
                    "type": "domain",
                    "value": "a" * (intake.MAX_INDICATOR_VALUE_BYTES + 1),
                }
            ]
        ),
        "INDICATOR_TOO_LARGE",
        413,
    )
    too_large = _payload()
    too_large["unrecognized"] = "x" * intake.MAX_PAYLOAD_BYTES
    _assert_error(too_large, "PAYLOAD_TOO_LARGE", 413)


@pytest.mark.parametrize(
    "payload,code",
    [
        ([], "INVALID_PAYLOAD"),
        ({}, "INVALID_AUTHORIZATION_REF"),
        ({"authorization_ref": "IR-1", "indicators": "example.com"},
         "INVALID_INDICATORS"),
        ({"authorization_ref": "contains spaces", "indicators": ["example.com"]},
         "INVALID_AUTHORIZATION_REF"),
        ({"authorization_ref": "IR-1", "indicators": []}, "INVALID_INDICATORS"),
    ],
)
def test_malformed_envelopes_fail_closed(payload, code):
    _assert_error(payload, code)


def test_receipt_digest_is_deterministic_and_detects_tampering():
    adapters = ["network-scan-report-review", "antimalware-report-review"]
    left = _payload(adapters=adapters)
    right = _payload(
        indicators=list(reversed(left["indicators"])),
        adapters=list(reversed(adapters)),
    )
    plan_left = intake.build_defensive_plan(left)
    plan_right = intake.build_defensive_plan(right)

    assert plan_left == plan_right
    digest = plan_left["receipt"]["subject"]["digest"]["sha256"]
    assert len(digest) == 64
    assert intake.verify_plan_receipt(plan_left) == (
        True,
        "CONTENT_DIGEST_VERIFIED_UNSIGNED",
    )
    assert plan_left["receipt"]["signed"] is False
    assert plan_left["receipt"]["authenticity"] == "NOT_ESTABLISHED"
    assert plan_left["selected_adapters"] == [
        "ioc-normalize",
        "antimalware-report-review",
        "network-scan-report-review",
    ]

    tampered = copy.deepcopy(plan_left)
    tampered["indicators"][0]["value"] = "CVE-2026-99999"
    assert intake.verify_plan_receipt(tampered) == (False, "DIGEST_MISMATCH")


def test_authorization_reference_is_only_retained_as_a_digest():
    authorization_ref = "CASE-PRIVATE-2026-77"
    plan = intake.build_defensive_plan(_payload(authorization_ref=authorization_ref))
    serialized = json.dumps(plan, sort_keys=True)
    assert authorization_ref not in serialized
    assert plan["authorization"]["verification"] == "NOT_PERFORMED_REFERENCE_ONLY"


def test_registry_is_default_deny_inert_and_clean_room():
    registry = intake.tool_registry_document()
    assert registry["policy"]["default_deny"] is True
    assert registry["policy"]["scanner_execution"] == "DISABLED"
    assert registry["policy"]["live_scanning"] is False
    assert registry["sandbox_boundary"]
    assert all(value is False for value in registry["sandbox_boundary"].values())

    adapter_ids = {adapter["id"] for adapter in registry["adapters"]}
    assert adapter_ids == {
        "ioc-normalize",
        "network-scan-report-review",
        "file-rule-report-review",
        "antimalware-report-review",
    }
    for adapter in registry["adapters"]:
        assert adapter["network_access"] is False
        assert adapter["accepts_live_targets"] is False
        assert adapter["execution_capability"] in {"NONE", "MEMORY_ONLY"}
        assert not ({"command", "args", "binary", "endpoint", "environment"} & adapter.keys())

    provenance = registry["provenance_review"]
    assert provenance["implementation"] == "SZL_CLEAN_ROOM"
    assert provenance["third_party_code_embedded"] is False
    assert provenance["third_party_content_embedded"] is False
    assert all(source["embedded"] is False for source in provenance["reviewed_sources"])
    licenses = {source["observed_license"] for source in provenance["reviewed_sources"]}
    assert "Apache-2.0" in licenses
    assert "CC-BY-NC-SA-4.0" in licenses


def test_module_has_no_network_process_shell_or_filesystem_effect_imports():
    source_path = Path(intake.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert roots.isdisjoint(
        {
            "aiohttp",
            "ftplib",
            "httpx",
            "paramiko",
            "requests",
            "shutil",
            "smtplib",
            "socket",
            "ssl",
            "subprocess",
            "telnetlib",
        }
    )
    assert called_names.isdisjoint(
        {"open", "Popen", "run", "system", "spawn", "urlopen", "create_connection"}
    )


@pytest.mark.parametrize(
    "headers,code,status",
    [
        ({"content-type": "text/plain"}, "JSON_CONTENT_TYPE_REQUIRED", 415),
        ({"content-type": ""}, "JSON_CONTENT_TYPE_REQUIRED", 415),
        ({"content-encoding": "gzip"}, "CONTENT_ENCODING_REJECTED", 415),
        ({"content-length": "not-a-number"}, "INVALID_CONTENT_LENGTH", 400),
        ({"content-length": "-1"}, "INVALID_CONTENT_LENGTH", 400),
    ],
)
def test_raw_request_metadata_fails_closed(headers, code, status):
    request = _request(_payload(), headers=headers)
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(request))
    assert captured.value.code == code
    assert captured.value.status_code == status


def test_missing_content_length_uses_the_same_bounded_stream_path():
    request = _request(_payload())
    del request.headers["content-length"]
    parsed = asyncio.run(intake.read_bounded_json_request(request))
    assert parsed == _payload()
    assert request.stream_called is True


def test_missing_content_length_cannot_bypass_stream_limit():
    oversized_chunk = b"x" * (intake.MAX_PAYLOAD_BYTES + 1)
    request = StubRequest(b"x", chunks=[oversized_chunk])
    del request.headers["content-length"]
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(request))
    assert captured.value.code == "PAYLOAD_TOO_LARGE"
    assert captured.value.status_code == 413


def test_oversized_declared_body_fails_before_body_read():
    request = StubRequest(
        b"{}", headers={"content-length": str(intake.MAX_PAYLOAD_BYTES + 1)}
    )
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(request))
    assert captured.value.code == "PAYLOAD_TOO_LARGE"
    assert captured.value.status_code == 413
    assert request.stream_called is False


def test_lying_length_cannot_bypass_stream_limit():
    oversized_chunk = b"x" * (intake.MAX_PAYLOAD_BYTES + 1)
    request = StubRequest(
        b"x", headers={"content-length": "1"}, chunks=[oversized_chunk]
    )
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(request))
    assert captured.value.code == "PAYLOAD_TOO_LARGE"
    assert captured.value.status_code == 413


def test_content_length_mismatch_and_malformed_json_fail_closed():
    mismatch = StubRequest(b"{}", headers={"content-length": "1"})
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(mismatch))
    assert captured.value.code == "CONTENT_LENGTH_MISMATCH"

    malformed = StubRequest(b"{not-json}")
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        asyncio.run(intake.read_bounded_json_request(malformed))
    assert captured.value.code == "MALFORMED_JSON"


def test_duplicate_json_keys_are_rejected_at_every_object_depth():
    duplicate_top = (
        b'{"authorization_ref":"IR-1","authorization_ref":"IR-2",'
        b'"indicators":["example.com"]}'
    )
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        intake.parse_json_body(duplicate_top)
    assert captured.value.code == "DUPLICATE_JSON_KEY"

    duplicate_nested = (
        b'{"authorization_ref":"IR-1","indicators":'
        b'[{"type":"domain","type":"url","value":"example.com"}]}'
    )
    with pytest.raises(intake.DefensiveIntakeError) as captured:
        intake.parse_json_body(duplicate_nested)
    assert captured.value.code == "DUPLICATE_JSON_KEY"


def test_register_exposes_only_registry_and_plan_routes():
    class StubApp:
        def __init__(self):
            self.routes = {}

        def get(self, path):
            return self._decorator("GET", path)

        def post(self, path):
            return self._decorator("POST", path)

        def _decorator(self, method, path):
            def decorate(handler):
                self.routes[(method, path)] = handler
                return handler

            return decorate

    app = StubApp()
    registered = intake.register(app, ns="killinchu")
    assert registered["scanner_execution"] == "DISABLED"
    assert set(app.routes) == {
        ("GET", "/api/killinchu/v1/defensive-intake/tools"),
        ("POST", "/api/killinchu/v1/defensive-intake/plan"),
    }
    handler = app.routes[("POST", "/api/killinchu/v1/defensive-intake/plan")]
    response = asyncio.run(handler(_request(_payload())))
    assert response["external_execution_state"] == "NOT_PERFORMED"


def test_real_fastapi_transport_preserves_bounded_request_contract():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    intake.register(app, ns="killinchu")
    client = TestClient(app)

    success = client.post(
        "/api/killinchu/v1/defensive-intake/plan", json=_payload()
    )
    assert success.status_code == 200
    assert success.json()["external_execution_state"] == "NOT_PERFORMED"

    duplicate = client.post(
        "/api/killinchu/v1/defensive-intake/plan",
        content=(
            b'{"authorization_ref":"IR-1","authorization_ref":"IR-2",'
            b'"indicators":["example.com"]}'
        ),
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json() == {
        "ok": False,
        "error": {
            "code": "DUPLICATE_JSON_KEY",
            "message": "duplicate JSON object keys are rejected",
        },
        "external_execution_state": "NOT_PERFORMED",
    }
