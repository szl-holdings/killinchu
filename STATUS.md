# STATUS.md — killinchu (Defense / Counter-UAS)

**Updated:** 2026-06-02
**Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17**

> **Doctrine v12 (ADDITIVE, 2026-06-01) — `781 / 14 / 194`.**
> v12 = v11 + PuriqFormulaLean scaffold module. **Same 14 unique axioms**
> (identical names). New sorries are clearly-marked roadmap
> (`SORRY_PURIQ_OPEN`). **Λ remains Conjecture 1.** SLSA L1 (honest). Quechua =
> brand only. **`yuyay_v3` replay hash `bacf5443…631fc5` UNCHANGED.** Monotone:
> declarations grew (749→781), sorries grew (163→194), axioms unchanged (14→14),
> so every v11 citation stays valid. Measured by `lake build` on lutar-lean PR
> #142 head `86d9fb2c` (CI run 26758112448, build green). v11 numbers below
> remain the LOCKED reference snapshot.

HF Space: <https://huggingface.co/spaces/SZLHOLDINGS/killinchu>

---

## What's Live

- **HF Space** — killinchu is deployed and operational on Hugging Face Spaces
- **`/healthz`** — returns Doctrine v11 numbers and service status
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

## What's Deprecated

- **Earlier track-decoder reference** — an earlier track-decoder reference predates killinchu; its decoder architecture is preserved but it is not the primary defense flagship.

---

*Co-Authored-By: Perplexity Computer Agent*
*Doctrine v11 — 749/14/163 — c7c0ba17*
