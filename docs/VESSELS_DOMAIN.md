# Vessels Domain — Canonical Killinchu Runtime

**Canonical vertical:** `killinchu`  
**Domain:** `vessels`  
**Doctrine:** v11; locked-proven formula IDs `{F1,F4,F7,F11,F12,F18,F19,F22}`  
**Λ uniqueness:** Conjecture 1 — open, never presented as a theorem

## Product boundary

Vessels is no longer a standalone SZL Holdings product. It is the sea-domain
operating picture inside **Killinchu**, alongside the counter-UAS/air domain.

Historical Vessels artifacts and seed datasets remain for compatibility and
reproducible demonstrations. They are not an independent production authority.

## Canonical runtime routes

| Route | Contract |
|---|---|
| `GET /api/killinchu/v1/vertical/contract` | Static product/data/formula/Anatomy/Second-Brain contract |
| `GET /api/killinchu/v1/vertical/runtime` | Request-level runtime state with explicit degraded organs |
| `GET /api/killinchu/v1/fleet/voyage-risk/current` | Current AIS + sanctions + formula + grounded-handle assessment |
| `GET /api/killinchu/v1/fleet/voyage-risk` | Compatibility **SAMPLE/REPLAY** decision loop |
| `GET /api/killinchu/v1/feeds/vessels` | TRACK-normalized AIS redundancy chain |
| `GET /api/killinchu/v1/feeds/vessels/stats` | Per-theater current/sample coverage rollup |
| `GET /api/killinchu/v1/osint/intel?vertical=sanctioned_vessels` | Public UN 1718 designated-vessel collection |

## Data plane

The current AIS route uses the source chain already implemented in
`killinchu_feeds_realdata.py`:

1. AISStream.io websocket when an authorized secret is present.
2. Fintraffic Digitraffic AIS, no key, geographically bounded to Finnish/Baltic coverage.
3. Norwegian Coastal Administration/Kystverket AIS, no key, geographically bounded.
4. Marinesia only when an authorized credential is present.
5. Bundled sample/replay only when no current source returns in-theater records.

Every track must carry `source`, `source_url`, `provenance`, `ts`, and `live`.
A sample record can never satisfy the current-data `LIVE` state.

NOAA MarineCadastre August 2024 records are real historical rows, but remain
`HISTORICAL_SAMPLE`; they are not current AIS.

The sanctions plane uses the public UN Security Council 1718 designated-vessel
dataset through OpenSanctions. It fails closed. `NO_EXACT_MATCH` is not
regulatory clearance, and identity transliteration, beneficial ownership, and
non-vessel sanctions still require human compliance review.

## Governed decision loop

The current endpoint implements the observable sequence:

`INGEST → TRANSFORM → ANALYZE → DECIDE → APPROVE → EXECUTE → VERIFY → AUDIT → DELIVER`

Execution authority is always `NONE` in the public runtime. The endpoint emits
an advisory recommendation, a rollback path, and a mandatory human-approval
gate. It does not authorize routing, detention, interdiction, engagement, or a
counterparty decision.

## Math and formula binding

The Vessels domain applies formulas only where their inputs are defensible:

- `lambda_aggregate` aggregates measured operational-sufficiency proxies.
- `lambda_bounded` verifies the aggregate remains bounded by measured inputs.
- `khipu_merkle_root` is reserved for downstream receipt integrity.
- `dsse_envelope` is reserved for a real signing path.

The runtime publishes all 13 Yuyay axes, but unmeasured axes remain `null` and
are excluded from the aggregate. The result is named
`partial_operational_lambda`; a full Yuyay-13 score is never inferred.

## Second Brain and Anatomy

The BRAIN organ prefers the local `second_brain` package and otherwise calls the
allowlisted public SZL Second Brain navigator. It receives handles and evidence
digests only. Retrieval scores are lexical overlap, never correctness.

Runtime organs are reported individually:

- `EYES_EARS` — current AIS sensing
- `IMMUNE` — sanctions/anomaly screening
- `BRAIN` — handles-only grounded retrieval
- `SKELETON` — formula/doctrine contract
- `HEART` — governed recommendation loop
- `HANDS` — human-only execution boundary
- `MEMORY` — evidence digest and receipt binding

Any unavailable dependency degrades the Anatomy state; no fabricated calm.

## Explicit gaps

| Capability | State | Rule |
|---|---|---|
| Beneficial-ownership graph | `UNAVAILABLE` in the public runtime | An operator-reported helper exists in source, but do not claim current ownership until an authenticated, runtime-bound and independently sourced graph is attached |
| Current class-society status | `UNAVAILABLE` | Do not infer from sample certificates |
| Keyless global current AIS | `PARTIAL` | No-key sources are geographically bounded |
| Statistical voyage forecast | `NOT_MODELLED` | Current deterministic assessment is not a casualty/delay prediction |

## Verification

```bash
pytest -q tests/test_killinchu_vertical_runtime.py
curl -fsS http://localhost:7860/api/killinchu/v1/vertical/contract | python -m json.tool
curl -fsS "http://localhost:7860/api/killinchu/v1/fleet/voyage-risk/current?theater=baltic&limit=20" | python -m json.tool
```

Production readiness still requires an exact-source deployment receipt and
post-deployment probes of the canonical routes.
