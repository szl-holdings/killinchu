# Killinchu — Deploy Runbook ("Just Works in San Diego")

Counter-UAS flagship of the SZL mesh. This runbook takes you from a clean laptop
to a running, signed killinchu instance — standalone Docker, Zarf package, or the
full UDS mesh bundle — plus the elite operator console and the kill-move curl.

**Doctrine v11 LOCKED · 749/14/163 · kernel `c7c0ba17` · Λ = Conjecture 1 (NOT a theorem)**
**SLSA L1 + L2** (cosign-signed images; signed SLSA provenance attestation verified via `cosign verify-attestation --type slsaprovenance`; L3 not claimed) ·
**Section 889 = exactly 5 vendors** (Huawei, ZTE, Hytera, Hikvision, Dahua) · **NO Iron Bank / FedRAMP / CMMC**

---

## 0. Tool versions (pinned — known-good at Warhacker)

| Tool      | Version    | Why                                  |
|-----------|------------|--------------------------------------|
| uds-cli   | v0.32.0    | mesh bundle deploy                   |
| Zarf      | v0.77.0    | standalone air-gap package           |
| cosign    | ≥ v2.2     | image + DSSE signature verification  |
| Docker    | ≥ 24       | standalone run                       |
| kubectl   | ≥ 1.28     | inspect the deployed namespace       |

```bash
uds version        # 0.32.0
zarf version       # 0.77.0
cosign version     # >= 2.2
```

---

## 1. Fastest path — standalone Docker (no cluster)

```bash
docker run --rm -p 7860:7860 ghcr.io/szl-holdings/killinchu:uds-v0.2.0
# open http://localhost:7860/elite        ← 14-tab elite operator console
```

The image is public on GHCR. Nothing to log in to.

---

## 2. Verify the artifact BEFORE you trust it (2 minutes)

```bash
# Image signature — cosign keyless OIDC (GitHub Actions issuer)
cosign verify ghcr.io/szl-holdings/killinchu:uds-v0.2.0 \
  --certificate-identity-regexp="^https://github.com/szl-holdings/" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"

# Live doctrine posture on a running instance
curl -s http://localhost:7860/api/killinchu/v1/honest | jq .kernel_commit   # => "c7c0ba17"
```

> Honest: rule-engine DSSE receipts are REAL only when the `SZL_COSIGN_PRIVATE_PEM`
> secret is present. When absent, the API returns an explicit **PLACEHOLDER** envelope
> — never a fabricated signature.

---

## 3. Zarf package (standalone / air-gap cluster)

```bash
# Build — pulls images + bundles the 3 K8s manifests in deploy/manifests/
zarf package create deploy/ --confirm
# => zarf-package-killinchu-amd64-uds-v0.2.0.tar.zst

# Deploy into the current kube-context
zarf package deploy zarf-package-killinchu-amd64-uds-v0.2.0.tar.zst --confirm

kubectl -n killinchu get pods,svc
kubectl -n killinchu port-forward svc/killinchu-svc 7860:7860
# open http://localhost:7860/elite
```

The package deploys: `Namespace killinchu` → `Deployment killinchu`
(image `ghcr.io/szl-holdings/killinchu:uds-v0.2.0`, port 7860,
`/api/killinchu/healthz` liveness+readiness) → `Service killinchu-svc`
(ClusterIP :7860, selector `app: killinchu`).

---

## 4. Full UDS mesh bundle (killinchu + sentra + amaru + a11oy + rosie)

```bash
uds-cli bundle deploy oci://ghcr.io/szl-holdings/szl-uds-bundle:uds-v0.2.1 --confirm
# applies deploy/uds-package.yaml (UDS Package CR): Istio ingress, SSO,
# network allow-list, and the killinchu health/fleet-state monitors.
```

After deploy, killinchu is exposed via the tenant gateway as host `killinchu`
(port 7860). The borrowed-powers panel in the console reads LIVE mesh state.

---

## 5. The kill-move — one curl, one signed 13-axis Λ-gate verdict

