# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_agentcoh.py — SZL Multi-Agent Memory Coherence organ (NEW AXIS).

Clean-room adoption of the TOKEN COHERENCE idea (arXiv:2603.15183, Parakhin): naïve
multi-agent LLM orchestration rebroadcasts full shared state on every update, costing
O(n·S·|D|); this maps exactly onto SHARED-MEMORY CACHE COHERENCE — an artifact held by
several agents is a cache line held by several cores. This organ PORTS the MESI protocol
(Modified / Exclusive / Shared / Invalid + LAZY INVALIDATION) to artifacts and shows, on
a fixed SEEDED operation trace, WHY lazy invalidation beats full-state rebroadcast while
preserving three safety properties: SINGLE-WRITER, MONOTONIC VERSIONING, BOUNDED STALENESS.

This is a DISTRIBUTED-SYSTEMS CONSISTENCY PROTOCOL for agent memory — NOT retrieval, NOT
single-agent storage, NOT governance policy. That is the NEW AXIS relative to SZL's other
memory organs (graphmem = multi-graph retrieval; episodic = single-agent temporal recall;
governance organs = policy/attestation).

  GET  /api/<ns>/v1/agentcoh/sync?seed=&num_agents=&num_artifacts=&write_fraction=&mode=

Returned JSON fields
--------------------
  label            : "MODELED" (verbatim — this is a toy deterministic simulation of the
                     MESI→artifact coherence MECHANISM, never a production coherence system)
  model            : "MESI→artifact coherence protocol (Token-Coherence-inspired)"
  seed             : RNG seed used (deterministic; same seed -> identical trace + result)
  num_agents (n)   : number of agents sharing the artifact set
  num_artifacts (m): number of shared artifacts (each = a "cache line")
  artifact_size    : |D|, the modeled per-artifact payload size (token/byte proxy units)
  write_fraction   : V, fraction of ops in the trace that are WRITEs
  staleness_bound  : k, the bounded-staleness constant for the BOUNDED-STALENESS invariant
  mode             : "naive" | "mesi" | "mesi_buggy"
  trace            : the fixed seeded operation trace (list of {step,agent,artifact,op})
  naive            : cost + final result for NAÏVE BROADCAST over the trace
  mesi             : cost + final result for the requested MESI mode over the SAME trace
  invariants       : per-invariant PASS/FAIL report (single-writer, monotonic, bounded-staleness)
  timeline         : per-artifact MESI state lane per agent (states + invalidation events)
  cost_curve       : naïve-vs-MESI cost as write_fraction V sweeps 0.05 -> 0.9
  honest_note      : plain-language honesty disclaimer (the HONESTY CAVEAT)
  citations        : dict of citable sources (verbatim, none claimed as SZL's own)
  computed_at      : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Inspired-not-real. Toy deterministic sim of the MESI→artifact coherence MECHANISM, not
  the paper's Artifact Coherence System. "Artifacts" are integer-versioned dict entries
  over 3–4 items + a handful of agents; "cost" is a counted token/byte proxy, not measured
  LLM tokens; invariants are checked by in-sim assertions, NOT the paper's TLA+ model
  checker (no ~2,400-state exploration); no LangGraph/CrewAI/AutoGen integration. The label
  "MODELED" is returned verbatim and displayed verbatim by the surface; never upgraded.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, verified real, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Token Coherence: Adapting MESI Cache Protocols to Minimize Synchronization "
    "Overhead in Multi-Agent LLM Systems (Parakhin)": "https://arxiv.org/abs/2603.15183",
    "Multi-Agent Memory from a Computer Architecture Perspective (Yu et al.)":
        "https://arxiv.org/abs/2603.10062",
    "Governed Shared Memory for Multi-Agent LLM Systems":
        "https://arxiv.org/abs/2606.24535",
}

