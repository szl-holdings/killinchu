# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
#
# killinchu — the SZL drone/edge organ.  REAL edge inference, REAL PAC-Bayes Λ,
# REAL DSSEv1 signing, REAL hash-chained Khipu DAG.  NO MOCKS.
#
# Doctrine v11 LOCKED · 749 / 14 / 163 · kernel c7c0ba17 · Λ = Conjecture 1
# SLSA L1 honest. Edge DSSE = real ECDSA-P256 over the cosign env-var key
# fallback (org > node-edge > ephemeral), verifiable by cosign verify-blob.
# We never claim L2 unless independently verified.
from .dsse import key_source, public_key_pem, sign_verdict, verify_envelope
from .edge import EdgeNode, Telemetry, telemetry_to_axes
from .khipu import KhipuDAG
from .lambda_calc import (
    LambdaVerdict,
    compute_lambda,
    lambda_aggregate,
    pac_bayes_penalty,
)
from .simulator import (
    NO_FLY_POLYGON,
    DroneProfile,
    TelemetrySimulator,
    default_fleet,
)

__all__ = [
    "compute_lambda", "lambda_aggregate", "pac_bayes_penalty", "LambdaVerdict",
    "sign_verdict", "verify_envelope", "public_key_pem", "key_source",
    "KhipuDAG", "EdgeNode", "Telemetry", "telemetry_to_axes",
    "TelemetrySimulator", "DroneProfile", "default_fleet", "NO_FLY_POLYGON",
]
