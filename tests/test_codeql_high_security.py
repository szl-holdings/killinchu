# SPDX-License-Identifier: Apache-2.0
"""Adversarial regressions for the high-severity CodeQL findings."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import killinchu_cot_interop as cot
import szl_connectors.governance as governance
import szl_connectors.oauth as oauth
import szl_dsse
from szl_connectors.base import cred_fingerprint
from szl_safe_static import RootedStaticFiles


VALID_COT = (
    '<event version="2.0" uid="security-test" type="a-f-A" '
    'time="2026-01-01T00:00:00Z" start="2026-01-01T00:00:00Z" '
    'stale="2026-01-01T00:02:00Z" how="m-g">'
    '<point lat="1" lon="2" hae="3" ce="4" le="5"/>'
    '<detail><contact callsign="TEST"/></detail></event>'
)


def _scope() -> dict:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }


def test_rooted_static_files_blocks_traversal_absolute_paths_and_symlinks(tmp_path: Path):
    root = tmp_path / "public"
    root.mkdir()
    (root / "ok.txt").write_text("public", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("never serve", encoding="utf-8")
    files = RootedStaticFiles(root)

    valid = asyncio.run(files.get("ok.txt", _scope()))
    assert valid is not None
    assert Path(valid.path).resolve() == (root / "ok.txt").resolve()
    for attack in (
        "../secret.txt", "..\\secret.txt", str(secret.resolve()), "Z:\\escape.txt",
    ):
        assert asyncio.run(files.get(attack, _scope())) is None

    link = root / "escape.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    assert asyncio.run(files.get("escape.txt", _scope())) is None


def test_cookbook_route_uses_index_and_fixed_mission_allowlists():
    from szl_killinchu_cookbook import register_cookbook

    app = FastAPI()
    register_cookbook(app)
    client = TestClient(app)

    assert client.get("/api/killinchu/v2/missions/P1").status_code == 200
    assert client.get(
        "/api/killinchu/v2/cookbook/recipe-decode-remote-id"
    ).status_code == 200
    for attack in (
        "..%5C..%5Crequirements",
        "%2E%2E%5CDockerfile",
        "P1.json%00",
    ):
        mission = client.get(f"/api/killinchu/v2/missions/{attack}")
        recipe = client.get(f"/api/killinchu/v2/cookbook/{attack}")
        assert mission.status_code == 404
        assert recipe.status_code == 404


def test_cot_valid_event_round_trips_through_hardened_parser():
    ok, errors = cot.validate_xml_string(VALID_COT)
    assert ok, errors
    track = cot.cot_xml_to_track(VALID_COT)
    assert track["track_id"] == "security-test"
    assert track["lat"] == 1.0


@pytest.mark.parametrize(
    "malicious",
    [
        (
            '<!DOCTYPE event [<!ENTITY x "expanded">]>'
            + VALID_COT.replace("<detail>", "<detail><remarks>&x;</remarks>")
        ),
        (
            '<!DOCTYPE event [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            + VALID_COT.replace("<detail>", "<detail><remarks>&x;</remarks>")
        ),
    ],
)
def test_cot_rejects_dtd_internal_and_external_entities(malicious: str):
    ok, errors = cot.validate_xml_string(malicious)
    assert not ok
    assert errors
    with pytest.raises(ValueError):
        cot.cot_xml_to_track(malicious)


def test_cot_rejects_excess_elements_depth_and_bytes():
    many_elements = VALID_COT.replace(
        "</detail>", "<x/>" * cot.MAX_COT_XML_ELEMENTS + "</detail>"
    )
    ok, errors = cot.validate_xml_string(many_elements)
    assert not ok
    assert "element limit" in errors[0]

    nested = VALID_COT.replace(
        "</detail>",
        "<x>" * cot.MAX_COT_XML_DEPTH + "</x>" * cot.MAX_COT_XML_DEPTH + "</detail>",
    )
    ok, errors = cot.validate_xml_string(nested)
    assert not ok
    assert "depth limit" in errors[0]

    oversized = "<event>" + "x" * cot.MAX_COT_XML_BYTES + "</event>"
    ok, errors = cot.validate_xml_string(oversized)
    assert not ok
    assert "byte limit" in errors[0]


def test_cot_ingest_errors_are_generic_and_do_not_expose_exceptions(caplog):
    app = FastAPI()
    cot.register(app)
    client = TestClient(app)

    caplog.set_level("INFO", logger=cot.__name__)
    oversized = client.post(
        "/api/killinchu/v1/cot/ingest",
        content=b"x" * (cot.MAX_COT_XML_BYTES + 1),
        headers={"content-type": "application/xml"},
    )
    assert oversized.status_code == 413
    assert oversized.json() == {"ok": False, "error": "CoT XML payload too large"}

    invalid_encoding = client.post(
        "/api/killinchu/v1/cot/ingest",
        content=b"\xffsecret-stack-marker",
        headers={"content-type": "application/xml"},
    )
    assert invalid_encoding.status_code == 400
    assert invalid_encoding.json() == {"ok": False, "error": "CoT XML must be UTF-8"}
    assert "secret-stack-marker" not in invalid_encoding.text

    malformed = client.post(
        "/api/killinchu/v1/cot/ingest",
        content=b"<event><secret-stack-marker></event>",
        headers={"content-type": "application/xml"},
    )
    assert malformed.status_code == 400
    assert malformed.json() == {"ok": False, "error": "invalid CoT XML"}
    assert "secret-stack-marker" not in malformed.text

    assert "Rejected oversized CoT ingest" in caplog.text
    assert "Rejected non-UTF-8 CoT ingest" in caplog.text
    assert "Rejected invalid CoT ingest" in caplog.text


def test_governance_recursively_scrubs_secrets_and_validates_fingerprints(monkeypatch):
    monkeypatch.setattr(governance, "_now", lambda: "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(governance, "_dsse_sign", lambda body: {"body": body})
    good_fp = cred_fingerprint("runtime-only-secret")
    receipt = governance.receipt_for_write(
        connector_id="test",
        action={
            "method": "write",
            "payload": {"rows": [{"client_secret": "raw-action-secret", "ok": True}]},
        },
        lambda_value=0.9,
        cred_fingerprints={
            "password": good_fp,
            "access_token": "raw-fingerprint-secret",
            "bad label with spaces": "another-secret",
        },
        result_summary={"nested": {"authorization": "Bearer raw-result-secret", "ok": True}},
    )

    serialized = json.dumps(receipt, sort_keys=True)
    assert "raw-action-secret" not in serialized
    assert "raw-result-secret" not in serialized
    assert "raw-fingerprint-secret" not in serialized
    assert receipt["body"]["action"]["payload"]["rows"] == [{"ok": True}]
    assert receipt["body"]["result"] == {"nested": {"ok": True}}
    assert receipt["body"]["credential_fingerprints"] == {
        "password": good_fp,
        "access_token": "invalid-fingerprint",
    }


def test_governance_gate_refuses_nested_secret_and_receipt_hash_is_compatible(monkeypatch):
    monkeypatch.setattr(governance, "_now", lambda: "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(governance, "_dsse_sign", lambda body: {"body": body})
    allowed, _, receipt, _, detail = governance.gate_write(
        connector_id="test",
        connected=True,
        action={"method": "write", "nested": [{"password": "raw-password"}]},
    )
    assert not allowed
    assert "raw secret" in detail
    assert "raw-password" not in json.dumps(receipt)

    compatible = governance.receipt_for_write(
        connector_id="test",
        action={"method": "write", "object": "record", "count": 1},
        lambda_value=0.9,
        cred_fingerprints={"token": cred_fingerprint("value")},
        result_summary={"allowed": True},
    )
    unhashed = dict(compatible["body"])
    unhashed.pop("receipt_hash")
    expected = hashlib.sha256(
        json.dumps(unhashed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert compatible["receipt_hash"] == f"sha256:{expected}"


def test_credential_and_oauth_secrets_use_pbkdf2(monkeypatch):
    monkeypatch.setenv("SZL_FINGERPRINT_PEPPER", "test-pepper")
    first = cred_fingerprint("password123")
    second = cred_fingerprint("password123")
    assert first == second
    assert first.startswith("pbkdf2-sha256:")
    assert first.removeprefix("pbkdf2-sha256:") != hashlib.sha256(
        b"password123"
    ).hexdigest()[:32]

    monkeypatch.setenv("SZL_OAUTH_STATE_SECRET", "state-secret")
    oauth._STATE_KEY_CACHE.clear()
    expected_key = hashlib.pbkdf2_hmac(
        "sha256",
        b"state-secret",
        oauth._STATE_KDF_SALT,
        oauth._STATE_KDF_ITERATIONS,
    )
    assert oauth._state_secret() == expected_key
    state = oauth.sign_state("salesforce", "nonce", ts=int(time.time()))
    assert oauth.verify_state(state, "salesforce")[0] is True


def test_dsse_pae_content_address_stays_byte_compatible(monkeypatch):
    for name in szl_dsse.PRIVATE_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    env = szl_dsse.sign_payload({"scope": "public", "unicode": "Perú"})
    body = base64.b64decode(env["payload"])
    expected = hashlib.sha256(szl_dsse.pae(env["payloadType"], body)).hexdigest()
    assert env["_pae_sha256"] == expected
