---
title: "killinchu — Andean Drone Intelligence"
emoji: "🦅"
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: "killinchu — counter-UAS edge organ; 13-axis Λ-gate; DSSE receipt per interdiction"
tags:
  - doctrine-v11
  - defense
  - drone-intelligence
  - counter-uas
  - szl-holdings
  - agentic-ai
  - dsse
  - slsa-l2
  - apache-2.0
ecosystem-stage: "operational"
---

# killinchu 🦅

> **Detect. Classify. Defeat under human authority. Counter-UAS edge organ with a DSSE Khipu receipt for every interdiction decision.**

> **53 drone fingerprints · 13-axis Λ-gate · DSSE-signed verdicts · human-on-the-loop**

[![SLSA L1 honest](https://img.shields.io/badge/SLSA-L1%20honest-2C5F2D?style=flat-square)](https://github.com/szl-holdings/killinchu/attestations/29917005)
[![doctrine-v11](https://img.shields.io/badge/doctrine-v11%20LOCKED-0B1F3A?style=flat-square)](https://github.com/szl-holdings/.github/tree/main/doctrine)
[![CI](https://github.com/szl-holdings/killinchu/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/killinchu/actions)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)

**749 declarations · 14 axioms · 163 sorries · Doctrine v11 LOCKED · kernel `c7c0ba17`**

[Live demo](#live) · [What it does](#what-it-does) · [Verify](#verify-it-yourself) · [Architecture](#architecture) · [Parity vs. leaders](#parity-vs-leaders) · [Honest status](#honest-status)

---

## Live

**HF Space (one-click, no login):** [![Open in Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Open%20in%20Spaces-killinchu-FF9D00?style=flat-square)](https://huggingface.co/spaces/SZLHOLDINGS/killinchu)

- Space URL: https://szlholdings-killinchu.hf.space
- Health: `curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/honest | jq .kernel_commit` → `"c7c0ba17"`
- Docs: https://docs.szlholdings.com/flagships/killinchu
- Release: [v1.0.0](https://github.com/szl-holdings/killinchu/releases/tag/v1.0.0)

---

## What it does

**killinchu is the counter-UAS edge organ.** It runs where the mission happens — detecting, classifying, and evaluating hostile UAS tracks at machine speed, signing every interdiction decision with a DSSE Khipu receipt, and surfacing the result to a human operator (rosie) before any action propagates.

This is the **Cannonico answer**: Defense Unicorns published the problem as "there's no independent system today that can monitor AI behavior in real time, catch the moment a line gets crossed, and back it up with a permanent, tamper-evident record." killinchu is that system — deployed in one signed UDS command.

Key capabilities:
- **Real protocol decoders (no mocks)** — Remote ID (ASTM F3411-22a), ADS-B (Mode-S 1090ES via pyModeS), MAVLink v1/v2 (pymavlink)
- **13-axis Λ-gate** — haversine geofence breach check fused with `yuyay_v3` score; decisions emit DSSE Khipu receipts
- **53 drone fingerprints** — pre-loaded drone signature library
- **ROE / policy endpoint** — `/roe/policy`, `/counter-uas/evaluate` (Anduril parity, live HTTP 200)
- **Competitive parity** — Anduril/defense endpoints live + differentiators (signed receipts, Λ-gate, BFT quorum) no competitor has

**Honest protocol note:** broadcast Remote-ID/ADS-B/MAVLink are unauthenticated and spoofable. Every decoded field is a *claim*, never ground truth. This is stated explicitly in `/v1/honest`.

---

## Verify it yourself

```bash
# 1. Confirm live doctrine posture
curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/honest | jq .kernel_commit
# => "c7c0ba17"

# 2. Verify the image provenance (private repo — GitHub Sigstore instance, SLSA L1 honest)
#    killinchu is a PRIVATE repo: its attestation is issued under GitHub's private
#    Fulcio (CN=Fulcio Intermediate l2, O=GitHub, Inc.) with NO public Rekor tlog
#    entry, so slsa-verifier against the public Sigstore log cannot confirm it.
#    We therefore honestly stay at L1; public-Rekor L2 is roadmap (Wire D).
gh attestation verify \
  oci://ghcr.io/szl-holdings/killinchu@sha256:85f92bd2... \
  --repo szl-holdings/killinchu
# Attestation: https://github.com/szl-holdings/killinchu/attestations/29917005
# (Requires authorized access to the private repo)

# 3. Exercise the counter-UAS evaluate endpoint
curl -s -X POST https://szlholdings-killinchu.hf.space/api/killinchu/counter-uas/evaluate \
  -H 'content-type: application/json' \
  -d '{"track":{"lat":32.71,"lon":-117.15,"alt_m":120,"vel_ms":25}}'
# => {"verdict":"CLASSIFY","lambda_score":0.73,"receipt_signed":true}

# 4. Deploy as part of the signed mesh bundle
uds deploy oci://ghcr.io/szl-holdings/szl-mesh:v0.4.0 --confirm
```

**Full guide:** [developers/VERIFY.md](https://github.com/szl-holdings/developers/blob/main/VERIFY.md)

---

## Architecture

```mermaid
graph TD
    RID[Remote ID\nASTM F3411-22a] --> DEC[Protocol decoder\nno mocks]
    ADS[ADS-B\nMode-S 1090ES] --> DEC
    MAV[MAVLink v1/v2] --> DEC
    DEC --> FP[53 drone fingerprints\nclassification]
    FP --> GATE[13-axis Λ-gate\nyuyay_v3\nhaversine geofence]
    GATE --> VRD[DSSE Khipu receipt\nP-256 signed\nMerkle DAG node]
    VRD --> ROE[sentra ROE check\n/roe/policy\nsigned deny/allow]
    ROE --> ROSIE[rosie console\nhuman-on-the-loop\nconfirm + authorize]
    VRD --> A11[a11oy Khipu DAG\nreceipts.in = receipts.out]
```

---

## Parity vs. leaders

| Capability | Anduril | killinchu | Differentiator |
|---|---|---|---|
| UAS track classification | ✅ | ✅ 53 fingerprints, 13-axis | — |
| Protocol decoders | ✅ (proprietary) | ✅ **open-source** (ASTM/ADS-B/MAVLink) | Open, auditable |
| Signed verdicts per interdiction | — | ✅ **DSSE receipt per decision** | Each block is a verifiable artifact |
| Human-on-the-loop gate | ✅ | ✅ rosie confirmation | — |
| Supply-chain provenance | — | ✅ **cosign-signed (SLSA L1 honest)** | — |
| Air-gap deployment | ✅ | ✅ **UDS bundle** | Open-source |
| BFT receipt quorum | — | ✅ | — |

---

## Quickstart

```bash
docker run --rm -p 7860:7860 ghcr.io/szl-holdings/killinchu:uds-v0.2.0
```

---

## Honest status

| Claim | Status |
|---|---|
| Live HF Space (HTTP 200) | ✅ |
| SLSA Build L1 honest | ✅ — cosign-signed via GitHub Sigstore (private repo — private Fulcio, no public Rekor by design); attestation [29917005](https://github.com/szl-holdings/killinchu/attestations/29917005). Public-Rekor L2 is roadmap (Wire D) — not yet earned. |
| cosign keyless signed | ✅ (private repo; GitHub Sigstore instance) |
| 53 drone fingerprints | ✅ |
| Real protocol decoders | ✅ — ASTM F3411-22a / pyModeS / pymavlink (no mocks) |
| Spoofing vulnerability | ⚠️ **Explicit** — broadcast protocols are unauthenticated; every field is a claim, not ground truth |
| Lean 749/14/163 @ `c7c0ba17` | ✅ |
| Λ-uniqueness | ⚠️ Conjecture 1 — not a theorem |
| SLSA L3 | ❌ Not claimed |
| FedRAMP / CMMC | ❌ Not claimed |

---

<sub>Doctrine v11 LOCKED · 749/14/163 · kernel `c7c0ba17` · SLSA L1 honest (private Fulcio, no public Rekor; L2 roadmap via Wire D) · Λ = Conjecture 1 · Apache-2.0</sub>

Signed-off-by: stephenlutar2-hash <stephenlutar2@gmail.com>
