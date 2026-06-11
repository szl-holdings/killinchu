# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# Offline regression suite for killinchu_osint — the amaru/rosie OSINT ingest +
# provenance layer.  Locks in the non-trivial logic that was previously only
# validated by a one-off manual smoke:
#
#   * no key + no cached corpus -> honest "unreachable", ZERO fabricated rows
#   * clean sha256 provenance chain hydrated from disk verifies True
#   * a TAMPERED persisted chain head hydrated from disk verifies False
#   * per-item item_mode: freshly scraped rows are "live", carried rows "cached"
#   * forced-refresh (fresh=1) is throttled inside _FRESH_MIN — Tavily is NOT hit
#
# Tavily is monkeypatched, so the suite runs fully OFFLINE: no network, no key.
# fastapi / fastapi.responses are stubbed before import because the CI runner
# installs only pytest (matching this session's offline smoke).
import json
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Stub fastapi + fastapi.responses BEFORE importing the module under test.
# killinchu_osint does `from fastapi import FastAPI` / `from fastapi.responses
# import JSONResponse` at module scope; the lean CI runner has neither.  The
# stub records routes so register() can be exercised honestly.
# ---------------------------------------------------------------------------
def _install_fastapi_stub() -> None:
    if "fastapi" in sys.modules:
        return

    class _StubApp:
        def __init__(self) -> None:
            self.routes: list = []

        def get(self, path):
            def _deco(fn):
                self.routes.append(("GET", path, fn))
                return fn
            return _deco

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = _StubApp

    responses = types.ModuleType("fastapi.responses")

    class _JSONResponse:
        def __init__(self, content=None, *args, **kwargs):
            self.content = content

    responses.JSONResponse = _JSONResponse
    fastapi.responses = responses

    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses


_install_fastapi_stub()

import killinchu_osint as ko  # noqa: E402  (must follow the stub install)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------
_STREAM = "naval"


def _clear_mem() -> None:
    """Reset the module's in-memory global state (does NOT touch disk)."""
    ko._CORPUS.clear()
    ko._META.clear()
    ko._CHAIN_HEAD.clear()
    ko._CHAIN_OK.clear()


@pytest.fixture
def osint(tmp_path, monkeypatch):
    """Fresh module state + isolated on-disk corpus dir + no live key/network."""
    _clear_mem()
    monkeypatch.setattr(ko, "_OSINT_DIR", tmp_path)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    # Known throttle/freshness windows so timing assertions are deterministic.
    monkeypatch.setattr(ko, "_FRESH_MIN", 60)
    monkeypatch.setattr(ko, "_TTL", 900)
    yield ko, tmp_path, monkeypatch
    _clear_mem()


def _raw(prefix, ids):
    """Build Tavily-shaped raw results for the given integer ids."""
    return [
        {
            "url": "https://navalnews.com/%s%d" % (prefix, i),
            "title": "Naval story %s%d" % (prefix, i),
            "content": "summary body %s%d" % (prefix, i),
            "score": 0.5,
            "published_date": "2026-06-10",
        }
        for i in ids
    ]