# The four MESI states ported onto artifacts (a cache line held by several agents).
MODIFIED  = "Modified"
EXCLUSIVE = "Exclusive"
SHARED    = "Shared"
INVALID   = "Invalid"


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Fixed SEEDED operation trace: list of (agent, artifact, READ|WRITE)
# ---------------------------------------------------------------------------
def _build_trace(seed: int, num_agents: int, num_artifacts: int,
                 write_fraction: float, n_ops: int = 48) -> list:
    """
    Deterministic operation trace over (agent, artifact, op) triples.

    Purely a function of (seed, n, m, V) — same inputs -> identical trace. Op is WRITE
    with probability write_fraction, else READ, drawn from the LCG stream.
    """
    rng = _lcg(seed)
    trace = []
    for step in range(n_ops):
        agent    = int(next(rng) * num_agents) % num_agents
        artifact = int(next(rng) * num_artifacts) % num_artifacts
        op = "WRITE" if next(rng) < write_fraction else "READ"
        trace.append({"step": step, "agent": agent, "artifact": artifact, "op": op})
    return trace


# ---------------------------------------------------------------------------
# Invariant checker — three runtime assertions over the (agent,artifact) cache grid
# ---------------------------------------------------------------------------
class InvariantError(AssertionError):
    """Raised when a coherence invariant is violated (surfaced under mesi_buggy)."""


def _check_single_writer(states: dict, num_agents: int, artifact: int) -> None:
    """SINGLE-WRITER: at most ONE agent may hold an artifact in Modified at any time."""
    n_mod = sum(1 for a in range(num_agents) if states[(a, artifact)] == MODIFIED)
    if n_mod > 1:
        raise InvariantError(
            f"single-writer violated: {n_mod} Modified copies of artifact {artifact}")


def _check_monotonic(prev_ver: int, new_ver: int, artifact: int) -> None:
    """MONOTONIC VERSIONING: a committed version number never decreases."""
    if new_ver < prev_ver:
        raise InvariantError(
            f"monotonic-versioning violated on artifact {artifact}: "
            f"{new_ver} < {prev_ver}")


def _check_bounded_staleness(read_ver: int, committed_ver: int, k: int,
                             artifact: int) -> None:
    """BOUNDED STALENESS: a READ returns version >= last committed WRITE minus k."""
    if read_ver < committed_ver - k:
        raise InvariantError(
            f"bounded-staleness violated on artifact {artifact}: read v{read_ver} "
            f"< committed v{committed_ver} - k({k})")


# ---------------------------------------------------------------------------
# Deterministic bug-injection planner for mesi_buggy mode
# ---------------------------------------------------------------------------
def _plan_dropped_invalidation(trace: list, num_agents: int,
                               staleness_bound: int):
    """
    Pre-scan the trace to find a WRITE at which dropping the invalidation to a specific
    peer is GUARANTEED to surface a BOUNDED-STALENESS failure later.

    We look for a WRITE (step w) by agent a on artifact j and a victim peer p != a such
    that:
      * p performs NO WRITE on artifact j between step w and its next READ of j (so p
        never self-refreshes its local version), and
      * that next READ by p on j occurs after at least (k+1) further committed WRITEs on
        j (so p's retained version lags the committed version by more than k).
    Because in buggy mode we also DROP p's invalidation at step w, p stays SHARED (thinks
    it is fresh), never re-fetches on the READ, and returns a version < committed - k.

    Returns {'write_step', 'victim', 'artifact'} or None if no such point exists.
    Deterministic: pure function of the (already-deterministic) trace.
    """
    n_ops = len(trace)
    for wi in range(n_ops):
        w = trace[wi]
        if w["op"] != "WRITE":
            continue
        a, j = w["agent"], w["artifact"]
        for p in range(num_agents):
            if p == a:
                continue
            committed_writes = 0        # committed WRITEs on j strictly after step wi
            victim_wrote = False
            for k2 in range(wi + 1, n_ops):
                e = trace[k2]
                if e["artifact"] != j:
                    continue
                if e["op"] == "WRITE":
                    committed_writes += 1
                    if e["agent"] == p:
                        victim_wrote = True   # p self-refreshes -> disqualified
                        break
                elif e["op"] == "READ" and e["agent"] == p:
                    # p's stale local version == committed at step wi (== committed_before)
                    # committed advances by committed_writes since; lag > k means fail.
                    if committed_writes > staleness_bound:
                        return {"write_step": w["step"], "victim": p, "artifact": j}
                    break  # p reads too soon to exceed bound; try another point
            if victim_wrote:
                continue
    return None


