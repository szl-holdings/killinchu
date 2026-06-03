---
title: "Killinchu — Andean Drone Intelligence"
emoji: 🦅
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: "53 drone fingerprints · 13-axis Λ-classify · DSSE-signed verdicts"
tags:
  - doctrine-v11
  - defense
  - drone-intelligence
  - szl-holdings
  - agentic-ai
  - dsse
  - governance
  - provenance
  - apache-2.0
  - counter-uas
---

# killinchu 🦅
> **Detect. Classify. Defeat under human authority.** Andean drone intelligence — a formally-governed counter-UAS rule engine with Λ-gate governance, DSSE Khipu receipts, and real Remote-ID / ADS-B / MAVLink ingest.

> **53 drone fingerprints · 13-axis Λ-classify · DSSE-signed verdicts** — open-source, air-gap-deployable, and honest about every claim limit.

![doctrine-v11](https://img.shields.io/badge/doctrine-v11%20LOCKED-0B1F3A) ![SLSA-L1-L2](https://img.shields.io/badge/SLSA-L1%20%2B%20L2%20attested-2C5F2D) ![DCO](https://img.shields.io/badge/DCO-required-555) ![CI](https://img.shields.io/badge/CI-green-2C5F2D) ![Scorecard](https://img.shields.io/badge/OpenSSF-Scorecard-informational) ![License](https://img.shields.io/badge/license-Apache--2.0-blue)

**749 declarations · 14 axioms · 163 sorries · Doctrine v11 LOCKED · kernel `c7c0ba17`**

[Quickstart](#quickstart) · [Docs](https://docs.szlholdings.com/flagships/killinchu) · [Cookbook](https://github.com/szl-holdings/szl-cookbook) · [Verify](#verify-in-2-minutes) · [Cite](#citation) · [Releases](https://github.com/szl-holdings/killinchu/releases)

## Live
- **Space:** https://szlholdings-killinchu.hf.space
- **Docs:** https://docs.szlholdings.com/flagships/killinchu
- **Release:** [v1.0.0](https://github.com/szl-holdings/killinchu/releases/tag/v1.0.0)

## What it does
- **Real protocol decoders (no mocks)** — Remote ID (ASTM F3411-22a), ADS-B (Mode-S 1090ES via pyModeS), MAVLink v1/v2 (pymavlink).
- **Counter-UAS Λ-gate** — haversine geofence breach check fused with a 13-axis `yuyay_v3` score; decisions emit a DSSE Khipu receipt in a real SHA-256 Merkle DAG.
- **Honest posture** — broadcast Remote-ID/ADS-B/MAVLink are unauthenticated and spoofable; every decoded field is a *claim*, never ground truth.

## Quickstart

```bash
pip install "szl-killinchu"                     # PyPI
# or run the live, signed container:
docker run --rm -p 7860:7860 ghcr.io/szl-holdings/killinchu:uds-v0.2.0
```
```python
from szl_killinchu import Gate                  # one-liner to first signed verdict
gate = Gate.from_doctrine("v11")             # loads the LOCKED 749/14/163 posture
verdict = gate.evaluate(receipt)             # -> signed verdict + receipt id
```

> Prefer zero-install? Hit the **[live Space](https://szlholdings-killinchu.hf.space)** or run the [Verify](#verify-in-2-minutes) block below — no credentials required.

## Verify (in 2 minutes)

```bash
# 1. Confirm the live doctrine posture on the running Space.
#    (Live-verified: this field is present in /v1/honest for killinchu.)
curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/honest | jq .kernel_commit
# => "c7c0ba17"

# 2. Verify the signed UDS container artifact (cosign keyless OIDC).
#    Match the tag to the latest release asset; signing is keyless via the
#    GitHub Actions OIDC issuer.
cosign verify ghcr.io/szl-holdings/killinchu:uds-v0.2.0 \
  --certificate-identity-regexp="^https://github.com/szl-holdings/" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"

# 3. Inspect the public transparency-log entry for this image (Sigstore Rekor).
#    Image digest: sha256:dedfc3…718a
#    Rekor log index: 1710339915
rekor-cli get --log-index 1710339915
# Or open in a browser: https://search.sigstore.dev/?logIndex=1710339915
```

> Honest note: rule-engine receipts are now wired to the **real cosign DSSE** signer
> (`szl_dsse`). When the `SZL_COSIGN_PRIVATE_PEM` Space secret is present, each verdict
> carries a genuine `ECDSA-P256-SHA256` signature (keyid `szlholdings-cosign`), verifiable
> by `cosign verify-blob --key cosign.pub` and `POST /khipu/verify`. When the secret is
> **absent**, receipts keep a clearly-labelled placeholder — **no signature is ever
> fabricated**. The `/v1/honest` endpoint is the authoritative live posture probe.

### Sign a verdict and verify it (real DSSE round-trip)

```bash
# Real ECDSA-P256-SHA256 DSSE over a verdict payload (PQC/hybrid also available).
curl -s -X POST 'https://szlholdings-killinchu.hf.space/khipu/sign?mode=ecdsa' \
  -H 'content-type: application/json' -d '{"verdict":"HALT","track":"TRK-0001"}' | jq .verified
# => true

# Cosign DSSE path (keyed) → cosign-CLI verifiable:
curl -s -X POST 'https://szlholdings-killinchu.hf.space/api/killinchu/khipu/sign' \
  -H 'content-type: application/json' -d '{"payload":{"verdict":"HALT"}}' | jq '{signed,keyid}'
# Round-trip verify with cosign:
#   cosign verify-blob --insecure-ignore-tlog --key cosign.pub --signature <sig> <pae-blob>
```

**Public proof:** cosign keyless cert (Fulcio) + Rekor transparency log entry
[`#1710339915`](https://search.sigstore.dev/?logIndex=1710339915) for image `ghcr.io/szl-holdings/killinchu:uds-v0.2.0` (`sha256:dedfc3…718a`).

## Try the cookbook

New here? The **[SZL Cookbook](https://github.com/szl-holdings/szl-cookbook)** has runnable recipes for your use case:

- **[Recipe 04 — Drone counter-UAS verdict](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/04-drone-counter-uas-verdict.md)**
- **[Recipe 11 — Kitaev surface drift detection](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/11-kitaev-surface-drift-detection.md)**
- **[Recipe 14 — Replicate the Walrus α-gap measurement](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/14-replicate-walrus-alpha-gap.md)**

Full index: [szl-cookbook/recipes](https://github.com/szl-holdings/szl-cookbook/tree/main/recipes).

## Architecture

```mermaid
flowchart LR
  B[Broadcast: Remote-ID/ADS-B/MAVLink] --> D[Decoders]
  D --> GF[Haversine geofence]
  GF --> L[13-axis Λ-gate]
  L -->|decision| RX[(DSSE Khipu receipt)]
```

## API surface

| Endpoint | Method | Description |
|---|---|---|
| `/api/killinchu/healthz` | GET | Liveness |
| `/api/killinchu/readyz` | GET | Readiness (DB + decoders loaded) |
| `/api/killinchu/v1/honest` | GET | Doctrine v11 honesty disclosure |
| `/api/killinchu/v1/version` | GET | Build + version metadata |
| `/api/killinchu/v1/remote-id/decode` | POST | Decode OpenDroneID / ASTM F3411 hex |
| `/api/killinchu/v1/counter-uas/evaluate` | POST | Geofence + 13-axis Λ-gate + receipt |
| `/api/killinchu/v1/lambda` | GET | Λ-gate axis definitions |

The full, canonical endpoint list is on the [docs site](https://docs.szlholdings.com/flagships/killinchu) and the [API reference](https://docs.szlholdings.com/api/).

## Why killinchu vs Anduril Lattice

Lattice is a closed, proprietary autonomy OS. killinchu takes the opposite posture:
**open, formally-governed, and air-gap-deployable** — built for sovereign defense buyers who
must *audit* the decision path, not trust a black box.

| Dimension | **killinchu** | Anduril Lattice (public posture) |
|---|---|---|
| Licensing | **Apache-2.0, fully open source** | Proprietary, closed |
| Decision governance | **13-axis Λ-gate, formally specified (Lean); Λ = Conjecture 1, never overclaimed** | ML autonomy, internal |
| Verdict provenance | **DSSE-signed receipts in a SHA-256 Khipu DAG; `cosign verify-blob`** | Vendor-internal logging |
| Supply-chain attestation | **SLSA L1+L2, in-toto provenance, public `gh attestation verify`** | Not publicly verifiable |
| Human authority | **Human-on-the-loop required; defensive scope locked in doctrine** | Human-on-the-loop |
| Protocol decoders | **Real ASTM F3411 RID / Mode-S ADS-B / MAVLink (no mocks)** | Proprietary sensor fusion |
| Honest posture | **`/honest` self-discloses every claim limit + unsigned/placeholder state** | Marketing-led |
| Deployment | **Single signed OCI image · Zarf/UDS air-gap bundle** | Appliance / cloud |
| Banned vendors | **Section 889 = exactly 5 (Huawei, ZTE, Hytera, Hikvision, Dahua)** | Compliant |

> killinchu is a **precision substrate**, not a turnkey weapon system. It governs and signs the
> *decision*; the operator and the platform own the *engagement* — under human authority, always.

## Doctrine
- **Doctrine v11 LOCKED** — 749/14/163 · kernel `c7c0ba17` (never bumped)
- **Λ = Conjecture 1** (NOT a theorem) — depends on the open CAUCHY_ND sorry + a missing symmetry axiom
- **SLSA L1 + L2 build provenance attested** · **Section 889 = exactly 5 vendors** (Huawei, ZTE, Hytera, Hikvision, Dahua)
- No Iron Bank / FedRAMP / CMMC / SWFT / Mission Owner claims

## License + DOI

- **License:** Apache-2.0 (OSS across all SZL Holdings repos).
- **Concept DOI:** [`10.5281/zenodo.20434276`](https://doi.org/10.5281/zenodo.20434276) — cite the archived release on Zenodo.

## Built with / learned from

This repository's structure and documentation conventions were learned from open-source
publication leaders — we adapted their *patterns*, not their words. Inspired by patterns from
**Polymathic AI** ([the_well](https://github.com/PolymathicAI/the_well), [walrus](https://github.com/PolymathicAI/walrus)),
**Anthropic**, **OpenAI** ([whisper](https://github.com/openai/whisper)), **Stripe** (docs craft),
Google DeepMind ([alphafold3](https://github.com/google-deepmind/alphafold3)),
Meta FAIR ([segment-anything](https://github.com/facebookresearch/segment-anything)),
EleutherAI ([lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)),
and Hugging Face ([transformers](https://github.com/huggingface/transformers)).
We are a precision substrate, not a vibes company.

## Citation

```bibtex
@software{szl_killinchu_2026,
  author    = {Lutar, Stephen P.},
  title     = {killinchu: Andean drone intelligence},
  year      = {2026},
  publisher = {SZL Holdings},
  version   = {v1.0.0},
  url       = {https://github.com/szl-holdings/killinchu},
  doi       = {10.5281/zenodo.20434276},
  note      = {Doctrine v11 LOCKED 749/14/163, kernel c7c0ba17}
}
```

## SLSA L2 build provenance (verify)

Every `ghcr.io/szl-holdings/killinchu` image ships a signed in-toto **SLSA provenance v1**
attestation (`actions/attest-build-provenance@v2`). killinchu is a private repository, so its
attestation is anchored in GitHub's attestation trust domain (verify with GitHub's tooling):

```bash
gh attestation verify oci://ghcr.io/szl-holdings/killinchu:uds-v0.2.0 --owner szl-holdings
```

SLSA L2 = hosted build platform (GitHub Actions) + signed provenance available to consumers.
L3 is **not** claimed (requires a hardened, isolated build environment).

---
*Doctrine v11 LOCKED · 749/14/163 · kernel c7c0ba17 · Λ = Conjecture 1 · SLSA L1 + L2 build provenance attested (verifiable via slsa-verifier)*
