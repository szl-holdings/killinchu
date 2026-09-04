# Killinchu Defensive Fusion — Wave 4

## Purpose

Defensive Fusion converts three existing, official, public cyber-defense sources
into one bounded CVE-prioritization instrument:

1. **CISA Known Exploited Vulnerabilities** — observed catalogue membership,
   required defensive action, date added, and the catalogue's ransomware-use field.
2. **NIST NVD CVE API 2.0** — exact CVE status, CVSS score/vector/version,
   publication dates, and CWE identifiers.
3. **FIRST EPSS** — the current probability estimate and percentile for the exact CVE.

The official references are:

- https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- https://nvd.nist.gov/developers/vulnerabilities
- https://www.first.org/epss/data.html

## Public interface

The capability is part of Killinchu's existing connector mesh; it does not create
another service or Space.

```text
GET /api/killinchu/v1/connectors/defensive_fusion/health
GET /api/killinchu/v1/connectors/defensive_fusion/read?q=CVE-2021-44228&limit=1
```

Only an exact identifier matching `CVE-YYYY-NNNN...` is admitted. There is no URL,
host, asset, IP address, hostname, credential, payload, or command parameter.

## Formula

`killinchu.defensive-priority/v1` uses:

```text
0.35 × normalized CVSS
+ 0.30 × EPSS
+ 0.30 × CISA KEV membership
+ 0.05 × CISA known-ransomware-use
```

The denominator contains only **observed** components. Missing source evidence is
not silently interpreted as zero risk. The score is capped at `0.99`; it is a
triage signal, not probability of compromise, proof of exploitation, or certainty.

Priority labels are deterministic:

- `IMMEDIATE`: KEV membership, known ransomware use, or score ≥ 0.85;
- `HIGH`: score ≥ 0.65;
- `ELEVATED`: score ≥ 0.40;
- `ROUTINE`: score below 0.40;
- `UNAVAILABLE`: no official component is available.

## Authority boundary

Every result declares:

```json
{
  "action_authority": "DEFENSIVE_PRIORITIZATION_ONLY",
  "human_approval_required": true,
  "exploit_content_included": false,
  "asset_scanning_performed": false
}
```

The connector does not scan assets, determine whether a specific organization is
vulnerable, retrieve exploit code, provide intrusion instructions, execute a
change, or authorize action against any third party. Recommended actions are
limited to inventory confirmation, vendor/CISA mitigation, exposure reduction,
change approval, and remediation verification.

## Evidence

Each record includes per-source `MEASURED`/`UNAVAILABLE` state, source coverage,
the observed formula components, and SHA-256 over the normalized retained
evidence. That digest is not represented as a hash of the original upstream bytes.
EPSS is an estimate and is never described as certainty.
