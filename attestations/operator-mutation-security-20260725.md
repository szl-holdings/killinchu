# Killinchu operator-mutation security proof

Date: 2026-07-25
Baseline: `c0e06d8c3c1b3a9c2cf550451132bd8c96ece1f3`

## Closed P0 path

The durable watchlist create/update/delete routes and manual crawler trigger now
use the repository's governed-compute bearer authority. Authority fails closed
when the configured SHA-256 digest is absent or malformed. Every accepted
mutation also requires a bounded `Idempotency-Key`.

The SQLite/Postgres schema stores only:

- the hash of the idempotency key;
- a non-secret actor fingerprint derived from the configured token digest;
- canonical request and result digests;
- the exact completed response and deterministic mutation receipt.

The reservation is durable before side effects. A completed request replays the
stored response. Reusing a key with a different operation, actor, or body
returns 409. An interrupted or failed reservation stays closed pending operator
reconciliation instead of risking a duplicate mutation.

## Verification

- `tests/test_operator_mutation_security.py`: 5 passed.
- Scheduler, crawler-honesty, watchlist integration, and security tests:
  30 passed.
- Wire-D authority, ntfy edge, and watchlist recovery regression tests:
  18 passed.
- Full repository suite before the final duplicate CI-placement assertion:
  684 passed, 11 failed, 4 skipped. The 11 failures match the audited baseline
  failure count and are outside this patch: eight Windows default-encoding
  failures in the corpus notification tests, one Windows SQLite temporary-file
  cleanup failure, and two OSINT test-double route-shape failures caused by
  full-suite import ordering.
- Python compile check passed for `killinchu_backend.py` and
  `szl_provenance.py`.
- Git whitespace/error check passed.

The security contract test also generates OpenAPI and asserts that all four
protected operations remain registered with `OperatorBearer`, while the
watchlist read route remains public.

## Honest residual boundary

Mutation receipts are deterministic SHA-256 evidence and are explicitly marked
`signed: false` / `signature_state: UNSIGNED`. They are not yet appended to the
host Khipu DAG or signed with the host DSSE key because the canonical host
receipt emitter is currently defined after backend registration. A later
architectural change must inject that emitter into `register()` before these
receipts can truthfully claim signer identity.

The write reservation is at-most-once and fail-closed. The current store API
does not wrap each multi-statement watchlist mutation and completion record in
one cross-engine transaction. A process loss can therefore leave a partial
mutation plus a closed `failed` reservation that requires operator
reconciliation; automatic retry will not duplicate it.
