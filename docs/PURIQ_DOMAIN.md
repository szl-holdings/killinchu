# PurIQ Domain — Doctrine Capability Charter

**Status:** DECLARED · **Date:** 2026-09-03 · **Doctrine:** v11 LOCKED · **Truth labels:** MEASURED / REPORTED / MODELED

## Declaration

PurIQ is a **horizontal doctrine capability** of the SZL estate: the formula corpus and its fail-closed Yuyay-13 governance gate. It is **not a product vertical** and is never contained inside one. Verticals and organs **consume** PurIQ; they do not embed it.

This charter formalizes what the code already reflects: PurIQ content has lived in the killinchu corpus since the corpus was assembled, hatun-mcp runs its tools under PURIQ governance, and puriq-live executes the corpus against live public signals.

## Canonical hosting

| Host | Role |
|---|---|
| `szl-holdings/killinchu` — `corpus/` | Canonical corpus home: PurIQ doctrine docs and formula corpus |
| `szl-holdings/puriq-live` | Live execution surface — the SZL formula corpus against live public signals |

## Corpus artifacts in this repository (MEASURED)

| Artifact | Role |
|---|---|
| `corpus/doctrine/docs-site__docs__doctrine__puriq.md` (7.9 KB) | PurIQ doctrine document |
| `corpus/doctrine/docs-site__docs__doctrine__v11-v12.md` (6.6 KB) | Doctrine v11→v12 lineage including PurIQ governance |
| `corpus/formulas/a11oy__szl_puriq_formulas.py` (31.2 KB) | PurIQ formula corpus (executable) |
| `corpus/formulas/a11oy__a11oy_v4_formulas.py` (61.6 KB) | Formula family the corpus sits within |
| `corpus/formulas/a11oy__gates_manifest.json` (53.5 KB) | Gate manifest (Yuyay-13 lineage) |
| `szl_cuas_formulas.py` (54.9 KB) | Counter-UAS formulas governed under the same gate family |

## Known consumers (REPORTED)

- **a11oy** — governed execution fabric; the PurIQ gate family governs its admission decisions
- **hatun-mcp** — 16 SZL tools under PURIQ governance (Yuyay-13 gate, Khipu receipts, DSSE-signed)
- **killinchu** — organs evaluate under the shared gate family
- **puriq-live** — executes the corpus against live public signals (symmetric vs Egyptian Λ, maxAgg counterexample, fail-closed Yuyay-13)
- **David Leads** — PLANNED: Decision Trace evidence-ranked queue to emit PurIQ-governed receipts (see the integration spec filed on `szl-holdings/a11oy`)

## The rule: consumed, not contained

No product vertical embeds PurIQ as an internal subsystem. A vertical that needs governed scoring **cites a PurIQ receipt** (Yuyay-13-gated, hash-chained) rather than re-implementing or absorbing the corpus. Shared capabilities consolidate into the substrate/trust plane; product verticals consolidate into flagships. PurIQ belongs to the first bucket.

## Retired artifacts

- `SZLHOLDINGS/puriq-markets` (Hugging Face Space) — already deleted. No orphaned PurIQ artifacts remain.

## Provenance

- Charter declared 2026-09-03 by betterwithage via connector.
- Artifact inventory measured from the killinchu Space file listing at commit `fa81186`.
- Vessels domain charter (same pattern): `docs/VESSELS_DOMAIN.md`, commit `985b8a30`.
- Λ = Conjecture 1 (advisory). Nothing here claims a proven Λ.
