# Killinchu Asset Exposure Wave 5

Wave 5 converts the Wave 4 exact-CVE defensive correlation into an
operator-specific remediation queue without turning Killinchu into a scanner.

The endpoint accepts an **inline, operator-supplied SBOM** and explicit
component-to-CVE findings. It validates every component reference and CVE before
the existing Defensive Fusion connector is invoked. Killinchu then correlates
CISA KEV, NIST NVD CVE 2.0, and FIRST EPSS evidence and ranks the submitted
findings against the operator-declared asset context.

## Runtime endpoints

```text
GET  /api/killinchu/uds/v1/sbom/exposure/schema
POST /api/killinchu/uds/v1/sbom/exposure/evaluate
```

The schema endpoint is network-free and describes accepted inputs, limits, and
authority boundaries.

## Accepted evidence

The evaluator accepts:

- CycloneDX JSON with addressable `bom-ref` values, or a unique `purl` when a
  `bom-ref` is absent;
- SPDX 2.x JSON with addressable package `SPDXID` values;
- one asset record with a stable ID, criticality from 1 through 5, and exposure
  classification;
- explicit findings that bind one exact component reference to one exact
  `CVE-YYYY-NNNN...` identifier.

A package name or version is never converted into a CVE. The association must
already exist in the submitted operator evidence or VEX workflow.

## Example request

```json
{
  "asset": {
    "asset_id": "asset:prod:payments-01",
    "name": "Payments API",
    "owner": "Platform Security",
    "environment": "production",
    "criticality": 5,
    "exposure": "internet"
  },
  "sbom": {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": "urn:uuid:example-wave5",
    "metadata": {
      "component": {
        "name": "payments-api"
      }
    },
    "components": [
      {
        "type": "library",
        "bom-ref": "pkg:maven/log4j-core@2.14.1",
        "name": "log4j-core",
        "version": "2.14.1",
        "purl": "pkg:maven/log4j-core@2.14.1"
      }
    ]
  },
  "findings": [
    {
      "component_ref": "pkg:maven/log4j-core@2.14.1",
      "cve": "CVE-2021-44228",
      "status": "affected",
      "evidence_ref": "operator-vex:2026-09-04:1"
    }
  ]
}
```

## Finding states

| State | Meaning |
|---|---|
| `affected` | Active operator finding; official evidence is resolved. |
| `under_investigation` | Active provisional finding; official evidence is resolved but the affected state is not asserted as final. |
| `fixed` | Closed finding. A justification is required; no official-source request is made. |
| `not_affected` | VEX-style exclusion. A justification is required; no official-source request is made. |

Unknown component references, malformed CVEs, duplicate JSON keys, unsupported
SBOM shapes, missing VEX justifications, and oversized inputs are rejected
before any official-source request is attempted.

## Formula

Wave 5 does not replace the Wave 4 formula. It consumes the measured
`killinchu.defensive-priority/v1` score and applies a bounded operator-context
multiplier:

```text
criticality_normalized = (criticality - 1) / 4
exposure_normalized =
    isolated  -> 0.0000
    internal  -> 0.3333
    partner   -> 0.6667
    internet  -> 1.0000

context_multiplier =
    0.55
  + 0.30 * criticality_normalized
  + 0.15 * exposure_normalized

asset_priority_score =
    defensive_priority_score * context_multiplier
```

The multiplier is bounded to `[0.55, 1.00]`; the final score is capped at
`0.99`. It is a deterministic ordering signal, not probability of compromise,
probability that a package is affected, or authorization to change a system.

Remediation lanes preserve urgent official evidence:

- `P0`: Wave 4 priority is `IMMEDIATE`;
- `P1`: Wave 4 priority is `HIGH`, or asset score is at least `0.65`;
- `P2`: Wave 4 priority is `ELEVATED`, or asset score is at least `0.40`;
- `P3`: measured `ROUTINE` item;
- `REVIEW`: official evidence is unavailable or insufficient;
- `VEX` and `CLOSED`: inactive findings retained for the evidence record.

## Output evidence

Each response includes:

- the exact canonical SHA-256 of the submitted SBOM JSON;
- a normalized-input SHA-256;
- per-finding official-source state and coverage;
- the Wave 4 normalized evidence SHA-256 when available;
- a deterministic Wave 5 evidence SHA-256;
- a sorted remediation queue;
- an honest DSSE envelope when the runtime signing key is available, or an
  explicit unsigned state when it is not.

The report retains these authority statements:

```json
{
  "action_authority": "DEFENSIVE_REMEDIATION_PLANNING_ONLY",
  "human_approval_required": true,
  "asset_scanning_performed": false,
  "sbom_fetched_remotely": false,
  "component_vulnerability_inference_performed": false,
  "third_party_mutation_performed": false,
  "data_persisted": false
}
```

## Limits

```text
Request body:        2,000,000 bytes
SBOM components:    1,000
Findings:           50
Unique active CVEs: 10
```

The active-CVE bound limits upstream load and prevents the public route from
becoming an unbounded bulk-query mechanism.

## Verification

Run the network-free contract suite:

```bash
python -m unittest -v tests.test_asset_exposure_wave5
```

The suite covers CycloneDX and SPDX parsing, strict JSON, exact-reference
validation, VEX closure, request bounds, deterministic evidence hashes, formula
bounds, honest unavailable states, and source scans proving that the Wave 5
module has no direct HTTP, socket, subprocess, or shell primitive.

## Safety boundary

Wave 5 is not a vulnerability scanner, package intelligence crawler, exploit
engine, patch executor, credential collector, or asset discovery system. It
correlates operator-owned evidence with the existing fixed-origin official
defensive sources and produces a human-approved remediation plan.