def _seed_live(monkeypatch, raw, stream=_STREAM, fresh=True):
    """Drive a real live ingest with Tavily monkeypatched to return `raw`."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key-not-used")
    monkeypatch.setattr(ko, "_tavily_search", lambda *a, **k: list(raw))
    return ko._ingest(stream, fresh=fresh)


# ---------------------------------------------------------------------------
# 1) no key + no cached corpus -> unreachable, zero fabricated rows
# ---------------------------------------------------------------------------
def test_no_key_no_corpus_is_unreachable_with_zero_rows(osint):
    ko, _tmp, _mp = osint
    bundle = ko._ingest(_STREAM)  # no key set, empty corpus dir
    assert bundle["mode"] == "unreachable"
    assert bundle["count"] == 0
    assert bundle["items"] == []          # NEVER fabricated rows
    # honest envelope is still present even when empty
    assert bundle["provenance"]["algo"] == "sha256"
    assert "honesty" in bundle


# ---------------------------------------------------------------------------
# 2) clean provenance chain hydrated from disk verifies True
# ---------------------------------------------------------------------------
def test_clean_chain_hydrates_and_verifies_true(osint):
    ko, tmp, mp = osint
    seeded = _seed_live(mp, _raw("a", [0, 1, 2]))
    assert seeded["mode"] == "live"
    assert seeded["count"] == 3
    # a real chain head was computed + persisted
    disk = json.loads((tmp / ("%s.json" % _STREAM)).read_text())
    assert disk["chain_head"] and len(disk["chain_head"]) == 64

    # cold-start hydrate: drop in-memory state, re-register from disk only
    _clear_mem()
    app = ko.FastAPI()
    ko.register(app, ns="killinchu")

    assert ko._CHAIN_OK[_STREAM]["verified"] is True
    assert ko._CORPUS[_STREAM] and len(ko._CORPUS[_STREAM]) == 3
    # endpoints actually got registered on the (stub) app
    paths = [p for _m, p, _fn in app.routes]
    assert "/api/killinchu/v1/amaru/naval" in paths
    assert "/api/killinchu/v1/osint/status" in paths


# ---------------------------------------------------------------------------
# 3) tampered persisted head hydrated from disk verifies False
# ---------------------------------------------------------------------------
def test_tampered_persisted_head_verifies_false(osint):
    ko, tmp, mp = osint
    _seed_live(mp, _raw("a", [0, 1, 2]))

    # Tamper the persisted chain head on disk (truncation/forgery scenario).
    path = tmp / ("%s.json" % _STREAM)
    disk = json.loads(path.read_text())
    good_head = disk["chain_head"]
    disk["chain_head"] = "deadbeef" * 8  # 64-hex but wrong
    path.write_text(json.dumps(disk))

    _clear_mem()
    app = ko.FastAPI()
    ko.register(app, ns="killinchu")

    integ = ko._CHAIN_OK[_STREAM]
    assert integ["verified"] is False
    assert integ["persisted"] == "deadbeef" * 8
    assert integ["recomputed"] == good_head        # recompute matched the good chain
    assert integ["recomputed"] != integ["persisted"]


def test_tampered_persisted_item_verifies_false(osint):
    """Editing a persisted ITEM (not just the head) must also flip verified
    False — the recompute over the loaded items diverges from the stored head."""
    ko, tmp, mp = osint
    _seed_live(mp, _raw("a", [0, 1, 2]))
    path = tmp / ("%s.json" % _STREAM)
    disk = json.loads(path.read_text())
    disk["items"][0]["prov_hash"] = "0" * 64       # corrupt one item's hash
    path.write_text(json.dumps(disk))

    _clear_mem()
    ko.register(ko.FastAPI(), ns="killinchu")
    assert ko._CHAIN_OK[_STREAM]["verified"] is False


# ---------------------------------------------------------------------------
# 4) per-item item_mode: fresh rows live, carried prior rows cached
# ---------------------------------------------------------------------------
def test_per_item_mode_live_vs_carried_cached(osint):
    ko, _tmp, mp = osint
    # disable throttle so a second forced refresh actually re-ingests
    mp.setattr(ko, "_FRESH_MIN", 0)

    first = _seed_live(mp, _raw("a", [0, 1, 2]))
    assert first["count"] == 3
    assert all(it["item_mode"] == "live" for it in first["items"])

    # Second scrape returns a different result set; item a2 overlaps (same
    # title/url/summary -> same prov_hash), a3 is new, a0/a1 must be carried.
    second_raw = _raw("a", [2, 3])
    mp.setattr(ko, "_tavily_search", lambda *a, **k: list(second_raw))
    second = ko._ingest(_STREAM, fresh=True)

    by_title = {it["title"]: it["item_mode"] for it in second["items"]}
    assert by_title["Naval story a3"] == "live"      # freshly scraped
    assert by_title["Naval story a2"] == "live"      # re-scraped this request
    assert by_title["Naval story a0"] == "cached"    # carried from prior corpus
    assert by_title["Naval story a1"] == "cached"
    # both modes coexist in the same "live" bundle — the point of per-item mode
    assert second["mode"] == "live"
    assert set(by_title.values()) == {"live", "cached"}


# ---------------------------------------------------------------------------
# 5) forced-refresh throttle within _FRESH_MIN — Tavily is NOT hit again
# ---------------------------------------------------------------------------
def test_forced_refresh_is_throttled_within_fresh_min(osint):
    ko, _tmp, mp = osint
    mp.setattr(ko, "_FRESH_MIN", 60)  # generous window; first fetch is "recent"

    _seed_live(mp, _raw("a", [0, 1, 2]))  # live fetch, ts = now

    # Any further Tavily call within _FRESH_MIN would be a cost/abuse bug.
    def _boom(*a, **k):
        raise AssertionError("Tavily must NOT be hit while throttled")

    mp.setattr(ko, "_tavily_search", _boom)

    throttled = ko._ingest(_STREAM, fresh=True)
    assert throttled["mode"] == "live"
    assert "mode_note" in throttled
    assert "throttled" in throttled["mode_note"]
    assert throttled["count"] == 3       # served the existing corpus, unchanged


def test_unthrottled_refresh_past_fresh_min_rehits_tavily(osint):
    """Counterpart to the throttle test: once outside _FRESH_MIN, a forced
    refresh DOES re-hit the search engine."""
    ko, _tmp, mp = osint
    mp.setattr(ko, "_FRESH_MIN", 0)      # no throttle window

    _seed_live(mp, _raw("a", [0, 1, 2]))

    calls = {"n": 0}

    def _counting(*a, **k):
        calls["n"] += 1
        return _raw("b", [9])

    mp.setattr(ko, "_tavily_search", _counting)
    again = ko._ingest(_STREAM, fresh=True)
    assert calls["n"] == 1               # Tavily WAS hit
    assert again["mode"] == "live"
    assert any(it["title"] == "Naval story b9" for it in again["items"])
