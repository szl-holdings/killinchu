# 30-second + 5-minute + full demo flows tuned for Defense Unicorns

**Recipe ID:** `recipe-andrew-greene-demo`  
**Tags:** demo, defense-unicorns, greene, pitch  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Three demo flows tuned for Defense Unicorns (Andrew Greene's Option-A endorsement: 'see a running deployment of what you've built').

## Steps
1. 30s: GET /api/killinchu/v2/pitch?for=DU -> narrate the one-paragraph DU pitch (UDS-deployable, cosign-attested, sense-and-evidence).
2. 5min: /globe live + POST /api/killinchu/v2/mission/plan (P3 geofence) -> signed plan + /api/killinchu/v2/uds/bundle-inspect (our own bundle SHA).
3. Full: walk recipe-uds-deploy (airgap) -> recipe-mission-replay (after-action BoE) -> recipe-yuyay-gate-defense (legal-heavy gate) -> /khipu/verify (cosign-verifiable).
4. Anchor to DU's real stack: UDS Core (Istio/Keycloak/NeuVector/Pepr) + Zarf airgap + cosign attestation chain.
5. Greene context: the szl-warhacker meta-bundle (v0.4.0) was built in direct response to his 'running deployment' ask (RELEASE_NOTES_v0.4.0).

## Live endpoints driven
- `/api/killinchu/v2/pitch`
- `/globe`
- `/api/killinchu/v2/mission/plan`
- `/api/killinchu/v2/uds/bundle-inspect`
- `/khipu/verify`

## Sources
- https://defenseunicorns.com/warhacker/
- https://github.com/defenseunicorns/uds-core
- https://docs.defenseunicorns.com/

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
