---
title: "Killinchu — Andean Drone Intelligence"
emoji: 🦅
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: "Provenanced defense intel · 53-drone mesh · cosign-signed"
tags:
  - formal-verification
  - lean4
  - mathlib
  - dsse
  - governance
  - agentic-ai
  - doctrine-v11
  - killinchu
  - counter-uas
  - defense
ecosystem-stage: operational
---

# killinchu — Signed UDS Payload

## Lean-Verified

[![Lean-verified: composition_preserves_doctrine](https://img.shields.io/badge/Lean%204%20kernel-composition__preserves__doctrine%20%E2%9C%85-22c55e?style=flat-square&logo=github)](https://github.com/szl-holdings/lutar-lean/actions/runs/26854942475)

> ✅ **Lean-verified theorem:** `composition_preserves_doctrine` in `Lutar/Composition/TH1_Composition.lean`  
> Verified by Lake CI at commit `acd0fd46` (Mathlib v4.13.0 + Lean 4, kernel commit `c7c0ba17`).  
> Zero sorries · Full kernel check pass · [CI Run](https://github.com/szl-holdings/lutar-lean/actions/runs/26854942475)  
> This theorem proves that sequential composition of two doctrine-locked Lutar systems yields a doctrine-locked composed system — the formal foundation for the SZL governance stack.  
> Λ remains **Conjecture 1** (uniqueness TH10 is not yet fully proved). This is the first named green theorem on [lutar-lean main](https://github.com/szl-holdings/lutar-lean).

Counter-UAS operator surface with drone telemetry, intercept actions, and cued-track triage.

## Prerequisites

- [Zarf](https://docs.zarf.dev/getting-started/install/) v0.38+
- [cosign](https://docs.sigstore.dev/cosign/installation/) v2.2+
- [UDS CLI](https://uds.defenseunicorns.com/docs/getting-started/) v0.14+
- OCI registry access to `ghcr.io/szl-holdings`

## Quickstart — Deploy on UDS

```bash
# 1. Pull the signed Zarf package
zarf package pull oci://ghcr.io/szl-holdings/killinchu:v0.1.8

# 2. Verify the cosign keyless signature (before deploying)
cosign verify-blob \
  --certificate-identity-regexp "https://github.com/szl-holdings/killinchu/.github/workflows/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --bundle zarf-package-killinchu-amd64-v0.1.8.tar.zst.sigstore.json \
  zarf-package-killinchu-amd64-v0.1.8.tar.zst

# 3. Deploy
uds deploy oci://ghcr.io/szl-holdings/killinchu:v0.1.8
```

## Runtime demonstration

The same payload, running on Hugging Face for live demo:  
[szlholdings-killinchu.hf.space](https://szlholdings-killinchu.hf.space)

## Source

Every file in this repository builds the signed payload above. See `deploy/zarf.yaml`, `deploy/uds-package.yaml`, `deploy/peat-node.yaml`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `cosign: no bundle found` | Wrong tag in bundle filename | Re-pull with exact tag from release assets |
| `uds deploy` hangs | UDS Core not running | `uds deploy k3d-core` first |
| `/healthz` returns 503 | Container starting | Wait 30s, retry |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All commits require a DCO sign-off:

```
Signed-off-by: Your Name <you@example.com>
```

Use `git commit -s` to add automatically.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability disclosure policy.

## License

Apache-2.0. See [LICENSE](LICENSE).

---


