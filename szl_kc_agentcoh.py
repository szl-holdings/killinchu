# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED: locked-proven=8 · Λ=Conjecture 1 · SLSA L1 honest / L2 attested / L3 roadmap
# Co-Authored-By: Perplexity Computer Agent
"""
szl_kc_agentcoh.py — ADDITIVE agent-coherence artifact-sync organ for killinchu's frontier
surface (backs a11oy static/3d/surfaces/agentcoh.js).

Token Coherence (Parakhin 2026, arXiv:2603.15183) observes that multi-agent LLM orchestration
under naive full-state rebroadcast incurs synchronization cost O(n x S x |D|) in agents (n),
steps (S), and artifact size (|D|) — a triply-multiplicative overhead. The paper maps this
onto the CACHE COHERENCE problem in shared-memory multiprocessors and transfers the MESI
invalidation protocol to artifact synchronization: instead of rebroadcasting full state, an
agent that writes an artifact INVALIDATES other agents' cached copies; a reader re-fetches
lazily only when it next needs the artifact. The Token Coherence Theorem gives a savings lower
bound converting O(n x S x |D|) to O((n + W) x |D|).

Deterministic MODELED formulation (seeded, no live agents):
  * n agents share |D| artifacts over S steps. Each step a seeded agent writes a seeded
    artifact (a write event). Two modes are simulated on the SAME event stream:
      - broadcast: every write pushes the full artifact to all n-1 peers -> tokens = |D| each.
      - MESI: a write only sends tiny INVALIDATION messages (cost ~1 each) to holders; a peer
        re-reads the full artifact lazily only when it actually accesses it next (access prob V).
  * Report: tokens under each mode, token-savings fraction, per-artifact coherence state
    counts (Modified/Exclusive/Shared/Invalid), and single-writer-safety (never two writers
    concurrently modified).

  broadcast_tokens = sum over writes of (n-1) * |artifact|
  mesi_tokens      = sum over writes of (holders * 1)  +  sum over lazy reads of |artifact|
  savings_frac     = 1 - mesi_tokens / broadcast_tokens

HONESTY SPINE (Doctrine v11):
  * MODELED deterministic MESI-vs-broadcast SIMULATION over a seeded write/read event stream.
    NOT LangGraph/CrewAI/AutoGen running; NO live agents, NO live LLM, NO GPU. Artifact "sizes"
    and the access probability V are SEEDED inputs, not measured token counts.
  * Single-writer safety and monotonic versioning are enforced BY CONSTRUCTION in the sim and
    asserted; that is a property of the modeled protocol, honestly labeled, not a live proof.
    This organ NEVER claims to prove anything or add to the locked-8.
  * The savings figure is a MODELED order-of-magnitude reading of the paper's theorem on this
    seeded workload, not a benchmark on a real agent system.
  * Label "MODELED" is returned verbatim and read verbatim by the frontend; never upgraded.
  * Advisory only (Λ = Conjecture 1); adds nothing to the locked-8; trust never 100%.

Route (NEW; never collides):
  GET /api/{ns}/v1/agentcoh/sync  — agent-coherence artifact-sync snapshot (MODELED)

Pure stdlib. Defensive: a compute failure NEVER raises out of a handler.
"""
from __future__ import annotations

import json as _json
import math as _math
from datetime import datetime, timezone

DOCTRINE_VERSION = "v11"
MODELED_LABEL = "MODELED"
HONESTY_LONG = "MODELED | MESI_COHERENCE_SIM | NOT_LIVE | NO_AGENTS | NO_LLM"

CITATIONS = {
    "token_coherence": ("Parakhin (2026) Token Coherence: Adapting MESI Cache Protocols to "
                        "Minimize Synchronization Overhead in Multi-Agent LLM Systems — "
                        "arXiv:2603.15183"),
    "token_coherence_url": "https://arxiv.org/abs/2603.15183",
}

# MESI states
_M, _E, _S, _I = "Modified", "Exclusive", "Shared", "Invalid"


