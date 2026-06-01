# Operate offline via the UDS Zarf bundle

**Recipe ID:** `recipe-airgap-mode`  
**Tags:** airgap, uds, offline, zarf  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Run Killinchu fully offline in an airgapped enclave: all decoders, the drone DB, geofences, and the signer run in-process with no network egress.

## Steps
1. Deploy via recipe-uds-deploy (USB drop-drive of the cosigned tarball).
2. Confirm no egress: decoders (pyModeS, pymavlink, OpenDroneID) are pure in-process; the drone DB + geofences are vendored.
3. The Khipu DAG + LMDB memory persist locally; signatures use the operator-provisioned Ed25519/EC secret.
4. GET /api/killinchu/healthz offline to confirm doctrine 749/14/163 + drones loaded.
5. HONESTY: external GEOINT/satellite feeds are unavailable airgapped; the system says so rather than faking a feed.

## Live endpoints driven
- `/api/killinchu/healthz`
- `/api/killinchu/v2/uds/deploy-instructions`

## Sources
- https://docs.defenseunicorns.com/
- https://github.com/defenseunicorns/zarf

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
