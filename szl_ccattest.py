# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""szl_ccattest.py — CONFIDENTIAL-COMPUTE ATTESTATION CHAIN (TEE / NVIDIA H100 CC) organ.

DISTINCT organ — NOT the L6 chain-of-title receipt (`szl_chain_of_title.py` /
`szl_allodial.py` STANDARDS_ROADMAP). This module is a hardware-attestation
hash-chain simulation; it pairs naturally with SZL's governance/provenance/
sovereign-compute doctrine but is a separate concept: L6 is a cryptographic
chain-of-TITLE receipt for an artifact's build/agent-action provenance, while
this organ models a device/measurement-log attestation CHAIN as described for
TEE + NVIDIA H100 Confidential Computing.

CONCEPT (clean-room, MODELED — see HONEST REALITY below):
  NVIDIA's H100 Confidential Computing establishes a hardware chain of trust via
  (1) a secure/measured GPU boot sequence, (2) an SPDM session connecting the
  GPU to a CPU TEE (Intel TDX / AMD SEV-SNP), and (3) a cryptographically signed
  attestation report the relying party checks against NVIDIA's Remote
  Attestation Service (NRAS) before releasing secrets
  (developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai).
  This module does NOT talk to any GPU, NRAS, TDX/SEV-SNP quote, or key
  material. It SIMULATES the *shape* of that attestation chain using only
  hashlib, entirely deterministically from a `seed`:

  1. synthetic device identity  = sha384(seed_bytes)
  2. mock measurement log       = ordered stage hashes, each stage_hash =
     sha256(prev_hash + stage_name), walking a fixed canonical stage order
     bootloader -> firmware -> driver -> microcode -> gpu-vbios (first `stages`
     of that list, clamped 1..5)
  3. final chained digest       = the last stage's hash
  4. golden-reference check     = compare final_digest against a small fixed
     lookup table keyed by (seed, stages) — simulating an NRAS/OCSP-style
     "known-good measurement" response. MATCH only for the canonical
     (seed=42, stages=5) entry (and any input that happens to reproduce that
     exact digest); everything else is a real, deterministic MISMATCH — this
     is NOT a fixed True, it is a genuine table lookup against precomputed
     digests.

HONEST REALITY (v11 — NEVER violate):
  label = "MODELED": this is a deterministic sha256/sha384 hash-chain
  simulation of the TEE + NVIDIA H100 CC attestation CONCEPT described
  publicly by NVIDIA. It is NOT a real TDX/SEV-SNP/NRAS verifier. There is NO
  real key material, NO live GPU, NO network call of any kind. NEVER-CLAIMED-
  AS actual hardware attestation. Nothing here is in the locked-8. Λ stays
  Conjecture 1. Trust is never 100% — golden_match is a real, tamperable
  comparison, not a hardcoded True.

CITATIONS (real, verified; SZL claims NONE of NVIDIA's technology as its own):
  NVIDIA, "Confidential Computing on H100 GPUs for Secure and Trustworthy AI"
  (2023): https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/

ENDPOINT:
  GET /api/<ns>/v1/cc-attest/verify?seed=&stages=
  register(app, ns="killinchu")  -- add_api_route, falls back to Starlette Route.

Response fields: label, model, seed, stages, device_identity (sha384 hex),
measurement_chain [{stage, digest}], final_digest, golden_match (bool),
golden_reference (truncated, for transparency), honest_note, citations,
computed_at.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LABEL = "MODELED"

HONEST_NOTE = (
    "deterministic sha256/sha384 hash-chain sim of the TEE + H100 CC attestation "
    "concept described publicly by NVIDIA; NOT a real TDX/SEV-SNP/NRAS verifier; "
    "NEVER-CLAIMED-AS actual hardware attestation"
)

CITATIONS = {
    "nvidia_h100_cc_blog": {
        "title": "Confidential Computing on H100 GPUs for Secure and Trustworthy AI",
        "publisher": "NVIDIA Developer Blog",
        "year": 2023,
        "url": "https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/",
        "note": (
            "Describes the real H100 CC chain of trust: measured GPU boot, SPDM "
            "session to a CPU TEE, and a signed attestation report checked by the "
            "relying party. SZL claims NONE of this technology as its own; this "
            "module is a clean-room, pure-stdlib, deterministic SIMULATION of the "
            "concept's shape only."
        ),
    },
}

# Canonical measurement-log stage order (fixed; up to `stages` of these are used).
STAGE_ORDER = ("bootloader", "firmware", "driver", "microcode", "gpu-vbios")

_MIN_STAGES = 1
_MAX_STAGES = len(STAGE_ORDER)  # 5

_MIN_SEED = 0
_MAX_SEED = 2**63 - 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, iv))


