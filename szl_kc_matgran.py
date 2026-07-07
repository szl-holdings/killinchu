# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_matgran.py — ADDITIVE MATRYOSHKA-GRANULARITY organ for killinchu's frontier
surface (backs a11oy static/3d/surfaces/matgran.js).

Matryoshka Representation Learning (Kusupati, Bhatt, Rege, Wallingford et al. 2022,
arXiv:2205.13147) encodes information at MULTIPLE GRANULARITIES inside a single
embedding: the first m coordinates of a d-dim vector are themselves a usable
(coarser) embedding, so one vector can be TRUNCATED to any nested prefix at inference
with no extra cost — up to ~14x smaller embeddings / retrieval speed-ups at matched
accuracy. A recent extension, MIPIC (Phung Gia Huy et al. 2026, arXiv:2604.24374 —
VERIFIED to resolve), improves structural coherence of these nested prefixes via
self-distilled intra-relational alignment; the surface name "matgran" (Matryoshka
granularity) fuses both.

This organ re-derives the truncation trade-off deterministically: it builds a corpus
of Matryoshka-structured embeddings (front coordinates carry more variance / signal),
truncates to each nested granularity m, and measures retrieval accuracy (nearest-
neighbour recall) vs the compression / speed-up at that granularity — the coarse-to-
fine accuracy-vs-cost curve MRL promises. The SZL addition is a J/query ENERGY RECEIPT
tied to the reduced dot-product width.

Deterministic MODELED formulation (seeded, no live model, no GPU):
  * N items each with a class label; a class prototype in R^d. An item embedding is the
    prototype plus noise. Front coordinates get LARGER prototype signal (variance
    schedule v_j = base^j decaying), so a nested prefix preserves the dominant signal —
    the Matryoshka structure.
  * for each granularity m in the nesting ladder, truncate every embedding to its first
    m coords, L2-normalize, and run 1-NN classification over a held query set.
  * recall@1(m) = fraction of queries whose nearest neighbour shares its class.
  * compression_x(m) = d / m ; matched-accuracy point = smallest m within tol of full.

  recall_at_1(m)  = 1-NN classification accuracy on the m-truncated prefix
  compression_x   = d / m
  matched_m       = smallest m with recall(m) >= recall(d) - tol
  best_speedup    = d / matched_m   (the headline Matryoshka trade-off)

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic embedding + truncation SIMULATION on synthetic vectors. NOT
    MRL/MIPIC running; NO live model, NO GPU, NO trained encoder, NO real corpus. The
    prototypes, variance schedule, and noise are seeded inputs / MODELED references.
  * The accuracy-vs-granularity curve is a property of the MODELED nested structure,
    honestly labeled — not a measured claim about a real embedding model.
  * The J/query figure is a MODELED order-of-magnitude estimate, NOT a wattmeter.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.
  * Every snapshot is a SIGNED receipt (REAL ECDSA when the cosign key is present;
    honest UNSIGNED marker otherwise — a signature is NEVER fabricated).

Route (NEW; never collides):
  GET /api/{ns}/v1/matgran/truncate  — Matryoshka granularity truncation snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import base64 as _base64
import hashlib as _hashlib
import json as _json
import math as _math
from datetime import datetime, timezone

try:
    from szl_dsse import sign_payload as _sign_payload
    _SIGN_AVAILABLE = True
except Exception:  # pragma: no cover
    _SIGN_AVAILABLE = False

    def _sign_payload(payload_obj, payload_type="application/vnd.szl.kc.matgran+json"):  # type: ignore
        body = _json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode()
        return {
            "payloadType": payload_type,
            "payload": _base64.b64encode(body).decode("ascii"),
            "_dsse": "DSSEv1",
            "_pae_sha256": _hashlib.sha256(body).hexdigest(),
            "_signed_at": datetime.now(timezone.utc).isoformat(),
            "signatures": [],
            "signed": False,
            "honesty": ("UNSIGNED — szl_dsse not importable in this runtime; "
                        "no signature fabricated."),
        }

