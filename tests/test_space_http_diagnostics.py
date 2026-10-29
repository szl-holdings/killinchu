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
    # The scoped answer hydrator is the next explicit RAG source generation.
    # Preserve every predecessor byte and retain every unrelated runtime pin.
    previous_guard = (root / ".github/shared-source-payloads/"
                      "agent-loop-execution-guards-20261008-v1.json").read_bytes()
    assert hashlib.sha256(previous_guard).hexdigest() == (
        "bb60cb1ee4ec606edb79f381ca2235349fbc298f14713bd6a0104958b6eaa8ac"
    )
    handoff_raw = (root / ".github/shared-source-payloads/"
                   "authorized-rag-answer-handoff-20261008-v1.json").read_bytes()
    assert hashlib.sha256(handoff_raw).hexdigest() == (
        "6e4138d0c4901ad60cfb93fed81d7f3737c02d78c4fd13befe137d02c84c7c13"
    )
    handoff = json.loads(handoff_raw)
    assert handoff["schema"] == "szl-shared-source-payload/v1"
    assert handoff["payload_id"] == "authorized-rag-answer-handoff-20261008-v1"
    rag_successor = "dbeca108e10a40210db375b66f9411efd347c8188643a65c6df6987aa80fb26d"
    assert handoff["files"]["a11oy_org_rag.py"] == rag_successor
    # The explicit lexical-only reference mode is the next RAG source generation.
    # Its manifest pins the archived handoff above byte-for-byte. A later pair
    # replaced the active slot, so this proof is read from its immutable archive.
    lexical_raw = (root / ".github/shared-source-payloads/"
                   "org-rag-lexical-reference-20261013-v1.json").read_bytes()
    assert hashlib.sha256(lexical_raw).hexdigest() == (
        "65f404ffe7c235d6a549ccd608761e1f4ed0101d074590d1e50e6fb12e115b7a"
    )
    lexical = json.loads(lexical_raw)
    lexical_successor = "0c98b17b37f5013a0a77aaccd71405d5be57dd37a0af4dceeff4f46f0982f227"
    assert lexical == {
        "files": {
            ".github/shared-source-payloads/authorized-rag-answer-handoff-20261008-v1.json":
                "6e4138d0c4901ad60cfb93fed81d7f3737c02d78c4fd13befe137d02c84c7c13",
            "a11oy_org_rag.py": lexical_successor,
        },
        "payload_id": "org-rag-lexical-reference-20261013-v1",
        "schema": "szl-shared-source-payload/v1",
    }
    expected["a11oy_org_rag.py"] = lexical_successor
    # Evaluation admission adds the operator gate without rewriting historical
    # manifests. Bind this reviewed successor and retain every unrelated pin.
    assert expected["szl_operator_auth.py"] == (
        "86ed8b445c05f26c66c8d41dba09fe889970aad0e091090efe795299b9336539"
    )
    expected["szl_operator_auth.py"] = (
        "38880e4b02658718dd8d69070a4edd2d4abca7793c535ecc95978e5a35a3a8d7"
    )
    # The paired observation/native-write repair is an explicit successor to
    # evaluation admission. Historical manifests and unrelated pins stay fixed.
    admission_raw = (root / ".github/shared-source-payloads/"
                     "execution-observer-operator-auth-20261016-v1.json").read_bytes()
    assert hashlib.sha256(admission_raw).hexdigest() == (
        "7dbf4ab396a4add29d22e7870951198accb3833f7feb32e8eebf6b7906ce8f1c"
    )
    admission = json.loads(admission_raw)
    assert admission["payload_id"] == "execution-observer-operator-auth-20261016-v1"
    assert admission["files"]["szl_operator_auth.py"] == (
        "5b511c270ebb0268974f144e2dc4d3754ad48803a9434f6976eb8c1681265c0d"
    )
    expected["szl_operator_auth.py"] = admission["files"]["szl_operator_auth.py"]
    # Snapshot replication adds the paired explicit-dispatch gates. Preserve the
    # historical admission above and bind this reviewed source successor exactly.
    expected["szl_operator_auth.py"] = (
        "c06458a8c846cdd2ff75efaf2dba06e3a9b9b996465e1035531c2715c73d13c6"
    )
    # Atlas retention is a new shared-source generation. Keep the 2026-10-03
    # payload immutable and bind the current shared surface and policy bytes.
    atlas_raw = (root / ".github/shared-source-payloads/"
                 "atlas-retention-space-policy-20261028-v1.json").read_bytes()
    atlas = json.loads(atlas_raw)
    assert atlas["schema"] == "szl-shared-source-payload/v1"
    assert atlas["payload_id"] == "atlas-retention-space-policy-20261028-v1"
    assert atlas["files"] == {
        ".github/shared-source-payloads/"
        "restraint-active-signer-space-policy-20261003-v1.json":
            "06f15a69fa4c6691e2547cdd9ed6af9459d8667134e2057e6cfe313c341a20ce",
        "docs/estate/hf-nine-flagship-keep.yaml":
            "dc217b5804c330f89009ee38c71f3a5b6b59e42b9895b0d4ff48db9647369d2e",
        "szl_spaces_surface.py":
            "6125466150f6b6b351a440ab04d22c1540c41ca01dbffe7b0414a1d06e42ee0d",
    }
    expected.update(atlas["files"])
    for relative, digest in expected.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest


def test_current_keep_policy_does_not_clear_extra_public_spaces():
    expected = {
        "a11oy", "killinchu", "terra", "counsel", "finance", "lyte",
        "curation-atlas", "david-leads", "szl-foundation-confirmation",
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
    assert inventory["canonical_count"] == 9
    assert inventory["configured_runtime_count"] == 5
    assert inventory["observed_count"] == 10
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