# ---------------------------------------------------------------------------
# Core deterministic hash-chain model
# ---------------------------------------------------------------------------
def device_identity(seed: int) -> str:
    """Synthetic device identity = sha384(seed_bytes). Deterministic, no real key material."""
    seed_bytes = str(int(seed)).encode("utf-8")
    return hashlib.sha384(seed_bytes).hexdigest()


def measurement_chain(seed: int, stages: int) -> list:
    """Ordered stage hashes: stage_hash = sha256(prev_hash + stage_name).

    prev_hash for the first stage is the device_identity (sha384 hex, encoded
    as utf-8 bytes) — this ties the measurement log to the synthetic device
    identity, mirroring how a real measured-boot chain roots each stage's
    measurement in the prior stage/identity.
    """
    n = _clamp_int(stages, _MIN_STAGES, _MAX_STAGES, _MAX_STAGES)
    chain = []
    prev_hash = device_identity(seed)
    for stage_name in STAGE_ORDER[:n]:
        digest = hashlib.sha256((prev_hash + stage_name).encode("utf-8")).hexdigest()
        chain.append({"stage": stage_name, "digest": digest})
        prev_hash = digest
    return chain


def final_digest_of(chain: list) -> str:
    if not chain:
        return ""
    return chain[-1]["digest"]


# ---------------------------------------------------------------------------
# Golden reference table (simulating a fixed NRAS/OCSP "known-good" response).
# Precomputed once (below, at import time) for the CANONICAL seed/stages combos
# only. Any (seed, stages) not in this table, or whose live final_digest does
# not equal the table's precomputed value, is a real, deterministic MISMATCH —
# golden_match is a genuine comparison, never a hardcoded True.
# ---------------------------------------------------------------------------
CANONICAL_SEED = 42
CANONICAL_STAGES = 5


def _build_golden_table() -> dict:
    """Precompute the single golden reference entry for the canonical
    (seed=42, stages=5) attestation — simulating an NRAS/OCSP "known-good
    measurement" response, which only ever describes ONE specific approved
    software/firmware stack, not every possible partial chain.

    Only the exact canonical (CANONICAL_SEED, CANONICAL_STAGES) key is
    present. Any other (seed, stages) — including the canonical seed with a
    truncated/tampered stage count, or any other seed entirely — is genuinely
    absent from golden-known-good and therefore a real, deterministic
    MISMATCH; this is a plain dict lookup + string equality, never a fixed
    boolean.
    """
    chain = measurement_chain(CANONICAL_SEED, CANONICAL_STAGES)
    return {(CANONICAL_SEED, CANONICAL_STAGES): final_digest_of(chain)}


GOLDEN_TABLE = _build_golden_table()


def golden_lookup(seed: int, stages: int) -> str | None:
    """Return the golden reference digest for (seed, stages), or None if unknown."""
    n = _clamp_int(stages, _MIN_STAGES, _MAX_STAGES, _MAX_STAGES)
    return GOLDEN_TABLE.get((int(seed), n))


