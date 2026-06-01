# Deploy Killinchu via UDS Zarf bundle in an airgapped env (cosign verify steps)

**Recipe ID:** `recipe-uds-deploy`  
**Tags:** uds, zarf, airgap, cosign, deploy  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Deploy Killinchu as a UDS Zarf package into an airgapped cluster, including the cosign verification steps (honest: bundle is STAGED, signature PENDING until FA-001).

## Steps
1. GET /api/killinchu/v2/uds/bundle-inspect to read the bundle metadata (name, version, SHA-256, SBOM ref, cosign status).
2. GET /api/killinchu/v2/uds/deploy-instructions for the exact zarf/uds commands.
3. On the airgap host: `uds zarf package deploy ./killinchu-uds-<ver>.tar.zst --confirm`.
4. Verify the signature: `cosign verify-blob --key cosign.pub --signature killinchu-uds-<ver>.tar.zst.sig killinchu-uds-<ver>.tar.zst`.
5. GET /api/killinchu/v2/uds/verify to see the live, HONEST verification status.
6. HONESTY: the Killinchu Zarf package is STAGED (SBOM-only at uds-v0.3.0); cosign verify will report PENDING until the org key (U5) is provisioned and the image is pushed (FA-001).

## Live endpoints driven
- `/api/killinchu/v2/uds/bundle-inspect`
- `/api/killinchu/v2/uds/deploy-instructions`
- `/api/killinchu/v2/uds/verify`

## Sources
- https://github.com/defenseunicorns/uds-cli
- https://docs.defenseunicorns.com/
- https://docs.sigstore.dev/cosign/verifying/verify/

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