# ---------------------------------------------------------------------------
# NAÏVE BROADCAST coordinator — every WRITE re-sends full artifact to all n agents
# ---------------------------------------------------------------------------
def _run_naive(trace: list, num_agents: int, num_artifacts: int,
               artifact_size: int, staleness_bound: int) -> dict:
    """
    Baseline: on every WRITE, the writer rebroadcasts the FULL artifact payload to all n
    agents (cost += |D|·n). Versions still bump monotonically and every agent is always
    in sync (Shared), so invariants trivially hold — but the byte/token cost is O(|D|·n)
    per write. This is the O(n·S·|D|) behaviour Token Coherence identifies as the problem.
    """
    versions = {j: 0 for j in range(num_artifacts)}          # committed version per artifact
    states   = {(a, j): SHARED for a in range(num_agents)     # every agent holds a copy
                for j in range(num_artifacts)}
    cost = 0
    reads = 0
    writes = 0
    invalidations = 0  # naïve never uses invalidations
    for ev in trace:
        a, j, op = ev["agent"], ev["artifact"], ev["op"]
        if op == "WRITE":
            prev = versions[j]
            versions[j] = prev + 1
            _check_monotonic(prev, versions[j], j)
            # full-state rebroadcast to ALL n agents (including writer)
            cost += artifact_size * num_agents
            # everyone stays fully in sync -> Shared at the new version
            for other in range(num_agents):
                states[(other, j)] = SHARED
            _check_single_writer(states, num_agents, j)
            writes += 1
        else:  # READ — always current in the naïve model, no fetch cost
            _check_bounded_staleness(versions[j], versions[j], staleness_bound, j)
            reads += 1
    return {
        "coordinator": "naive-broadcast",
        "cost": cost,
        "reads": reads,
        "writes": writes,
        "invalidations": invalidations,
        "final_versions": {str(j): versions[j] for j in range(num_artifacts)},
    }


