# killinchu — Signed UDS Payload

Counter-UAS operator surface with drone telemetry, intercept actions, and cued-track triage.

## Verify the latest signed release

    zarf package pull oci://ghcr.io/szl-holdings/killinchu:uds-v0.3.1-rc.1
    cosign verify-blob \
      --certificate-identity-regexp "https://github.com/szl-holdings/killinchu/.github/workflows/.*" \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com \
      --bundle zarf-package-killinchu-amd64-uds-v0.3.1-rc.1.tar.zst.sigstore.json \
      zarf-package-killinchu-amd64-uds-v0.3.1-rc.1.tar.zst

## Deploy on UDS

    uds deploy oci://ghcr.io/szl-holdings/killinchu:uds-v0.3.1-rc.1

## Runtime demonstration

The same payload, running on Hugging Face for live demo:
[szlholdings-killinchu.hf.space](https://szlholdings-killinchu.hf.space)

## Source

Every file in this repository builds the signed payload above. See `deploy/zarf.yaml`, `deploy/uds-package.yaml`, `deploy/peat-node.yaml`.

## Doctrine

- Doctrine v11 LOCKED 749/14/163 at kernel commit c7c0ba17
- Λ-aggregator: Conjecture 1 (NOT theorem)
- SLSA L1 honest
- Section 889 = exactly 5 vendors

## Prerequisites

- [Zarf](https://docs.zarf.dev/getting-started/install/) v0.38+
- [cosign](https://docs.sigstore.dev/cosign/installation/) v2.2+
- [UDS CLI](https://uds.defenseunicorns.com/docs/getting-started/) v0.14+
- OCI registry access to `ghcr.io/szl-holdings`

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `cosign: no bundle found` | Wrong tag in bundle filename | Re-pull with exact tag from release assets |
| `uds deploy` hangs | UDS Core not running | `uds deploy k3d-core` first |
| `/healthz` returns 503 | Container starting | Wait 30s, retry |
| Image pull backoff | GHCR auth | `zarf tools registry login ghcr.io` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All commits require a DCO sign-off:

```bash
git commit -s -m "your message"
```

## Security

See [SECURITY.md](SECURITY.md) for vulnerability disclosure policy.

## License

Apache-2.0. See [LICENSE](LICENSE).


---

---
title: "Killinchu — Andean Drone Intelligence"
emoji: 🦅
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: "Provenanced defense intel · 53-drone mesh · cosign-signed"
---

# Killinchu 🦅 — Andean Drone Intelligence

> **Killinchu** (Quechua: *kestrel / hawk*) — the SZL Holdings drone-intelligence
> flagship. A formally-verified **counter-UAS rule engine** with **Λ-gate
> governance**, **DSSE Khipu receipts**, and real **Remote-ID / ADS-B / MAVLink**
> protocol ingest. Counter-UAS rule engine for the SZL governance substrate.

## What this is

Killinchu ingests the broadcast self-identification signals that uncrewed aircraft
emit and turns them into governed counter-UAS decisions:

- **Real protocol decoders (no mocks):**
  - **Remote ID** — OpenDroneID / ASTM F3411-22a 25-byte message parser (Basic ID,
    Location/Vector, Self ID, System, Operator ID).
  - **ADS-B** — Mode-S 1090ES (DF17) via `pyModeS` v3, including CPR even/odd pair
    resolution for global position.
  - **MAVLink** — v1/v2 frame parsing via `pymavlink` (HEARTBEAT and beyond).
- **Real drone database** — 53 systems across allied, dual-use, adversary, and
  counter-UAS categories, organized by US DoD UAS Groups 1–5, each with telemetry
  surfaces, specs, and sourced notes.
- **Counter-UAS Λ-gate** — a haversine geofence breach check fused with a
  **13-axis `yuyay_v3`** governance score (Λ); decisions emit a **DSSE Khipu
  receipt** anchored in an in-memory Merkle DAG (real SHA-256).
- **Swarm topology** — Union-Find connected-component detection over proximity
  graphs to flag coordinated swarms.

## Honesty disclosure (Doctrine v11)

This Space follows **SZL Doctrine v11** and discloses its real posture:

- **Λ is a Conjecture, not a Theorem.** The 13-axis governance score is a
  decision aid, not a proof of safety.
- **DSSE receipt signatures are `PLACEHOLDER`** — Sigstore CI signing is not yet
  wired into CI. Receipts carry a real SHA-256 Merkle digest but an unsigned
  envelope. **SLSA Level 1** honest.
- **Broadcast Remote ID, ADS-B, and civilian MAVLink are unauthenticated and
  spoofable.** Every decoded field is a *claim*, not ground truth. Malformed
  decoder input returns an **honest error**, never a silent pass.
- Formal-verification corpus: **749 declarations / 14 unique axioms (15 raw) /
  163 sorries**.

`GET /api/killinchu/v1/honest` returns this disclosure as JSON.

## API

Base: `/api/killinchu`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/killinchu/healthz` | Liveness |
| GET | `/api/killinchu/readyz` | Readiness (drone DB + decoders loaded) |
| GET | `/api/killinchu/v1/honest` | Doctrine v11 honesty disclosure |
| POST | `/api/killinchu/v1/remote-id/decode` | Decode OpenDroneID/ASTM F3411 hex |
| POST | `/api/killinchu/v1/ads-b/decode` | Decode ADS-B (single frame or even/odd pair) |
| POST | `/api/killinchu/v1/mavlink/parse` | Parse MAVLink v1/v2 frames |
| GET | `/api/killinchu/v1/drones/database` | Drone DB (filters: side, group, country, role) |
| GET | `/api/killinchu/v1/drones/{id}` | Single drone record |
| POST | `/api/killinchu/v1/counter-uas/evaluate` | Geofence + 13-axis Λ-gate + receipt |
| GET/POST | `/api/killinchu/v1/swarm/topology` | Union-Find swarm component detection |
| GET | `/api/killinchu/v1/threats/active` | Active threat board |
| POST | `/api/killinchu/v1/receipt/emit` | Emit a Khipu DSSE receipt |
| GET | `/api/killinchu/v1/receipt/ledger` | Khipu Merkle ledger |
| GET | `/api/killinchu/v1/lambda` | Λ-gate axis definitions |
| GET | `/api/killinchu/v1/research` | Sourced research corpus |
| GET | `/api/killinchu/v1/samples` | Verified sample test vectors |

## Stack

FastAPI · uvicorn · pyModeS v3 · pymavlink · React + Vite SPA (wouter) ·
MapLibre GL (OpenFreeMap tokenless tiles) · Docker on Hugging Face Spaces.

---

© 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 ·
Apache-2.0 · Doctrine v11 · *Hatun-Willay*

Built with Yachay CTO + Opus 4.8.

---

## Understudy Parity (Doctrine v11 · 2026-06-01)

**Provenanced defense intelligence · 53-drone mesh · cosign-signed missions · geofence-enforced.**

Killinchu carries every a11oy moat plus the **11 understudy capabilities** under its defense
namespace `/api/killinchu/v2/*`, so it is failover-ready to substitute for the a11oy platform
while keeping its defense-vertical (legal/authority) gate posture:

- **7-tier LLM router** (open stack) — `/llm/{tiers,route}`
- **Agentic RAG** — `/rag/{ingest,query,stats}` (honest 503 where embedding deps absent)
- **MCP server, 18 tools, streamable-HTTP** — `/mcp`, `/mcp/{tools,claude-config,rpc}`
- **Understudy failover** — `/understudy/{health,promote,ask}` (`ready_to_substitute: true`; promote gated)
- **PURIQ 12 organs · 23 formulas · KIPU/QILLQAQ 16 genomes · Khipu DAG RS(10,6) · AYNI-OS · WAYRA**
- Canonical cross-organ: `/healthz`, `/khipu/{sign,verify,pubkey}`, `/wires/D`, `/v1/yuyay/gate`, `/api/killinchu/v2/metrics`

Built from `platform/packages/understudy-runtime` (`szl_understudy.register(app, "killinchu")`).
Additive — no routes removed. See `docs/moat-equivalence.md`.