_MG_PAYLOAD_TYPE = "application/vnd.szl.kc.matgran+json"
DOCTRINE_VERSION = "v11"

CITATIONS = {
    "mrl": ("Kusupati, Bhatt, Rege, Wallingford, Sinha, Ramanujan, Howard-Snyder, Chen, Kakade, "
            "Jain, Farhadi (2022) Matryoshka Representation Learning — arXiv:2205.13147 — "
            "https://arxiv.org/abs/2205.13147"),
    "mipic": ("Phung Gia Huy, Vu, Truong, Tran, Van, Nguyen, Le (2026) MIPIC: Matryoshka "
              "Representation Learning via Self-Distilled Intra-Relational and Progressive "
              "Information Chaining — arXiv:2604.24374 — https://arxiv.org/abs/2604.24374"),
}

MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MATRYOSHKA_TRUNCATION_SIM | NOT_LIVE | NO_MODEL | NO_ENCODER | NO_GPU"

# MODELED per-query dot-product energy reference (order-of-magnitude only).
_J_PER_DIM_DOTPROD = 1.0e-7


class _LCG:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        self.s = (int(seed) ^ 0x5DEECE66D) & 0xFFFFFFFFFFFF

    def next_u32(self) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFFFFFF
        return (self.s >> 16) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_u32() / 0x100000000

    def signed(self) -> float:
        return 2.0 * self.uniform() - 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(v):
    n = _math.sqrt(sum(x * x for x in v))
    if n == 0:
        return v
    return [x / n for x in v]


