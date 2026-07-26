# STATUS.md — killinchu (Defense / Counter-UAS)

**Updated:** 2026-07-26
**Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17**

HF Space: <https://huggingface.co/spaces/SZLHOLDINGS/killinchu>

---

## What's Live

- **HF Space** — killinchu is deployed and operational on Hugging Face Spaces
- **`/api/killinchu/healthz`** — returns service liveness
- **`/api/build-info`** — reports `OBSERVED` only for a valid 40-hex
  `SZL_GIT_SHA`; the source-bound deploy verifies it against the exact GitHub
  commit before declaring success
- **`/console`** — existing Killinchu Edge Verdict Console
- **`/code` and `/chat`** — explicit HTTP 302 compatibility aliases to
  `/console`, not separate products
- **`/sign`** — Wire D DSSE signing endpoint
- **FAA Remote ID decoder** — live
- **ADS-B Mode-S decoder** — live
- **MAVLink decoder** — live
- **STANAG 4609 decoder** — live
- **Geofence + policy scoring** — telemetry scored as claim against geofence polygons; Λ-receipt emitted
- **`/viz/*`** — Map panel SPA with live telemetry feed

## What's Experimental

- **STANAG 4609 full-frame decode** — partial implementation; metadata extraction live, full video analytics experimental
- **Adaptive geofence updates** — geofence polygons currently static; dynamic update mechanism under development

## Evidence Boundaries

- **`/.well-known/szl-source.json`** — historical unsigned structural snapshot
  captured 2026-07-16. It is preserved evidence, not proof of the current
  running source revision; `/api/build-info` is the runtime identity probe.

## What's Deprecated

- **Earlier track-decoder reference** — an earlier track-decoder reference predates killinchu; its decoder architecture is preserved but it is not the primary defense flagship.

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
