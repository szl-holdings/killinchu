# Vessels consolidation — maritime is a Killinchu capability plane

- Status: **CONSOLIDATED · LEGACY SPACE RETIREMENT IN PROGRESS**
- Effective date: **2026-09-04**
- Decision owner: **Stephen Lutar**
- Public product of record: **Killinchu — Cyber-Physical Resilience Command**
- Sole public Hugging Face runtime: **`SZLHOLDINGS/killinchu`**

## Decision

Vessels is not a standalone product or permanent public Space. It is the
**Maritime** mission pack inside Killinchu. Killinchu is the governed operator
surface for counter-UAS, maritime resilience, defensive security and shared
evidence.

This record supersedes the earlier “retain as a historical Space” treatment.
Historical source and evidence remain in GitHub and immutable receipts; the
legacy `SZLHOLDINGS/vessels` Space is to be deleted after active keep-lists,
catalogs and publishers are changed so no automation can recreate it.

See `KILLINCHU-CYBER-RESILIENCE-CONSOLIDATION.md` and the machine-readable
`killinchu-cyber-resilience-consolidation.v1.json` contract.

## Capability map

| Vessels capability | Canonical Killinchu home | Truth state |
|---|---|---|
| AIS sensing and replay | Maritime plane | Live or replay only when explicitly observed and labeled |
| Dark-vessel detection | `killinchu_maritime_risk.py` | Source implemented; runtime state comes from the live route |
| Voyage analytics | `killinchu_maritime_intel.py` | Source implemented; no fabricated live feed |
| Fleet view | `killinchu_fleet_vessels.py` and `killinchu_maritime_globe.py` | Source implemented |
| Sanctions screening | `killinchu_vessels_screening.py` | Exact list matching against operator-supplied lists; no live sanctions feed claimed |
| Ownership graph | `killinchu_vessels_screening.py` | Declared ownership is `REPORTED`; graph computation is deterministic |
| Transitional API engine | `szl-holdings/vertical-services` under `/vessels/*` | Component engine, not a second product surface |

## Retirement gates for `SZLHOLDINGS/vessels`

Current state: **REFERENCE_CLEANUP_REQUIRED**.

The legacy Space is deletion-ready only after all of the following are proven:

1. Vessels is removed from every active Hugging Face keep-list and flagship
   inventory.
2. No publication workflow can create or update `SZLHOLDINGS/vessels` as a
   product runtime.
3. Atlas, website and in-product links resolve to Killinchu's Maritime plane.
4. The replacement `/vessels` route is reachable and bound to the exact
   Killinchu source revision.
5. Unique source, licensing, release hashes and evidence remain preserved.
6. The delete operation writes a secret-free receipt naming the replacement
   Space and source revision.

Pausing or making the Space private is not the final state because an
organization administrator will still see it. After the gates close, deletion
is the intended terminal state and recreation is forbidden.

## Honest boundaries

- No public route may claim a live AIS, OFAC, EU or UN sanctions feed unless a
  current connector observation proves it.
- A `200` response proves reachability, not readiness, data freshness or legal
  clearance.
- Screening and ownership findings are advisory; they are not sanctions,
  regulatory or operational clearance.
- Historical source is preserved in GitHub. The obsolete public application
  surface is not preserved merely for nostalgia.

References: `szl-holdings/.github#606` and the Killinchu cyber-resilience
consolidation contract.
