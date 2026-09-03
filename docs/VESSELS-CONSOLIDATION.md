# Vessels consolidation — maritime is a Killinchu vertical

- Status: **CONSOLIDATED** (2026-09-03)
- Decision owner: Stephen Lutar
- Engine source of record: [szl-holdings/vertical-services](https://github.com/szl-holdings/vertical-services) (`vessels` maritime-risk service)
- Public surface of record: this repository and the [SZLHOLDINGS/killinchu Space](https://huggingface.co/spaces/SZLHOLDINGS/killinchu)

## Decision

The standalone Vessels vertical is consolidated into **Killinchu**, the governed Counter-UAS & Maritime C2 console — one field tool for air and sea. The prior standalone `szl-holdings/vessels` repository no longer exists; the vessels maritime-risk engine lives on in `vertical-services`, and its public face is this console.

## Capability map

| Vessels capability | Home | State |
|---|---|---|
| Sanctions screening | Killinchu — Maritime screening | LIVE on sample / replay AIS data (demonstration, not a live feed) |
| Dark-vessel detection | Killinchu — Maritime screening | LIVE on sample / replay AIS data (same honest label) |
| Ownership graph analysis | Killinchu roadmap | ROADMAP — not claimed live until it is |
| Voyage analytics | Killinchu roadmap | ROADMAP — not claimed live until it is |

## Honest boundaries

- Sample-data demonstrations stay labeled as demonstrations. No live AIS feed is claimed.
- The staged replacement card for the `SZLHOLDINGS/vessels` Space lives at `docs/hf-cards/SZLHOLDINGS-vessels.README.md` and applies via the HF UI or a write-scoped HF token (the session OAuth credential lacks org-Space write scope). The Space is retained as a historical record, not deleted.
- `vertical-services` remains the deployable engine source; this document governs the public narrative, not the code path.

References szl-holdings/.github#606 (public-surface rollout).
