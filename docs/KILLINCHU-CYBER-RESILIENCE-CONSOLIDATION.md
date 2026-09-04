# Killinchu cyber-resilience consolidation

- Status: **ACCEPTED FOR IMPLEMENTATION**
- Effective date: **2026-09-04**
- Decision owner: **Stephen Lutar**
- Public product: **Killinchu — Cyber-Physical Resilience Command**
- Sole public Hugging Face runtime: **`SZLHOLDINGS/killinchu`**

## Decision

Killinchu is the single external product and public runtime for SZL Holdings'
defensive cyber-physical resilience work. The estate must not present Aegis,
Sentra, IMMUNE, Vessels, or counter-UAS as competing public products.

The consolidation is a product-boundary decision, not a request to flatten every
source repository into one unmaintainable codebase. Unique engines remain
versioned, testable modules with exact source provenance; Killinchu composes and
presents them through one source-bound runtime.

## Canonical taxonomy

| Name | Canonical role | External status |
|---|---|---|
| **Killinchu** | Product, operator experience, public API and deployment | **SOLE PUBLIC RUNTIME** |
| **Aegis** | Internal portfolio/vertical name for the complete resilience capability | Not a separate product or Space |
| **Sentra** | Defensive control-plane engine: event ingestion, detections, cases, approvals and allowlisted response | Capability plane inside Killinchu |
| **IMMUNE** | Agent/AI safety engine: admission, tripwires, signed authority and tamper-evident receipts | Capability plane inside Killinchu |
| **Vessels** | Maritime sensing, risk, sanctions screening and ownership analysis | Mission pack inside Killinchu |
| **Counter-UAS** | Airspace sensing, classification and governed response recommendations | Mission pack inside Killinchu |
| **A11oy** | Horizontal governed-AI command fabric and cross-product orchestration | Separate platform boundary |

Public naming must use descriptive plane names such as **Defend**, **Immune**,
**Maritime**, **Airspace**, and **Evidence**. `Sentra` and `Aegis` may remain
source identifiers or internal architecture labels, but they are not additional
front doors.

## Target product surface

| Route | Plane | Minimum contract before legacy retirement |
|---|---|---|
| `/resilience` | Aegis portfolio overview | One inventory and one truthful readiness summary |
| `/defend` and `/api/defend/*` | Sentra defensive control plane | Source-bound read API, deterministic case flow, no arbitrary command execution |
| `/immune` and `/api/immune/*` | IMMUNE admission and evidence | Signed authority, ledger verification, tripwire state and fail-closed readiness |
| `/vessels` and `/api/vessels/*` | Maritime mission pack | Existing Killinchu source, compatibility routes and source identity |
| `/airspace` | Counter-UAS mission pack | Existing Killinchu sensing and decision-support surface |
| `/evidence` | Shared receipts and provenance | Cross-plane receipt verification without secret disclosure |

Legacy routes may redirect to these same-origin paths for compatibility. They
must not iframe, reverse-proxy, or depend at runtime on the retired Spaces.

## Source architecture

The surviving product repository is `szl-holdings/killinchu`. Engine source is
preserved as follows:

- Sentra source: `szl-holdings/szl-defensive-control-plane` until imported as an
  exact-pinned package or vendored release.
- IMMUNE source: `szl-holdings/immune` until its Python/TypeScript contracts are
  imported as exact-pinned modules with parity tests.
- Vessels source: already captured in Killinchu and the transitional
  `szl-holdings/vertical-services` engine.
- Aegis assurance: a thin roadmap adapter; it has no authority to become a
  separate product runtime.

Source repositories may remain active component repositories. After a component
is fully consumed from Killinchu, its former product repository can be archived
with a migration notice; source history must not be destroyed merely to reduce
public-product sprawl.

## Hugging Face retirement gates

A legacy Space can be deleted only when all gates are true:

1. **Source captured** — every unique module and license is retained in GitHub or
   an immutable release artifact.
2. **Product captured** — the Killinchu route provides the useful workflow and
   does not merely link to the old Space.
3. **Evidence captured** — receipts, benchmarks, release hashes and historical
   provenance remain discoverable.
4. **Publisher removed** — no workflow, keep-list, catalog or factory can recreate
   the old Space.
5. **Replacement verified** — `SZLHOLDINGS/killinchu` is running, source-bound,
   and the replacement route passes its contract.
6. **No unique secret dependency** — retirement does not destroy the only copy of
   a required secret or signing identity.

Deletion is irreversible. Therefore the runtime migration and publisher removal
must land before the delete operation, and the delete operation must emit a
secret-free receipt naming the exact replacement source and route.

## Current retirement readiness

| Legacy Space | State | Required next action |
|---|---|---|
| `SZLHOLDINGS/vessels` | **REFERENCE_CLEANUP_REQUIRED** | Remove it from active keep-lists/catalogs/publishers, verify `/vessels`, then delete |
| `SZLHOLDINGS/aegis-assurance` | **DELETE_READY_AFTER_REFERENCE_CLEANUP** | Remove the roadmap adapter from Packet8/factory inventories, then delete if it exists |
| `SZLHOLDINGS/sentra` | **MIGRATION_REQUIRED** | Integrate the defensive-control-plane contract into Killinchu before deletion |
| `SZLHOLDINGS/immune` | **MIGRATION_REQUIRED** | Integrate admission, signed authority, HUKLLA and YAWAR/ledger contracts before deletion |
| `SZLHOLDINGS/immune-lattice` | **PARITY_AUDIT_REQUIRED** | Prove its unique Python runtime is captured by the active IMMUNE source and Killinchu |

## Safety and truth boundary

This consolidation remains defensive-only. It does not authorize intrusion,
arbitrary shell execution, credential access, civilian targeting or operations
outside an approved defensive scope. Simulated RANGE capabilities remain clearly
labeled simulation. Live provider connectors remain `UNAVAILABLE` until they are
implemented, configured and observed. A healthy endpoint proves reachability,
not operational or legal authorization.

## Completion definition

The work is complete only when:

- the SZLHOLDINGS organization presents one Killinchu public runtime for this
  family;
- all surviving capability planes are same-origin and source-bound;
- no active policy calls Sentra, IMMUNE, Vessels or Aegis a separate flagship;
- legacy Spaces are absent rather than merely renamed, after their gates close;
- GitHub component sources and immutable migration receipts remain available;
- Killinchu's title, README, API catalog and product route all describe the same
  cyber-physical resilience boundary.
