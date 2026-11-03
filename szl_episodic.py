# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_episodic.py — SZL governed episodic-memory / temporal-knowledge-graph endpoint.

Clean-room adoption of the EPISODIC/GRAPH memory idea popularized by MemMachine
(github.com/MemMachine/MemMachine, Apache-2.0): conversational "episodes" are stored
as nodes in a graph, linked by temporal succession and semantic relatedness, and later
RECALLED by a scored graph query. SZL's ecosystem today is vector+ledger (waqay/rag/lake)
with NO episodic-graph layer — this organ is a GOVERNED, honest, MODELED demonstration
of that missing layer, not a reproduction of MemMachine's code or a claim of its
performance. The classic cognitive-science root of "episodic" (vs. semantic) memory is
Tulving (1972); a related open temporal-knowledge-graph approach is Zep/Graphiti
(github.com/getzep/graphiti).

  GET  /api/<ns>/v1/episodic/recall?seed=&k=&query=&n_episodes=

Returned JSON fields
--------------------
  label               : "MODELED" (always — this is a simulation, not a production
                         episodic-memory store; PUBLIC/synthetic episode content only)
  model                : "temporal knowledge-graph of episodic memory (MemMachine-inspired)"
  n_episodes           : number of episode nodes in the modeled graph
  seed                 : RNG seed used (deterministic; same seed -> same graph + recall)
  query_episode        : the synthetic query episode {id, text, t, salience}
  k                    : number of recalled episodes requested
  graph                : snapshot of all episodes (nodes) + edges (succession/relatedness)
  recall               : top-k episodes for the query, each with the combined score and
                         its three components (recency, salience, relatedness)
  scoring_formula       : the exact deterministic formula used (documented, reproducible)
  honesty_receipts      : per-episode + per-recall-result content-hash + HONEST-STUB
                          signature receipt (see HONEST STATUS below — NEVER a real
                          Sigstore/DSSE signature)
  honest_note           : plain-language honesty disclaimer
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, closed-form simulation of an episodic-memory temporal
  knowledge-graph: a small set of synthetic PUBLIC "episodes" (event/fact nodes with a
  timestamp + salience), edges for temporal succession and semantic relatedness (cosine
  of a MODELED embedding — not a real trained embedding model), and a RECALL operator
  that ranks episodes by recency * salience * relatedness. It is NOT wired to any real
  conversation history, NOT a reproduction of MemMachine's implementation, and stores NO
  private data — synthetic/public content only. The label "MODELED" is returned verbatim
  and displayed verbatim by the surface; it is never upgraded client-side.

GOVERNED DIFFERENCE (what makes this OURS, per doctrine)
  Every episode node and every recall result carries:
    (a) a deterministic SHA-256 content hash of its canonical fields, and
    (b) a Λ-style "honesty receipt" stub — explicitly labeled HONEST-STUB, i.e. a local,
        non-cryptographic placeholder that mimics the SHAPE of a signed provenance
        receipt (see szl_dsse.py / szl_rekor_anchor.py for SZL's REAL Sigstore/DSSE
        signing path elsewhere in the stack). This stub is NEVER presented as a real
        Sigstore signature, DSSE envelope, or Rekor transparency-log entry. It exists so
        the episodic-memory organ demonstrates the GOVERNANCE PATTERN (content-addressed,
        receipted, auditable memory) without fabricating cryptographic trust it hasn't
        earned.

