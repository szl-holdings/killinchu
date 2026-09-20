# Opt-in local receipt persistence

The default remains `EPHEMERAL`; shipping this adapter does not activate it.
`killinchu_ledger_sqlite.py` provides a real standard-library SQLite store for
single-host process-restart recovery. It permanently reports
`production_ready: false` and `persistence_scope: LOCAL_FILESYSTEM`.
`DURABLE_EXTERNAL` is the existing runtime adapter mode, not proof of a
provider-persistent volume or protection against container replacement.

## Provisioning and activation boundary

First select and verify storage, ownership, access controls, capacity, backup
and restore procedures. Do not use a container's disposable filesystem for a
production retention claim. Do not activate this adapter in a running Space
until its storage lifecycle and migration of any existing receipts are handled.
This release does not provision volumes, change Space variables, migrate an
existing in-memory ledger, or introduce credentials.

For an isolated local test, create a private directory, then run:

```text
python -m killinchu_ledger_sqlite init ABSOLUTE_PATH_TO_NEW_LEDGER.sqlite3
```

The parent directory must exist. Initialization exclusively creates a new file
and refuses every existing target. A failed initialization leaves its partial
file for inspection, never automatically deletes or recreates it. The output
contains a non-secret `store_id`. Explicit runtime configuration is:

```text
KILLINCHU_LEDGER_MODE=DURABLE_EXTERNAL
KILLINCHU_LEDGER_ADAPTER=killinchu_ledger_sqlite:from_environment
KILLINCHU_LEDGER_SQLITE_PATH=ABSOLUTE_PATH_TO_EXISTING_LEDGER.sqlite3
KILLINCHU_LEDGER_SQLITE_ID=EXACT_STORE_ID_FROM_PROVISIONING
```

All four settings are required for this adapter. No relative paths, in-memory
fallback, implicit initialization, schema repair, or readiness promotion flag.
Secure the parent directory and OS account: POSIX file mode is requested as
0600; Windows ACLs and provider-volume permissions remain operator obligations.

## Integrity and concurrency contract

Each append uses `BEGIN IMMEDIATE`, checks the existing full chain and head,
then commits both the new receipt and head/count metadata atomically. Competing
writers from a stale head fail rather than overwriting or forking it. Retry an
ambiguous acknowledgment by replaying; an identical full stored node is
idempotent, but a matching digest with changed DSSE metadata is rejected.

Replay checks the SQLite structure, exact schema and configured store identity,
canonical JSON, strict integer indices, parent continuity, existing receipt
digest format, and metadata head/count. Missing, incompatible, locked, or
corrupt storage fails closed. Readiness never recreates a missing database.
Runtime readiness failures require replay before recovery; failed appends never
expose an unconfirmed node through the in-memory projection.

The adapter uses rollback journaling and full synchronization. SQLite's storage
guarantees still depend on the operating system and filesystem honoring locks
and synchronization. See [SQLite atomic commits](https://www.sqlite.org/atomiccommit.html)
and [transaction semantics](https://www.sqlite.org/lang_transaction.html).

## What these checks do not establish

- No DSSE signer authentication, independent approval, or remote attestation.
- No resistance to a privileged writer coherently rewriting the entire store
  or restoring an older valid snapshot with the same identity. That needs an
  independently retained, authenticated checkpoint/anchor.
- No provider rebuild/replacement persistence, replication, HA, power-loss
  experiment, production capacity benchmark, or completed backup/restore drill.
- No network filesystem or multi-host deployment support claim. Verification
  scans the full chain and is linear in ledger size; this is not a high-volume
  replacement for an externally operated database. A node is capped at 1 MiB.
- Existing legacy adapters keep their prior readiness behavior, explicitly
  labelled `LEGACY_ADAPTER_CONTRACT`; this is not new provider evidence.

Back up through SQLite's supported backup facilities or a quiesced, consistent
filesystem snapshot, never by copying a changing database alone. Restore into
an isolated environment and compare receipt count/root and pinned store ID
against separately retained evidence before considering activation. Do not
reset or reprovision the configured path to hide a missing or corrupt store.

## Verification

```text
python -m pytest -q tests/test_killinchu_ledger_runtime.py tests/test_killinchu_ledger_sqlite.py tests/test_receipt_export_contract.py
```

Tests use temporary stores, including separate processes for append and replay,
independent competing writers, corruption, missing-file recovery, writer lock
failure, idempotency and lost-acknowledgment recovery. These are local software
tests, not evidence of provider storage retention or cryptographic signatures.
