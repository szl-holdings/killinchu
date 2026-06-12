# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# Offline regression suite for the killinchu PUBLIC intel archive (Task #772):
# the append-only, content-addressed NDJSON stream that killinchu_osint writes
# to the public HF dataset via the shared szl_hf_bucket.
#
# Locks in the contract WITHOUT touching Hugging Face (FakeTransport):
#   * a successful live OSINT scrape STREAMS its normalized items into the
#     archive bucket (wired in _ingest, off the request path)
#   * re-archiving the same items dedups to zero (content-addressed id)
#   * the keyless ADS-B / AIS feeds append bounded, deduped rows and SKIP
#     entirely when the feed is not genuinely "live" (never fabricates)
#   * archiving NEVER raises into the request path, even if the bucket throws
#   * disabled (KILLINCHU_INTEL_ARCHIVE unset) is a hard no-op
#   * osint/status archive block is honest (sha256 dedup NOT a signature)
#
# Run by file path (module shipped flat next to serve.py):
#   python3 -m pytest test_killinchu_archive.py
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Stub fastapi + fastapi.responses BEFORE importing the module under test
# (the lean CI runner installs only pytest). Mirrors test_osint.py.
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
from szl_hf_bucket import HFBucket, Transport  # noqa: E402


# ---------------------------------------------------------------------------
# Offline transport + bucket (no network, never sleeps).
# ---------------------------------------------------------------------------
class FakeTransport(Transport):
    def __init__(self):
        self.files = {}

    def read_file(self, path):
        return self.files.get(path)

    def list_files(self, prefix):
        pref = prefix.rstrip("/") + "/"
        return sorted(p for p in self.files if p.startswith(pref))

    def commit(self, operations, message):
        for path, blob in operations:
            self.files[path] = blob
        return "oid"


def _mk_bucket(tmp):
    return HFBucket(
        repo_id="SZLHOLDINGS/killinchu-osint-corpus", source="killinchu",
        prefix="intel", queue_dir=str(tmp), transport=FakeTransport(),
        backoff_base=0.0, max_backoff=0.0, sleep=lambda s: None,
    )


class _FakeLF:
    """Stand-in for killinchu_live_feeds with canned get_feed() results."""

    def __init__(self, air=None, ais=None):
        self._air, self._ais = air, ais

    def get_feed(self, which):
        return self._air if which == "air" else self._ais


def _live_air():
    return {
        "mode": "live", "fetched_at": "2026-06-12T00:00:00Z",
        "data": {
            "endpoint": "https://api.adsb.lol/v2/mil",
            "attribution": "adsb.lol / adsb.fi community ADS-B (ODbL)",
            "aircraft": [
                {"hex": "ae01ce", "flight": "RCH123", "lat": 50.11, "lon": 8.21,
                 "alt_baro": 31000, "gs": 420, "track": 90, "category": "A4",
                 "type": "C17", "squawk": "1234"},
                {"hex": "ae02df", "flight": "PAT47", "lat": 51.55, "lon": 7.02,
                 "alt_baro": 28000, "gs": 380, "track": 180, "category": "A3",
                 "type": "C130", "squawk": "5678"},
            ],
        },
    }


def _live_ais():
    return {
        "mode": "live", "fetched_at": "2026-06-12T00:00:00Z",
        "data": {
            "attribution": "Fintraffic / Digitraffic (CC BY 4.0)",
            "vessels": [
                {"mmsi": 230123456, "name": "FINNMAID", "sog": 12.3, "cog": 88.0,
                 "heading": 90, "navStat": 0, "lat": 60.16, "lon": 24.95},
                {"mmsi": 265987654, "name": "STENA", "sog": 0.1, "cog": 0.0,
                 "heading": 511, "navStat": 5, "lat": 59.32, "lon": 18.07},
            ],
        },
    }


