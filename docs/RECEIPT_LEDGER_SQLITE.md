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

The existing `GET /readyz`, `/api/killinchu/v1/readyz`, `/honest`, and
`/api/killinchu/v1/honest` routes read the same canonical ledger readiness
provider with recovery disabled and an explicit read-only adapter probe. A
missing or malformed provider fails closed
with HTTP 503. These reads do not provision, replay, append, or mint a receipt.
Readiness describes the configured ledger's software state; an HTTP 200 does
not establish production retention, authorization, or deployment qualification.

The readiness response identifies `ledger_role: CANONICAL_RECEIPT_LEDGER` and
exposes its full readiness envelope under `ledger`. The former root-level
`khipu_backend`, `khipu_depth`, `khipu_chain_ok`, and `khipu_first_break_seq`
fields now appear as `backend`, `depth`, `chain_ok`, and `first_break_seq` under
`backend_store_diagnostics`. They describe the separate backend hardening
store, which retains its independent chain gate. Its diagnostics always report
`provider_persistence: UNKNOWN` and `production_ready: false`; a working SQLite
diagnostic store does not make the canonical receipt ledger durable. Existing
browser consumers read the honesty labels or display the raw disclosure and
do not consume these former readiness fields. External readiness consumers
must use `ledger` for canonical storage status and the nested diagnostics only
for the backend store.

Canonical health, readiness, receipt-ledger, receipt-export, and the early
honesty/readiness aliases use `readiness(recover=False, read_only=True)`.
Read-only probes never trigger startup or replay, even when an external ledger
is unready. External adapters must accept `readiness(read_only=True)`; missing
passive capability returns unavailable without calling their writer probe.
The SQLite adapter opens `mode=ro`, begins a read transaction, and checks its
schema, identity, and complete hash chain. It does not acquire a writer lock.
The response identifies `readiness_probe: READ_ONLY`; this establishes readable
integrity only and does not promise that a later write can acquire a lock or
commit. Explicit startup/recovery and receipt writes retain the original writer
readiness probe and fail closed if writer-lock acquisition or append fails.
The SQLite adapter still reports local filesystem scope and production false.

The two engagement after-action GET/HEAD exports also use this passive provider
and export only existing closure/decision receipt references and ledger nodes.
They never mint an `after_action_export` receipt. Their v1 bundle keeps the
`export_receipt` object but now returns null `index`/`digest`, `signed: false`,
and `state: UNSIGNED_READ_ONLY`, with `receipt_minted: false` and
`export_read_only: true`. Existing signed receipt evidence remains in the bundle;
the export operation itself is unsigned. An unavailable ledger returns HTTP 503
with `NOT_VERIFIABLE_IN_THIS_RUNTIME` evidence sections; an absent track or
record still returns HTTP 404. The existing console downloads the JSON and
reads closure/truth-state fields; the offline verifier checks the existing
sections, receipt chain, and witness material. Neither consumes export-receipt
coordinates. External consumers expecting a newly minted export receipt must
handle the explicit null coordinates. Existing POST receipt operations retain
their writer/recovery behavior; this change adds no write endpoint.

```text
python -m pytest -q tests/test_killinchu_passive_get.py tests/test_killinchu_ledger_attribution.py tests/test_be_hardening.py tests/test_killinchu_ledger_runtime.py tests/test_killinchu_ledger_sqlite.py tests/test_killinchu_ledger_recovery.py tests/test_receipt_export_contract.py tests/test_roe_decisions_api.py tests/test_after_action_bundle.py
```

Tests use temporary stores, including separate processes for append and replay,
independent competing writers, corruption, missing-file recovery, writer lock
failure, idempotency and lost-acknowledgment recovery. These are local software
tests, not evidence of provider storage retention or cryptographic signatures.
