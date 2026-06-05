# killinchu — Developer Onboarding

> **Doctrine v11 LOCKED** · 749 declarations · 14 axioms · 163 sorries · Λ = Conjecture 1 · SLSA L1 honest

killinchu (Quechua: kestrel/hawk) is the SZL counter-UAS drone intelligence organ.

---

## 1. What killinchu actually is

killinchu provides:

1. **Real protocol decoders** (no mocks) — Remote ID (ASTM F3411-22a), ADS-B (Mode-S 1090ES via pyModeS), MAVLink v1/v2 (pymavlink).
2. **Counter-UAS Λ-gate** — haversine geofence breach + 13-axis `yuyay_v3` Lambda score → ALLOW/HALT verdict with DSSE Khipu receipt.
3. **53-drone fingerprint database** — curated from open sources.
4. **Swarm topology analysis** — Remote-ID broadcasts → connected-component clustering.
5. **Edge formula surface** — PAC-Bayes confidence, Kalman trajectory smoothing, Byzantine quorum.

**Honest posture**: Remote-ID/ADS-B/MAVLink are unauthenticated broadcasts. Every
decoded field is a *claim*, never ground truth. The verdicts reflect governance logic
over those claims, not cryptographic authenticity.

---

## 2. Architecture diagram

```
  HF Space: SZLHOLDINGS/killinchu  (port 7860)
  ┌──────────────────────────────────────────────────────────┐
  │  serve.py (FastAPI)                                      │
  │  ├── /                    SPA (Drone Intelligence UI)    │
  │  ├── /api/killinchu/v1/remote-id/decode  OpenDroneID     │
  │  ├── /api/killinchu/v1/ads-b/decode      ADS-B Mode-S    │
  │  ├── /api/killinchu/v1/mavlink/parse     MAVLink v1/v2   │
  │  ├── /api/killinchu/v1/drones/database   53 drones DB    │
  │  ├── /api/killinchu/v1/counter-uas/evaluate  Λ-gate      │
  │  ├── /api/killinchu/v1/swarm/topology    Clustering       │
  │  ├── /api/killinchu/v1/threats/active    Threat board     │
  │  ├── /api/killinchu/v1/receipt/emit      Khipu emit       │
  │  ├── /api/killinchu/v1/edge/*            Edge formulas    │
  │  └── /api/killinchu/healthz              Liveness         │
  │                                                          │
  │  Core modules:                                           │
  │  killinchu_protocols.py   Protocol decoders (start here) │
  │  killinchu_edge_formulas.py  PAC-Bayes, Kalman, quorum   │
  │  killinchu_kalman.py      Kalman filter implementation    │
  │  szl_dsse.py              DSSE receipt signing            │
  │  szl_be_hardening.py      Rate-limit, SQLite, logs        │
  └──────────────────────────────────────────────────────────┘
```

---

## 3. The counter-UAS Λ-gate (the core logic)

`POST /api/killinchu/v1/counter-uas/evaluate` is the main decision endpoint.
It fuses:

1. **Haversine geofence** — `_haversine_m(lat, lon, fence_lat, fence_lon)` in metres.
2. **13-axis Lambda score** — `_lambda_aggregate(axes)` via geometric mean of 13 scores.
3. **DSSE Khipu receipt** — every verdict mints a receipt via `_emit_receipt()` which
   either uses the real `szl_dsse` signer or emits an honest PLACEHOLDER.

The receipt chain is a local SHA-256 Merkle DAG (`_digest_node()`). Each receipt
links to its parent digest. The Khipu root is available at `/api/killinchu/v1/receipt/ledger`.

---

## 4. Running locally

```bash
# FULL clone
git clone https://github.com/szl-holdings/killinchu.git && cd killinchu

pip install fastapi uvicorn httpx cryptography pydantic numpy
# Optional real decoders:
pip install pyModeS pymavlink

PORT=7860 uvicorn serve:app --host 0.0.0.0 --port 7860 --reload
```

---

## 5. Endpoint map

```
GET  /                                 SPA
POST /api/killinchu/v1/remote-id/decode   OpenDroneID decode
POST /api/killinchu/v1/ads-b/decode       ADS-B Mode-S decode
POST /api/killinchu/v1/mavlink/parse      MAVLink parse
GET  /api/killinchu/v1/drones/database    53-drone DB
POST /api/killinchu/v1/counter-uas/evaluate  Λ-gate → ALLOW/HALT
GET  /api/killinchu/v1/swarm/topology     Swarm cluster detection
GET  /api/killinchu/v1/threats/active     Live threat board
POST /api/killinchu/v1/receipt/emit       Mint Khipu receipt
GET  /api/killinchu/v1/receipt/ledger     Khipu chain
POST /api/killinchu/v1/edge/verdict       PAC-Bayes + Kalman verdict
GET  /api/killinchu/v1/edge/quorum-status Byzantine quorum status
GET  /api/killinchu/v1/formulas/index     Wired formulas + Lean links
GET  /api/killinchu/healthz               Liveness
GET  /api/killinchu/v1/honest             Doctrine posture (749/14/163)
```

---

## 6. OTel hotfix — disabled

The `szl_otel` import in `serve.py` is **hard-disabled** with a comment:
```python
# HOTFIX 2026-06-01 Yachay: OTel middleware crash-looping the Space.
# Hard-disable szl_otel import. Real OTel ships in next clean PR.
def _szl_otel_setup(*a, **kw): pass
```
Do NOT re-enable this without first testing that the OTel middleware does not
crash-loop the Space. The crash was silent — the Space appeared healthy but
returned 500 on all routes.

---

## 7. HF Space deploy caveats

Same as a11oy: `hf-sync.yml` syncs README.md only.
Space: `SZLHOLDINGS/killinchu` (https://szlholdings-killinchu.hf.space).

---

## 8. Doctrine constants (LOCKED)

749/14/163 · `c7c0ba17` · Λ = Conjecture 1 · SLSA L1 honest.

---

## 9. Key module index

| Module | Purpose |
|---|---|
| `serve.py` | FastAPI app, all routes, Λ-gate logic |
| `killinchu_protocols.py` | Real Remote-ID, ADS-B, MAVLink decoders |
| `killinchu_edge_formulas.py` | PAC-Bayes, Kalman, Byzantine quorum |
| `killinchu_kalman.py` | Kalman filter (numpy) |
| `killinchu_fusion.py` | Sensor fusion |
| `szl_dsse.py` | DSSE signing (shared) |
| `szl_be_hardening.py` | Backend hardening (shared) |
| `build_drone_db.py` | Build/update the 53-drone JSON DB |

---

*Authored by Perplexity Computer Agent on behalf of Yachay (CTO).*
*Doctrine v11 LOCKED · 749/14/163 · Λ = Conjecture 1.*
*Signed-off-by: stephenlutar2-hash <stephenlutar2@gmail.com>*
