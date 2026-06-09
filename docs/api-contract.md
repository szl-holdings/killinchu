# API Contract — killinchu v1.0
**Doctrine v11 LOCKED 749/14/163 | SLSA L1 honest · L2 roadmap | Version: 1.0.0**  
**Updated:** 2026-06-03

This document is the canonical API contract for the `killinchu` flagship.
It is versioned with the code release (see `CHANGELOG.md` for history).

## Base URL

```
https://szlholdings-killinchu.hf.space
```

## Authentication

No API key required for public endpoints. All responses include doctrine invariants.

## Doctrine Invariants in All Responses

Every JSON response from `killinchu` includes:

```json
{
  "doctrine": "v11",
  "declarations": 749,
  "axioms_unique": 14,
  "sorries_total": 163
}
```

These values are LOCKED. Any deviation is a bug.

## Core Endpoints

### GET `/api/killinchu/v1/lambda`

Returns the 13-axis Lambda (Λ) trust aggregation score.

**Response:**
```json
{
  "trust_axes": 13,
  "axes": [{"name": "soundness", "score": 0.92}, ...],
  "lambda": 0.91911,
  "lambda_floor": 0.90,
  "pass": true,
  "aggregate": "geometric mean (yuyay_v3 canonical, 13-axis)",
  "uniqueness": "Conjecture 1 — NOT a Theorem",
  "declarations": 749,
  "axioms_unique": 14,
  "sorries_total": 163,
  "doctrine": "v11"
}
```

**Note:** Lambda (Λ) is Conjecture 1, NOT a closed theorem. This is an honest disclosure.

### GET `/api/killinchu/v1/honest`

Returns honest doctrine disclosure for compliance auditors.

**Response:**
```json
{
  "doctrine": "v11",
  "declarations": 749,
  "axioms_unique": 14,
  "sorries_total": 163,
  "lambda_uniqueness": "Conjecture 1 — NOT a closed theorem",
  "slsa": "L1 (honest)",
  "kernel_commit": "c7c0ba17",
  "section_889_vendors": ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]
}
```

### GET `/api/killinchu/v4/fleet` (a11oy only) / `/api/killinchu/v1/brain` (Provenance Anchor / Operator roles, in a11oy)

Product-specific endpoints (see per-product docs below). The honest roles
Provenance Anchor and Operator (retired internal codenames `amaru`/`rosie`)
are not separately shipping products — that capability lives inside a11oy.
Only a11oy and killinchu ship today.

## Response Headers

| Header | Description |
|--------|-------------|
| `x-szl-space` | Flagship identifier |
| `x-szl-wire-d` | Wire D DSSE provenance |
| `traceparent` | W3C TraceContext format |

## Error Responses

| Status | Meaning |
|--------|---------|
| 200 | OK |
| 404 | Route not found (never returns 405) |
| 503 | Space starting (cold start, retry in 30s) |

## SLSA Level

**SLSA L1 honest; L2 roadmap.** Images are cosign-signed and verifiable via `cosign verify` (keyless Fulcio + Rekor, strict per-organ identity). L2 (attested build-service provenance, `cosign verify-attestation --type slsaprovenance`) is on the roadmap and **not yet claimed as achieved today**. L3 (hardened, isolated builder) is not claimed.

## Section 889 Compliance

This flagship does NOT use prohibited components from:
Huawei, ZTE, Hytera, Hikvision, or Dahua.

**Signed-off-by: Yachay <yachay@szlholdings.ai>**  
**ORCID 0009-0001-0110-4173**
