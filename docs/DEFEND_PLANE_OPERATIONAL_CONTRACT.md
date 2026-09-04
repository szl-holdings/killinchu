# Killinchu Defend Plane Operational Contract

## Product boundary

Killinchu is the sole public cyber-physical resilience product. Aegis is the portfolio name and Sentra is the defensive-control-plane capability source. Neither is a separate public front door after migration.

## Public routes

| Route | Contract |
|---|---|
| `/resilience` | Same-origin resilience overview |
| `/defend` | Defensive event, case, proposal, approval, rehearsal, rollback and receipt workspace |
| `/aegis` | Compatibility alias to `/defend` |
| `/sentra` | Compatibility alias to `/defend` |
| `/api/defend/status` | Machine-readable authority and readiness boundary |
| `/api/defend/source` | Exact source repository and revision binding |

## Operational truth

The public runtime performs real validation, deterministic detection, case formation, bounded proposal construction, independent human approval, simulation-only containment rehearsal, append-only receipt chaining and receipt verification. It does not execute arbitrary commands or operate an external system.

A production connector can be admitted only through a separate authenticated private control plane with fixed action schemas, tenant and asset authorization, dry-run support, rollback evidence, durable exactly-once semantics and independent post-action verification.

## Source authority

The capability contract is source-bound to `szl-holdings/szl-defensive-control-plane` at the revision returned by `/api/defend/source`. The integrated public module is an explicit bounded port rather than a runtime dependency on the former Sentra Space.

## Retirement rule

`SZLHOLDINGS/sentra` may be deleted only after the merged Killinchu revision is live and all of the following pass:

1. `/defend` returns its dedicated HTML surface.
2. `/api/defend/status` reports Killinchu as public product, Defend as capability plane, human approval required and effectors disabled.
3. `/api/defend/source` reports the exact source repository and a 40-character revision.
4. The old Sentra Space is snapshotted and hashed.
5. Active publishers cannot recreate the old Space.
6. A secret-free retirement receipt names the replacement routes and source revisions.