class _LCG:
    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (int(seed) * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def random(self) -> float:
        self._s = (self._s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._s >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    def randint(self, lo: int, hi: int) -> int:
        return lo + int(self.random() * (hi - lo + 1)) % (hi - lo + 1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def agentcoh_sync(seed: int = 42, agents: int = 6, artifacts: int = 5, steps: int = 400,
                  artifact_size: int = 64, access_prob: float = 0.25) -> dict:
    """Agent-coherence artifact-sync snapshot (MODELED).

    agents        — n cooperating agents.
    artifacts     — |D| shared artifacts.
    steps         — S orchestration steps (each step: one write, then probabilistic reads).
    artifact_size — MODELED token size of a full artifact push / lazy re-read.
    access_prob   — V, per-peer probability of accessing an invalidated artifact next.
    """
    n = max(2, min(256, int(agents)))
    D = max(1, min(256, int(artifacts)))
    S = max(1, min(50000, int(steps)))
    sz = max(1, min(100000, int(artifact_size)))
    V = max(0.0, min(1.0, float(access_prob)))
    rng = _LCG(int(seed) * 1_000_003 + n * 131 + D * 17 + S)

    # per-artifact MESI state per agent; start all Invalid
    state = [[_I] * n for _ in range(D)]
    version = [0] * D
    holders = [set() for _ in range(D)]   # agents with a valid (M/E/S) copy

    broadcast_tokens = 0
    mesi_tokens = 0
    invalidations = 0
    lazy_reads = 0
    writes = 0
    max_concurrent_modified = 0
    version_monotone = True

    for _ in range(S):
        a = rng.randint(0, n - 1)     # writer
        art = rng.randint(0, D - 1)   # artifact written
        writes += 1

        # --- broadcast mode cost: push full artifact to all peers ---
        broadcast_tokens += (n - 1) * sz

        # --- MESI mode cost: invalidate holders (cheap), writer becomes Modified ---
        peers_holding = holders[art] - {a}
        invalidations += len(peers_holding)
        mesi_tokens += len(peers_holding) * 1   # tiny invalidation message
        # single-writer safety: exactly one Modified after a write
        for ag in range(n):
            state[art][ag] = _I
        state[art][a] = _M
        holders[art] = {a}
        prev_v = version[art]
        version[art] = prev_v + 1
        if version[art] <= prev_v:
            version_monotone = False
        # count Modified copies of THIS artifact across agents (must be exactly 1)
        mod_count = sum(1 for ag in range(n) if state[art][ag] == _M)
        max_concurrent_modified = max(max_concurrent_modified, mod_count)

        # --- lazy reads: each other agent re-reads with prob V (its next access) ---
        for ag in range(n):
            if ag == a:
                continue
            if rng.random() < V:
                lazy_reads += 1
                mesi_tokens += sz            # lazy full re-read only when actually accessed
                # reader now Shared; writer downgrades Modified->Shared
                if state[art][a] == _M:
                    state[art][a] = _S
                state[art][ag] = _S
                holders[art].add(ag)

    savings_frac = (1.0 - mesi_tokens / broadcast_tokens) if broadcast_tokens > 0 else 0.0

    # final coherence-state census across all artifacts x agents
    census = {_M: 0, _E: 0, _S: 0, _I: 0}
    for art in range(D):
        for ag in range(n):
            census[state[art][ag]] += 1

    return {
        "service": "agent-coherence-artifact-sync",
        "label": MODELED_LABEL,
        # --- fields read VERBATIM by a11oy static/3d/surfaces/agentcoh.js ---
        "agents": int(n),
        "artifacts": int(D),
        "steps": int(S),
        "artifact_size": int(sz),
        "broadcast_tokens": int(broadcast_tokens),
        "mesi_tokens": int(mesi_tokens),
        "token_savings_frac": round(float(savings_frac), 6),
        "token_savings_pct": round(float(savings_frac * 100.0), 3),
        "invalidations": int(invalidations),
        "lazy_reads": int(lazy_reads),
        "writes": int(writes),
        "coherence_state_census": {k: int(v) for k, v in census.items()},
        "single_writer_safe": bool(max_concurrent_modified <= 1),
        "version_monotone": bool(version_monotone),
        "formulas": {
            "broadcast_tokens": "sum_writes (n-1) * |artifact|",
            "mesi_tokens": "sum_writes (holders * 1) + sum_lazy_reads |artifact|",
            "token_savings_frac": "1 - mesi_tokens / broadcast_tokens",
        },
        "compute_backend": {
            "backend": "CPU pure-Python MESI-vs-broadcast simulation",
            "label": "MODELED",
            "honest_note": ("Deterministic MESI-vs-broadcast sim over a seeded write/read stream; "
                            "NO LangGraph/CrewAI/AutoGen, NO live agents, NO live LLM, NO GPU. "
                            "Artifact sizes and access prob V are seeded inputs. A live "
                            "multi-agent integration is ROADMAP."),
        },
        "doctrine": DOCTRINE_VERSION,
        "lambda": "Conjecture 1 (advisory, NOT a theorem)",
        "effector_posture": "SIMULATED · human-on-loop (sync advisory — never an autonomous action)",
        "wired_into": "frontier ring — Agent-Coherence surface",
        "honest_note": ("MODELED deterministic simulation of MESI artifact-coherence vs naive "
                        "broadcast for multi-agent LLM sync, following the Token Coherence paper. "
                        "Single-writer safety and monotonic versioning are enforced in the sim, "
                        "NOT proven; this organ adds nothing to the locked-8. MODELED, not live; "
                        "advisory to Λ (Conjecture 1)."),
        "citations": {"token_coherence": CITATIONS["token_coherence"],
                      "token_coherence_url": CITATIONS["token_coherence_url"]},
        "computed_at": _now_iso(),
    }


# =====================================================================================
# Registration (additive).
# =====================================================================================
def register(app, ns: str = "killinchu") -> dict:
    from fastapi.responses import JSONResponse

    base = "/api/%s/v1/agentcoh" % ns

    @app.get("%s/sync" % base)
    async def _kc_agentcoh(seed: int = 42, agents: int = 6, artifacts: int = 5,
                           steps: int = 400):  # noqa: ANN202
        try:
            return JSONResponse(agentcoh_sync(seed=seed, agents=agents, artifacts=artifacts,
                                              steps=steps))
        except Exception as exc:  # pragma: no cover — never 500 the surface
            return JSONResponse({"service": "agent-coherence-artifact-sync",
                                 "label": MODELED_LABEL,
                                 "error": "compute fail-open: %s" % (str(exc)[:160]),
                                 "token_savings_frac": None}, status_code=200)

    try:
        from starlette.routing import Route  # noqa: F401
    except Exception:  # pragma: no cover
        pass
    return {"ok": True, "ns": ns, "routes": ["%s/sync" % base]}


# =====================================================================================
# No-server self-test.
# =====================================================================================
def _selftest() -> dict:
    out: dict = {}
    r = agentcoh_sync(seed=42, agents=6, artifacts=5, steps=400)

    assert r["label"] == MODELED_LABEL, r["label"]
    for f in ("agents", "artifacts", "steps", "artifact_size", "broadcast_tokens",
              "mesi_tokens", "invalidations", "lazy_reads", "writes"):
        assert isinstance(r[f], int), (f, r.get(f))
    # MESI must beat broadcast on this workload
    assert r["mesi_tokens"] < r["broadcast_tokens"], r
    assert 0.0 < r["token_savings_frac"] < 1.0, r
    # protocol invariants enforced in the sim
    assert r["single_writer_safe"] is True, r
    assert r["version_monotone"] is True, r
    cen = r["coherence_state_census"]
    assert set(cen.keys()) == {"Modified", "Exclusive", "Shared", "Invalid"}, cen
    assert sum(cen.values()) == r["agents"] * r["artifacts"], cen
    assert "2603.15183" in r["citations"]["token_coherence"], r
    out["metrics"] = {"broadcast_tokens": r["broadcast_tokens"], "mesi_tokens": r["mesi_tokens"],
                      "token_savings_pct": r["token_savings_pct"],
                      "invalidations": r["invalidations"], "lazy_reads": r["lazy_reads"],
                      "single_writer_safe": r["single_writer_safe"]}

    # determinism
    r2 = agentcoh_sync(seed=42, agents=6, artifacts=5, steps=400)
    assert r2["mesi_tokens"] == r["mesi_tokens"], "non-deterministic"
    assert r2["token_savings_frac"] == r["token_savings_frac"], "non-deterministic savings"
    out["deterministic"] = True

    p = register(_FakeApp())
    assert p["routes"] == ["/api/killinchu/v1/agentcoh/sync"], p
    out["route"] = p["routes"][0]

    out["ok"] = True
    return out


class _FakeApp:
    def get(self, path):
        def _d(fn):
            return fn
        return _d


if __name__ == "__main__":
    import sys
    res = _selftest()
    print(_json.dumps(res, indent=2), file=sys.stderr)
    m = res["metrics"]
    print("broadcast=%d  mesi=%d  savings=%.1f%%  invalidations=%d  lazy_reads=%d  swsafe=%s"
          % (m["broadcast_tokens"], m["mesi_tokens"], m["token_savings_pct"],
             m["invalidations"], m["lazy_reads"], m["single_writer_safe"]))
    assert res["ok"]
    print("ALL OK")