CITATIONS (clean-room; none claimed as SZL's own)
  MemMachine — episodic/graph memory (Apache-2.0):
    https://github.com/MemMachine/MemMachine
  Tulving, E. (1972) "Episodic and Semantic Memory". In Tulving & Donaldson (eds.),
    Organization of Memory, Academic Press. (Classic source of the episodic/semantic
    memory distinction.) https://alicekim.ca/EpisodicSemantic.pdf
  Zep / Graphiti — temporal knowledge-graph memory for agents (related open approach):
    https://github.com/getzep/graphiti

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  PUBLIC/synthetic episode data only — no private conversational content is stored,
  read, or modeled.
"""
from __future__ import annotations

import hashlib
import math
import json
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "MemMachine — episodic/graph memory (Apache-2.0)": "https://github.com/MemMachine/MemMachine",
    "Tulving (1972) — Episodic and Semantic Memory": "https://alicekim.ca/EpisodicSemantic.pdf",
    "Zep / Graphiti — temporal knowledge-graph memory (related open approach)": "https://github.com/getzep/graphiti",
}

# A small bank of PUBLIC/synthetic episode texts — generic, non-personal "events" of the
# kind an episodic-memory demo needs. No real user, customer, or private conversational
# content of any kind. Purely illustrative.
_EPISODE_BANK = [
    "user asked: what is the capital of France?",
    "system answered: Paris.",
    "user asked: convert 10 km to miles.",
    "system answered: approximately 6.21 miles.",
    "user asked: remind me about the Paris question later.",
    "system logged: follow-up reminder scheduled.",
    "user asked: what did I ask about earlier?",
    "system recalled: the Paris capital question.",
    "user asked: what's the weather like generally in Paris?",
    "system answered: temperate oceanic climate, mild summers.",
    "user asked: any relation between km/miles and travel time?",
    "system answered: depends on speed; provided a worked example.",
    "user asked: summarize this session so far.",
    "system answered: two topics covered — geography and unit conversion.",
    "user asked: is Paris also relevant to the reminder?",
    "system answered: yes, the reminder references the earlier Paris question.",
]


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _sha256_hex(obj) -> str:
    """Deterministic content hash of a JSON-canonicalized object."""
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _honesty_receipt_stub(content_hash: str, seed: int, salt: str) -> dict:
    """
    HONEST-STUB receipt — mimics the SHAPE of a signed provenance receipt so this organ
    demonstrates the GOVERNANCE PATTERN, but is explicitly NOT a real cryptographic
    signature. Deterministic from (content_hash, seed, salt) — never random-faked.

    Real SZL signing paths (Sigstore/DSSE/Rekor) live in szl_dsse.py / szl_rekor_anchor.py
    / szl_intoto.py — this stub does not call them and must never be confused with them.
    """
    stub_material = f"{content_hash}:{seed}:{salt}"
    stub_digest = hashlib.sha256(stub_material.encode("utf-8")).hexdigest()
    return {
        "type": "HONEST-STUB",
        "note": (
            "NOT a real Sigstore signature, DSSE envelope, or Rekor transparency-log "
            "entry. This is a local, non-cryptographic placeholder that demonstrates "
            "the governance SHAPE (content hash + receipt) without fabricating trust."
        ),
        "content_hash_sha256": content_hash,
        "stub_signature": stub_digest[:32],  # truncated, clearly illustrative
        "trust_level": "NONE — HONEST-STUB, not verifiable, not a real attestation",
    }


# ---------------------------------------------------------------------------
# MODELED embedding — deterministic, low-dimensional, pure stdlib
# ---------------------------------------------------------------------------
def _modeled_embedding(text: str, seed: int, dim: int = 12) -> list:
    """
    Deterministic MODELED embedding of an episode's text: NOT a real trained embedding
    model (no sentence-transformers, no LLM). Derived from a per-character LCG stream
    seeded by (text, seed), so semantically-similar synthetic strings sharing substrings
    will drift toward the same seed stream deterministically but the vectors are purely
    illustrative — never claimed as a real semantic embedding.
    """
    text_seed = seed
    for ch in text:
        text_seed = (text_seed * 33 + ord(ch)) & 0xFFFFFFFF
    rng = _lcg(text_seed)
    vec = [next(rng) * 2.0 - 1.0 for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Deterministic episodic-memory graph construction
# ---------------------------------------------------------------------------
def _build_graph(seed: int = 42, n_episodes: int = 12, embed_dim: int = 12) -> dict:
    """
    Build a small deterministic temporal knowledge-graph of episodes.

    Nodes  : episodes = {id, text, t (timestamp, minutes since epoch-of-session),
                          salience (0..1, MODELED importance), embedding, content_hash}
    Edges  : (a) temporal-succession — episode i -> i+1 (chronological chain)
             (b) semantic-relatedness — cosine(embedding_i, embedding_j) above a
                 threshold, for non-adjacent pairs (creates cross-references, the
                 hallmark of graph memory vs. a flat log)

    Pure stdlib; deterministic — same seed -> identical graph.
    """
    n_episodes = max(2, min(n_episodes, len(_EPISODE_BANK)))
    rng = _lcg(seed)

    episodes = []
    t_cursor = 0.0
    for i in range(n_episodes):
        text = _EPISODE_BANK[i % len(_EPISODE_BANK)]
        # deterministic inter-episode gap (minutes) — sessions are bursty, not uniform
        gap = 0.5 + 4.5 * next(rng)
        t_cursor += gap
        salience = round(0.25 + 0.75 * next(rng), 4)  # MODELED importance weight
        emb = _modeled_embedding(text, seed=seed + i, dim=embed_dim)
        node = {
            "id": f"ep{i:03d}",
            "text": text,
            "t": round(t_cursor, 3),  # minutes since session start (synthetic clock)
            "salience": salience,
            "embedding": emb,
        }
        node["content_hash"] = _sha256_hex({"id": node["id"], "text": node["text"], "t": node["t"], "salience": node["salience"]})
        episodes.append(node)

    # temporal-succession edges: chronological chain ep_i -> ep_{i+1}
    edges = []
    for i in range(len(episodes) - 1):
        edges.append({
            "src": episodes[i]["id"],
            "dst": episodes[i + 1]["id"],
            "type": "temporal-succession",
            "weight": 1.0,
        })

    # semantic-relatedness edges: non-adjacent pairs above a relatedness threshold
    REL_THRESHOLD = 0.35
    for i in range(len(episodes)):
        for j in range(i + 2, len(episodes)):  # skip adjacent (already temporal)
            rel = _cosine(episodes[i]["embedding"], episodes[j]["embedding"])
            if rel >= REL_THRESHOLD:
                edges.append({
                    "src": episodes[i]["id"],
                    "dst": episodes[j]["id"],
                    "type": "semantic-relatedness",
                    "weight": round(rel, 4),
                })

    return {"episodes": episodes, "edges": edges}


# ---------------------------------------------------------------------------
# RECALL: score = recency * salience * relatedness  (exact, documented, deterministic)
# ---------------------------------------------------------------------------
_SCORING_FORMULA = (
    "score(e, q) = recency(e) * salience(e) * relatedness(e, q), where "
    "recency(e) = exp(-lambda_decay * |t_max - t_e|) (lambda_decay=0.05 per synthetic "
    "minute, most-recent episode has recency=1.0), salience(e) in [0,1] is the MODELED "
    "importance weight stored on the episode node, and relatedness(e, q) = "
    "max(0, cosine(embedding_e, embedding_q)) using the MODELED embedding (not a real "
    "trained embedding model). Top-k episodes by score are returned, ties broken by "
    "episode id (ascending) for full determinism."
)

_LAMBDA_DECAY = 0.05


def _recall(graph: dict, query_text: str, seed: int, k: int, embed_dim: int) -> dict:
    episodes = graph["episodes"]
    if not episodes:
        return {"query_episode": None, "results": []}

    q_emb = _modeled_embedding(query_text, seed=seed + 9973, dim=embed_dim)
    t_max = max(e["t"] for e in episodes)
    query_episode = {
        "id": "query",
        "text": query_text,
        "t": round(t_max, 3),  # query happens "now" = latest timestamp
        "embedding": q_emb,
    }

    scored = []
    for e in episodes:
        recency = math.exp(-_LAMBDA_DECAY * abs(t_max - e["t"]))
        relatedness = max(0.0, _cosine(e["embedding"], q_emb))
        salience = e["salience"]
        score = recency * salience * relatedness
        scored.append({
            "id": e["id"],
            "text": e["text"],
            "t": e["t"],
            "score": round(score, 8),
            "components": {
                "recency": round(recency, 6),
                "salience": salience,
                "relatedness": round(relatedness, 6),
            },
            "content_hash": e["content_hash"],
        })

    scored.sort(key=lambda r: (-r["score"], r["id"]))
    top = scored[: max(1, min(k, len(scored)))]

    # attach an honesty receipt stub to each recall result (per-result, content-addressed)
    for rank, r in enumerate(top):
        r["rank"] = rank
        r["honesty_receipt"] = _honesty_receipt_stub(r["content_hash"], seed=seed, salt=f"recall:{r['id']}")

    return {"query_episode": query_episode, "results": top}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _fi(req: Request, key: str, default) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_recall(req: Request):
    seed       = _ii(req, "seed",       42)
    k          = max(1, min(_ii(req, "k", 3), 10))
    query      = req.query_params.get("query", "what did I ask about earlier?")
    n_episodes = max(2, min(_ii(req, "n_episodes", 12), len(_EPISODE_BANK)))
    embed_dim  = 12

    graph = _build_graph(seed=seed, n_episodes=n_episodes, embed_dim=embed_dim)
    recall = _recall(graph, query_text=query, seed=seed, k=k, embed_dim=embed_dim)

    # per-episode honesty receipts for the full graph snapshot (content-addressed)
    episodes_out = []
    for e in graph["episodes"]:
        e_out = dict(e)
        e_out["honesty_receipt"] = _honesty_receipt_stub(e["content_hash"], seed=seed, salt=f"episode:{e['id']}")
        episodes_out.append(e_out)

    return JSONResponse({
        "label":          "MODELED",
        "model":          "temporal knowledge-graph of episodic memory (MemMachine-inspired)",
        "method":         "content-addressed episode graph + recency*salience*relatedness recall",
        "n_episodes":     n_episodes,
        "seed":           seed,
        "k":              k,
        "query":          query,
        "graph": {
            "episodes": episodes_out,
            "edges":    graph["edges"],
        },
        "recall": {
            "query_episode": recall["query_episode"],
            "top_k":         recall["results"],
        },
        "scoring_formula": _SCORING_FORMULA,
        "honest_note": (
            "MODELED: this is a deterministic closed-form simulation of an episodic-memory "
            "temporal knowledge-graph, clean-room-inspired by MemMachine's episodic/graph "
            "memory concept (github.com/MemMachine/MemMachine, Apache-2.0) — SZL claims NONE "
            "of MemMachine's implementation or performance as its own; this is a studied, "
            "made-ours demonstration of the PATTERN. Episode content is synthetic/PUBLIC only "
            "— no private conversational data is stored, read, or modeled. Embeddings are a "
            "MODELED deterministic construction, not a real trained embedding model. Every "
            "episode and recall result carries a real SHA-256 content hash plus an explicitly "
            "labeled HONEST-STUB receipt — this stub is NOT a real Sigstore signature, DSSE "
            "envelope, or Rekor transparency-log entry (see szl_dsse.py for SZL's real signing "
            "path). Deterministic: same seed -> identical graph and recall. Cite also: Tulving "
            "(1972) for the episodic/semantic memory distinction; Zep/Graphiti "
            "(github.com/getzep/graphiti) as a related open temporal-KG approach. Nothing here "
            "is in the locked-8; Λ stays Conjecture 1; trust never 100%."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_interpretability.register() / szl_neuromorphic.register()
# ---------------------------------------------------------------------------
def register(app, ns: str = "a11oy"):
    """Wire /api/<ns>/v1/episodic/recall onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/episodic"
    handlers = [
        (f"{base}/recall", _h_recall),
    ]
    add_api_route = getattr(app, "add_api_route", None)
    for path, fn in handlers:
        if callable(add_api_route):
            app.add_api_route(path, fn, methods=["GET"])
        else:
            app.router.routes.append(Route(path, fn))
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    graph = _build_graph(seed=42, n_episodes=12, embed_dim=12)
    recall = _recall(graph, query_text="what did I ask about earlier?", seed=42, k=3, embed_dim=12)
    print("label: MODELED")
    print("n_episodes:", len(graph["episodes"]))
    print("n_edges:", len(graph["edges"]))
    print("query:", recall["query_episode"]["text"])
    print("top_k recall scores:")
    for r in recall["results"]:
        print(
            "  ", r["id"], "score=", r["score"],
            "(recency=", r["components"]["recency"],
            ", salience=", r["components"]["salience"],
            ", relatedness=", r["components"]["relatedness"], ")",
            "text=", r["text"],
        )
    print("honesty_receipt[0] type:", recall["results"][0]["honesty_receipt"]["type"])
