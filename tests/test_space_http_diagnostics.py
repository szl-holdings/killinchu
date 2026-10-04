# SPDX-License-Identifier: Apache-2.0
"""Offline regression of the shared public HTTP diagnostic boundary."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest
import szl_spaces_surface as surface


def test_shared_http_payload_is_content_bound():
    root = Path(__file__).resolve().parents[1]
    # The active admission manifest changes with each paired contribution.
    # Preserve this prior proof and every runtime digest at an immutable path.
    raw = (root / ".github/shared-source-payloads/"
           "restraint-active-signer-space-policy-20261003-v1.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "06f15a69fa4c6691e2547cdd9ed6af9459d8667134e2057e6cfe313c341a20ce"
    )
    payload = json.loads(raw)
    assert payload == {
        "files": {
            "szl_operator_auth.py":
                "1ee6a88e37d522c5404ac04ac90eadcbfc6f7e59140a778d03275832e217e2cf",
            "szl_restraint.py":
                "f8cb46ae49066785fd3b7a4ef74635d1559a0772711ba3d26e169b6eb99c62b0",
            "szl_spaces_proxy.py":
                "d3d79e9ca6dfe551001e4dab4d3eaa09fbcac83e5dcfc578069eb65e7992d380",
            "szl_spaces_surface.py":
                "b56a1225f883bc25430ab559e72b187e5eed53ffa1fefd5a69ae98fa71ba179a",
        },
        "payload_id": "restraint-active-signer-space-policy-20261003-v1",
        "schema": "szl-shared-source-payload/v1",
    }
    # A later paired contribution may replace a shared file. Bind that new
    # generation explicitly while retaining this original manifest unchanged.
    current_raw = (root / ".github/shared-source-payloads/"
                   "estate-rag-operator-auth-20261004-v1.json").read_bytes()
    assert hashlib.sha256(current_raw).hexdigest() == (
        "e0b02c5a579eb8be1ca4d896f09a6a14c1a0e2796442428efa626872fbb62c61"
    )
    current = json.loads(current_raw)
    assert current["schema"] == "szl-shared-source-payload/v1"
    assert current["payload_id"] == "estate-rag-operator-auth-20261004-v1"
    assert set(current["files"]) == {
        "a11oy_org_rag.py", "szl_hf_bucket.py", "szl_operator_auth.py",
        "test_szl_hf_bucket.py",
    }
    storage_raw = (root / ".github/shared-source-payloads/"
                   "estate-rag-operator-auth-20261004-v2.json").read_bytes()
    assert hashlib.sha256(storage_raw).hexdigest() == (
        "ca5e677d22c1b072b1ae5c6e404ecf063dabfac51f17f27d35fc014eecdbf7bf"
    )
    storage = json.loads(storage_raw)
    assert storage["schema"] == "szl-shared-source-payload/v1"
    assert storage["payload_id"] == "estate-rag-operator-auth-20261004-v2"
    assert set(storage["files"]) == set(current["files"])
    expected = {**payload["files"], **current["files"], **storage["files"]}
    for relative, digest in expected.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest


def test_current_keep_policy_does_not_clear_extra_public_spaces():
    expected = {
        "a11oy", "killinchu", "terra", "counsel", "finance", "lyte",
        "david-leads", "szl-foundation-confirmation",
    }
    assert surface.PUBLIC_ORG_KEEP_POLICY == expected
    assert len(surface.SPACES) == 5

    class Client:
        async def get(self, *_args, **_kwargs):
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"id": "SZLHOLDINGS/" + name}
                              for name in sorted(expected | {"README", "extra"})],
            )

    inventory = asyncio.run(surface._probe_inventory(Client()))
    assert inventory["canonical_count"] == 8
    assert inventory["configured_runtime_count"] == 5
    assert inventory["observed_count"] == 9
    assert inventory["missing"] == []
    assert inventory["unexpected"] == ["extra"]
    assert inventory["state"] == "DEGRADED"


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 503])
@pytest.mark.parametrize("want_json", [False, True])
def test_http_error_retains_status_without_body_or_message(monkeypatch, status, want_json):
    class UnreadableBody(io.BytesIO):
        def read(self, *args, **kwargs):
            raise AssertionError("untrusted error body must not be read")

    body = UnreadableBody(b"untrusted body")

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://unit.invalid", status, "untrusted", {}, body)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert surface._urllib_probe("https://unit.invalid", 1, want_json) == (status, None)
    assert body.closed


@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (404, 1), (429, 2), (500, 2), (503, 2)])
def test_status_drives_unchanged_contract_retry_policy(monkeypatch, status, attempts):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://unit.invalid/health", status, "untrusted", {}, io.BytesIO())

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(surface, "_CONTRACT_CIRCUITS", {})
    contract = {"id": "http-status-" + str(status), "url": "https://unit.invalid/health", "expected": {"ok": True}}
    result = asyncio.run(surface._probe_contract(None, contract))
    assert result["state"] == "UNAVAILABLE"
    assert result["http_status"] == status
    assert result["error"] == "HTTPStatus"
    assert result["attempts"] == len(calls) == attempts


@pytest.mark.parametrize("status", [200, 204, 299, 300, 301, 401, 403, 404, 429, 500, 503])
@pytest.mark.parametrize("transport", ["httpx-head", "httpx-get", "urllib"])
def test_liveness_consistent_across_adapters(monkeypatch, status, transport):
    class Client:
        async def request(self, *args, **kwargs):
            if transport == "httpx-get":
                raise TimeoutError("isolated HEAD failure")
            return SimpleNamespace(status_code=status)

        async def get(self, url, **kwargs):
            if url.startswith("https://huggingface.co/api/"):
                return SimpleNamespace(status_code=200, json=lambda: {"runtime": {"stage": "RUNNING"}})
            return SimpleNamespace(status_code=status)

    def probe(url, timeout, want_json=False):
        if url.startswith("https://huggingface.co/api/"):
            return 200, {"runtime": {"stage": "RUNNING"}}
        return status, None

    async def no_contracts(*args):
        return []

    monkeypatch.setattr(surface, "_urllib_probe", probe)
    monkeypatch.setattr(surface, "_probe_contracts", no_contracts)
    result = asyncio.run(surface._probe_one(None if transport == "urllib" else Client(), surface.SPACES[0]))
    assert result["app_status"] == status
    assert result["app_reachable"] is (200 <= status < 300)
    assert result["probe_via"] == ("urllib" if transport == "urllib" else "httpx")


def test_transport_failure_does_not_invent_status(monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError("isolated")

    monkeypatch.setattr(urllib.request, "urlopen", timeout)
    with pytest.raises(TimeoutError):
        surface._urllib_probe("https://unit.invalid", 1)
