# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_episodic.py — FRONTIER WAVE C. ADDITIVE governed EPISODIC-MEMORY /
temporal-knowledge-graph backend for the a11oy frontier surface
(static/3d/surfaces/episodic.js → GET /api/killinchu/v1/episodic/recall).

WHAT THIS IS
------------
A deterministic, seeded SIMULATION of the *pattern* of a temporal knowledge-graph
episodic memory: discrete "episodes" (event/fact nodes) laid out on a TIME axis,
linked by (a) temporal-succession edges (the chronological chain) and (b)
semantic-relatedness edges (cosine of a MODELED embedding). A RECALL query ranks
episodes by a closed-form recency×salience×relatedness score, and the top-k light
up on the frontier ring. Every episode carries a REAL content hash and an explicitly
labeled HONEST receipt (REAL ECDSA/DSSE when the cosign key is present in-Space; an
explicit UNSIGNED honesty marker otherwise — never a fabricated signature). Writes
are RECEIPT-KEYED: each episode id is derived from its content hash, so a write is
addressable and tamper-evident.

CLOSED-FORM RECALL SCORE (shown verbatim in the surface overlay):
  recency_i      = exp(-(t_query - t_i) / tau)                 (exponential recency decay)
  relatedness_i  = cos(e_query, e_i) = (e_query · e_i)/(|e_q||e_i|)   (MODELED embedding)
  score_i        = recency_i ^ w_r · salience_i ^ w_s · max(0, relatedness_i) ^ w_rel
  top_k          = argsort_desc(score_i)[:k]

HONESTY SPINE (Doctrine v11):
  * MODELED. PUBLIC/synthetic episode content only. The embeddings are a MODELED
    hash-seeded construction — NOT a real trained embedding model. The score is a
    demonstration of the recall MECHANISM, not a benchmark of a production memory store.
  * Clean-room-inspired by (NOT a reproduction of) MemMachine's episodic/graph memory
    idea and Zep/Graphiti's temporal knowledge-graph memory. Cited, never claimed-as.
  * Adds NOTHING to the locked-8. Λ stays Conjecture 1 (advisory, never "green").
  * Receipts REAL ECDSA only in-Space; honest UNSIGNED marker otherwise.

Route (NEW; never collides):
  GET /api/{ns}/v1/episodic/recall  — recall over a SAMPLE/synthetic episodic graph

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.

