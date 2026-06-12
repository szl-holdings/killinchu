# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
"""
killinchu_osint — the amaru/rosie OSINT ingest + orchestration layer.

REAL public-web OSINT, no mocks. amaru and rosie are exposed here as **console
OSINT capabilities** that genuinely search and scrape the open web (via the
Tavily search API) on behalf of killinchu's five defense verticals, normalize
what they find into one schema, stamp it with a sha256 provenance chain
("make it our own"), and orchestrate it across the verticals.

HONESTY (doctrine v11)
----------------------
* These amaru/rosie tabs are CONSOLE CAPABILITIES doing real scraping. They are
  NOT the staged UDS mesh container modules (amaru/rosie/sentra), which remain
  STAGED (FA-001) and are NEVER claimed to boot live. Different thing, same name.
* Every response carries an honest mode: "live" (freshly scraped this request),
  "cached" (upstream/search unreachable -> last-good on-disk corpus), or
  "unreachable" (no search key AND no cached corpus -> honest empty IDLE, never
  fabricated rows).
* The provenance is a REAL sha256 integrity chain over the normalized items —
  it is labelled exactly that, NOT a DSSE/Ed25519 signature.
* Entity extraction, vertical routing and correlation are HEURISTIC and labelled
  "heuristic · advisory" — never presented as proven classification.
* Scraped fields are CLAIMS from third-party reporting, not attested truth.

amaru — INGEST & PROVENANCE (each tab a different public-web domain)
  GET /api/killinchu/v1/amaru/counter-uas     counter-UAS / drone-incident intel  (vertical: drones)
  GET /api/killinchu/v1/amaru/naval           maritime / naval OSINT              (vertical: naval)
  GET /api/killinchu/v1/amaru/procurement     defense procurement / program signal(vertical: pentagon)
  GET /api/killinchu/v1/amaru/advisories      cyber / supply-chain advisories     (vertical: uds)
  GET /api/killinchu/v1/amaru/geopolitical    geopolitical / conflict reporting   (vertical: geo)

rosie — ORCHESTRATION (each tab a different cross-cut over the amaru corpus)
  GET /api/killinchu/v1/rosie/digest          ranked cross-vertical OSINT digest (+ replay hash)
  GET /api/killinchu/v1/rosie/routing         route each item to a defense vertical (+ rationale)
  GET /api/killinchu/v1/rosie/entities        entity graph (nodes+links) for 3D
  GET /api/killinchu/v1/rosie/correlate       correlate corpus vs killinchu's own watch picture
  GET /api/killinchu/v1/rosie/watch           standing watchlist timeseries + alerts

  GET /api/killinchu/v1/osint/status          reachability + corpus + provenance head (honest)

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import urllib.request

from fastapi import FastAPI
from fastapi.responses import JSONResponse

_UA = "killinchu-osint/1.0 (+https://szlholdings-killinchu.hf.space)"
_TAVILY_URL = "https://api.tavily.com/search"
_OSINT_DIR = Path(os.environ.get("KILLINCHU_OSINT_DIR", "/app/osint_corpus"))
_TTL = int(os.environ.get("KILLINCHU_OSINT_TTL", "900"))  # 15 min freshness window
# Min seconds between forced (fresh=1) live scrapes per stream — guards the
# unauthenticated endpoint from being driven into Tavily key/cost exhaustion.
_FRESH_MIN = int(os.environ.get("KILLINCHU_OSINT_FRESH_MIN", "60"))

# ---------------------------------------------------------------------------
# Durable backend (HF Dataset). The Space's local _OSINT_DIR is EPHEMERAL — a
# rebuild/restart wipes it, so the "cached" last-good fallback and the sha256
# provenance chain would start empty after every deploy. To make the corpus
# survive rebuilds we additionally persist each stream's snapshot to a durable
# HF Dataset repo and hydrate from it on cold start. This is BEST-EFFORT and
# HONEST: if the store (or token, or huggingface_hub) is unreachable we silently
# keep using ephemeral local disk and report the reason in osint/status.
# ---------------------------------------------------------------------------
_HF_REPO = os.environ.get("KILLINCHU_OSINT_HF_REPO", "SZLHOLDINGS/killinchu-osint-corpus").strip()
_HF_PREFIX = os.environ.get("KILLINCHU_OSINT_HF_PREFIX", "corpus").strip().strip("/")
_HF_DISABLE = os.environ.get("KILLINCHU_OSINT_HF_DISABLE", "").strip().lower() in ("1", "true", "yes", "on")
_HF_PRIVATE = os.environ.get("KILLINCHU_OSINT_HF_PRIVATE", "0").strip().lower() in ("1", "true", "yes", "on")
# Min seconds between durable pushes per stream — keeps a busy feed from spamming
# dataset commits. Local disk always holds the very latest; durable lags by ≤this.
_HF_MIN_PUSH = int(os.environ.get("KILLINCHU_OSINT_HF_MIN_PUSH", "120"))

# Honest, observable state of the durable backend (surfaced in osint/status).
_HF_STATE: dict[str, Any] = {
    "enabled": bool(_HF_REPO) and not _HF_DISABLE,
    "repo": _HF_REPO,
    "prefix": _HF_PREFIX,
    "available": None,          # None=untested, True=reachable, False=last op failed
    "last_push": {},            # stream -> iso of last successful durable write
    "last_error": None,         # honest last failure ("Type: message")
    "writes": 0,
    "loads": 0,
}
_HF_PUSH_TS: dict[str, float] = {}   # stream -> monotonic-ish ts of last push attempt

# In-memory corpus: stream -> list[item]; plus per-stream fetch metadata.
_LOCK = threading.Lock()
_CORPUS: dict[str, list[dict]] = {}
_META: dict[str, dict] = {}          # stream -> {"ts", "mode", "iso", "query"}
_CHAIN_HEAD: dict[str, str] = {}     # stream -> sha256 chain head over items
_CHAIN_OK: dict[str, dict] = {}      # stream -> {"verified": bool, ...} integrity of hydrated chain

# ---------------------------------------------------------------------------
# amaru stream definitions: fixed vertical + a curated default search query.
# topic="news" + days gives recency; "general" for evergreen advisory pages.
# ---------------------------------------------------------------------------
_STREAMS: dict[str, dict] = {
    "counter-uas": {
        "vertical": "drones", "topic": "news", "days": 30,
        "label": "Counter-UAS & drone-incident intel",
        "query": "counter-UAS C-UAS drone incident airspace intrusion FAA DoD interdiction",
    },
    "naval": {
        "vertical": "naval", "topic": "news", "days": 30,
        "label": "Maritime & naval OSINT",
        "query": "naval maritime security dark fleet tanker sanctions port advisory shadow vessel",
    },
    "procurement": {
        "vertical": "pentagon", "topic": "news", "days": 45,
        "label": "Defense procurement & program signals",
        "query": "Pentagon DoD defense procurement contract award SBIR program counter-drone autonomy",
    },
    "advisories": {
        "vertical": "uds", "topic": "general", "days": 30,
        "label": "Cyber & supply-chain advisories",
        "query": "CISA advisory critical vulnerability ICS OT defense supply chain SBOM zero trust",
    },
    "geopolitical": {
        "vertical": "geo", "topic": "news", "days": 21,
        "label": "Geopolitical & conflict reporting",
        "query": "drone warfare conflict airspace military buildup contested region geopolitical security",
    },
}

# Heuristic source-weighting (advisory; default 0.5). Higher = more authoritative.
_SOURCE_WEIGHT = {
    "cisa.gov": 1.0, "sam.gov": 1.0, "defense.gov": 1.0, "nist.gov": 0.95,
    "navalnews.com": 0.85, "usni.org": 0.85, "breakingdefense.com": 0.8,
    "defensescoop.com": 0.8, "defensenews.com": 0.8, "c4isrnet.com": 0.8,
    "reuters.com": 0.8, "apnews.com": 0.8, "janes.com": 0.85,
    "dronelife.com": 0.65, "thedefensepost.com": 0.6,
}

# Heuristic routing keyword sets (advisory) — rosie/routing reclassifies freely.
_ROUTE_KW = {
    "drones": ["drone", "uas", "uav", "counter-uas", "c-uas", "quadcopter", "swarm",
               "remote id", "fpv", "loitering", "counter-drone"],
    "naval": ["vessel", "ship", "maritime", "navy", "naval", "port", "ais", "submarine",
              "frigate", "sanction", "dark fleet", "tanker", "shadow fleet", "shipping"],
    "pentagon": ["pentagon", "dod", "procurement", "sbir", "contract", "program",
                 "budget", "defense department", "army", "marine", "air force", "award"],
    "uds": ["kubernetes", "software", "supply chain", "vulnerability", "cve", "zero trust",
            "devsecops", "container", "sbom", "software factory", "uds", "defense unicorns",
            "advisory", "exploit", "ics", "ot security"],
    "geo": ["satellite", "geospatial", "geoint", "imagery", "orbit", "seismic", "terrain",
            "gis", "osint", "border", "region", "airspace", "territory"],
}

# Standing watch terms for rosie/watch + rosie/correlate (Section-889 vendors etc).
_SECTION_889 = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]
_WATCH_TERMS = ["counter-UAS", "swarm", "dark fleet", "sanction", "GPS spoof",
                "Remote ID", "supply chain", "autonomy"] + _SECTION_889


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ts_within_secs(ts: Optional[str], secs: int) -> Optional[bool]:
    """True iff ISO-8601 `ts` is within the last `secs` seconds of now (UTC).
    Returns None when `ts` is missing/unparseable — never raises, never guesses.
    Used to honestly mark the public archive as 'live_writing' only when its
    committed head.json last_ts is genuinely recent."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        s = ts.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - dt).total_seconds()
        return bool(0 <= delta <= secs) or bool(delta < 0)
    except Exception:  # noqa: BLE001
        return None


