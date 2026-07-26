# Killinchu operator-mutation security proof

Date: 2026-07-25
Canonical pull request: `#267`

## Closed mutation paths

The durable watchlist create/update/delete routes, manual crawler trigger, and
live-refresh route now use the repository's governed-compute bearer authority:

- `POST /api/killinchu/live`
- `POST /api/killinchu/crawl/run`
- `POST /api/killinchu/watchlists`
- `PUT /api/killinchu/watchlists/{wid}`
- `DELETE /api/killinchu/watchlists/{wid}`

Authority fails closed when the configured SHA-256 digest is absent or
malformed. Every accepted mutation also requires a bounded
`Idempotency-Key`. The initial claim is an atomic insert-on-conflict operation,
so concurrent processes cannot both reserve the same key.

The SQLite/Postgres schema stores only:

- the hash of the idempotency key;
- a non-secret actor fingerprint derived from the configured token digest;
- canonical request and result digests;
- the exact replay response and canonical mutation receipt.

Within each supported database engine, the domain mutation and
`receipt_pending` replay material commit in one transaction. A completed
request replays the stored response. Reusing a key with a different operation,
actor, or body returns 409.

## Canonical receipt integration

The host injects its existing Khipu/DSSE receipt emitter into backend
registration. Successful operator mutations therefore use the canonical host
hash-chain and envelope path. The response reports `signed: true` only when a
real configured host key signed the envelope. An isolated backend with no
injected emitter uses the explicitly labelled `UNSIGNED_NO_EMITTER` fallback.

The Khipu append and database commit remain separate systems. The durable
state machine is:

`in_progress -> receipt_pending -> receipt_emitting -> completed`

Operators can inspect and reconcile by hashed key:

- `GET /api/killinchu/operator-mutations/{key_digest}`
- `POST /api/killinchu/operator-mutations/{key_digest}/reconcile`

A `receipt_pending` row can safely resume receipt emission without replaying
the domain mutation. An ambiguous `receipt_emitting` row cannot retry unless an
operator explicitly confirms that the canonical receipt is absent. An
uncertain domain-side-effect row can only be closed after explicit inspection;
reconciliation never replays the domain mutation.

## Verification

- Real Postgres 16 run of `tests/test_operator_mutation_security.py`:
  13 passed.
- Local no-Postgres run of the same file: 12 passed, 1 skipped.
- Focused security, scheduler, crawler-honesty, watchlist, Wire-D, canonical
  receipt, and DSSE regression set: 64 passed, 2 skipped.
- Full repository suite: 692 passed, 11 failed, 5 skipped. The 11 failures match
  the audited baseline categories outside this patch: eight Windows
  default-encoding failures in `tests/test_corpus_autosync_notify.py`, one
  Windows SQLite temporary-file cleanup failure in
  `test_be_hardening.py::test_rate_limit_enforced`, and two full-suite
  OSINT route-shape/import-order failures in `test_killinchu_archive.py` and
  `test_osint.py`.
- Python compile check passed for `killinchu_backend.py` and `serve.py`.
- Workflow YAML parsing and Git whitespace/error checks passed.

The contract tests generate OpenAPI and assert that all seven protected
operations use `OperatorBearer`, while the watchlist read route remains public.
SQLite and real-Postgres tests cover same-key concurrency, exact replay,
transaction rollback, post-commit crash recovery, ambiguous receipt emission,
and explicit reconciliation without domain remutation.

## Honest residual boundary

The host Khipu DAG is currently process memory and resets when the host process
restarts. Its append cannot share a transaction with SQLite or Postgres.
Accordingly, this proof does not claim cross-system atomicity. An ambiguous
append/finalization outcome remains fail-closed in `receipt_emitting` until an
operator independently confirms receipt absence before authorizing a retry.