# ---------------------------------------------------------------------------
# MESI ARTIFACT COHERENCE SYSTEM coordinator — lazy invalidation
# ---------------------------------------------------------------------------
def _run_mesi(trace: list, num_agents: int, num_artifacts: int,
              artifact_size: int, staleness_bound: int, buggy: bool = False) -> dict:
    """
    MESI-style coordinator over the SAME trace:

      WRITE by agent a on artifact j:
        - writer -> Modified, version bumps monotonically
        - LAZILY mark every OTHER agent's copy Invalid (cost += n invalidation *tokens*,
          NOT the full |D| payload) — this is the whole point: cheap invalidations vs.
          full-state rebroadcast
        - each invalidated line remembers it is stale (needs a re-fetch on next READ)

      READ by agent a on artifact j:
        - if the line is Invalid, do a full re-fetch ON DEMAND (cost += |D| once), then the
          line becomes Shared at the current version
        - otherwise the local copy is fresh -> no cost

    Invariants are asserted at each step. In buggy=True (mesi_buggy) mode we DELIBERATELY
    DROP one invalidation to a peer whose NEXT op on that artifact is a READ, chosen so
    that enough later WRITEs commit in between to push the peer's stale copy past the
    staleness bound k. That later READ then returns a stale version and BOUNDED STALENESS
    FAILS — making the guarantee visible by showing exactly what breaks without it.
    """
    drop_plan = _plan_dropped_invalidation(
        trace, num_agents, staleness_bound) if buggy else None
    versions = {j: 0 for j in range(num_artifacts)}   # last globally-committed version
    states   = {(a, j): SHARED for a in range(num_agents)
                for j in range(num_artifacts)}
    local_ver = {(a, j): 0 for a in range(num_agents)  # version each agent last saw
                 for j in range(num_artifacts)}
    cost = 0
    reads = 0
    writes = 0
    invalidations = 0
    refetches = 0
    dropped_once = False
    invariant_error = None
    # In buggy mode, once we drop the invalidation to a victim on artifact j, the
    # coherence directory has LOST that sharer, so the victim is skipped on ALL later
    # writes to j too, until it self-touches j (read/write) and re-registers. This is
    # the realistic failure of a dropped invalidation — a silently stale sharer.
    lost_sharer = {}  # artifact_j -> victim_agent while stale

    # per-(agent,artifact) state lane timeline for visualization
    lanes = {(a, j): [] for a in range(num_agents) for j in range(num_artifacts)}
    invalidation_events = []

    def snapshot():
        for a in range(num_agents):
            for j in range(num_artifacts):
                lanes[(a, j)].append(states[(a, j)])

    snapshot()  # initial state

    for ev in trace:
        a, j, op = ev["agent"], ev["artifact"], ev["op"]
        try:
            if op == "WRITE":
                prev = versions[j]
                versions[j] = prev + 1
                _check_monotonic(prev, versions[j], j)
                # writer takes the line Exclusive->Modified at the new version
                states[(a, j)] = MODIFIED
                local_ver[(a, j)] = versions[j]
                writes += 1
                # if the lost sharer itself writes, it re-registers (no longer stale)
                if lost_sharer.get(j) == a:
                    del lost_sharer[j]
                # lazily invalidate other copies (cheap: n tokens, not |D|)
                peers = [o for o in range(num_agents) if o != a]
                skip_peer = None
                if (buggy and not dropped_once and drop_plan is not None
                        and ev["step"] == drop_plan["write_step"]):
                    # DELIBERATE BUG: drop the invalidation to the planned victim peer,
                    # who will later READ this artifact while stale beyond bound k.
                    skip_peer = drop_plan["victim"]
                    dropped_once = True
                if skip_peer is not None:
                    lost_sharer[j] = skip_peer
                for o in peers:
                    if o == skip_peer or lost_sharer.get(j) == o:
                        continue  # dropped/lost sharer keeps a silently stale copy
                    if states[(o, j)] != INVALID:
                        states[(o, j)] = INVALID
                    cost += 1            # one invalidation token per peer
                    invalidations += 1
                    invalidation_events.append(
                        {"step": ev["step"], "artifact": j, "from": a, "to": o})
                # after a write, exactly one Modified copy must exist
                _check_single_writer(states, num_agents, j)
            else:  # READ
                reads += 1
                # a self-touch clears the lost-sharer flag (victim re-registers)
                if lost_sharer.get(j) == a:
                    del lost_sharer[j]
                if states[(a, j)] == INVALID:
                    # on-demand full re-fetch (the only place we pay |D| in MESI)
                    cost += artifact_size
                    refetches += 1
                    states[(a, j)] = SHARED
                    local_ver[(a, j)] = versions[j]
                # bounded-staleness check on what THIS read observes
                _check_bounded_staleness(
                    local_ver[(a, j)], versions[j], staleness_bound, j)
        except InvariantError as e:
            invariant_error = str(e)
            snapshot()
            break
        snapshot()

    return {
        "coordinator": "mesi-acs" + ("-buggy" if buggy else ""),
        "cost": cost,
        "reads": reads,
        "writes": writes,
        "invalidations": invalidations,
        "refetches": refetches,
        "final_versions": {str(j): versions[j] for j in range(num_artifacts)},
        "invariant_error": invariant_error,   # None unless an invariant FAILED
        "lanes": lanes,
        "invalidation_events": invalidation_events,
    }


