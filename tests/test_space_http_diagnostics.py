# SPDX-License-Identifier: Apache-2.0
"""Offline regression of the shared public HTTP diagnostic boundary."""
import asyncio
import io
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest
import szl_spaces_surface as surface


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