LEADERS ADOPTED & CITED (clean-room; NOT claimed as SZL's own):
  Rasmussen, Paliwal et al. (2025) "Zep: A Temporal Knowledge Graph Architecture for
    Agent Memory" (Graphiti) — arXiv:2501.13956 — https://arxiv.org/abs/2501.13956
  Graphiti (Zep) temporal knowledge-graph memory — https://github.com/getzep/graphiti
  MemMachine — episodic/graph memory (Apache-2.0) — https://github.com/MemMachine/MemMachine
  Tulving (1972) "Episodic and Semantic Memory" — https://alicekim.ca/EpisodicSemantic.pdf
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import random as _random
from datetime import datetime, timezone, timedelta

# --- signed receipts: the SINGLE source of truth (never fabricate a signature) ----
try:
    from szl_dsse import sign_payload as _sign_payload  # REAL ECDSA when key present
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover — honest UNSIGNED marker otherwise
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.episodic+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": __import__("base64").b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_EPISODIC_PAYLOAD_TYPE = "application/vnd.szl.kc.episodic+json"

DOCTRINE_VERSION = "v11"

CITATIONS = {
    "zep_graphiti": ("Rasmussen, Paliwal et al. (2025) Zep: A Temporal Knowledge Graph "
                     "Architecture for Agent Memory (Graphiti) — arXiv:2501.13956"),
    "graphiti_repo": "Graphiti (Zep) temporal knowledge-graph memory — github.com/getzep/graphiti",
    "memmachine": "MemMachine — episodic/graph memory (Apache-2.0) — github.com/MemMachine/MemMachine",
    "tulving": "Tulving (1972) Episodic and Semantic Memory — alicekim.ca/EpisodicSemantic.pdf",
}

# MODELED label — labeled model output, synthetic content, never live, never claimed-as.
MODELED_LABEL = "MODELED"
MODELED_LABEL_LONG = "MODELED | SAMPLE_SYNTHETIC | NOT_LIVE | CLEAN_ROOM_INSPIRED"

# recall hyperparameters (deterministic, documented)
_TAU = 6.0        # recency decay constant (episode-time units)
_W_RECENCY = 1.0
_W_SALIENCE = 1.0
_W_RELATED = 1.0
_EMBED_DIM = 8

# a small deterministic bank of PUBLIC/synthetic episode texts (agent-session flavored)
_EPISODE_BANK = [
    "user asked about the signed-receipt verifier",
    "explained the deny-by-default governance gate",
    "user reported a maritime track anomaly near the strait",
    "walked through the Lean-checked ROE gate",
    "user asked what killinchu is",
    "described the BFT witness quorum",
    "logged joules-per-token on the energy receipt",
    "user asked how memory persists between sessions",
    "clarified that the effector stays SIMULATED",
    "summarized the below-threshold QEC survival demo",
    "user asked about air-gapped / on-prem deployment",
    "recorded the topological fracture regime-shift alert",
    "explained the locked-8 machine-checked theorem",
    "user asked what did I ask about earlier?",
    "noted Λ remains Conjecture 1, advisory only",
    "captured the temporal knowledge-graph episode chain",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text: str) -> str:
    return _hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embed(text: str, dim: int = _EMBED_DIM):
    """MODELED, deterministic hash-seeded unit embedding — NOT a trained model."""
    h = _hashlib.sha256(("szl-episodic::" + text).encode("utf-8")).digest()
    rng = _random.Random(int.from_bytes(h[:8], "big"))
    v = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = _math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))  # already unit vectors


def _honesty_receipt(text: str, cid: str) -> dict:
    """Per-episode receipt-keyed HONEST marker (never a fabricated signature)."""
    return {
        "type": "HONEST-STUB",
        "content_hash": cid,
        "key_scheme": "receipt-keyed (episode id = sha256(content)[:12])",
        "signed": False,
        "honesty": ("HONEST-STUB — real content fingerprint; a labeled placeholder for "
                    "real Sigstore/DSSE signing, never faked as one."),
    }


