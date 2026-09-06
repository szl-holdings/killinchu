# Killinchu Defend — durable-state production boundary

Status: **source implemented in part; deployed production durability is NOT VERIFIED**  
Parent gate: `#399`  
Seam decision: `#401`, corrected by its provider-topology note dated 2026-09-06  
Implementation anchors: `#410`, `#422`

## 1. Authority and honesty boundary

This document defines how the public, non-effecting Killinchu Defend plane may
cross from explicit demo persistence into a production-grade durable store. It
does not declare a database, backup, restore, or deployed Space production-ready.
That state remains false until one exact protected source revision produces live,
immutable evidence for every gate below.

Public effectors remain disabled. Persistence does not grant command execution,
third-party write authority, caller-selected destinations, or a way around the
existing approval and effector guards.

## 2. Deployment topology

### Demo and local mode

SQLite remains supported only for tests, local development, and explicitly
labelled demo mode. Every readiness response in that mode must say that the
store is not production durable. A local SQLite file, an ephemeral container
filesystem, or a Hugging Face storage mount is never represented as the
production PostgreSQL service.

### Production mode

Production uses **external managed PostgreSQL 16 or newer** through the existing
`DATABASE_URL` seam. The database is outside the Hugging Face application
container and must provide managed durable volumes, backups, point-in-time
recovery or equivalent restore capability, TLS, credential rotation, and an
operator-owned availability boundary.

The earlier proposal to run a PostgreSQL sidecar with a Kubernetes
`PersistentVolumeClaim` inside a Hugging Face Space is rejected as an
unverified provider assumption. A Docker Space exposes the application
container; the public provider contract does not establish a user-managed
sidecar/PVC control plane. Optional mounted storage is not treated as a
PostgreSQL volume and does not satisfy this gate.

The exact deployed Space must prove one provider-supported connection path:

1. a TLS-verified PostgreSQL connection supported by the runtime's outbound
   network policy; or
2. an HTTPS database gateway/data API that preserves the required transaction,
   isolation, identity, and error semantics.

Source configuration alone is insufficient. A direct database endpoint is not
accepted until live connectivity, certificate verification, transaction
behavior, failure behavior, and source revision are recorded in one readiness
receipt.

## 3. Connection and transaction contract

The production engine keeps these bounded settings:

| Control | Required value |
|---|---:|
| `pool_size` | 5 |
| `max_overflow` | 5 |
| `pool_timeout` | 30 seconds |
| `pool_recycle` | 1,800 seconds |
| read isolation | `REPEATABLE READ` |
| approval and receipt-write isolation | `SERIALIZABLE` |

A connection pool must not grow without a reviewed change. Approval persistence,
the prior-receipt hash read, the domain mutation, and durable receipt replay
material must retain the transactional guarantees already introduced by `#422`.
Retries are bounded and must not convert an unknown commit outcome into a second
mutation.

## 4. Schema ownership

Alembic owns the production schema. Every migration is committed, numbered, and
immutable after merge. Runtime code must not issue ad-hoc schema changes.
Startup and `/api/defend/readyz` compare the code Alembic head with the database
head and refuse service on drift.

A migration that creates a table also owns its constraints, indexes, tenant key,
and rollback statement. Destructive migrations require a separate reviewed data
migration, backup proof, rollback rehearsal, and explicit operator approval.

## 5. Idempotency

Every state-changing route requires `Idempotency-Key`.

The durable idempotency record contains:

- tenant and immutable principal identity;
- the key;
- a canonical request digest;
- terminal response status and response body;
- creation and expiry timestamps;
- the receipt-chain event identity.

The key is unique within its tenant and route boundary. A replay with the same
canonical request returns the stored terminal result without re-executing. A
replay with different request bytes is rejected and audited. The default expiry
is 24 hours. Purging expired records is bounded, observable, and cannot delete a
receipt-chain event.

## 6. Readiness contract

Production `/api/defend/readyz` returns `503` unless all of the following are
true for the same source revision and tenant-neutral probe transaction:

1. `DATABASE_URL` resolves through the approved provider connection path;
2. TLS and server identity verification succeed;
3. a bounded write/read/delete probe commits;
4. connection-pool acquisition stays inside the timeout;
5. the database Alembic head equals the source Alembic head;
6. the latest `BACKUP_COMMITTED` event is within 36 hours;
7. receipt-chain verification succeeds through the latest durable event;
8. required database and signing credentials have owner and rotation metadata.

The response never exposes a connection string, hostname containing credentials,
token, certificate private key, or raw provider error. It reports typed states
and a receipt identifier. Demo mode may be ready for demonstration while
explicitly reporting `durable: false`.

## 7. Backup and restore

Backups are produced by the managed database service or a bounded `pg_dump`
worker outside the request path. The backup object is stored in operator-owned
object storage, encrypted in transit and at rest, and identified by SHA-256.
Only metadata is appended as `BACKUP_COMMITTED`: backup identity, digest,
source revision, database schema revision, start/completion times, and retention
class. Credentials and database contents are never written into the receipt.

At least monthly, automation restores the newest eligible backup into an
isolated scratch database, migrates only when the recovery procedure requires
it, and runs the full receipt-chain verifier. The immutable rehearsal receipt
records:

- measured RPO, target no more than 24 hours;
- measured RTO, target no more than 1 hour;
- restored Alembic revision;
- restored receipt-chain validity;
- backup digest and exact protected source revision;
- cleanup result for the scratch environment.

No production-complete claim is allowed until one successful restore rehearsal
has been witnessed after the final deployment topology is selected.

## 8. Failure and recovery behavior

Database unavailability, TLS failure, migration drift, stale backup evidence,
pool exhaustion, serialization exhaustion, or unknown transaction outcome all
fail closed. The public plane may continue to serve non-mutating explanatory
content, but state-changing Defend routes and production readiness remain
disabled.

Rollback means restoring the previously attested application image and applying
the migration-specific rollback or forward-repair procedure that was rehearsed.
It never means pointing a newer binary at an older unknown schema.

## 9. Mapping to `#399`

| `#399` requirement | Binding in this document |
|---|---|
| durable provider or verified persistent volume | §2: external managed PostgreSQL; no unverified Space sidecar/PVC |
| SQLite only for local tests/demo | §2 demo boundary |
| migrations, pool, isolation, idempotency, concurrency | §§3–5 |
| backup/restore, RPO/RTO, receipt validity | §7 |
| readiness fails when durability is absent | §6 and §8 |
| secret ownership and rotation | §6, plus the production secrets inventory |
| exact source and immutable evidence | §§1, 6, and 7 |

## 10. Remaining proof before closure

Source contracts and injected-connection tests are necessary but not sufficient.
The durable-state portion of `#399` remains open until a selected database
provider, exact deployed Space revision, live connection, migration, backup,
restore, rotation, concurrency, and readiness receipt are all verified. Until
then the truthful state is:

```text
production_durable_state: NOT_VERIFIED
demo_sqlite: AVAILABLE_BUT_NOT_PRODUCTION
public_effectors: DISABLED
```
