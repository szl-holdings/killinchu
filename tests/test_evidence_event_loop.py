"""Evidence source checks must not stall unrelated FastAPI requests."""

import asyncio
import threading
import time

import httpx
import pytest
from fastapi import FastAPI

import szl_evidence_research as evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/killinchu/v1/evidence/research/claim/live",
        "/api/killinchu/v1/evidence/research/claim/sources/live",
        "/api/killinchu/v1/evidence/research/refresh",
    ],
)
async def test_slow_evidence_source_does_not_block_health(path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def slow_sources(_sources):
        entered.set()
        assert release.wait(2), "the source check was never released"
        return [{"reachable": True, "http_status": 200, "mode": "live"}]

    claim = {
        "id": "claim",
        "claim": "A source-bound claim",
        "sources": [{"kind": "official", "title": "Source", "url": "https://example.org"}],
        "github": [],
        "arxiv_query": "claim",
    }
    monkeypatch.setattr(evidence, "_claims_for", lambda _namespace: [claim])
    monkeypatch.setattr(evidence, "_sources_live", slow_sources)
    monkeypatch.setattr(evidence, "_arxiv", lambda *_args, **_kwargs: {"count": 0, "mode": "unreachable"})
    monkeypatch.setattr(evidence, "_start_warmer", lambda: None)

    app = FastAPI()
    evidence.register(app, ns="killinchu")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # The fallback timer also makes the test fail promptly against the old
        # async handlers, where a blocking source check occupied the event loop.
        timer = threading.Timer(1, release.set)
        timer.start()
        evidence_task = asyncio.create_task(client.get(path))
        try:
            assert await asyncio.to_thread(entered.wait, 1.5)
            assert not release.is_set(), "evidence blocked the event loop until the source check ended"
            health = await asyncio.wait_for(client.get("/healthz"), timeout=0.5)
            assert health.status_code == 200
            assert health.json() == {"ok": True}
            assert not release.is_set(), "health replied only after the source check ended"
        finally:
            release.set()
            timer.cancel()
            response = await asyncio.wait_for(evidence_task, timeout=2)
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_index_uses_observations_without_network(monkeypatch):
    """The summary must answer promptly on a cold cache and mark unknown probes."""
    claim = {
        "id": "claim",
        "claim": "A source-bound claim",
        "sources": [{"kind": "official", "title": "Source", "url": "https://example.org"}],
        "github": [],
    }
    monkeypatch.setattr(evidence, "_CACHE", {})
    monkeypatch.setattr(evidence, "_disk_load", lambda: None)
    monkeypatch.setattr(evidence, "_start_warmer", lambda: None)
    monkeypatch.setattr(evidence, "_claims_for", lambda _namespace: [claim])

    def forbidden_probe(_sources):
        raise AssertionError("index performed network source checks")

    monkeypatch.setattr(evidence, "_sources_live", forbidden_probe)
    app = FastAPI()
    evidence.register(app, ns="killinchu")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await asyncio.wait_for(
            client.get("/api/killinchu/v1/evidence/research"), timeout=1.0
        )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["sources_reachable"] == 0
    observation = body["claims"][0]["sources"][0]["liveness"]
    assert observation["mode"] == "unavailable"
    assert observation["checked_at"] is None
    assert observation["reachable"] is False


def test_index_cache_never_renews_stale_or_malformed_observation(monkeypatch):
    url = "https://example.org"
    monkeypatch.setattr(evidence, "_disk_load", lambda: None)
    monkeypatch.setattr(evidence, "_CACHE", {
        "live:" + url: {
            "v": {"url": url, "reachable": True, "http_status": 200},
            "_t": time.time() - evidence._LIVENESS_TTL - 1,
            "at": "2026-10-01T00:00:00Z",
        }
    })
    stale = evidence._cached_liveness(url)
    assert stale["mode"] == "cached"
    assert stale["stale"] is True
    assert stale["checked_at"] == "2026-10-01T00:00:00Z"
    evidence._CACHE["live:" + url]["_t"] = "bad-clock"
    invalid = evidence._cached_liveness(url)
    assert invalid["mode"] == "unavailable"
    assert invalid["reachable"] is False
