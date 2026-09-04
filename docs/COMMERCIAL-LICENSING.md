# Killinchu commercial licensing

- Status: **OPEN FOR PILOTS** (2026-09-03)
- Contact: stephen@szlholdings.com
- Scope of this document: data, licensing, and support for the Killinchu public corpus and consoles. It does not sell, license, or authorize any weapon, effector, or kinetic capability — see `LEGAL_BOUNDARIES.md`.

## What is free and stays free

- The public Killinchu console: synthetic / replay demonstration tracks, honest labels, signed receipts.
- The public OSINT corpus on Hugging Face, as published, under its posted license.
- Public documentation, schemas, and the receipt-verification path.

## What the commercial tier adds

| Offering | What it is | State |
|---|---|---|
| Enriched corpus feed | Scheduled, signed updates to the OSINT corpus with provenance receipts per batch | PILOT — cadence and scope agreed per engagement |
| Commercial-use license | Terms for embedding the corpus and derived screeners in a product or service | PILOT |
| Advisory screening integration | Wiring the exact-match / normalized-name advisory screening flow (UN SC 1718 designated-vessel evidence via OpenSanctions) into your systems | PILOT — advisory only, never regulatory clearance |
| Support & verification review | Receipt-chain review, deployment walkthrough, evidence-pack export | PILOT |

## Hard boundaries (non-negotiable)

- Screening output is advisory. `NO_EXACT_MATCH` is not sanctions clearance, and no output is a legal determination.
- `requires_human_approval=true` and `automation_authority=NONE` are architectural, not marketing. A human with authority makes every consequential decision.
- No sale, license, or support for effectors, targeting, or kinetic use. Inquiries of that kind are declined.
- Export-control and sanctions counsel review applies to every engagement (ITAR/EAR and equivalent regimes).
- Where a feed depends on an upstream license or credential, that dependency is disclosed before signature, not after.

## How a pilot starts

1. Email stephen@szlholdings.com with your use case and jurisdiction.
2. Receive a fixed-scope pilot letter: data included, cadence, boundaries, and the measurable acceptance criteria in writing up front.
3. Run the pilot against your own workflows; every batch carries a signed receipt you can verify offline.

References szl-holdings/.github#606. Honest by design: if a capability is not listed here as live, it is not claimed.
