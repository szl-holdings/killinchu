# Generate an attestation snapshot for a FedRAMP / IL-4 audit

**Recipe ID:** `recipe-fedramp-attestation`  
**Tags:** fedramp, il-4, attestation, sbom, compliance  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Produce a point-in-time attestation snapshot (SBOM + cosign status + Khipu root + doctrine numbers) suitable for a FedRAMP / IL-4 audit evidence package.

## Steps
1. GET /provenance for the Wire-D provenance block (SLSA level, traceparent continuity).
2. GET /api/killinchu/v2/uds/bundle-inspect for the SBOM reference + cosign status.
3. GET /api/killinchu/v1/receipt/ledger for the current Khipu root (chain integrity anchor).
4. Assemble the snapshot {doctrine:749/14/163, slsa_level, sbom_ref, cosign_status, khipu_root, ts_utc}; sign it via /khipu/sign.
5. HONESTY: this is an attestation SNAPSHOT, NOT an ATO. FedRAMP/IL-4 ATO is a roadmap item; SLSA is L1 honest (NOT L2 or L3 — LOCKED Doctrine v11).

## Live endpoints driven
- `/provenance`
- `/api/killinchu/v2/uds/bundle-inspect`
- `/api/killinchu/v1/receipt/ledger`
- `/khipu/sign`

## Sources
- https://www.fedramp.gov/
- https://public.cyber.mil/dccs/dccs-documents/
- https://slsa.dev/

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