# ---------------------------------------------------------------------------
# Invariant report — runs all three invariants under the requested mode
# ---------------------------------------------------------------------------
def _invariant_report(mesi_result: dict) -> dict:
    """
    Summarize the three invariants. Under 'mesi' all three hold; under 'mesi_buggy' the
    dropped invalidation surfaces as a BOUNDED-STALENESS failure (a stale READ).
    """
    err = mesi_result.get("invariant_error")
    single_writer = monotonic = bounded = "PASS"
    detail = "all three invariants hold on the trace"
    if err:
        detail = err
        if "single-writer" in err:
            single_writer = "FAIL"
        elif "monotonic" in err:
            monotonic = "FAIL"
        elif "bounded-staleness" in err:
            bounded = "FAIL"
    return {
        "single_writer":     {"status": single_writer,
                              "invariant": "at most one Modified copy of any artifact"},
        "monotonic_versioning": {"status": monotonic,
                              "invariant": "committed version never decreases"},
        "bounded_staleness": {"status": bounded,
                              "invariant": "a READ returns version >= committed - k"},
        "all_hold": (err is None),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Cost curve — naïve vs MESI-ACS as write_fraction V sweeps 0.05 -> 0.9
# ---------------------------------------------------------------------------
def _cost_curve(seed: int, num_agents: int, num_artifacts: int,
                artifact_size: int, staleness_bound: int) -> list:
    """
    Sweep write_fraction V across 0.05..0.9 and record naïve vs MESI cost. Savings shrink
    but persist as writes dominate — the honest result, not the paper's measured 84–95%.
    """
    curve = []
    for i in range(18):
        V = round(0.05 + (0.9 - 0.05) * i / 17, 4)
        trace = _build_trace(seed, num_agents, num_artifacts, V)
        naive = _run_naive(trace, num_agents, num_artifacts, artifact_size, staleness_bound)
        mesi  = _run_mesi(trace, num_agents, num_artifacts, artifact_size, staleness_bound)
        nc, mc = naive["cost"], mesi["cost"]
        savings = round(1.0 - (mc / nc), 4) if nc else 0.0
        curve.append({
            "write_fraction": V,
            "naive_cost": nc,
            "mesi_cost": mc,
            "savings_ratio": savings,
        })
    return curve


# ---------------------------------------------------------------------------
# Top-level deterministic simulation
# ---------------------------------------------------------------------------
def simulate(seed: int = 42, num_agents: int = 3, num_artifacts: int = 4,
             artifact_size: int = 64, write_fraction: float = 0.35,
             staleness_bound: int = 1, mode: str = "mesi") -> dict:
    num_agents      = max(2, min(num_agents, 8))
    num_artifacts   = max(2, min(num_artifacts, 8))
    artifact_size   = max(1, min(artifact_size, 4096))
    write_fraction  = max(0.0, min(write_fraction, 1.0))
    staleness_bound = max(0, min(staleness_bound, 8))
    if mode not in ("naive", "mesi", "mesi_buggy"):
        mode = "mesi"

    trace = _build_trace(seed, num_agents, num_artifacts, write_fraction)
    naive = _run_naive(trace, num_agents, num_artifacts, artifact_size, staleness_bound)

    buggy = (mode == "mesi_buggy")
    mesi = _run_mesi(trace, num_agents, num_artifacts, artifact_size,
                     staleness_bound, buggy=buggy)
    invariants = _invariant_report(mesi)

    # compact per-artifact timeline (agent lanes) for the surface visualization
    lanes = mesi.pop("lanes")
    timeline = []
    for j in range(num_artifacts):
        agent_lanes = []
        for a in range(num_agents):
            agent_lanes.append({"agent": a, "states": lanes[(a, j)]})
        timeline.append({"artifact": j, "lanes": agent_lanes})

    curve = _cost_curve(seed, num_agents, num_artifacts, artifact_size, staleness_bound)

    return {
        "seed": seed,
        "num_agents": num_agents,
        "num_artifacts": num_artifacts,
        "artifact_size": artifact_size,
        "write_fraction": write_fraction,
        "staleness_bound": staleness_bound,
        "mode": mode,
        "trace": trace,
        "naive": naive,
        "mesi": mesi,
        "invariants": invariants,
        "timeline": timeline,
        "invalidation_events": mesi.get("invalidation_events", []),
        "cost_curve": curve,
    }


_HONEST_NOTE = (
    "MODELED: Inspired-not-real. Toy deterministic sim of the MESI\u2192artifact coherence "
    "MECHANISM, not the paper's Artifact Coherence System. 'Artifacts' are integer-versioned "
    "dict entries over 3\u20134 items + a handful of agents; 'cost' is a counted token/byte "
    "proxy, not measured LLM tokens; invariants are checked by in-sim assertions, NOT the "
    "paper's TLA+ model checker (no ~2,400-state exploration); no LangGraph/CrewAI/AutoGen "
    "integration. Demonstrates WHY lazy invalidation beats full-state rebroadcast while "
    "preserving single-writer safety, monotonic versioning, bounded staleness on a "
    "constructed trace; does NOT reproduce Token Coherence's 84\u201395% measured savings or "
    "prove the Token Coherence Theorem. NEW AXIS: distributed-consistency protocol "
    "(\u2260 graphmem retrieval, \u2260 single-agent memory organs, \u2260 governance policy). "
    "Cite: Token Coherence (arXiv:2603.15183, Parakhin); Multi-Agent Memory from a Computer "
    "Architecture Perspective (arXiv:2603.10062, Yu et al.); Governed Shared Memory for "
    "Multi-Agent LLM Systems (arXiv:2606.24535). Nothing here is in the locked-8; \u039b stays "
    "Conjecture 1; trust never 100%."
)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _fi(req: Request, key: str, default: float) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _h_sync(req: Request):
    seed           = _ii(req, "seed", 42)
    num_agents     = _ii(req, "num_agents", 3)
    num_artifacts  = _ii(req, "num_artifacts", 4)
    artifact_size  = _ii(req, "artifact_size", 64)
    write_fraction = _fi(req, "write_fraction", 0.35)
    staleness_bound = _ii(req, "staleness_bound", 1)
    mode           = req.query_params.get("mode", "mesi")

    sim = simulate(seed=seed, num_agents=num_agents, num_artifacts=num_artifacts,
                   artifact_size=artifact_size, write_fraction=write_fraction,
                   staleness_bound=staleness_bound, mode=mode)

    return JSONResponse({
        "label": "MODELED",
        "model": "MESI\u2192artifact coherence protocol (Token-Coherence-inspired)",
        "method": ("two coordinators over one seeded op trace: naive full-state broadcast "
                   "vs MESI-style lazy-invalidation artifact coherence; three invariants "
                   "asserted at runtime; mesi_buggy drops an invalidation to surface a "
                   "stale-read failure"),
        "seed": sim["seed"],
        "num_agents": sim["num_agents"],
        "num_artifacts": sim["num_artifacts"],
        "artifact_size": sim["artifact_size"],
        "write_fraction": sim["write_fraction"],
        "staleness_bound": sim["staleness_bound"],
        "mode": sim["mode"],
        "trace": sim["trace"],
        "naive": sim["naive"],
        "mesi": sim["mesi"],
        "invariants": sim["invariants"],
        "timeline": sim["timeline"],
        "invalidation_events": sim["invalidation_events"],
        "cost_curve": sim["cost_curve"],
        "honest_note": _HONEST_NOTE,
        "citations": CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — additive, try/except-guarded; add_api_route with Route fallback
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/agentcoh/sync onto app. Additive, guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/agentcoh"
    handlers = [
        (f"{base}/sync", _h_sync),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    sim = simulate(seed=42, num_agents=3, num_artifacts=4,
                   artifact_size=64, write_fraction=0.35, staleness_bound=1, mode="mesi")
    print("label: MODELED")
    print("num_agents:", sim["num_agents"], "num_artifacts:", sim["num_artifacts"])
    print("artifact_size |D|:", sim["artifact_size"], "write_fraction V:", sim["write_fraction"])
    print("trace ops:", len(sim["trace"]),
          "(writes=", sim["mesi"]["writes"], "reads=", sim["mesi"]["reads"], ")")
    print("naive-broadcast cost:", sim["naive"]["cost"])
    print("mesi-acs cost       :", sim["mesi"]["cost"],
          "(invalidations=", sim["mesi"]["invalidations"],
          "refetches=", sim["mesi"]["refetches"], ")")
    _nc, _mc = sim["naive"]["cost"], sim["mesi"]["cost"]
    print("savings ratio       :", round(1.0 - _mc / _nc, 4) if _nc else 0.0)
    print("invariants:",
          "single_writer=", sim["invariants"]["single_writer"]["status"],
          "monotonic=", sim["invariants"]["monotonic_versioning"]["status"],
          "bounded_staleness=", sim["invariants"]["bounded_staleness"]["status"],
          "all_hold=", sim["invariants"]["all_hold"])

    print("--- mesi_buggy mode (deliberately drops an invalidation) ---")
    bug = simulate(seed=42, num_agents=3, num_artifacts=4,
                   artifact_size=64, write_fraction=0.35, staleness_bound=1,
                   mode="mesi_buggy")
    print("buggy all_hold:", bug["invariants"]["all_hold"],
          "| detail:", bug["invariants"]["detail"])
    print("buggy invariant statuses:",
          "single_writer=", bug["invariants"]["single_writer"]["status"],
          "monotonic=", bug["invariants"]["monotonic_versioning"]["status"],
          "bounded_staleness=", bug["invariants"]["bounded_staleness"]["status"])
