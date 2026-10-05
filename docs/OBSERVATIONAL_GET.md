# Observation reads and receipt writes

The following GET and HEAD routes observe catalogue, planning, telemetry, or
drift data without minting, signing, recording a receipt, provisioning storage,
or recovering the canonical receipt ledger:

- `/api/killinchu/v1/borrowed-powers`
- `/api/killinchu/v1/geoint`
- `/api/killinchu/v1/drones/{drone_id}/integrity`
- `/api/killinchu/v1/twin/state`
- `/api/killinchu/v1/posture/drift`

Their existing receipt objects retain null `index` and `digest`, `signed: false`,
and `state: UNSIGNED_READ_ONLY`. Borrowed powers uses `query_receipt`, with
`dsse: null`; the other routes use `receipt`. Every successful observation adds
`receipt_minted: false` and `export_read_only: true`. A reported existing
`khipu_root` is an observation of the current head, never a new receipt.

Observation availability does not claim ledger readiness or production
retention. The routes can return an unsigned preview when the canonical ledger
is unstarted or unavailable, without replaying it. Missing drone IDs still
return HTTP 404. Planning confidences and integrity tripwires retain their
existing modeled/demo limits. Health-twin trust axes, their aggregate, and the
reported trust band now retain the 0.97 ceiling; nonfinite or invalid aggregate
inputs return zero. Missing, malformed, or failed canonical YUYAY gate evidence denies
authorization instead of using a smaller local gate. These are policy bounds,
not a new mathematical result or measured calibration. A gate's `pass` must be
an actual JSON boolean; strings and numeric values cannot authorize. Compromise calculations
retain their existing limits. GET/HEAD reads the previous fix without
updating either AIS or ADS-B fix history. Threat/feed caches are observational
data caches, not receipt records or actuation authorization.

The existing POST operations for GEOINT, drone integrity, and twin remediation
retain their receipt writers. POST fix mapping can still record a new previous
fix. Twin remediation remains SIMULATED and retains its ROE/trust gates. This
change adds no new write operation or physical effect.

The console's GEOINT view now describes GET as an unsigned planning preview and
does not display missing coordinates as a receipt. Its twin and drift views read
health/detector data; they do not consume the removed GET receipt coordinates.
External consumers must handle the explicit null receipt coordinates and use
the existing POST operation when a recorded decision is required.

`/api/build-info` retains its legacy `receipt_minted` field for consumers that
check the captured GitHub OIDC deployment release reference. That field can be
true for a historical release; it does not report a new receipt on a GET.
`receipt_minted_on_request: false` and
`receipt_minted_scope: DEPLOYMENT_RELEASE_REFERENCE` make the distinction
explicit. Repeated GET/HEAD requests export the identity captured at
registration without fetching or minting an attestation.

Local qualification command:

```text
python -m pytest -q -p tests.observation_offline tests/test_killinchu_observational_get.py tests/test_elite_wiring.py tests/test_public_route_repair.py
```

Tests use real served route order, a real SQLite adapter, controlled offline
telemetry and unavailable threat-feed fixtures, and the existing explicit
writers. They establish local software behavior only, not provider retention,
scientific validity, deployment, authorization, or production qualification.
The suite disables the unrelated background readiness snapshot builder and
blocks provider access; it does not qualify that background lane.
This scope covers these five observation routes. Other GET signing/recording
sites, including shared backend assurance and energy routes, require separate
source and peer qualification.
