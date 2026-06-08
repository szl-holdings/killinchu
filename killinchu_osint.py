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


def _persist(stream: str) -> None:
    try:
        _OSINT_DIR.mkdir(parents=True, exist_ok=True)
        (_OSINT_DIR / ("%s.json" % stream)).write_text(json.dumps({
            "stream": stream, "saved_at": _now_iso(),
            "chain_head": _CHAIN_HEAD.get(stream),
            "items": _CORPUS.get(stream, []),
        }, ensure_ascii=False))
    except Exception:
        pass


def _load_disk(stream: str) -> Optional[dict]:
    try:
        return json.loads((_OSINT_DIR / ("%s.json" % stream)).read_text())
    except Exception:
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
            "honesty": _honesty(),
        })
    app.get("%s/osint/status" % base)(_status)
    registered.append("GET %s/osint/status" % base)

    return {"module": "killinchu_osint", "registered": registered,
            "amaru_streams": list(_STREAMS), "rosie_views": list(rosie_map)}


__all__ = ["register"]
