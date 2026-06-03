# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu — the SZL drone/edge organ.  REAL edge inference, REAL PAC-Bayes Λ,
# REAL DSSEv1 signing, REAL hash-chained Khipu DAG.  NO MOCKS.
#
# Doctrine v11 LOCKED · 749 / 14 / 163 · kernel c7c0ba17 · Λ = Conjecture 1
# SLSA L1 honest + L2 attested (in-toto SLSA Provenance v1; cosign keyless) — NOT L3
from .lambda_calc import compute_lambda, lambda_aggregate, pac_bayes_penalty, LambdaVerdict
from .dsse import sign_verdict, verify_envelope, public_key_pem, key_source
from .khipu import KhipuDAG
from .edge import EdgeNode, Telemetry, telemetry_to_axes

__all__ = [
    "compute_lambda", "lambda_aggregate", "pac_bayes_penalty", "LambdaVerdict",
    "sign_verdict", "verify_envelope", "public_key_pem", "key_source",
    "KhipuDAG", "EdgeNode", "Telemetry", "telemetry_to_axes",
]
