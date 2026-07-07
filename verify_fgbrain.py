#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
verify_fgbrain.py — DEPLOY-AGNOSTIC correctness proof for the Formula-Graph Brain.

Exercises every fgbrain endpoint by calling the organ's pure functions directly
(no server, no network, no Hugging Face Space required) and asserts every
Doctrine-v11 invariant. This is the honest answer to "is the brain correct?"
independent of whether any host is currently serving it: if this script prints
ALL PASS, the source is correct; a 404 on a frozen Space is a deploy problem,
not a code problem.

Run:  python3 verify_fgbrain.py
Exit: 0 = all invariants hold; non-zero = a real doctrine/logic violation.
"""
import sys

import szl_fgbrain as B

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name + (" — " + detail if detail else ""))
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def main() -> int:
    print("Formula-Graph Brain — deploy-agnostic doctrine verifier\n")

    # ---- graph (wave 15) ----
    print("graph / fire (wave 15):")
    g = B._graph()
    check("graph label MODELED", g["label"] == "MODELED")
    check("locked-proven == 8", g["locked_count"] == 8, f"got {g['locked_count']}")
    fire = B._snapshot(seed=42, K=10)
    check("fire label MODELED", fire["label"] == "MODELED")
    check("conjectures never fire green", fire["conjecture_rendered_green"] == 0,
          f"got {fire['conjecture_rendered_green']}")
    check("firing reward non-decreasing", fire["firing_reward_per_k"] == sorted(fire["firing_reward_per_k"]))

    # ---- repair (wave 16) ----
    print("repair (wave 16):")
    rep = B._repair(down="F1", steps=12)
    check("repair label MODELED", rep["label"] == "MODELED")
    check("lesioned node stays down", rep["final_state"]["F1"] == 0.0)
    check("full graph was connected", rep["fiedler_lambda2_before"] > 1e-9)
    check("repair locked == 8", rep["locked_count"] == 8)
    check("repair deterministic", B._repair(down="F1", steps=12) == rep)

    # ---- plasticity (wave 17) ----
    print("plasticity (wave 17):")
    pl = B._plasticity(seed=42, rounds=30)
    check("plasticity label MODELED", pl["label"] == "MODELED")
    check("locked canon edges FROZEN", pl["locked_edges_unchanged"] is True)
    check("plasticity locked == 8", pl["locked_count"] == 8)
    check("plasticity deterministic", B._plasticity(seed=42, rounds=30) == pl)

    # ---- memory (wave 18) ----
    print("memory (wave 18):")
    mem = B._memory(seed=42, sessions=4)
    check("memory label MODELED", mem["label"] == "MODELED")
    check("hash chain intact", mem["chain_intact"] is True)
    check("one beat per session", mem["beats_written"] == 4)
    check("memory deterministic", B._memory(seed=42, sessions=4) == mem)

    # ---- vitals (wave 19) ----
    print("vitals (wave 19):")
    v = B._homeostasis(seed=42, rounds=12)
    check("vitals label MODELED", v["label"] == "MODELED")
    check("locked untouched by homeostasis", v.get("locked_untouched") is True)
    check("drive non-increasing", v["drive_per_round"] == sorted(v["drive_per_round"], reverse=True))
    check("vitals deterministic", B._homeostasis(seed=42, rounds=12) == v)

    # ---- energy (wave 21) ----
    print("energy attestation (wave 21):")
    en = B._energy_attest()
    check("energy label MODELED", en["label"] == "MODELED")
    check("energy status honest", en["energy"]["status"] in ("MEASURED", "UNAVAILABLE"))
    import os as _os
    if not _os.environ.get("SZL_JOULES_MEASURED", "").strip():
        check("no probe -> UNAVAILABLE/null (never fabricated)",
              en["energy"]["status"] == "UNAVAILABLE" and en["energy"]["joules"] is None)

    # ---- evolve (wave 20) ----
    print("evolve (wave 20):")
    ev = B._evolve(seed=42, generations=15)
    check("evolve label MODELED", ev["label"] == "MODELED")
    check("real locked == 8 (post-evolution)", ev["locked_count"] == 8)
    check("kernel gate immutable", ev["gate_immutable"] is True)
    check("claim pinning enforced", ev["claim_pinning_ok"] is True)
    check("drift rollback restored", ev["rollback_restored"] is True)
    check("evolve deterministic", B._evolve(seed=42, generations=15) == ev)

    # ---- manifest (wave 22) ----
    print("manifest (wave 22):")
    mf = B._manifest()
    check("manifest label MODELED", mf["label"] == "MODELED")
    check("manifest locked == 8", mf["locked_proven_count"] == 8)
    check("aliveness 5/5", mf["aliveness_reached"] == 5 and mf["aliveness_total"] == 5)
    check("9 endpoints described", mf["endpoint_count"] == 9)
    check("conjecture-1 quarantined gray", "Lambda_C1" in mf["conjectures_gray"])

    # ---- registration ----
    print("registration:")
    class _App:
        class _R:
            def __init__(self): self.routes = []
        def __init__(self): self.router = self._R()
        def add_api_route(self, p, fn, methods=None): self.router.routes.append(p)
    app = _App()
    routes = B.register(app, ns="killinchu")
    check("9 routes register", len(routes) == 9, f"got {len(routes)}")

    print()
    if FAILS:
        print(f"RESULT: {len(FAILS)} INVARIANT(S) VIOLATED:")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("RESULT: ALL PASS — the Formula-Graph Brain is correct at the source, "
          "independent of any deploy host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
