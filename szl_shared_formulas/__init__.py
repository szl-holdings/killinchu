#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""szl_shared_formulas — thesis-v22 formulas living in the killinchu edge organ.

a11oy is the canonical home (src/a11oy/formulas/*); welford + bloom_filter are VERBATIM
vendored copies. The real-edge-v2 cycle ADDS three formulas that materially help the edge:
  - pac_bayes        : Catoni/McAllester verdict-confidence bound
  - kalman           : constant-velocity Kalman smoothing of noisy drone telemetry
  - byzantine_quorum : n ≥ 3f+1 multi-sensor fusion (5 sensors, tolerate 1 byzantine)

Each module carries a real thesis_v22.pdf citation + a real Lean theorem/obligation name
(permalinked into szl-holdings/lutar-lean). No mocks.

Doctrine v11 LOCKED — 749/14/163 — c7c0ba17 · Λ = Conjecture 1 (NEVER a theorem).
"""
from __future__ import annotations
from . import welford
from . import bloom_filter
from . import pac_bayes
from . import kalman
from . import byzantine_quorum
__all__ = ['welford', 'bloom_filter', 'pac_bayes', 'kalman', 'byzantine_quorum']
# SLSA L1 honest + L2 attested (public Sigstore+Rekor) where slsa-verifier confirms.
