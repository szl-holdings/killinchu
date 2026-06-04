# Killinchu Deploy Guide

**Image:** `ghcr.io/szl-holdings/killinchu:uds-v0.2.0` (PUBLIC, SLSA L1, cosign-signed)  
**Repo:** `szl-holdings/killinchu`  
**Updated:** 2026-06-05  
**Doctrine:** v11 LOCKED 749/14/163 · SLSA L1 · Λ = Conjecture 1  
**Signed-off-by:** stephenlutar2-hash \<stephenlutar2@gmail.com\>

---

## What Killinchu Does

Killinchu is the SZL counter-UAS organ. It:

1. **Decodes drone telemetry** — OpenDroneID (ASTM F3411-22a), ADS-B Mode-S 1090ES, MAVLink
2. **Scores threats** through the 13-axis Λ-gate geofence + governance model (Conjecture 1, NOT a theorem)
3. **Signs verdicts** with DSSE Khipu receipts for tamper-evident audit trail
4. **Emits** drone fleet state, threat tracks, and intercept logs to the mesh

This is the Warhacker "Cannonico" answer: an independent system that monitors AI behavior in real time and backs it up with a permanent, tamper-evident record.

---

## Prerequisites

- **UDS Core running** (Istio, Pepr, Keycloak) — killinchu deploys into an existing UDS Core cluster
- **uds-cli v0.32.0** for bundle deploy (recommended)
- **zarf v0.77.0** for standalone package deploy

---

## Deploy — Recommended: Bundle

The recommended way to deploy killinchu is via the **szl-mesh bundle**, which includes all 5 organs in deploy order:

```bash
# USB tarball (airgap — Warhacker San Diego):
uds-cli bundle deploy szl-mesh-v0.4.0.tar.zst --confirm

# OCI pull (internet):
uds deploy oci://ghcr.io/szl-holdings/szl-mesh:v0.4.0 --confirm
```

See [uds-bundles DEPLOY.md](https://github.com/szl-holdings/uds-bundles/blob/main/DEPLOY.md) for full bundle instructions.

---

## Deploy — Standalone (killinchu only)

If you need to deploy killinchu without the full mesh bundle:

```bash
# From this repo root (deploy/zarf.yaml + deploy/manifests/ must be present):
zarf package create deploy/ --confirm
zarf package deploy zarf-package-killinchu-amd64-uds-v0.2.0.tar.zst --confirm
```

This creates a Zarf package with:
- `killinchu-runtime` — image + k8s manifests (Namespace, Deployment, Service)
- `killinchu-drone-surfaces` — drone API routes file
- `killinchu-peat-node` (optional) — peat-node CRDT mesh sidecar

**Note:** Standalone deploy skips the UDS Package CR registration. SSO and UDS network policy will NOT be auto-provisioned. For full UDS integration, use the bundle path.

---

## Verify

```bash
# Health check
kubectl port-forward -n killinchu deploy/killinchu 7860:7860 &
curl -sf http://localhost:7860/api/killinchu/healthz && echo "killinchu OK"
kill %1

# Counter-UAS evaluation test
curl -X POST http://localhost:7860/api/killinchu/v1/counter-uas/evaluate \
  -H "Content-Type: application/json" \
  -d '{"track_id":"4840D6","lat":32.7,"lon":-117.2,"alt_m":120,"speed_ms":15}'
# Expected: {"track_id":"4840D6","verdict":"MONITOR","receipt_id":"sha256:..."}

# Verify image signature
cosign verify ghcr.io/szl-holdings/killinchu:uds-v0.2.0 \
  --certificate-identity-regexp="^https://github.com/szl-holdings/" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
# Expected: Verified OK
```

---

## Image Tags

| Tag | Status | Notes |
|-----|--------|-------|
| `uds-v0.2.0` | ✅ PUBLIC, cosign-signed | Bundle-ready; canonical tag for v0.4.0 |
| `latest` | ✅ PUBLIC | Points to same digest as uds-v0.2.0 |
| `uds-v0.3.1-rc.1` | ❌ NOT PUBLISHED | Was referenced in deploy/zarf.yaml in error — removed |
| `v1.0.0-alpha` | ❌ NOT PUBLISHED | Was referenced in deploy/zarf.yaml in error — removed |

**Only `uds-v0.2.0` is the correct bundle-ready image tag.**

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/killinchu/healthz` | GET | Health check |
| `/api/killinchu/v1/counter-uas/evaluate` | POST | Evaluate a drone track through the Λ-gate |
| `/api/killinchu/drone/telemetry` | POST | Ingest drone telemetry |
| `/api/killinchu/drone/intercept` | POST | Log a signed intercept verdict |
| `/api/killinchu/drone/cued-tracks` | GET | Get current cued threat tracks |
| `/api/killinchu/drone/fleet-state` | GET | Get drone fleet state |
| `/metrics` | GET | Prometheus metrics |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ImagePullBackOff` | Verify Zarf init was run before deploy; image must be in Zarf internal registry |
| `Connection refused` on healthz | Pod may take 30–60s to start; `kubectl logs -n killinchu deploy/killinchu` for startup errors |
| `zarf package create` fails with `404` on image | Use `uds-v0.2.0` tag only — `uds-v0.3.1-rc.1` and `v1.0.0-alpha` don't exist |
| UDS Package CR not reconciled | Run with bundle (not standalone) so UDS operator processes the Package CR |

---

## Honesty Doctrine

- SLSA **L1** honest — keyless cosign provenance in Rekor (logIndex 1710339915)
- Λ = **Conjecture 1** (NEVER a theorem; do not claim theorem status)
- **No Iron Bank** — not in Iron Bank registry
- **No FedRAMP / CMMC**