def episodic_recall(query: str = "what did I ask about earlier?",
                    k: int = 3, n_episodes: int = 12, seed: int = 42) -> dict:
    """Build a SAMPLE episodic temporal knowledge-graph and run a closed-form recall.

    Returns a JSON shape read VERBATIM by a11oy static/3d/surfaces/episodic.js:
      { label, graph:{episodes[],edges[]}, recall:{query_episode,top_k[]},
        scoring_formula, signed_receipt, ... }
    """
    # ---- bounds (defensive) ----
    n_episodes = max(3, min(16, int(n_episodes)))
    k = max(1, min(n_episodes, int(k)))
    query = str(query or "what did I ask about earlier?")[:240]

    rng = _random.Random(int(seed))
    base_t = 0.0

    # ---- build episodes on a monotone time axis with MODELED salience ----
    episodes = []
    embeds = {}
    for i in range(n_episodes):
        text = _EPISODE_BANK[i % len(_EPISODE_BANK)]
        # monotone increasing time (older -> newer), deterministic jitter
        t = round(base_t + i * 1.0 + rng.uniform(0.0, 0.35), 4)
        # MODELED salience in (0,1]: hash-seeded, stable per text
        sal_seed = int(_hashlib.sha256(("sal::" + text).encode()).hexdigest()[:8], 16)
        salience = round(0.35 + 0.6 * ((sal_seed % 1000) / 1000.0), 4)
        cid = _content_hash(text)
        eid = "ep-" + cid[:12]  # RECEIPT-KEYED id derived from content hash
        embeds[eid] = _embed(text)
        episodes.append({
            "id": eid,
            "text": text,
            "t": t,
            "salience": salience,
            "content_hash": cid,
            "honesty_receipt": _honesty_receipt(text, cid),
        })

    t_query = episodes[-1]["t"] + 1.0  # query episode = "now"
    q_embed = _embed(query)

    # ---- edges: temporal-succession chain + semantic-relatedness (cosine threshold) ----
    edges = []
    for i in range(1, len(episodes)):
        edges.append({
            "src": episodes[i - 1]["id"],
            "dst": episodes[i]["id"],
            "type": "temporal-succession",
            "weight": 1.0,
        })
    sem_threshold = 0.35
    for i in range(len(episodes)):
        for j in range(i + 1, len(episodes)):
            a = embeds[episodes[i]["id"]]
            b = embeds[episodes[j]["id"]]
            rel = _cos(a, b)
            if rel >= sem_threshold:
                edges.append({
                    "src": episodes[i]["id"],
                    "dst": episodes[j]["id"],
                    "type": "semantic-relatedness",
                    "weight": round(float(rel), 4),
                })

    # ---- closed-form recall: recency×salience×relatedness ----
    scored = []
    for e in episodes:
        dt = max(0.0, t_query - e["t"])
        recency = _math.exp(-dt / _TAU)
        relatedness = max(0.0, _cos(q_embed, embeds[e["id"]]))
        salience = e["salience"]
        # weighted geometric combination (documented formula)
        score = (recency ** _W_RECENCY) * (salience ** _W_SALIENCE) * \
                ((relatedness + 1e-9) ** _W_RELATED)
        scored.append((e["id"], score, recency, salience, relatedness))

    scored.sort(key=lambda r: r[1], reverse=True)
    top_k = []
    for rank, (eid, score, recency, salience, relatedness) in enumerate(scored[:k], start=1):
        top_k.append({
            "id": eid,
            "score": round(float(score), 6),
            "rank": rank,
            "components": {
                "recency": round(float(recency), 6),
                "salience": round(float(salience), 6),
                "relatedness": round(float(relatedness), 6),
            },
        })

    query_episode = {
        "id": "ep-query",
        "text": query,
        "t": round(float(t_query), 4),
        "content_hash": _content_hash(query),
    }

    scoring_formula = ("score_i = recency_i^w_r · salience_i^w_s · relatedness_i^w_rel ; "
                       "recency_i = exp(-(t_q - t_i)/tau) ; "
                       "relatedness_i = cos(e_q, e_i) ; "
                       "tau=%.1f, w_r=%.1f, w_s=%.1f, w_rel=%.1f" %
                       (_TAU, _W_RECENCY, _W_SALIENCE, _W_RELATED))

    receipt = {
        "window_timestamp": _now_iso(),
        "organ": "episodic-memory-temporal-kg",
        "organ_version": "szl-kc-episodic-v0.1",
        "data_source": "SAMPLE_SYNTHETIC",
        "n_episodes": len(episodes),
        "n_edges": len(edges),
        "query": query,
        "top_recall_id": top_k[0]["id"] if top_k else None,
        "top_recall_score": top_k[0]["score"] if top_k else None,
        "label": MODELED_LABEL_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "N/A (read-only memory organ — never an engage)",
        "citations": [CITATIONS["zep_graphiti"], CITATIONS["graphiti_repo"],
                      CITATIONS["memmachine"], CITATIONS["tulving"]],
        "honesty": ("MODELED episodic temporal-knowledge-graph. Synthetic/public episodes; "
                    "embeddings are a hash-seeded MODELED construction (NOT a trained model). "
                    "Receipt-keyed writes; per-episode HONEST-STUB receipt (never a fabricated "
                    "signature). Clean-room-inspired by Zep/Graphiti + MemMachine; not claimed-as."),
    }
    dsse = _sign_payload(receipt, _EPISODIC_PAYLOAD_TYPE)

    return {
        "service": "episodic-memory",
        "label": MODELED_LABEL,          # read VERBATIM by episodic.js
        "graph": {"episodes": episodes, "edges": edges},
        "recall": {
            "query_episode": query_episode,
            "top_k": top_k,
        },
        "query": query,
        "scoring_formula": scoring_formula,
        "formulas": {
            "recency": "recency_i = exp(-(t_q - t_i)/tau)",
            "relatedness": "relatedness_i = cos(e_q, e_i)",
            "score": "score_i = recency_i^w_r · salience_i^w_s · relatedness_i^w_rel",
        },
        "compute_backend": {
            "backend": "CPU pure-Python (stdlib)",
            "label": "MODELED",
            "honest_note": ("Deterministic hash-seeded embeddings + closed-form recall. NO "
                            "trained embedding model, NO vector DB, NO live session store."),
        },
        "wired_into": "frontier ring · episodic-memory organ (episodic.js)",
        "citations": [CITATIONS["zep_graphiti"], CITATIONS["graphiti_repo"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/episodic" % ns

    @app.get("%s/recall" % base)
    async def _kc_episodic(query: str = "what did I ask about earlier?",
                           k: int = 3, n_episodes: int = 12, seed: int = 42):  # noqa: ANN202
        try:
            return JSONResponse(episodic_recall(query=query, k=k,
                                                n_episodes=n_episodes, seed=seed))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "episodic-memory", "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (type(exc).__name__),
                                 "graph": {"episodes": [], "edges": []},
                                 "recall": {"top_k": []}}, status_code=200)

    return {"ok": True, "ns": ns, "routes": ["%s/recall" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = episodic_recall(query="what did I ask about earlier?", k=3, n_episodes=12, seed=42)
    assert r["label"] == MODELED_LABEL, r["label"]
    eps = r["graph"]["episodes"]
    assert len(eps) == 12, len(eps)
    for e in eps:
        for f in ("id", "text", "t", "salience", "content_hash", "honesty_receipt"):
            assert f in e, (f, e)
        assert e["honesty_receipt"]["type"] == "HONEST-STUB", e["honesty_receipt"]
        assert 0.0 < e["salience"] <= 1.0, e["salience"]
        # receipt-keyed: id derived from content hash
        assert e["id"] == "ep-" + e["content_hash"][:12], e
    edges = r["graph"]["edges"]
    assert any(x["type"] == "temporal-succession" for x in edges), "no temporal edges"
    for x in edges:
        assert x["type"] in ("temporal-succession", "semantic-relatedness"), x
        for f in ("src", "dst", "type", "weight"):
            assert f in x, (f, x)
    tk = r["recall"]["top_k"]
    assert 1 <= len(tk) <= 12, len(tk)
    for row in tk:
        for f in ("id", "score", "rank", "components"):
            assert f in row, (f, row)
        for c in ("recency", "salience", "relatedness"):
            assert c in row["components"], (c, row)
    # scores are sorted descending
    assert all(tk[i]["score"] >= tk[i + 1]["score"] for i in range(len(tk) - 1)), tk
    assert r["scoring_formula"] and "recency" in r["scoring_formula"], r["scoring_formula"]
    assert r["recall"]["query_episode"]["text"], r["recall"]["query_episode"]
    out["top_k"] = [(t["id"], t["score"]) for t in tk]

    # determinism: same seed -> identical top ids
    r2 = episodic_recall(query="what did I ask about earlier?", k=3, n_episodes=12, seed=42)
    assert [t["id"] for t in r2["recall"]["top_k"]] == [t["id"] for t in tk], "non-deterministic"

    # signed receipt present + honest label; never fabricated
    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    out["signed"] = d.get("signed")
    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    print(_json.dumps(_selftest(), indent=2), file=sys.stderr)