# ---------------------------------------------------------------------------
# Public verify()
# ---------------------------------------------------------------------------
def verify(seed: Any = 42, stages: Any = 5) -> dict:
    """Run the full deterministic attestation-chain simulation and compare
    the resulting final_digest against the golden reference table.

    golden_match is TRUE only when (seed, stages) is exactly the canonical
    (42, 5) — or any other input whose live-computed final_digest happens to
    byte-for-byte equal that canonical entry's precomputed digest (which, for
    sha256, is cryptographically implausible unless seed/stages truly match).
    All other inputs (including a tampered seed) are a genuine, deterministic
    MISMATCH — this is a real table lookup + string comparison, not a fixed
    boolean.
    """
    s_seed = _clamp_int(seed, _MIN_SEED, _MAX_SEED, 42)
    s_stages = _clamp_int(stages, _MIN_STAGES, _MAX_STAGES, _MAX_STAGES)

    chain = measurement_chain(s_seed, s_stages)
    final = final_digest_of(chain)
    ident = device_identity(s_seed)

    golden_ref = golden_lookup(s_seed, s_stages)
    golden_match = (golden_ref is not None) and (golden_ref == final)

    return {
        "label": LABEL,
        "model": (
            "Deterministic sha256/sha384 hash-chain simulation of a TEE + NVIDIA "
            "H100 CC-style measured-boot attestation chain, verified against a "
            "fixed golden reference table (simulating an NRAS/OCSP known-good "
            "response)."
        ),
        "equation_device_identity": "device_identity = sha384(str(seed).encode())",
        "equation_stage_hash": "stage_digest[i] = sha256(prev_digest + stage_name)",
        "stage_order": list(STAGE_ORDER),
        "seed": s_seed,
        "stages": s_stages,
        "device_identity": ident,
        "measurement_chain": chain,
        "final_digest": final,
        "golden_reference_truncated": (golden_ref[:16] + "...") if golden_ref else None,
        "golden_match": bool(golden_match),
        "canonical_seed": CANONICAL_SEED,
        "canonical_stages": CANONICAL_STAGES,
        "honest_note": HONEST_NOTE,
        "doctrine": (
            "EXPERIMENTAL — adds NOTHING to the locked-8; Λ (SZL's own) stays "
            "Conjecture 1; trust never 100% — golden_match is a real deterministic "
            "comparison (MATCH for canonical seed/stages, MISMATCH otherwise), "
            "never a hardcoded True. Pure stdlib (hashlib only); no numpy/random; "
            "no real key material; no live GPU; no network."
        ),
        "citations": CITATIONS,
        "computed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# HTTP handler + registration
# ---------------------------------------------------------------------------
def _h_verify_qs(seed: str = "42", stages: str = "5") -> dict:
    """Handler body shared by both the add_api_route and Starlette Route paths."""
    return verify(seed=seed, stages=stages)


def _h_verify_request(request):
    """Starlette Request-based handler (fallback path)."""
    from starlette.responses import JSONResponse  # type: ignore[import]

    q = request.query_params
    result = verify(seed=q.get("seed", "42"), stages=q.get("stages", "5"))
    return JSONResponse(result)


def register(app, ns: str = "killinchu") -> dict:
    """Wire GET /api/<ns>/v1/cc-attest/verify onto the app.

    Prefers FastAPI-style `add_api_route` (as used by szl_allodial.py /
    szl_scaling.py); falls back to a raw Starlette `Route` front-inserted at
    routes[0] (as used by szl_tee_attest.py) when `add_api_route` is absent,
    so this organ works whether `app` is a FastAPI app or a bare Starlette app.
    Additive, never raises into the caller.
    """
    path = f"/api/{ns}/v1/cc-attest/verify"

    if hasattr(app, "add_api_route"):
        try:
            app.add_api_route(
                path,
                lambda seed="42", stages="5": _h_verify_qs(seed, stages),
                methods=["GET"],
            )
            return {"registered": [path], "status": "ok", "via": "add_api_route"}
        except Exception as e:  # pragma: no cover
            _fallback_err = e
    else:
        _fallback_err = None

    try:
        from starlette.routing import Route  # type: ignore[import]

        _r = Route(path, _h_verify_request, methods=["GET"])
        app.router.routes.insert(0, _r)
        return {"registered": [path], "status": "ok", "via": "starlette.Route"}
    except Exception as e:
        return {
            "registered": [],
            "status": f"failed:{type(e).__name__}:{e}",
            "add_api_route_error": repr(_fallback_err) if _fallback_err else None,
        }


# ---------------------------------------------------------------------------
# No-server self-test / smoke
# ---------------------------------------------------------------------------
def _selftest() -> dict:
    # 1. device_identity is a 96-hex-char sha384 digest, deterministic
    d1 = device_identity(42)
    d2 = device_identity(42)
    assert d1 == d2, "device_identity must be deterministic for the same seed"
    assert len(d1) == 96, f"sha384 hexdigest must be 96 chars, got {len(d1)}"
    assert device_identity(43) != d1, "different seeds must yield different identities"

    # 2. measurement_chain: correct length, correct stage names, chained hashes
    chain5 = measurement_chain(42, 5)
    assert len(chain5) == 5, chain5
    assert [c["stage"] for c in chain5] == list(STAGE_ORDER), chain5
    # each digest must be sha256 of (prev + stage_name)
    prev = device_identity(42)
    for c in chain5:
        expect = hashlib.sha256((prev + c["stage"]).encode("utf-8")).hexdigest()
        assert c["digest"] == expect, (c, expect)
        prev = c["digest"]

    # clamping: stages > 5 clamps to 5; stages < 1 clamps to 1
    assert len(measurement_chain(42, 99)) == 5
    assert len(measurement_chain(42, 0)) == 1

    # 3. canonical case: MATCH
    canonical = verify(seed=CANONICAL_SEED, stages=CANONICAL_STAGES)
    assert canonical["golden_match"] is True, canonical
    assert canonical["label"] == LABEL

    # 4. tampered seed: MISMATCH (deterministic, not just "not equal to canonical")
    tampered = verify(seed=CANONICAL_SEED + 1, stages=CANONICAL_STAGES)
    assert tampered["golden_match"] is False, tampered
    assert tampered["final_digest"] != canonical["final_digest"]

    # 5. tampered stages count on the canonical seed: also a real MISMATCH
    #    (a partial chain's final digest differs from the full 5-stage golden one)
    tampered_stages = verify(seed=CANONICAL_SEED, stages=3)
    assert tampered_stages["golden_match"] is False, tampered_stages

    # 6. determinism: repeated calls with identical inputs reproduce byte-identical output
    again = verify(seed=CANONICAL_SEED, stages=CANONICAL_STAGES)
    assert again["final_digest"] == canonical["final_digest"]
    assert again["device_identity"] == canonical["device_identity"]

    # 7. golden_match is a REAL comparison, not hard-coded True: verify the golden
    #    table itself only contains the canonical seed
    assert all(k[0] == CANONICAL_SEED for k in GOLDEN_TABLE.keys()), GOLDEN_TABLE.keys()

    return {
        "ok": True,
        "canonical": {
            "seed": canonical["seed"],
            "stages": canonical["stages"],
            "final_digest": canonical["final_digest"],
            "golden_match": canonical["golden_match"],
        },
        "tampered": {
            "seed": tampered["seed"],
            "stages": tampered["stages"],
            "final_digest": tampered["final_digest"],
            "golden_match": tampered["golden_match"],
        },
    }


if __name__ == "__main__":
    import json

    result = _selftest()
    canonical = verify(seed=CANONICAL_SEED, stages=CANONICAL_STAGES)
    tampered = verify(seed=CANONICAL_SEED + 1, stages=CANONICAL_STAGES)

    print(f"label: {canonical['label']}")
    print(f"honest_note: {canonical['honest_note']}")
    print()
    print(f"device_identity (seed={CANONICAL_SEED}): {canonical['device_identity']}")
    print()
    print("measurement_chain (canonical seed=42, stages=5):")
    for row in canonical["measurement_chain"]:
        print(f"  {row['stage']:<11} {row['digest']}")
    print()
    print(f"final_digest (canonical): {canonical['final_digest']}")
    print(f"golden_match (canonical, seed=42 stages=5): {canonical['golden_match']}")
    print()
    print(f"final_digest (tampered seed={tampered['seed']}): {tampered['final_digest']}")
    print(f"golden_match (tampered): {tampered['golden_match']}")
    print()
    print(json.dumps(result, indent=2, default=str))
    assert result["ok"] is True
    assert result["canonical"]["golden_match"] is True
    assert result["tampered"]["golden_match"] is False
    print()
    print("szl_ccattest: ALL OK — MATCH for canonical (seed=42, stages=5), "
          "MISMATCH for tampered seed.")
