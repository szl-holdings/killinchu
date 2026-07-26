# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities via email to **security@szlholdings.ai** with:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact assessment
4. Any suggested mitigations

### Response SLA

| Severity | Initial Response | Resolution Target |
|---|---|---|
| Critical | 24 hours | 7 days |
| High | 48 hours | 30 days |
| Medium | 5 business days | 90 days |
| Low | 10 business days | 180 days |

We follow a **90-day responsible disclosure** policy. After 90 days from initial report, details may be published regardless of patch status (with appropriate notice to reporter).

## Supply-Chain Security

- **SLSA Build Level 1 + 2** — signed build provenance per release; the SLSA provenance attestation is independently verified via `cosign verify-attestation --type slsaprovenance` (keyless Fulcio + Rekor, strict per-organ identity); L3 not claimed
- **DCO required** — all commits carry `Signed-off-by:` trailers per [Linux Foundation DCO](https://developercertificate.org/)
- **Cosign keyless signing** — containers signed via Sigstore OIDC keyless mode; verify with `cosign verify ghcr.io/szl-holdings/<repo>:<tag>`
- **SBOM** — CycloneDX SBOM attached to each GitHub Release

## Operator Mutation Controls

The public timeline, alerts, watchlist list, crawler status, and health routes
remain read-only. Durable operator mutations fail closed:

- `POST /api/killinchu/live`
- `POST /api/killinchu/crawl/run`
- `POST /api/killinchu/watchlists`
- `PUT /api/killinchu/watchlists/{wid}`
- `DELETE /api/killinchu/watchlists/{wid}`

Each request requires `Authorization: Bearer <operator-token>` and a unique
`Idempotency-Key`. The runtime stores only the lowercase SHA-256 digest of the
operator token in `A11OY_COMPUTE_TOKEN_SHA256`; it never stores or returns the
raw bearer or raw idempotency key. Missing authority configuration returns 503,
while missing or invalid authority returns 401.

The host injects its canonical Khipu/DSSE emitter when registering this backend.
Successful mutations therefore return the same hash-chained receipt shape as
other Killinchu decisions. `signed: true` is reported only when the configured
host key actually signs the DSSE envelope; a missing key remains honestly
unsigned. Isolated apps that do not inject an emitter use an explicitly labelled
`UNSIGNED_NO_EMITTER` fallback.

Within either SQLite or Postgres, the domain mutation and durable
`receipt_pending` replay material commit in one database transaction. The
separate Khipu append cannot be atomic with that database transaction, so its
durable state advances through `receipt_pending`, `receipt_emitting`, and
`completed`. Operators can inspect and reconcile by hashed key at:

- `GET /api/killinchu/operator-mutations/{key_digest}`
- `POST /api/killinchu/operator-mutations/{key_digest}/reconcile`

An ambiguous `receipt_emitting` state never retries automatically. Retrying
emission requires operator confirmation that the canonical receipt is absent.
Reservations with an uncertain domain side effect likewise remain closed until
an operator confirms inspection; reconciliation never replays the domain
mutation.

## Section 889 Attestation

SZL Holdings attests that no covered telecommunications equipment or services from the following vendors are used in this software:

1. Huawei Technologies Company
2. ZTE Corporation
3. Hytera Communications Corporation
4. Hangzhou Hikvision Digital Technology Company
5. Dahua Technology Company

Per NDAA Section 889, 41 U.S.C. § 4713.

## Doctrine

- Doctrine v11 LOCKED — kernel commit `c7c0ba17` (749 declarations / 14 axioms / 163 sorries)
- Λ = Conjecture 1 (never a theorem)
- No Iron Bank, FedRAMP, CMMC, or SWFT claims

## Contact

- **Security disclosures:** security@szlholdings.ai
- **General:** hello@szlholdings.ai
- **Website:** https://szlholdings.ai

*This policy follows [OpenSSF Vulnerability Disclosure Guide](https://github.com/ossf/oss-vulnerability-guide).*
