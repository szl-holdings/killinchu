#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
verify_flower.py — DEPLOY-AGNOSTIC correctness proof for the Flower Brain organ.

Exercises all 3 flower endpoints (/flower/graph, /flower/bloom, /flower/manifest)
by calling the organ's pure functions directly (no server, no network, no Hugging
Face Space required) and asserts every Doctrine-v11 invariant. If this script prints
ALL PASS, the source is correct independent of any deploy host: a 404 on a frozen
Space is a deploy problem, not a code problem.

Run:  python3 verify_flower.py
Exit: 0 = all invariants hold; non-zero = a real doctrine/logic violation.
"""
import sys

import szl_kc_flower as F

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name + (" — " + detail if detail else ""))
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def main() -> int:
    print("Flower Brain — deploy-agnostic Doctrine-v11 verifier\n")

    g = F.flower_graph(seed=42)
    b = F.flower_bloom(seed=42, K=10)
    mf = F.flower_manifest(seed=42)

    # ---- label == "MODELED" verbatim on all 3 endpoints ----
    print("label (MODELED verbatim on all 3 endpoints):")
    check("graph label MODELED", g["label"] == "MODELED", f"got {g['label']!r}")
    check("bloom label MODELED", b["label"] == "MODELED", f"got {b['label']!r}")
    check("manifest label MODELED", mf["label"] == "MODELED", f"got {mf['label']!r}")

    # ---- exactly 8 petals present on every endpoint ----
    print("8 petals present:")
    check("graph has 8 petals", len(g["petals"]) == 8, f"got {len(g['petals'])}")
    check("manifest petals_total == 8", mf["petals_total"] == 8, f"got {mf['petals_total']}")
    check("all 8 petals populated (>=1 node each)",
          all(g["petal_node_counts"][pn] >= 1 for pn in range(1, 9)),
          f"counts={g['petal_node_counts']}")

    # ---- locked_count == 8 on every endpoint; pistil == locked-8 ----
    print("locked_count == 8 (immutable pistil == locked-8):")
    check("graph locked_count == 8", g["locked_count"] == 8, f"got {g['locked_count']}")
    check("bloom locked_count == 8", b["locked_count"] == 8, f"got {b['locked_count']}")
    check("manifest locked_count == 8", mf["locked_count"] == 8, f"got {mf['locked_count']}")
    check("center_is_locked8", g["center_is_locked8"] is True)
    check("pistil == locked-8 ids",
          sorted(g["pistil"]) == sorted(n["id"] for n in F._PETAL1),
          f"pistil={sorted(g['pistil'])}")

    # ---- conjecture_rendered_green == 0 (gray petal never green) ----
    print("conjecture_rendered_green == 0 (gray petal never green):")
    check("bloom conjecture_rendered_green == 0", b["conjecture_rendered_green"] == 0,
          f"got {b['conjecture_rendered_green']}")
    check("manifest conjecture_rendered_green == 0", mf["conjecture_rendered_green"] == 0,
          f"got {mf['conjecture_rendered_green']}")
    conj_pp = next(pp for pp in b["per_petal_bloom"] if pp["petal"] == 8)
    check("conjecture petal is gray + bloom_fraction 0.0",
          conj_pp["gray"] is True and conj_pp["bloom_fraction"] == 0.0,
          f"gray={conj_pp['gray']} frac={conj_pp['bloom_fraction']}")

    # ---- provenance coverage == 1.0 (every node has a real provenance) ----
    print("provenance coverage == 1.0 (every node traces to something real):")
    check("manifest provenance_coverage == 1.0", mf["provenance_coverage"] == 1.0,
          f"got {mf['provenance_coverage']}")
    check("every graph node has non-empty provenance",
          all(str(n.get("provenance", "")).strip() for n in g["nodes"]),
          "some node missing provenance")

    # ---- center / pistil never grows across bloom rounds ----
    print("center (pistil) never grows across bloom rounds:")
    check("bloom pistil_immutable (pinned at 1.0)", b["pistil_immutable"] is True)
    # explicit sweep over K: pistil activation must stay exactly 1.0 every round
    set(g["pistil"])
    pistil_never_grows = True
    detail_grow = ""
    for k in range(1, 11):
        bk = F.flower_bloom(seed=42, K=k)
        pk = next(pp for pp in bk["per_petal_bloom"] if pp["is_pistil"])
        # pistil petal is exactly the locked-8; its mean bloom must be exactly 1.0, never above
        if not (abs(pk["bloom_fraction"] - 1.0) < 1e-9):
            pistil_never_grows = False
            detail_grow = f"K={k} pistil bloom={pk['bloom_fraction']}"
            break
        if not bk["pistil_immutable"]:
            pistil_never_grows = False
            detail_grow = f"K={k} pistil_immutable False"
            break
    check("pistil pinned at 1.0 across every K=1..10 (never grows)", pistil_never_grows, detail_grow)

    # ---- bloom is monotonic non-decreasing ----
    print("bloom monotonic non-decreasing:")
    opk = b["overall_bloom_per_k"]
    check("overall_bloom_per_k non-decreasing", opk == sorted(opk), f"{opk}")
    check("bloom ends >= it starts", opk[-1] >= opk[0], f"start={opk[0]} end={opk[-1]}")
    check("overall_bloom in (0,1]", 0.0 < b["overall_bloom"] <= 1.0, f"got {b['overall_bloom']}")
    check("non-gray non-pistil petals actually open",
          any(pp["bloom_fraction"] > 0.0 for pp in b["per_petal_bloom"]
              if not pp["gray"] and not pp["is_pistil"]))

    # ---- deterministic (same seed => identical) ----
    print("deterministic (same seed => identical):")
    check("graph deterministic", F.flower_graph(42) == F.flower_graph(42))
    check("bloom deterministic", F.flower_bloom(42, 10) == F.flower_bloom(42, 10))
    check("manifest deterministic", F.flower_manifest(42) == F.flower_manifest(42))
    check("layout seed-sensitive", F.flower_graph(7) != F.flower_graph(42))

    # ---- cross-petal edges are real dependencies spanning petals ----
    print("cross-petal dependencies:")
    check("cross_petal_edges >= 8", g["cross_petal_edges"] >= 8, f"got {g['cross_petal_edges']}")

    # ---- manifest honesty invariants block all True ----
    print("manifest honesty_invariants block:")
    hi = mf["honesty_invariants"]
    check("label_is_MODELED", hi["label_is_MODELED"] is True)
    check("locked_proven_is_exactly_8", hi["locked_proven_is_exactly_8"] is True)
    check("conjecture_rendered_green_is_zero", hi["conjecture_rendered_green_is_zero"] is True)
    check("provenance_coverage_full", hi["provenance_coverage_full"] is True)
    check("center_never_grows", hi["center_never_grows"] is True)

    # ---- registration returns the 3 exact paths ----
    print("registration:")
    class _App:
        class _R:
            def __init__(self): self.routes = []
        def __init__(self): self.router = self._R()
        def add_api_route(self, p, fn, methods=None): self.router.routes.append(p)
    routes = F.register(_App(), ns="killinchu")
    check("register returns 3 exact paths", routes == [
        "/api/killinchu/v1/flower/graph",
        "/api/killinchu/v1/flower/bloom",
        "/api/killinchu/v1/flower/manifest",
    ], f"got {routes}")

    print()
    if FAILS:
        print(f"RESULT: {len(FAILS)} INVARIANT(S) VIOLATED:")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("RESULT: ALL PASS — the Flower Brain is correct at the source, "
          "independent of any deploy host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