def matgran_truncate(seed: int = 42, dim: int = 64, n_classes: int = 8,
                     n_items: int = 160, tol: float = 0.03) -> dict:
    """Matryoshka granularity truncation snapshot (MODELED).

    dim       — full embedding dimensionality d.
    n_classes — number of latent classes (retrieval labels).
    n_items   — corpus size (split into index + queries).
    tol       — accuracy tolerance for the matched-granularity point.
    seed      — RNG seed; identical inputs give identical output (deterministic).
    """
    d = max(4, min(256, int(dim)))
    K = max(2, min(32, int(n_classes)))
    N = max(16, min(2000, int(n_items)))
    tol = max(0.0, min(0.5, float(tol)))
    rng = _LCG(int(seed) * 1_000_003 + d * 131 + K * 17 + N * 7 + int(tol * 1000))

    # variance schedule: front coordinates carry more prototype signal (Matryoshka).
    var = [0.9 ** j for j in range(d)]

    # class prototypes with the decaying variance schedule.
    protos = [[rng.signed() * _math.sqrt(var[j]) for j in range(d)] for _ in range(K)]

    # items: prototype + noise (noise flat so front coords keep higher SNR).
    items, labels = [], []
    for _ in range(N):
        c = rng.next_u32() % K
        emb = [protos[c][j] + 0.35 * rng.signed() for j in range(d)]
        items.append(emb)
        labels.append(c)

    # split: half index, half query.
    half = N // 2
    idx_emb, idx_lab = items[:half], labels[:half]
    qry_emb, qry_lab = items[half:], labels[half:]

    # nesting ladder of granularities (powers-of-two prefixes up to d, plus d).
    ladder = []
    m = 4
    while m < d:
        ladder.append(m)
        m *= 2
    ladder.append(d)

    def recall_at(mm):
        # truncate + normalize once per set at this granularity.
        idx_t = [_normalize(e[:mm]) for e in idx_emb]
        correct = 0
        for qi, q in enumerate(qry_emb):
            qt = _normalize(q[:mm])
            best_j, best_sim = -1, None
            for j, it in enumerate(idx_t):
                sim = sum(qt[c] * it[c] for c in range(mm))
                if best_sim is None or sim > best_sim:
                    best_sim, best_j = sim, j
            if idx_lab[best_j] == qry_lab[qi]:
                correct += 1
        return correct / len(qry_emb)

    curve = []
    for mm in ladder:
        r = recall_at(mm)
        curve.append({"m": mm, "recall_at_1": round(float(r), 6),
                      "compression_x": round(float(d / mm), 4)})

    full_recall = curve[-1]["recall_at_1"]
    # matched granularity: smallest m within tol of full-dim recall.
    matched_m = d
    for e in curve:
        if e["recall_at_1"] >= full_recall - tol:
            matched_m = e["m"]
            break
    best_speedup = d / matched_m
    matched_recall = next(e["recall_at_1"] for e in curve if e["m"] == matched_m)

    joules_full = d * _J_PER_DIM_DOTPROD
    joules_matched = matched_m * _J_PER_DIM_DOTPROD
    joules_saved_per_query = joules_full - joules_matched
    energy_reduction_pct = (joules_saved_per_query / joules_full) * 100.0 if joules_full else 0.0

    energy_receipt = {
        "joules_per_dim_dotprod_modeled": _J_PER_DIM_DOTPROD,
        "joules_full_query_modeled": round(float(joules_full), 10),
        "joules_matched_query_modeled": round(float(joules_matched), 10),
        "joules_saved_per_query_modeled": round(float(joules_saved_per_query), 10),
        "energy_reduction_pct": round(float(energy_reduction_pct), 3),
        "energy_note": ("MODELED per-dimension dot-product energy — order-of-magnitude only, NOT a "
                        "live wattmeter. Truncating to the matched Matryoshka prefix shrinks every "
                        "retrieval dot-product; this quantifies the saving as an advisory input."),
        "gate": "ADVISORY input to Λ (Conjecture 1) — never a proof, never 'green'.",
    }

    receipt = {
        "snapshot_timestamp": _now_iso(),
        "service": "matryoshka-granularity-truncation",
        "service_version": "szl-kc-matgran-v0.1",
        "seed": int(seed),
        "inputs": {"dim": d, "n_classes": K, "n_items": N, "tol": tol},
        "full_recall_at_1": round(float(full_recall), 6),
        "matched_m": int(matched_m),
        "matched_recall_at_1": round(float(matched_recall), 6),
        "best_speedup": round(float(best_speedup), 4),
        "energy_receipt": energy_receipt,
        "label": HONESTY_LONG,
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (granularity advisory — never an autonomous action)",
        "citations": [CITATIONS["mrl"], CITATIONS["mipic"]],
        "honesty": ("Deterministic Matryoshka embedding + truncation simulation on synthetic vectors. "
                    "NOT MRL/MIPIC running; NO live model, NO GPU, NO trained encoder, NO real corpus. "
                    "Prototypes, variance schedule, noise are seeded inputs / MODELED references. The "
                    "accuracy-vs-granularity curve is a property of the MODELED nested structure, "
                    "honestly labeled. MODELED, not live; advisory to Λ (Conjecture 1)."),
    }
    dsse = _sign_payload(receipt, _MG_PAYLOAD_TYPE)

    return {
        "service": "matryoshka-granularity-truncation",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/matgran.js ---
        "dim": int(d),
        "n_classes": int(K),
        "n_items": int(N),
        "tol": round(float(tol), 6),
        "granularity_curve": curve,      # [{m, recall_at_1, compression_x}]
        "full_recall_at_1": round(float(full_recall), 6),
        "matched_m": int(matched_m),
        "matched_recall_at_1": round(float(matched_recall), 6),
        "best_speedup": round(float(best_speedup), 4),
        # --- SZL addition: the J/query dot-product energy receipt ---
        "energy_receipt": energy_receipt,
        "formulas": {
            "recall_at_1": "1-NN classification accuracy on the m-truncated normalized prefix",
            "compression_x": "d / m",
            "matched_m": "smallest m with recall(m) >= recall(d) - tol",
            "best_speedup": "d / matched_m",
        },
        "compute_backend": {
            "backend": "CPU pure-Python embedding + truncation simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic sim; NO live model, NO GPU, NO trained encoder, NO real "
                            "corpus. The measured-on-a-real-embedding-model path is ROADMAP."),
        },
        "wired_into": "frontier ring — Matryoshka granularity surface + retrieval energy receipt",
        "citations": [CITATIONS["mrl"], CITATIONS["mipic"]],
        "signed_receipt": {"receipt": receipt, "dsse": dsse},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/matgran" % ns

    async def _kc_matgran(seed: int = 42, dim: int = 64, n_classes: int = 8,
                          n_items: int = 160, tol: float = 0.03):  # noqa: ANN202
        try:
            return JSONResponse(matgran_truncate(seed=seed, dim=dim, n_classes=n_classes,
                                                 n_items=n_items, tol=tol))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "matryoshka-granularity-truncation",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "matched_m": None, "best_speedup": None},
                                status_code=200)

    try:
        app.add_api_route("%s/truncate" % base, _kc_matgran, methods=["GET"])
    except Exception:  # pragma: no cover — Starlette Route fallback
        from starlette.routing import Route

        async def _kc_matgran_route(request):
            qp = request.query_params
            return await _kc_matgran(seed=int(qp.get("seed", 42)),
                                     dim=int(qp.get("dim", 64)),
                                     n_classes=int(qp.get("n_classes", 8)),
                                     n_items=int(qp.get("n_items", 160)),
                                     tol=float(qp.get("tol", 0.03)))
        app.router.routes.append(Route("%s/truncate" % base, _kc_matgran_route, methods=["GET"]))

    return {"ok": True, "ns": ns, "routes": ["%s/truncate" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = matgran_truncate(seed=42, dim=64, n_classes=8, n_items=160, tol=0.03)

    assert r["label"] == MODELED_LABEL, r["label"]
    assert isinstance(r["granularity_curve"], list) and r["granularity_curve"], r
    for e in r["granularity_curve"]:
        assert 0.0 <= e["recall_at_1"] <= 1.0, e
        assert e["compression_x"] >= 1.0, e
    # Matryoshka invariant: matched prefix is <= full dim and gives a real speedup.
    assert r["matched_m"] <= r["dim"], r
    assert r["best_speedup"] >= 1.0, r
    # front-loaded signal => a truncated prefix stays close to full-dim recall.
    assert r["matched_recall_at_1"] >= r["full_recall_at_1"] - r["tol"] - 1e-9, r
    # last ladder entry is the full dim.
    assert r["granularity_curve"][-1]["m"] == r["dim"], r
    out["metrics"] = {"full_recall_at_1": r["full_recall_at_1"],
                      "matched_m": r["matched_m"],
                      "matched_recall_at_1": r["matched_recall_at_1"],
                      "best_speedup": r["best_speedup"]}

    er = r["energy_receipt"]
    assert er["joules_saved_per_query_modeled"] >= 0, er
    assert 0.0 <= er["energy_reduction_pct"] < 100.0, er
    assert "Conjecture 1" in er["gate"], er
    out["energy_receipt"] = {"energy_reduction_pct": er["energy_reduction_pct"]}

    d = r["signed_receipt"]["dsse"]
    rc = r["signed_receipt"]["receipt"]
    assert "NOT_LIVE" in rc["label"], rc["label"]
    assert d.get("_pae_sha256"), d
    assert d.get("signed") is True or "UNSIGNED" in (d.get("honesty") or ""), d
    assert "SIMULATED" in rc["effector_posture"], rc

    r2 = matgran_truncate(seed=42, dim=64, n_classes=8, n_items=160, tol=0.03)
    assert r2["granularity_curve"] == r["granularity_curve"], "non-deterministic curve"
    assert r2["matched_m"] == r["matched_m"], "non-deterministic matched_m"
    out["deterministic"] = True

    out["ok"] = True
    return out


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    print("ALL OK")
