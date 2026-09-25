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
filesystem snapshot, never by copying a changing database alone. The commands
below use SQLite's backup API. Do not reset or reprovision the configured path
to hide a missing or corrupt store.

## Verified local backup and restore

All paths below are placeholders for absolute paths. The destination must be
new and its parent directory must exist. This is a local maintenance operation:
its read transaction can delay other writers in rollback-journal mode.

```text
python -m killinchu_ledger_sqlite backup SOURCE_DB NEW_SNAPSHOT_DB --store-id PINNED_UUID
```

On success only, stdout contains a checkpoint with the store ID, node count,
head, and SHA-256 over every complete canonical node, including DSSE metadata.
Save that JSON as `EXPECTED_CHECKPOINT_JSON` and retain it separately from the
snapshot. It is explicitly `UNSIGNED_LOCAL_CHECKPOINT`: it is not a signature,
independent authorization, or an authenticated latest-head anchor. A checkpoint
supplied by the same untrusted party as a snapshot does not establish trust.

```text
python -m killinchu_ledger_sqlite verify SNAPSHOT_DB --expected-checkpoint EXPECTED_CHECKPOINT_JSON
python -m killinchu_ledger_sqlite restore SNAPSHOT_DB NEW_RESTORED_DB --expected-checkpoint EXPECTED_CHECKPOINT_JSON
```

Verification checks the schema, identity, chain and full-node content against
the supplied checkpoint. Restore performs this comparison before creating a
target, then uses the backup API, closes and reopens the destination, and
verifies it again. It preserves the store identity and does not activate or
replace the configured runtime path. Existing targets, including aliases to
the source, are refused. Source files are opened read-only without creation.

Backup and restore accept `--timeout SECONDS` (default 30, maximum 300). The
copy's progress callback bounds SQLite's internal busy/locked retry loop;
ordinary replay/hash scans and OS I/O are not a hard real-time deadline. An
expired copy budget or failed verification exits nonzero without a success
checkpoint. A failed operation can leave its newly created partial target for
inspection; retries must use a new path, never overwrite that partial file.

The checkpoint binds the entire node, not just the receipt hash, so changing
DSSE metadata is detected against a retained checkpoint even though it is not
part of the existing receipt hash. Its content hash is SHA-256 initialized with
ASCII `szl.killinchu.sqlite-checkpoint/v1` followed by a zero byte, then for each
node an unsigned 8-byte big-endian UTF-8 length and its existing sorted-key,
default-spacing canonical JSON bytes. Empty stores hash the domain prefix only.

Run restore drills into an isolated path and retain their evidence separately.
These tools prove local content matching and replay only: they do not establish
off-host retention, checkpoint freshness/authenticity, provider-volume survival,
or production readiness. Do not promote a restored file into service until
storage lifecycle, authorization, access controls, and migration are resolved.

## Verification

```text
python -m pytest -q tests/test_killinchu_ledger_runtime.py tests/test_killinchu_ledger_sqlite.py tests/test_killinchu_ledger_recovery.py tests/test_receipt_export_contract.py
```

Tests use temporary stores, including separate processes for append and replay,
independent competing writers, corruption, missing-file recovery, writer lock
failure, idempotency and lost-acknowledgment recovery. These are local software
tests, not evidence of provider storage retention or cryptographic signatures.
