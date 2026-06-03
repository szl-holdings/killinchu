#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""Byzantine quorum n ≥ 3f+1 — multi-sensor fusion for the edge.

Real edge use case: a killinchu node fuses 5 telemetry sensors (e.g. 2 GPS, ADS-B,
Remote-ID, IMU dead-reckoning). One may be byzantine (spoofed / stuck / adversarial).
The PBFT bound n ≥ 3f+1 says 5 sensors tolerate f=1 byzantine fault with a quorum of
2f+1 = 3 agreeing sensors. We compute the quorum, decide feasibility, and (given actual
sensor reports) return the agreed value via a 2f+1 majority — refusing to decide if no
such quorum exists.

Lamport, Shostak, Pease, "The Byzantine Generals Problem", ACM TOPLAS 4(3) (1982);
Castro & Liskov, "Practical Byzantine Fault Tolerance", OSDI 1999.

Lean: ``Lutar/KhipuConsensus.lean`` — runtime defs ``faultyCount`` (L116),
``validCount_le_n`` (L142, sorry-free). BFT safety is **Conjecture 2**
(``khipu_consensus_safety`` L174) — NEVER a theorem, an honest open obligation.
Permalink pinned at commit abd58d1.

CITATION: thesis_v22.pdf §2  ·  LEAN: Lutar/KhipuConsensus.lean::faultyCount (Conjecture 2 safety)
"""
from __future__ import annotations

from collections import Counter

CITATION = "thesis_v22.pdf §2"
LEAN_THEOREM = "Lutar/KhipuConsensus.lean::faultyCount (Conjecture 2: khipu_consensus_safety)"
LEAN_PERMALINK = (
    "https://github.com/szl-holdings/lutar-lean/blob/"
    "abd58d159f1bdb79a017d71a6b94ab160ead8d9d/Lutar/KhipuConsensus.lean#L116"
)


def required_quorum(n: int, f: int) -> dict:
    """PBFT quorum sizing. bft_feasible iff n ≥ 3f+1; quorum = 2f+1."""
    if n < 0 or f < 0:
        raise ValueError("n, f must be non-negative")
    feasible = n >= 3 * f + 1
    quorum = 2 * f + 1
    return {
        "value": quorum,
        "n": n,
        "f": f,
        "required_quorum": quorum,
        "bft_feasible": feasible,
        "max_tolerable_faults": (n - 1) // 3,
        "citation": CITATION,
        "lean_theorem": LEAN_THEOREM,
    }


def fuse_sensors(reports: dict, f: int = 1, tol: float = 1e-6) -> dict:
    """Fuse sensor reports under the byzantine quorum rule.

    reports : {sensor_id: value}. Numeric values are bucketed within `tol`; the agreed
    value needs ≥ 2f+1 sensors in one bucket. Returns the agreed value or refuses.
    No mock data — operates on whatever real reports are passed in.
    """
    n = len(reports)
    q = required_quorum(n, f)
    quorum = q["required_quorum"]
    items = list(reports.items())

    # Bucket numeric reports by approximate equality; fall back to exact for non-numeric.
    buckets: list[tuple[float, list[str]]] = []
    for sid, val in items:
        placed = False
        try:
            v = float(val)
            for i, (rep, members) in enumerate(buckets):
                if abs(rep - v) <= tol:
                    members.append(sid)
                    placed = True
                    break
            if not placed:
                buckets.append((v, [sid]))
        except (TypeError, ValueError):
            for i, (rep, members) in enumerate(buckets):
                if rep == val:
                    members.append(sid)
                    placed = True
                    break
            if not placed:
                buckets.append((val, [sid]))

    buckets.sort(key=lambda b: len(b[1]), reverse=True)
    top_value, top_members = buckets[0]
    agreement = len(top_members)
    has_quorum = q["bft_feasible"] and agreement >= quorum
    outliers = [sid for rep, members in buckets[1:] for sid in members]

    return {
        "value": (top_value if has_quorum else None),
        "agreed_value": (top_value if has_quorum else None),
        "agreement_count": agreement,
        "required_quorum": quorum,
        "quorum_met": has_quorum,
        "bft_feasible": q["bft_feasible"],
        "n": n,
        "f": f,
        "agreeing_sensors": top_members,
        "suspected_byzantine": outliers,
        "verdict": ("DECIDE" if has_quorum else "REFUSE"),
        "citation": CITATION,
        "lean_theorem": LEAN_THEOREM,
    }


__all__ = ["required_quorum", "fuse_sensors", "CITATION", "LEAN_THEOREM", "LEAN_PERMALINK"]

# Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem)
# SLSA L1 honest (killinchu never claims L2 unless independently verified).
