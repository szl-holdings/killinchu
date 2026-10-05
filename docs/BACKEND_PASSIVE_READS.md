# Passive backend observations

GET and explicit HEAD on `/api/killinchu/v1/assurance/attest` export current
backend-chain diagnostics. The response is unsigned: `dsse: null`,
`signed: false`, `receipt_minted: false`, `export_read_only: true`, and
`Cache-Control: no-store`. It does not retrieve or verify a previous signed
deployment attestation. A broken chain remains visible as `chain_ok: false`;
unavailable store reads retain the framework's failure response without
creating or recovering storage.

`/assurance/credential` still exports the active verifying key. Consumers must
not expect `/assurance/attest` to create a matching signature on GET. The
credential tests retain direct signer verification with ephemeral test keys.
The direct signer and existing explicit write operations are unchanged.

GET/HEAD on `/api/killinchu/v1/energy/cheapest-watt` only observes an already
loaded helper module and its existing placement ledger. It does not import a
helper, initialize a singleton, start an operator, read live operator status,
record a new decision, or sign one. The response carries the same unsigned
metadata. `ledger_state` is `AVAILABLE`, `EMPTY`, or `UNAVAILABLE`.

`latest_decision` preserves the last existing raw decision payload, or is null.
The top-level unsigned fields describe this read export. They do not rewrite
or establish historical signature state: `retained_signature_verified: false`
and `retained_attestation_state: UNKNOWN` make that boundary explicit.
The existing ledger's `recent_decisions` contains
decision payloads rather than retained DSSE receipt wrappers; this response
does not invent receipt coordinates or prove a previous signature. Missing
initialization remains unavailable. Invalid, nonfinite, or failed status reads
return HTTP 503 with a stable unavailable diagnostic and no recovery.

Killinchu's current source does not contain the optional placement/operator
modules. An optional binding supplied elsewhere is not established by this
source repair. A11oy contains these modules; its coordinated repair tests the
actual placement-ledger implementation as well as absent bindings. New recorded
placement decisions require an existing explicit writer; this change adds no
writer or provider activation.

Local qualification:

```text
python -m pytest -q -p tests.backend_read_offline tests/test_backend_passive_reads.py tests/test_assurance_credential.py tests/test_be_hardening.py tests/test_dsse_real_signing.py
```

Tests serve the registered backend routes through FastAPI, verify the first
matching route before a fallback, retain real SQLite chain and write controls,
and use offline optional-module fixtures. The test-owned precollection plugin
blocks provider access and disables only the unrelated background readiness
snapshot builder; it does not disable request checks or receipt-ledger gates.
That background lane is outside this qualification. Tests establish local software
behavior only. Provider binding, deployment, retained attestation authenticity,
energy measurement, and production qualification remain separate.

This scope covers the two named backend read contracts. It does not certify
that every GET in either application is passive. The sibling backend's
intentional rate-limit differences and existing shared-file guards remain.