def _osint_items(n=3, prefix="x"):
    return [
        {"title": "Item %s%d" % (prefix, i), "url": "https://ex.com/%s%d" % (prefix, i),
         "host": "ex.com", "summary": "body %d" % i, "stream": "naval",
         "vertical": "naval", "prov_hash": ("%s%d" % (prefix, i)).ljust(64, "0")}
        for i in range(n)
    ]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Enable the archive with an injected offline bucket; reset module state."""
    # No real HF token anywhere (keeps the durable/ensure_public paths inert).
    for k in ("HF_WRITE_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN",
              "HF_TOKEN", "HF_ORG_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    ko._CORPUS.clear(); ko._META.clear(); ko._CHAIN_HEAD.clear(); ko._CHAIN_OK.clear()
    monkeypatch.setattr(ko, "_OSINT_DIR", tmp_path)
    monkeypatch.setattr(ko, "_ARCHIVE_ENABLED", True)
    bucket = _mk_bucket(tmp_path / "queue")
    monkeypatch.setattr(ko, "_ARCHIVE_BUCKET", bucket)
    # Pretend boot already happened so the request path never spawns the
    # network boot thread; reset observable counters.
    ko._ARCHIVE_STARTED.set()
    ko._ARCHIVE_STATE["appended"] = {}
    ko._ARCHIVE_STATE["last_error"] = None
    yield ko, bucket, tmp_path, monkeypatch
    ko._ARCHIVE_STARTED.clear()
    ko._ARCHIVE_LOOP_STARTED.clear()
    ko._CORPUS.clear(); ko._META.clear(); ko._CHAIN_HEAD.clear(); ko._CHAIN_OK.clear()


# ---------------------------------------------------------------------------
# 1) a successful live OSINT scrape streams items into the archive
# ---------------------------------------------------------------------------
def test_live_ingest_streams_into_archive(archive):
    ko, bucket, _tmp, mp = archive
    mp.setenv("TAVILY_API_KEY", "test-key-not-used")
    raw = [{"url": "https://navalnews.com/a%d" % i, "title": "Naval a%d" % i,
            "content": "summary a%d" % i, "score": 0.5, "published_date": "2026-06-10"}
           for i in range(3)]
    mp.setattr(ko, "_tavily_search", lambda *a, **k: list(raw))

    bundle = ko._ingest("naval", fresh=True)
    assert bundle["mode"] == "live" and bundle["count"] == 3
    # The archive received exactly the 3 freshly-scraped items.
    assert ko._ARCHIVE_STATE["appended"].get("osint-item") == 3
    recs = bucket.read_recent(50)
    assert recs and all(r["kind"] == "osint-item" for r in recs)
    assert all(r["source"] == "naval" for r in recs)
    # honest payload: sha256 prov_hash labelled integrity, not a signature
    assert "signature" in recs[0]["payload"]["honesty"]


# ---------------------------------------------------------------------------
# 2) re-archiving the same items dedups to zero (content-addressed id)
# ---------------------------------------------------------------------------
def test_osint_archive_dedups(archive):
    ko, _bucket, _tmp, _mp = archive
    items = _osint_items(4)
    ko._archive_osint_items("naval", items)
    first = ko._ARCHIVE_STATE["appended"].get("osint-item")
    ko._archive_osint_items("naval", items)  # identical content again
    second = ko._ARCHIVE_STATE["appended"].get("osint-item")
    assert first == 4
    assert second == 4  # unchanged: the second pass queued zero new rows


# ---------------------------------------------------------------------------
# 3) keyless ADS-B / AIS feeds append + dedup + skip non-live
# ---------------------------------------------------------------------------
def test_feed_air_appends_and_dedups(archive):
    ko, bucket, _tmp, _mp = archive
    lf = _FakeLF(air=_live_air())
    n1 = ko._archive_feed_air(lf, bucket)
    n2 = ko._archive_feed_air(lf, bucket)  # same hour + cell -> deduped
    assert n1 == 2
    assert n2 == 0
    recs = [r for r in bucket.read_recent(50) if r["kind"] == "adsb-aircraft"]
    assert len(recs) == 2 and all(r["source"] == "adsb" for r in recs)


def test_feed_ais_appends(archive):
    ko, bucket, _tmp, _mp = archive
    lf = _FakeLF(ais=_live_ais())
    assert ko._archive_feed_ais(lf, bucket) == 2
    recs = [r for r in bucket.read_recent(50) if r["kind"] == "ais-vessel"]
    assert len(recs) == 2 and all(r["source"] == "ais" for r in recs)


def test_feed_skips_when_not_live(archive):
    ko, bucket, _tmp, _mp = archive
    cached = {"mode": "cached", "data": {"aircraft": [{"hex": "x"}], "vessels": [{"mmsi": 1}]}}
    lf = _FakeLF(air=cached, ais=cached)
    assert ko._archive_feed_air(lf, bucket) == 0   # never archive non-live
    assert ko._archive_feed_ais(lf, bucket) == 0


# ---------------------------------------------------------------------------
# 4) archiving NEVER raises into the request path
# ---------------------------------------------------------------------------
def test_osint_archive_never_raises(archive):
    ko, _bucket, _tmp, mp = archive

    class _Boom:
        def make_record(self, *a, **k):
            return {"schema": "x", "id": "i"}

        def append_many(self, *a, **k):
            raise RuntimeError("HF exploded")

    mp.setattr(ko, "_ARCHIVE_BUCKET", _Boom())
    # Must not raise; the failure is recorded honestly instead.
    ko._archive_osint_items("naval", _osint_items(2))
    assert ko._ARCHIVE_STATE["last_error"] and "osint-archive" in ko._ARCHIVE_STATE["last_error"]


# ---------------------------------------------------------------------------
# 5) disabled is a hard no-op (no bucket touch, no records)
# ---------------------------------------------------------------------------
def test_disabled_is_noop(archive):
    ko, bucket, _tmp, mp = archive
    mp.setattr(ko, "_ARCHIVE_ENABLED", False)
    ko._archive_osint_items("naval", _osint_items(3))
    assert ko._ARCHIVE_STATE["appended"].get("osint-item") in (None, 0)
    assert not bucket.read_recent(10)


# ---------------------------------------------------------------------------
# 6) status block is honest + browsable
# ---------------------------------------------------------------------------
def test_archive_status_is_honest(archive):
    ko, _bucket, _tmp, _mp = archive
    st = ko._archive_status()
    assert st["enabled"] is True
    assert st["repo"] == "SZLHOLDINGS/killinchu-osint-corpus"
    assert st["browse_url"].startswith("https://huggingface.co/datasets/")
    assert "viewer" in st["viewer_url"]
    # never claims a signature / proof
    assert "NOT a signature" in st["note"]


def test_status_endpoint_includes_archive(archive):
    ko, _bucket, _tmp, _mp = archive
    app = ko.FastAPI()
    ko.register(app, ns="killinchu")
    paths = [p for _m, p, _fn in app.routes]
    assert "/api/killinchu/v1/osint/archive" in paths


def test_dataset_card_is_honest():
    card = ko._archive_card()
    assert "third-party CLAIM" in card
    assert "NOT a DSSE / Ed25519 signature" in card
    assert "intel/*.ndjson" in card        # viewer config over the NDJSON shards
    assert "proven" not in card.lower().split("no \"proven\"")[0]