```bash
curl -s -X POST http://localhost:7860/api/killinchu/v1/counter-uas/evaluate \
  -H 'content-type: application/json' -d '{
    "telemetry": {"latitude":32.7157,"longitude":-117.1611,"ground_speed_m_s":22,
                  "side":"unknown","remote_id_present":false},
    "geofence":  {"center_lat":32.7157,"center_lon":-117.1611,"radius_m":500},
    "policy":    {"max_speed_m_s":25,"allow_sides":["friendly"],"require_remote_id":true},
    "axis_scores":[0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95,0.95]
  }' | jq '{decision, lambda, lambda_pass, breaches, receipt: .lambda_receipt.index}'
# => HALT (no remote-id + intruder side) with a DSSE Khipu receipt index.
```

---

## 6. Elite console

`GET /elite` (or `/killinchu/elite`) — 14 vertical-specific tabs, each backed by a
REAL endpoint (no mocks): Live Track Board, Sensor-Fusion, Multi-Track Queue, ROE
Editor, Engagement Audit, DSSE Receipt Verifier, 13-axis Λ-gate, 3-of-4 BFT Quorum,
PQC Hybrid Signing, Protocol Decoders, Geofence Editor, Swarm Topology, Threat DB,
and the **Cross-Flagship Borrowed Powers** panel (`GET /api/killinchu/v1/borrowed-powers`).

---

## 7. Image Tags

| Tag | Status | Notes |
|-----|--------|-------|
| `uds-v0.2.0` | ✅ PUBLIC, cosign-signed | Bundle-ready; canonical tag for v0.4.0 |
| `latest` | ✅ PUBLIC | Points to same digest as uds-v0.2.0 |
| `uds-v0.3.1-rc.1` | ❌ NOT PUBLISHED | Was referenced in deploy/zarf.yaml in error — removed |
| `v1.0.0-alpha` | ❌ NOT PUBLISHED | Was referenced in deploy/zarf.yaml in error — removed |

**Only `uds-v0.2.0` is the correct bundle-ready image tag.**

---

## 8. API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/killinchu/healthz` | GET | Health check |
| `/api/killinchu/v1/counter-uas/evaluate` | POST | Evaluate a drone track through the Λ-gate |
| `/api/killinchu/v1/honest` | GET | Live doctrine posture (SLSA L1, Λ Conjecture 1, kernel commit) |
| `/api/killinchu/v1/borrowed-powers` | GET | Cross-flagship borrowed-powers state |
| `/api/killinchu/drone/telemetry` | POST | Ingest drone telemetry |
| `/api/killinchu/drone/intercept` | POST | Log a signed intercept verdict |
| `/api/killinchu/drone/cued-tracks` | GET | Get current cued threat tracks |
| `/api/killinchu/drone/fleet-state` | GET | Get drone fleet state |
| `/metrics` | GET | Prometheus metrics |

---

## 9. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `/elite` returns the SPA shell | Module not COPY'd — confirm `killinchu_elite_console.py` in image; it registers BEFORE the SPA catch-all. |
| PQC sign → `503 ML-DSA backend unavailable` | Expected when `oqs-python`/`dilithium-py` absent. **ecdsa mode still works.** Honest, not a bug. |
| Receipts show `PLACEHOLDER` | `SZL_COSIGN_PRIVATE_PEM` secret absent. Set it for REAL DSSE; absence is honest, never fabricated. |
| `ImagePullBackOff` | Verify Zarf init was run before deploy; image must be in Zarf internal registry. |
| `Connection refused` on healthz | Pod may take 30–60s to start; `kubectl logs -n killinchu deploy/killinchu` for startup errors. |
| `zarf package create` fails with `404` on image | Use `uds-v0.2.0` tag only — `uds-v0.3.1-rc.1` and `v1.0.0-alpha` don't exist. |
| UDS Package CR not reconciled | Run with bundle (not standalone) so the UDS operator processes the Package CR. |

---

## 10. Honesty Doctrine

- SLSA **L1 + L2** — cosign-signed images; signed SLSA provenance attestation verified via `cosign verify-attestation --type slsaprovenance` (keyless Fulcio + Rekor, strict per-organ identity). L3 not claimed.
- Λ = **Conjecture 1** (NEVER a theorem; do not claim theorem status).
- DSSE Khipu receipts REAL only when `SZL_COSIGN_PRIVATE_PEM` present; honest **PLACEHOLDER** envelope otherwise.
- **No Iron Bank** — not in the Iron Bank registry.
- **No FedRAMP / CMMC**.
- Section 889 = exactly 5 vendors (Huawei, ZTE, Hytera, Hikvision, Dahua).

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