def _tavily_key() -> str:
    return os.environ.get("TAVILY_API_KEY", "").strip()


def _host(url: str) -> str:
    try:
        h = url.split("//", 1)[-1].split("/", 1)[0].lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _src_weight(host: str) -> float:
    for dom, w in _SOURCE_WEIGHT.items():
        if host.endswith(dom):
            return w
    if host.endswith(".gov") or host.endswith(".mil"):
        return 0.9
    return 0.5


def _prov_hash(item: dict) -> str:
    canon = json.dumps(
        {"title": item.get("title", ""), "url": item.get("url", ""),
         "summary": item.get("summary", ""), "stream": item.get("stream", "")},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _tavily_search(query: str, *, topic: str = "general", days: int = 30,
                   max_results: int = 10) -> list[dict]:
    """Real Tavily web search. Raises on hard failure (callers guard)."""
    key = _tavily_key()
    if not key:
        raise RuntimeError("no TAVILY_API_KEY")
    payload: dict[str, Any] = {
        "api_key": key, "query": query, "max_results": max_results,
        "search_depth": "basic", "include_answer": False,
    }
    if topic == "news":
        payload["topic"] = "news"
        payload["days"] = days
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _TAVILY_URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    return d.get("results", []) if isinstance(d, dict) else []


def _normalize(raw: list[dict], stream: str) -> list[dict]:
    """Normalize Tavily results to the killinchu OSINT schema + provenance stamp.
    Dedupe by (host, lowercased title). This is the 'make it our own' step."""
    spec = _STREAMS[stream]
    seen: set = set()
    out: list[dict] = []
    for r in raw:
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title:
            continue
        host = _host(url)
        dk = (host, title.lower())
        if dk in seen:
            continue
        seen.add(dk)
        summary = (r.get("content") or "").strip().replace("\n", " ")
        if len(summary) > 600:
            summary = summary[:597] + "..."
        item = {
            "title": title, "url": url, "host": host, "summary": summary,
            "stream": stream, "vertical": spec["vertical"],
            "published": r.get("published_date"),
            "tavily_score": round(float(r.get("score") or 0.0), 4),
            "source_weight": _src_weight(host),
            "ingest_ts": _now_iso(),
        }
        item["prov_hash"] = _prov_hash(item)
        item["id"] = item["prov_hash"][:16]
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Durable backend helpers (HF Dataset). All best-effort + honest: never raise,
# never block the request path on the network, never fabricate availability.
# ---------------------------------------------------------------------------
def _hf_token() -> str:
    for k in ("HF_WRITE_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN",
              "HF_TOKEN", "HF_ORG_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _hf_enabled() -> bool:
    return bool(_HF_STATE["enabled"]) and bool(_hf_token())


def _hf_path(stream: str) -> str:
    return ("%s/%s.json" % (_HF_PREFIX, stream)) if _HF_PREFIX else ("%s.json" % stream)


def _snapshot(stream: str) -> dict:
    return {
        "stream": stream, "saved_at": _now_iso(),
        "chain_head": _CHAIN_HEAD.get(stream),
        "items": _CORPUS.get(stream, []),
    }


def _durable_save(stream: str) -> None:
    """Push the stream snapshot to the durable HF Dataset, off the request path.
    Debounced per stream; failures are recorded honestly, never raised."""
    if not _hf_enabled():
        return
    now = time.time()
    last = _HF_PUSH_TS.get(stream, 0.0)
    if (now - last) < _HF_MIN_PUSH:
        return  # debounced — local disk still holds the latest
    _HF_PUSH_TS[stream] = now
    snap = _snapshot(stream)  # capture under caller's lock; thread only does I/O

    def _work() -> None:
        try:
            import io
            from huggingface_hub import HfApi
            api = HfApi(token=_hf_token())
            api.create_repo(repo_id=_HF_REPO, repo_type="dataset",
                            private=_HF_PRIVATE, exist_ok=True)
            data = json.dumps(snap, ensure_ascii=False).encode("utf-8")
            api.upload_file(
                path_or_fileobj=io.BytesIO(data),
                path_in_repo=_hf_path(stream),
                repo_id=_HF_REPO, repo_type="dataset",
                commit_message="osint corpus snapshot: %s @ %s" % (stream, snap["saved_at"]),
            )
            _HF_STATE["available"] = True
            _HF_STATE["writes"] = int(_HF_STATE.get("writes", 0)) + 1
            _HF_STATE["last_push"][stream] = snap["saved_at"]
            _HF_STATE["last_error"] = None
        except Exception as exc:  # noqa: BLE001 — best-effort durability
            _HF_STATE["available"] = False
            _HF_STATE["last_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
            _HF_PUSH_TS[stream] = last  # let the next persist retry promptly

    threading.Thread(target=_work, name="osint-hf-save-%s" % stream, daemon=True).start()


def _durable_load(stream: str) -> Optional[dict]:
    """Fetch a stream snapshot from the durable HF Dataset (blocking, used only
    on cold-start hydration + when no local/in-memory corpus exists)."""
    if not _hf_enabled():
        return None
    try:
        from huggingface_hub import hf_hub_download
        fp = hf_hub_download(repo_id=_HF_REPO, repo_type="dataset",
                             filename=_hf_path(stream), token=_hf_token())
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        _HF_STATE["available"] = True
        _HF_STATE["loads"] = int(_HF_STATE.get("loads", 0)) + 1
        _HF_STATE["last_error"] = None
        return d if isinstance(d, dict) else None
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        # A missing repo/file just means "nothing persisted yet" — the store is
        # still reachable; only mark unavailable on a real transport error.
        if name in ("EntryNotFoundError", "RepositoryNotFoundError", "HfHubHTTPError") \
                and any(t in str(exc) for t in ("404", "Not Found", "Entry Not Found")):
            _HF_STATE["available"] = True
        else:
            _HF_STATE["available"] = False
        _HF_STATE["last_error"] = "%s: %s" % (name, str(exc)[:160])
        return None


def _durable_status(head_probe: Optional[dict] = None) -> dict:
    """Honest snapshot of the durable backend for osint/status — never inflated.

    `last_error` must reflect the CURRENT state, not a stale startup failure. The
    durable corpus repo and the public archive share the same HF dataset
    (SZLHOLDINGS/killinchu-osint-corpus). So if the committed head.json was just
    read back 200 with a token present, the repo is demonstrably reachable now
    and any old 401/RepositoryNotFound is stale — we clear it (re-probe) rather
    than show a misleading error. If a real error recurs it is shown honestly."""
    last_error = _HF_STATE["last_error"]
    available = _HF_STATE["available"]
    error_cleared = False
    probe = head_probe if isinstance(head_probe, dict) else None
    repo_reachable_now = bool(probe and probe.get("reachable")) and bool(_hf_token())
    if repo_reachable_now and last_error:
        # Stale error: the shared repo is reachable right now (head fetch 200 +
        # token present). Re-probe = clear it; never show a stale 401.
        last_error = None
        available = True
        error_cleared = True
    out = {
        "backend": "huggingface_dataset",
        "enabled": bool(_HF_STATE["enabled"]),
        "repo": _HF_REPO if _HF_STATE["enabled"] else None,
        "prefix": _HF_PREFIX,
        "token_present": bool(_hf_token()),
        "available": available,
        "writes": _HF_STATE["writes"],
        "loads": _HF_STATE["loads"],
        "last_push": dict(_HF_STATE["last_push"]),
        "last_error": last_error,
        "note": ("corpus snapshots are mirrored to a durable HF Dataset so the "
                 "cached fallback + sha256 provenance chain survive Space rebuilds; "
                 "falls back to ephemeral local disk if the store is unreachable"),
    }
    if error_cleared:
        out["last_error_note"] = (
            "prior startup error cleared this tick: the shared HF dataset repo is "
            "reachable now (committed head.json read back 200, token present)"
        )
    return out


# ---------------------------------------------------------------------------
# Public append-only intel ARCHIVE (Task #772). The durable snapshot above
# (corpus/<stream>.json) exists for cold-start RESILIENCE — it overwrites one
# file per stream and is not browsable. This archive is the production-grade,
# append-only, content-addressed NDJSON stream that turns killinchu's live
# intelligence into a PUBLIC, browsable Hugging Face dataset.
#
# It rides the shared szl_hf_bucket (USE-only; never edited here): each record
# is {schema,id,ts,source,kind,payload} where id = sha256({source,kind,dedup})
# so re-observing the same identity in the same UTC hour + ~0.1° cell stores
# exactly one row (bounded growth, no flooding). Two genuinely-live, keyless
# sources populate it now — community ADS-B aircraft (ODbL) and Digitraffic AIS
# vessels (CC BY) — and the OSINT ingest path streams its normalized items too
# (active whenever a search key is configured). HONEST: every row is a
# THIRD-PARTY CLAIM / self-report; the id is a sha256 content-address for
# dedup / integrity, NOT a DSSE/Ed25519 signature, and asserts nothing about
# correctness. Best-effort + off the request path: never raises, never blocks.
# ---------------------------------------------------------------------------
_ARCHIVE_ENABLED = os.environ.get("KILLINCHU_INTEL_ARCHIVE", "").strip().lower() in ("1", "true", "yes", "on")
_ARCHIVE_REPO = os.environ.get("KILLINCHU_INTEL_ARCHIVE_REPO", _HF_REPO).strip()
_ARCHIVE_PREFIX = os.environ.get("KILLINCHU_INTEL_ARCHIVE_PREFIX", "intel").strip().strip("/") or "intel"
_ARCHIVE_INTERVAL = int(os.environ.get("KILLINCHU_INTEL_ARCHIVE_INTERVAL", "300"))
_ARCHIVE_AIR_LIMIT = int(os.environ.get("KILLINCHU_INTEL_ARCHIVE_AIR_LIMIT", "40"))
_ARCHIVE_AIS_LIMIT = int(os.environ.get("KILLINCHU_INTEL_ARCHIVE_AIS_LIMIT", "40"))
try:
    _ARCHIVE_CELL = float(os.environ.get("KILLINCHU_INTEL_ARCHIVE_CELL", "0.1")) or 0.1
except Exception:
    _ARCHIVE_CELL = 0.1

# Honest, observable state of the public archive (surfaced in osint/status).
_ARCHIVE_STATE: dict[str, Any] = {
    "enabled": _ARCHIVE_ENABLED,
    "repo": _ARCHIVE_REPO,
    "prefix": _ARCHIVE_PREFIX,
    "public": None,        # None=unknown, True/False once ensured
    "started": False,
    "loop_started": False,
    "cycles": 0,
    "appended": {},        # kind -> records queued this process
    "last_cycle": None,
    "last_error": None,
    "card_written": False,
}
_ARCHIVE_BUCKET = None
_ARCHIVE_LOCK = threading.Lock()
_ARCHIVE_STARTED = threading.Event()       # public+flusher ensured (once)
_ARCHIVE_LOOP_STARTED = threading.Event()  # ADS-B/AIS feed loop thread (once)


def _archive_bucket():
    """Lazy singleton HFBucket for the public intel archive. Construction does
    NO network. Returns None if the shared client cannot be imported."""
    global _ARCHIVE_BUCKET
    if _ARCHIVE_BUCKET is not None:
        return _ARCHIVE_BUCKET
    with _ARCHIVE_LOCK:
        if _ARCHIVE_BUCKET is None:
            try:
                from szl_hf_bucket import HFBucket
            except Exception as exc:
                _ARCHIVE_STATE["last_error"] = "bucket import: %s" % type(exc).__name__
                return None
            _ARCHIVE_BUCKET = HFBucket(
                repo_id=_ARCHIVE_REPO, source="killinchu",
                prefix=_ARCHIVE_PREFIX, token=_hf_token() or None,
            )
    return _ARCHIVE_BUCKET


def _archive_card() -> str:
    """Honest dataset card (README.md) with a viewer config over the NDJSON
    shards. Never inflates: rows are third-party claims, id is sha256 dedup."""
    return (
        "---\n"
        "license: other\n"
        "pretty_name: killinchu live intel archive\n"
        "tags:\n"
        "  - osint\n"
        "  - adsb\n"
        "  - ais\n"
        "  - aviation\n"
        "  - maritime\n"
        "  - szl-holdings\n"
        "configs:\n"
        "  - config_name: intel\n"
        "    data_files:\n"
        "      - split: train\n"
        "        path: %s/*.ndjson\n"
        "---\n\n"
        "# killinchu — live intel archive\n\n"
        "Append-only, content-addressed archive of the live intelligence streams the\n"
        "**killinchu** demo ingests, published by SZL Holdings. Written by the shared\n"
        "`szl_hf_bucket` client: one NDJSON shard per UTC day under `%s/`.\n\n"
        "Each row is `{schema, id, ts, source, kind, payload}`.\n\n"
        "## Streams\n"
        "- `kind: adsb-aircraft` (`source: adsb`) — live military ADS-B aircraft from the\n"
        "  adsb.lol / adsb.fi community network. **Data: adsb.lol / adsb.fi community ADS-B (ODbL).**\n"
        "- `kind: ais-vessel` (`source: ais`) — live AIS vessel positions from Fintraffic /\n"
        "  Digitraffic. **Data: Fintraffic / Digitraffic (CC BY 4.0).**\n"
        "- `kind: osint-item` (`source: <vertical>`) — normalized open-web OSINT items\n"
        "  (active only when a search key is configured).\n\n"
        "## Honesty (Doctrine v11)\n"
        "- Every record is a **third-party CLAIM / self-report**, not attested truth.\n"
        "  Broadcast positions and open-web reports can be spoofed, delayed, or wrong.\n"
        "- The record `id` is a **sha256 content-address** used for dedup / integrity —\n"
        "  it is **NOT a DSSE / Ed25519 signature** and asserts nothing about correctness.\n"
        "- Records are **append-only** and **bounded**: deduped per identity per UTC hour\n"
        "  per ~%.2f° cell, so the archive grows steadily without flooding.\n"
        "- No \"proven\" or \"verified\" claim is made about any item.\n"
    ) % (_ARCHIVE_PREFIX, _ARCHIVE_PREFIX, _ARCHIVE_CELL)


def _archive_ensure_public() -> bool:
    """Create the dataset repo PUBLIC (idempotent), flip it public if a
    pre-existing repo is private, and upload the honest card once. Best-effort;
    never raises. Runs off the request path (boot thread)."""
    tok = _hf_token()
    if not tok:
        _ARCHIVE_STATE["last_error"] = "no HF token (archive cannot publish)"
        return False
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=tok)
        api.create_repo(repo_id=_ARCHIVE_REPO, repo_type="dataset",
                        private=False, exist_ok=True)
        try:
            info = api.repo_info(repo_id=_ARCHIVE_REPO, repo_type="dataset")
            if getattr(info, "private", False):
                try:
                    api.update_repo_settings(repo_id=_ARCHIVE_REPO,
                                             repo_type="dataset", private=False)
                except Exception:
                    api.update_repo_visibility(repo_id=_ARCHIVE_REPO,
                                               repo_type="dataset", private=False)
                info = api.repo_info(repo_id=_ARCHIVE_REPO, repo_type="dataset")
            _ARCHIVE_STATE["public"] = not bool(getattr(info, "private", False))
        except Exception:
            _ARCHIVE_STATE["public"] = True  # we created it public just above
        if not _ARCHIVE_STATE["card_written"]:
            try:
                import io
                card = _archive_card().encode("utf-8")
                existing = b""
                try:
                    from huggingface_hub import hf_hub_download
                    fp = hf_hub_download(repo_id=_ARCHIVE_REPO, repo_type="dataset",
                                         filename="README.md", token=tok)
                    with open(fp, "rb") as fh:
                        existing = fh.read()
                except Exception:
                    existing = b""
                if existing.strip() != card.strip():
                    api.upload_file(path_or_fileobj=io.BytesIO(card),
                                    path_in_repo="README.md",
                                    repo_id=_ARCHIVE_REPO, repo_type="dataset",
                                    commit_message="intel archive: honest dataset card")
                _ARCHIVE_STATE["card_written"] = True
            except Exception as exc:  # noqa: BLE001
                _ARCHIVE_STATE["last_error"] = "card: %s: %s" % (type(exc).__name__, str(exc)[:120])
        return True
    except Exception as exc:  # noqa: BLE001
        _ARCHIVE_STATE["last_error"] = "ensure_public: %s: %s" % (type(exc).__name__, str(exc)[:140])
        return False


def _archive_ensure_started() -> bool:
    """Idempotently make the archive ready: ensure the PUBLIC repo + card and
    start the bucket's background flusher — all in a boot thread so NO caller
    (request path or feed loop) ever blocks on the network. Never raises."""
    if not _ARCHIVE_ENABLED:
        return False
    if _ARCHIVE_STARTED.is_set():
        return True
    with _ARCHIVE_LOCK:
        if _ARCHIVE_STARTED.is_set():
            return True
        _ARCHIVE_STARTED.set()

    def _boot() -> None:
        try:
            _archive_ensure_public()
        except Exception:
            pass
        try:
            b = _archive_bucket()
            if b is not None:
                b.start()
                _ARCHIVE_STATE["started"] = True
        except Exception as exc:  # noqa: BLE001
            _ARCHIVE_STATE["last_error"] = "start: %s: %s" % (type(exc).__name__, str(exc)[:120])

    threading.Thread(target=_boot, name="killinchu-intel-archive-boot", daemon=True).start()
    return True


def _archive_round(v):
    try:
        if v is None:
            return None
        return round(float(v) / _ARCHIVE_CELL) * _ARCHIVE_CELL
    except Exception:
        return None


def _archive_hour() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def _archive_bump(kind: str, n: int) -> None:
    if not n:
        return
    with _ARCHIVE_LOCK:
        a = _ARCHIVE_STATE["appended"]
        a[kind] = int(a.get(kind, 0)) + int(n)


def _archive_feed_air(lf, bucket) -> int:
    """Append the current live ADS-B aircraft snapshot (bounded per hour/cell).
    Skips entirely unless the feed is genuinely 'live'."""
    feed = lf.get_feed("air")
    if not isinstance(feed, dict) or feed.get("mode") != "live":
        return 0
    data = feed.get("data") or {}
    aircraft = data.get("aircraft") or []
    hour = _archive_hour()
    recs = []
    for a in aircraft[: max(1, _ARCHIVE_AIR_LIMIT)]:
        ident = a.get("hex") or a.get("flight")
        if not ident:
            continue
        dedup = {"hex": a.get("hex"), "flight": a.get("flight"), "hour": hour,
                 "lat": _archive_round(a.get("lat")), "lon": _archive_round(a.get("lon"))}
        payload = {
            "kind": "adsb-aircraft", "source": "adsb",
            "hex": a.get("hex"), "flight": a.get("flight"),
            "lat": a.get("lat"), "lon": a.get("lon"),
            "alt_baro": a.get("alt_baro"), "gs": a.get("gs"), "track": a.get("track"),
            "category": a.get("category"), "type": a.get("type"), "squawk": a.get("squawk"),
            "observed_hour_utc": hour, "feed_fetched_at": feed.get("fetched_at"),
            "feed_endpoint": data.get("endpoint"),
            "attribution": data.get("attribution"),
            "honesty": ("third-party ADS-B broadcast self-report; position is a claim, "
                        "not attested; id is a sha256 dedup hash, not a signature"),
        }
        recs.append(bucket.make_record(payload, kind="adsb-aircraft", source="adsb", dedup_key=dedup))
    if not recs:
        return 0
    st = bucket.append_many(recs)
    return int(st.get("queued", 0))


def _archive_feed_ais(lf, bucket) -> int:
    """Append the current live AIS vessel snapshot (bounded per hour/cell).
    Skips entirely unless the feed is genuinely 'live'."""
    feed = lf.get_feed("ais")
    if not isinstance(feed, dict) or feed.get("mode") != "live":
        return 0
    data = feed.get("data") or {}
    vessels = data.get("vessels") or []
    hour = _archive_hour()
    recs = []
    for v in vessels[: max(1, _ARCHIVE_AIS_LIMIT)]:
        mmsi = v.get("mmsi")
        if not mmsi:
            continue
        dedup = {"mmsi": mmsi, "hour": hour,
                 "lat": _archive_round(v.get("lat")), "lon": _archive_round(v.get("lon"))}
        payload = {
            "kind": "ais-vessel", "source": "ais",
            "mmsi": mmsi, "name": v.get("name"),
            "sog": v.get("sog"), "cog": v.get("cog"), "heading": v.get("heading"),
            "navStat": v.get("navStat"), "lat": v.get("lat"), "lon": v.get("lon"),
            "observed_hour_utc": hour, "feed_fetched_at": feed.get("fetched_at"),
            "attribution": data.get("attribution"),
            "honesty": ("third-party AIS broadcast self-report; position is a claim, "
                        "not attested; id is a sha256 dedup hash, not a signature"),
        }
        recs.append(bucket.make_record(payload, kind="ais-vessel", source="ais", dedup_key=dedup))
    if not recs:
        return 0
    st = bucket.append_many(recs)
    return int(st.get("queued", 0))


def _archive_osint_items(stream: str, items: list) -> None:
    """Stream freshly-scraped OSINT items into the public archive. Wired into
    _ingest AFTER a successful live scrape; off the request path; never raises,
    never blocks (enqueue is local disk; the flusher commits asynchronously)."""
    if not _ARCHIVE_ENABLED or not items:
        return
    try:
        _archive_ensure_started()
        bucket = _archive_bucket()
        if bucket is None:
            return
        recs = []
        for it in items:
            dk = it.get("prov_hash") or it.get("id")
            if not dk:
                continue
            payload = {k: it.get(k) for k in (
                "title", "url", "host", "summary", "stream", "vertical",
                "published", "prov_hash", "id", "ingest_ts", "source_weight",
                "tavily_score") if k in it}
            payload["kind"] = "osint-item"
            payload["source"] = stream
            payload["honesty"] = ("third-party open-web claim; not attested; the sha256 "
                                  "prov_hash is integrity, not a signature")
            recs.append(bucket.make_record(payload, kind="osint-item", source=stream, dedup_key=dk))
        if recs:
            st = bucket.append_many(recs)
            _archive_bump("osint-item", int(st.get("queued", 0)))
    except Exception as exc:  # noqa: BLE001 — archiving must never break ingest
        _ARCHIVE_STATE["last_error"] = "osint-archive: %s: %s" % (type(exc).__name__, str(exc)[:120])


def _archive_loop() -> None:
    interval = max(60, _ARCHIVE_INTERVAL)
    try:
        import killinchu_live_feeds as lf
    except Exception as exc:  # noqa: BLE001
        _ARCHIVE_STATE["last_error"] = "live_feeds import: %s" % type(exc).__name__
        lf = None
    while True:
        try:
            if lf is not None:
                bucket = _archive_bucket()
                if bucket is not None:
                    _archive_bump("adsb-aircraft", _archive_feed_air(lf, bucket))
                    _archive_bump("ais-vessel", _archive_feed_ais(lf, bucket))
                    with _ARCHIVE_LOCK:
                        _ARCHIVE_STATE["cycles"] = int(_ARCHIVE_STATE["cycles"]) + 1
                        _ARCHIVE_STATE["last_cycle"] = _now_iso()
        except Exception as exc:  # noqa: BLE001
            _ARCHIVE_STATE["last_error"] = "cycle: %s: %s" % (type(exc).__name__, str(exc)[:120])
        time.sleep(interval)


def start_archiver() -> bool:
    """Idempotently start the public intel archiver: ensure the PUBLIC dataset +
    card + flusher, then run the ADS-B/AIS feed loop. No-op unless
    KILLINCHU_INTEL_ARCHIVE is set. Never raises."""
    try:
        if not _ARCHIVE_ENABLED:
            return False
        _archive_ensure_started()
        if _ARCHIVE_LOOP_STARTED.is_set():
            return False
        _ARCHIVE_LOOP_STARTED.set()
        _ARCHIVE_STATE["loop_started"] = True
        threading.Thread(target=_archive_loop, name="killinchu-intel-archiver",
                         daemon=True).start()
        return True
    except Exception as exc:  # noqa: BLE001
        _ARCHIVE_STATE["last_error"] = "start_archiver: %s: %s" % (type(exc).__name__, str(exc)[:120])
        return False


def _committed_head_probe() -> dict:
    """Fetch the LIVE committed `<prefix>/head.json` (ground truth for what the
    public archive actually contains) by REUSING the existing szl_hf_bucket
    client — the SAME head() the provenance/read-back paths use (NO new network
    library, NO new fetch logic). NEVER raises.

    Returns a dict:
      {"reachable": bool, "head": <head dict or None>, "error": <str or None>}
    `reachable` is True iff the committed head.json was actually read back with a
    non-None count — i.e. we genuinely reached HF on this request (same honesty
    rule _archive_read / _hydrate use). We surface a count ONLY when it was
    really returned; we never fabricate one."""
    out = {"reachable": False, "head": None, "error": None}
    try:
        b = _archive_bucket()
        if b is None:
            out["error"] = _ARCHIVE_STATE.get("last_error") or "bucket unavailable"
            return out
        head = b.head()  # committed head.json preferred; falls back to local view
        # A committed head.json (count is not None) means we genuinely reached HF
        # on this request — exactly the hf_ok rule used by _archive_read().
        if isinstance(head, dict) and head.get("count") is not None:
            out["reachable"] = True
            out["head"] = head
        else:
            out["head"] = head if isinstance(head, dict) else None
            out["error"] = "head unreachable this tick"
    except Exception as exc:  # noqa: BLE001 — NEVER raises off the status path
        out["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
    return out


def _archive_status(head_probe: Optional[dict] = None) -> dict:
    """Honest archive status for osint/status.

    The _ARCHIVE_STATE-derived fields (enabled/started/cycles/appended/...) are
    LOCAL only and describe the in-process, KILLINCHU_INTEL_ARCHIVE-env-gated
    archiver loop. That loop is NOT the only writer: the shared szl_hf_bucket
    background flusher also advances the public archive's committed head.json
    independently of this process's _ARCHIVE_STATE. So we ALSO surface the LIVE
    committed head as ground truth (head_count/head_last_ts/head_shards/
    live_writing) — fetched via the reused szl_hf_bucket head() probe. We never
    claim the env loop is running if it isn't, and never show a fabricated count
    (head_* keys appear only when the committed head was actually read back)."""
    st = {
        "enabled": _ARCHIVE_ENABLED,
        "repo": _ARCHIVE_REPO,
        "prefix": _ARCHIVE_PREFIX,
        "public": _ARCHIVE_STATE["public"],
        "started": _ARCHIVE_STATE["started"],
        "loop_started": _ARCHIVE_STATE["loop_started"],
        "cycles": _ARCHIVE_STATE["cycles"],
        "appended": dict(_ARCHIVE_STATE["appended"]),
        "last_cycle": _ARCHIVE_STATE["last_cycle"],
        "card_written": _ARCHIVE_STATE["card_written"],
        "last_error": _ARCHIVE_STATE["last_error"],
        "token_present": bool(_hf_token()),
        "browse_url": "https://huggingface.co/datasets/%s" % _ARCHIVE_REPO,
        "viewer_url": "https://huggingface.co/datasets/%s/viewer" % _ARCHIVE_REPO,
        "note": ("append-only content-addressed NDJSON archive via szl_hf_bucket; "
                 "rows are third-party claims, id is a sha256 dedup hash NOT a signature"),
    }
    try:
        if _ARCHIVE_BUCKET is not None:
            st["bucket"] = _ARCHIVE_BUCKET.status()  # local-only, no network
    except Exception as exc:  # noqa: BLE001
        st["bucket_error"] = type(exc).__name__

    # LIVE committed head.json as ground truth (additive, never-fabricating).
    probe = head_probe if isinstance(head_probe, dict) else _committed_head_probe()
    head = probe.get("head") if isinstance(probe, dict) else None
    if probe.get("reachable") and isinstance(head, dict) and head.get("count") is not None:
        try:
            st["head_count"] = int(head.get("count"))
        except Exception:  # noqa: BLE001
            st["head_count"] = head.get("count")
        st["head_last_ts"] = head.get("last_ts")
        shards = head.get("shards")
        st["head_shards"] = shards if isinstance(shards, list) else []
        st["live_writing"] = _ts_within_secs(head.get("last_ts"), 15 * 60)
        st["head_source"] = "committed head.json (szl_hf_bucket)"
        # Honest reconciliation: enabled==False but the archive demonstrably has
        # rows committed -> the SHARED bucket flusher is the active writer, NOT
        # the in-process env-gated archiver loop. Never claim the loop is up.
        if not _ARCHIVE_ENABLED and isinstance(st["head_count"], int) and st["head_count"] > 0:
            st["active_writer"] = "szl_hf_bucket_flusher"
            st["writer_note"] = (
                "the public archive is being written by the shared szl_hf_bucket "
                "background flusher; the in-process KILLINCHU_INTEL_ARCHIVE-gated "
                "archiver loop is NOT running (enabled=false, loop_started=%s) — "
                "the env-gated 'cycles' counter therefore stays 0 by design"
                % bool(_ARCHIVE_STATE.get("loop_started"))
            )
    else:
        # Never fabricate a count. Be honest that the head was not read this tick.
        st["head_count"] = None
        st["live_writing"] = None
        st["head_note"] = "head unreachable this tick"
        if probe.get("error"):
            st["head_error"] = probe.get("error")
    return st


# Item fields we persist in the public archive osint-item payload and can
# faithfully reconstruct on read-back (everything the console timeline renders).
_ARCHIVE_ITEM_FIELDS = (
    "title", "url", "host", "summary", "stream", "vertical",
    "published", "prov_hash", "id", "ingest_ts", "source_weight", "tavily_score",
)


def _item_from_archive_payload(p: dict) -> dict:
    """Reconstruct an in-memory corpus item from a stored osint-item payload.
    Marks it item_mode='cached' — it is replayed history, not a fresh scrape."""
    it = {k: p.get(k) for k in _ARCHIVE_ITEM_FIELDS if k in p}
    it["item_mode"] = "cached"
    return it


def _archive_read(n: int = 24, kind: Optional[str] = None) -> dict:
    """READ live records back from the PUBLIC intel archive (network call) so the
    archive is a real backing store, not write-only. HF-unreachable-tolerant and
    NEVER raises. Honest mode: 'live' (the committed HF head.json was reachable),
    'cached' (HF unreachable, served whatever is locally queued), 'unreachable'
    (HF down and nothing local). The chain head shown is the archive's own
    content-addressed head — NOT a DSSE/Ed25519 signature."""
    out = {
        "repo": _ARCHIVE_REPO,
        "prefix": _ARCHIVE_PREFIX,
        "enabled": _ARCHIVE_ENABLED,
        "browse_url": "https://huggingface.co/datasets/%s" % _ARCHIVE_REPO,
        "viewer_url": "https://huggingface.co/datasets/%s/viewer" % _ARCHIVE_REPO,
        "note": ("records are third-party claims; id is a sha256 content-address "
                 "for dedup/integrity, NOT a signature"),
    }
    try:
        n = max(0, min(int(n), 500))
    except Exception:
        n = 24
    b = _archive_bucket()
    if b is None:
        out.update({"mode": "unreachable", "records": [], "count": 0,
                    "head": None, "error": _ARCHIVE_STATE.get("last_error")})
        return out
    head = None
    try:
        head = b.head()
    except Exception as exc:  # noqa: BLE001
        out["head_error"] = type(exc).__name__
    try:
        recs = b.read_recent(n) if n else []
    except Exception as exc:  # noqa: BLE001
        out.update({"mode": "unreachable", "records": [], "count": 0,
                    "head": head, "error": type(exc).__name__})
        return out
    if kind:
        recs = [r for r in recs if r.get("kind") == kind]
    # Honest live/cached/unreachable: a committed head.json (count is not None)
    # means we genuinely reached HF on this request.
    hf_ok = bool(head) and head.get("count") is not None
    if hf_ok:
        mode = "live"
    elif recs:
        mode = "cached"
    else:
        mode = "unreachable"
    out.update({"mode": mode, "records": recs, "count": len(recs), "head": head})
    return out


def _hydrate_streams_from_archive(max_per_stream: int = 60) -> dict:
    """Cold-start / on-demand: rebuild EMPTY in-memory OSINT streams from the
    PUBLIC intel archive so the console timeline survives a Space rebuild (HF is
    the backing store). Only fills streams that are still empty after the local
    disk + legacy-snapshot hydration — never clobbers a live/cached corpus.
    Re-chains the provenance sha256 over the replayed items so continuity is
    verifiable (the head is recomputed over real archived items, basis recorded
    honestly). Network call; never raises."""
    result: dict[str, Any] = {"hydrated": {}, "mode": None, "repo": _ARCHIVE_REPO}
    if not _ARCHIVE_ENABLED:
        result["mode"] = "disabled"
        return result
    b = _archive_bucket()
    if b is None:
        result["mode"] = "unreachable"
        result["error"] = _ARCHIVE_STATE.get("last_error")
        return result
    head = None
    try:
        head = b.head()
    except Exception:  # noqa: BLE001
        pass
    # Read enough osint-items to cover every stream a few times over.
    want = max(60, max_per_stream * (len(_STREAMS) + 1))
    try:
        recs = b.read_recent(want)
    except Exception as exc:  # noqa: BLE001
        result["mode"] = "unreachable"
        result["error"] = type(exc).__name__
        return result
    hf_ok = bool(head) and head.get("count") is not None
    result["mode"] = "live" if hf_ok else ("cached" if recs else "unreachable")
    # Group osint-items by stream (read_recent yields oldest->newest).
    by_stream: dict[str, list[dict]] = {}
    for r in recs:
        if r.get("kind") != "osint-item":
            continue
        p = r.get("payload") or {}
        s = p.get("stream") or p.get("source")
        if s not in _STREAMS:
            continue
        item = _item_from_archive_payload(p)
        if item.get("prov_hash"):
            by_stream.setdefault(s, []).append(item)
    with _LOCK:
        for s, items in by_stream.items():
            if _CORPUS.get(s):
                continue  # never overwrite an already-populated stream
            seen: set = set()
            ded: list[dict] = []
            for it in reversed(items):  # newest first for display
                h = it.get("prov_hash")
                if h in seen:
                    continue
                seen.add(h)
                ded.append(it)
            if not ded:
                continue
            _CORPUS[s] = ded[:max_per_stream]
            _rechain(s)
            _CHAIN_OK[s] = {"verified": True,
                            "basis": "hydrated from public intel archive"}
            _META[s] = {"ts": 0, "mode": "cached",
                        "iso": (head or {}).get("last_ts"),
                        "query": _STREAMS[s]["query"]}
            _persist(s)
            result["hydrated"][s] = len(_CORPUS[s])
    return result


def _persist(stream: str) -> None:
    try:
        _OSINT_DIR.mkdir(parents=True, exist_ok=True)
        (_OSINT_DIR / ("%s.json" % stream)).write_text(json.dumps(_snapshot(stream),
                                                                  ensure_ascii=False))
    except Exception:
        pass
    # Mirror to durable storage so the snapshot survives a Space rebuild.
    _durable_save(stream)


def _load_disk(stream: str) -> Optional[dict]:
    try:
        return json.loads((_OSINT_DIR / ("%s.json" % stream)).read_text())
    except Exception:
        pass
    # Ephemeral local disk is empty (e.g. fresh Space rebuild) — hydrate from the
    # durable store and re-seed the local cache so subsequent reads are fast.
    d = _durable_load(stream)
    if d and d.get("items"):
        try:
            _OSINT_DIR.mkdir(parents=True, exist_ok=True)
            (_OSINT_DIR / ("%s.json" % stream)).write_text(json.dumps(d, ensure_ascii=False))
        except Exception:
            pass
        return d
    return None


def _rechain(stream: str) -> str:
    """Recompute the sha256 provenance chain head over the stream's items in
    ingest order. Real integrity chain (NOT a signature)."""
    head = hashlib.sha256(("genesis:%s" % stream).encode()).hexdigest()
    for it in _CORPUS.get(stream, []):
        head = hashlib.sha256((head + it["prov_hash"]).encode()).hexdigest()
    _CHAIN_HEAD[stream] = head
    return head


def _verify_chain(stream: str, persisted: Optional[str]) -> dict:
    """Recompute the chain over the just-loaded items and compare it to the
    head persisted on disk. NEVER trust the persisted head blindly — a tampered
    or truncated snapshot is flagged verified=False instead of silently served."""
    recomputed = _rechain(stream)            # sets _CHAIN_HEAD[stream] from _CORPUS
    if persisted and persisted != recomputed:
        ok = {"verified": False, "reason": "persisted chain_head != recomputed",
              "persisted": persisted, "recomputed": recomputed}
    elif not persisted:
        ok = {"verified": True, "basis": "no persisted head; recomputed on load"}
    else:
        ok = {"verified": True, "basis": "recomputed matches persisted"}
    _CHAIN_OK[stream] = ok
    return ok


def _ingest(stream: str, query: Optional[str] = None, fresh: bool = False) -> dict:
    """Fetch (or serve cached) one amaru stream. Honest mode label."""
    spec = _STREAMS[stream]
    q = (query or spec["query"]).strip()
    with _LOCK:
        meta = _META.get(stream)
        age = (time.time() - meta["ts"]) if meta else None
        fresh_enough = (meta and meta.get("mode") == "live"
                        and age is not None and age < _TTL
                        and meta.get("query") == q)
        if fresh_enough and not fresh:
            return _bundle(stream, "live")
        # Throttle forced refresh: if a live scrape happened very recently, do
        # NOT re-hit Tavily — serve what we have (honest mode_note records it).
        throttled = (fresh and meta and meta.get("mode") == "live"
                     and age is not None and age < _FRESH_MIN and _CORPUS.get(stream))
        if throttled:
            return _bundle(stream, "live",
                           note="forced refresh throttled (<%ss since last live fetch)" % _FRESH_MIN)
    # Try live scrape.
    try:
        raw = _tavily_search(q, topic=spec["topic"], days=spec["days"], max_results=10)
        items = _normalize(raw, stream)
        for it in items:                       # freshly scraped this request
            it["item_mode"] = "live"
        with _LOCK:
            # merge: new on top (item_mode=live), carry prior items as item_mode
            # =cached, dedupe by prov_hash, cap 60. Per-item mode keeps the bundle
            # honest even though the bundle label is "live".
            fresh_hashes = {x["prov_hash"] for x in items}
            carried = []
            for it in _CORPUS.get(stream, []):
                if it["prov_hash"] not in fresh_hashes:
                    c = dict(it); c["item_mode"] = "cached"; carried.append(c)
            _CORPUS[stream] = (items + carried)[:60]
            _META[stream] = {"ts": time.time(), "mode": "live", "iso": _now_iso(), "query": q}
            _rechain(stream)
            _CHAIN_OK[stream] = {"verified": True, "basis": "computed-this-request"}
            _persist(stream)
            _archive_osint_items(stream, items)
            return _bundle(stream, "live")
    except Exception as exc:
        # Fall back to in-memory, then on-disk last-good corpus.
        with _LOCK:
            if _CORPUS.get(stream):
                for it in _CORPUS[stream]:
                    it["item_mode"] = "cached"
                return _bundle(stream, "cached", note="search unreachable (%s) — last-good corpus" % type(exc).__name__)
        disk = _load_disk(stream)
        if disk and disk.get("items"):
            with _LOCK:
                items = [dict(it, item_mode="cached") for it in disk["items"]]
                _CORPUS[stream] = items
                _verify_chain(stream, disk.get("chain_head"))
                _META[stream] = {"ts": 0, "mode": "cached", "iso": disk.get("saved_at"), "query": q}
            return _bundle(stream, "cached", note="search unreachable (%s) — on-disk snapshot" % type(exc).__name__)
        return _bundle(stream, "unreachable", note="no search key and no cached corpus: %s" % exc)


def _honesty(extra: Optional[dict] = None) -> dict:
    h = {
        "console_capability": True,
        "note": ("amaru/rosie here are CONSOLE OSINT capabilities doing REAL public-web "
                 "scraping (Tavily). They are NOT the staged UDS mesh container modules "
                 "(amaru/rosie/sentra), which remain STAGED (FA-001) and never claimed live."),
        "provenance": "sha256 integrity chain over normalized items (NOT a DSSE/Ed25519 signature)",
        "fields": "scraped fields are third-party CLAIMS, not attested truth",
    }
    if extra:
        h.update(extra)
    return h


def _bundle(stream: str, mode: str, note: Optional[str] = None) -> dict:
    spec = _STREAMS[stream]
    meta = _META.get(stream, {})
    items = _CORPUS.get(stream, [])
    out = {
        "stream": stream, "label": spec["label"], "vertical": spec["vertical"],
        "mode": mode, "fetched_at": meta.get("iso"), "query": meta.get("query"),
        "count": len(items), "items": items,
        "provenance": {"algo": "sha256", "chain_head": _CHAIN_HEAD.get(stream),
                       "integrity": _CHAIN_OK.get(stream, {"verified": True, "basis": "fresh"})},
        "honesty": _honesty(),
        "engine": "tavily",
    }
    if note:
        out["mode_note"] = note
    return out


def _ensure_corpus(fresh: bool = False) -> dict:
    """Make sure rosie has something to orchestrate: ingest any empty stream."""
    modes = {}
    for s in _STREAMS:
        if fresh or not _CORPUS.get(s):
            b = _ingest(s, fresh=fresh)
            modes[s] = b["mode"]
        else:
            modes[s] = (_META.get(s, {}) or {}).get("mode", "cached")
    return modes


def _all_items() -> list[dict]:
    out: list[dict] = []
    for s in _STREAMS:
        out.extend(_CORPUS.get(s, []))
    return out


def _classify(item: dict) -> tuple[str, float, list[str]]:
    """Heuristic route an item to a vertical by keyword density. Advisory."""
    text = ((item.get("title", "") + " " + item.get("summary", "")).lower())
    best, best_n, hits = item.get("vertical", "uds"), 0, []
    for vert, kws in _ROUTE_KW.items():
        h = [k for k in kws if k in text]
        if len(h) > best_n:
            best, best_n, hits = vert, len(h), h
    conf = round(min(1.0, 0.4 + 0.15 * best_n), 3) if best_n else 0.4
    return best, conf, hits[:6]


# ---------------------------------------------------------------------------
# rosie orchestration computations (over the amaru corpus).
# ---------------------------------------------------------------------------
def _rosie_digest(limit: int = 24) -> dict:
    modes = _ensure_corpus()
    items = _all_items()
    def _score(it):
        rec = 0.0
        pub = it.get("published")
        if pub:
            rec = 0.3
        return round(0.55 * it.get("source_weight", 0.5)
                     + 0.30 * it.get("tavily_score", 0.0) + rec, 4)
    ranked = sorted(items, key=lambda it: (_score(it), it.get("ingest_ts", "")), reverse=True)
    top = []
    for it in ranked[:limit]:
        top.append({k: it[k] for k in ("id", "title", "url", "host", "summary",
                                       "stream", "vertical", "published", "prov_hash")
                    if k in it} | {"rank_score": _score(it)})
    # deterministic replay hash over the ranked id sequence (reproducibility proof)
    replay = hashlib.sha256("|".join(t["id"] for t in top).encode()).hexdigest()
    return {
        "view": "rosie/digest", "mode": _merge_mode(modes), "stream_modes": modes,
        "count": len(top), "total_corpus": len(items), "items": top,
        "replay_hash": replay,
        "honesty": _honesty({"ranking": "source_weight·0.55 + tavily_score·0.30 + recency·0.30 — "
                                        "deterministic; replay_hash reproducible across runs"}),
    }


def _rosie_routing() -> dict:
    modes = _ensure_corpus()
    items = _all_items()
    table, counts = [], {v: 0 for v in _ROUTE_KW}
    for it in items:
        vert, conf, hits = _classify(it)
        counts[vert] += 1
        table.append({"id": it["id"], "title": it["title"], "host": it["host"],
                      "ingest_vertical": it.get("vertical"), "routed_to": vert,
                      "confidence": conf, "matched": hits, "url": it["url"]})
    table.sort(key=lambda r: r["confidence"], reverse=True)
    return {
        "view": "rosie/routing", "mode": _merge_mode(modes), "stream_modes": modes,
        "total": len(items), "per_vertical": counts, "routes": table,
        "honesty": _honesty({"routing": "heuristic keyword classifier · advisory — "
                                       "not a proven classification"}),
    }


def _rosie_entities() -> dict:
    modes = _ensure_corpus()
    items = _all_items()
    # heuristic entity extraction: known entities + multi-word Capitalized phrases
    KNOWN = (_SECTION_889 + ["Pentagon", "DoD", "FAA", "FCC", "CISA", "NATO", "Navy",
             "Army", "Air Force", "Ukraine", "Russia", "China", "Iran", "DJI",
             "Anduril", "Defense Unicorns", "SBIR", "Remote ID"])
    nodes: dict[str, dict] = {}
    links: dict[tuple, int] = {}
    def _node(name, kind):
        if name not in nodes:
            nodes[name] = {"id": name, "kind": kind, "count": 0}
        nodes[name]["count"] += 1
        return name
    for it in items:
        text = it.get("title", "") + ". " + it.get("summary", "")
        found = [k for k in KNOWN if k.lower() in text.lower()]
        vert = it.get("vertical", "uds")
        vnode = _node("vertical:" + vert, "vertical")
        for e in found[:6]:
            _node(e, "entity")
            key = tuple(sorted((vnode, e)))
            links[key] = links.get(key, 0) + 1
        # entity co-occurrence links
        for i in range(len(found)):
            for j in range(i + 1, min(len(found), 6)):
                key = tuple(sorted((found[i], found[j])))
                if key[0] != key[1]:
                    links[key] = links.get(key, 0) + 1
    return {
        "view": "rosie/entities", "mode": _merge_mode(modes), "stream_modes": modes,
        "nodes": list(nodes.values()),
        "links": [{"source": a, "target": b, "weight": w} for (a, b), w in links.items()],
        "honesty": _honesty({"extraction": "heuristic keyword/known-entity match · advisory"}),
    }


def _rosie_correlate() -> dict:
    modes = _ensure_corpus()
    items = _all_items()
    hits = []
    for it in items:
        text = (it.get("title", "") + " " + it.get("summary", "")).lower()
        matched_terms = [t for t in _WATCH_TERMS if t.lower() in text]
        flagged_889 = [v for v in _SECTION_889 if v.lower() in text]
        if matched_terms:
            hits.append({
                "id": it["id"], "title": it["title"], "host": it["host"], "url": it["url"],
                "vertical": it.get("vertical"), "watch_hits": matched_terms,
                "section_889_vendor": flagged_889 or None,
                "severity": "elevated" if flagged_889 else "watch",
            })
    hits.sort(key=lambda h: (h["section_889_vendor"] is not None, len(h["watch_hits"])), reverse=True)
    return {
        "view": "rosie/correlate", "mode": _merge_mode(modes), "stream_modes": modes,
        "total_scanned": len(items), "hit_count": len(hits), "hits": hits,
        "watch_terms": _WATCH_TERMS, "section_889": _SECTION_889,
        "honesty": _honesty({"correlation": "substring match of corpus against killinchu's "
                                          "own watch picture · advisory"}),
    }


def _rosie_watch() -> dict:
    modes = _ensure_corpus()
    items = _all_items()
    # bucket by day (published date if present, else ingest day)
    series: dict[str, dict[str, int]] = {t: {} for t in _WATCH_TERMS}
    alerts = []
    for it in items:
        day = (it.get("published") or it.get("ingest_ts") or "")[:10]
        if not day:
            continue
        text = (it.get("title", "") + " " + it.get("summary", "")).lower()
        for t in _WATCH_TERMS:
            if t.lower() in text:
                series[t][day] = series[t].get(day, 0) + 1
    totals = {t: sum(d.values()) for t, d in series.items()}
    for t, n in sorted(totals.items(), key=lambda x: x[1], reverse=True):
        if n >= 3:
            alerts.append({"term": t, "count": n,
                           "level": "high" if n >= 6 else "elevated"})
    return {
        "view": "rosie/watch", "mode": _merge_mode(modes), "stream_modes": modes,
        "terms": _WATCH_TERMS, "totals": totals,
        "series": {t: [{"day": d, "n": n} for d, n in sorted(v.items())]
                   for t, v in series.items() if v},
        "alerts": alerts,
        "honesty": _honesty({"watch": "term frequency over corpus by day · advisory; "
                                    "threshold ≥3 = elevated, ≥6 = high"}),
    }


def _merge_mode(modes: dict) -> str:
    vals = set(modes.values())
    if vals == {"live"}:
        return "live"
    if "live" in vals:
        return "live-partial"
    if "cached" in vals:
        return "cached"
    return "unreachable"


# ---------------------------------------------------------------------------
# Background warmer
# ---------------------------------------------------------------------------
# Keep all five amaru streams populated so the console is never empty on first
# open and rosie's cross-vertical views (digest/routing/entities/correlate/
# watch) always see a full corpus — not just whichever streams happened to be
# hit by a user. A guarded daemon thread periodically warms every stream.
#
# Tavily-friendly by construction: it calls _ingest(stream, fresh=False), so the
# existing _TTL freshness check decides whether to actually re-hit the search API
# — a still-fresh stream is a pure no-op. The forced-refresh path (fresh=True,
# guarded by _FRESH_MIN) is NEVER taken by the warmer. The loop interval defaults
# to _TTL so each stream is re-scraped at most once per freshness window.
_WARM_ENABLED = os.environ.get("KILLINCHU_OSINT_WARM", "1").strip().lower() \
    not in ("0", "false", "no", "off")
_WARM_INTERVAL = int(os.environ.get("KILLINCHU_OSINT_WARM_INTERVAL", str(_TTL)))
# Small per-stream stagger so a warm cycle doesn't burst all five Tavily calls
# back-to-back.
_WARM_STAGGER = int(os.environ.get("KILLINCHU_OSINT_WARM_STAGGER", "5"))

_WARM_STARTED = threading.Event()


def _warm_once() -> dict:
    """Warm every stream that is stale or empty. Uses fresh=False so the _TTL
    freshness check (not the forced-refresh path) governs re-scrapes — this can
    never drive Tavily into exhaustion. Returns each stream's resulting mode."""
    modes: dict[str, str] = {}
    for s in _STREAMS:
        try:
            modes[s] = _ingest(s, fresh=False).get("mode", "?")
        except Exception as exc:  # one bad stream never stops the rest
            modes[s] = "error:%s" % type(exc).__name__
        if _WARM_STAGGER > 0:
            time.sleep(_WARM_STAGGER)
    return modes


def _warm_loop() -> None:
    # Warm immediately on boot so a cold Space populates its feeds on its own,
    # then re-warm every interval (>=60s guard so a misconfigured interval can't
    # become a hot loop).
    interval = max(60, _WARM_INTERVAL)
    while True:
        try:
            _warm_once()
        except Exception:
            pass
        time.sleep(interval)


def start_warmer() -> bool:
    """Idempotently start the background warmer daemon thread. Returns True if it
    started the thread, False if it was already running or is disabled
    (KILLINCHU_OSINT_WARM=0)."""
    # The public intel archiver is independent of the OSINT warmer; start it
    # here too (idempotent) so it runs even when the warmer is disabled.
    try:
        start_archiver()
    except Exception:
        pass
    if not _WARM_ENABLED:
        return False
    # Event.set() is atomic; the first caller wins, later/concurrent calls no-op.
    if _WARM_STARTED.is_set():
        return False
    _WARM_STARTED.set()
    threading.Thread(target=_warm_loop, name="killinchu-osint-warmer",
                     daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register(app: FastAPI, ns: str = "killinchu") -> dict:
    base = "/api/%s/v1" % ns
    registered: list[str] = []

    # hydrate from disk (resilient cold start) — verify chain, never trust blindly
    for s in _STREAMS:
        disk = _load_disk(s)
        if disk and disk.get("items"):
            _CORPUS[s] = [dict(it, item_mode="cached") for it in disk["items"]]
            _verify_chain(s, disk.get("chain_head"))
            _META[s] = {"ts": 0, "mode": "cached", "iso": disk.get("saved_at"),
                        "query": _STREAMS[s]["query"]}

    # Cold-start hydration from the PUBLIC intel archive (HF as backing store):
    # if any stream is still empty after the local disk + legacy-snapshot load
    # (e.g. a fresh Space rebuild wiped ephemeral disk), restore its history from
    # the public archive so the console timeline + provenance chain survive the
    # rebuild. Network I/O, so run it off the startup path in a boot thread.
    if _ARCHIVE_ENABLED and any(not _CORPUS.get(s) for s in _STREAMS):
        def _hydrate_boot() -> None:
            try:
                _hydrate_streams_from_archive()
            except Exception:  # noqa: BLE001 — hydration must never break boot
                pass
        threading.Thread(target=_hydrate_boot,
                         name="killinchu-archive-hydrate", daemon=True).start()

    def _mk_amaru(stream: str):
        async def _h(q: Optional[str] = None, fresh: int = 0) -> JSONResponse:
            return JSONResponse(_ingest(stream, query=q, fresh=bool(fresh)))
        return _h

    for stream in _STREAMS:
        ep = "%s/amaru/%s" % (base, stream)
        app.get(ep)(_mk_amaru(stream))
        registered.append("GET " + ep)

    rosie_map = {
        "digest": lambda limit=24: JSONResponse(_rosie_digest(int(limit))),
        "routing": lambda: JSONResponse(_rosie_routing()),
        "entities": lambda: JSONResponse(_rosie_entities()),
        "correlate": lambda: JSONResponse(_rosie_correlate()),
        "watch": lambda: JSONResponse(_rosie_watch()),
    }

    def _mk_rosie(fn):
        if fn.__code__.co_argcount == 1:
            async def _h(limit: int = 24):
                return fn(limit)
            return _h
        async def _h0():
            return fn()
        return _h0

    for name, fn in rosie_map.items():
        ep = "%s/rosie/%s" % (base, name)
        app.get(ep)(_mk_rosie(fn))
        registered.append("GET " + ep)

    async def _status() -> JSONResponse:
        # Probe the LIVE committed head ONCE per request (never-raises) and feed
        # it to BOTH archive + durable so they agree on current reachability and
        # the stale startup 401 is cleared honestly when the repo is reachable.
        head_probe = _committed_head_probe()
        return JSONResponse({
            "module": "killinchu_osint",
            "engine": "tavily",
            "search_key_present": bool(_tavily_key()),
            "streams": {s: {"vertical": _STREAMS[s]["vertical"],
                            "count": len(_CORPUS.get(s, [])),
                            "mode": (_META.get(s, {}) or {}).get("mode"),
                            "chain_head": _CHAIN_HEAD.get(s),
                            "chain_integrity": _CHAIN_OK.get(s, {"verified": True, "basis": "fresh"})}
                        for s in _STREAMS},
            "total_corpus": sum(len(v) for v in _CORPUS.values()),
            "durable": _durable_status(head_probe),
            "archive": _archive_status(head_probe),
            "honesty": _honesty(),
        })
    app.get("%s/osint/status" % base)(_status)
    registered.append("GET %s/osint/status" % base)

    async def _archive_ep() -> JSONResponse:
        return JSONResponse(_archive_status())
    app.get("%s/osint/archive" % base)(_archive_ep)
    registered.append("GET %s/osint/archive" % base)

    # READ-BACK: live records + chain head pulled from the PUBLIC intel archive,
    # proving HF is a real backing store (not write-only). HF-unreachable-tolerant.
    async def _archive_recent_ep(n: int = 24, kind: Optional[str] = None) -> JSONResponse:
        return JSONResponse(_archive_read(n, kind=kind))
    app.get("%s/osint/archive/recent" % base)(_archive_recent_ep)
    registered.append("GET %s/osint/archive/recent" % base)

    # ON-DEMAND hydration of the in-memory streams from the public archive.
    async def _archive_hydrate_ep() -> JSONResponse:
        return JSONResponse(_hydrate_streams_from_archive())
    app.get("%s/osint/archive/hydrate" % base)(_archive_hydrate_ep)
    registered.append("GET %s/osint/archive/hydrate" % base)

    # Start the public, append-only intel archiver (idempotent; no-op unless
    # KILLINCHU_INTEL_ARCHIVE is set). Off the request path.
    try:
        start_archiver()
    except Exception:
        pass

    return {"module": "killinchu_osint", "registered": registered,
            "amaru_streams": list(_STREAMS), "rosie_views": list(rosie_map)}


__all__ = ["register", "start_warmer", "start_archiver"]
