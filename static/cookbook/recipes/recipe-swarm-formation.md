# Coordinate N drones in a boids formation toward objective X

**Recipe ID:** `recipe-swarm-formation`  
**Tags:** swarm, boids, F11, coordination  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Drive N own-fleet drones into a cohesive boids formation (separation, alignment, cohesion) advancing toward an objective, with F11 swarm-coherence monitoring.

## Steps
1. POST /api/killinchu/v2/swarm/coordinate with {drones:[...], objective:{lat,lon}, weights:{separation,alignment,cohesion}}.
2. The boids engine returns per-drone velocity vectors each tick (separation repels close neighbors, alignment matches heading, cohesion pulls to centroid).
3. Read F11 swarm coherence from the response; coherence < floor -> tighten cohesion weight or split into sub-swarms.
4. Each tick emits a Khipu frame; sign the formation command with /khipu/sign for cross-organ replay.
5. Own-fleet ONLY. Attach disclaimer.

## Live endpoints driven
- `/api/killinchu/v2/swarm/coordinate`
- `/khipu/sign`

## Formulas
- F11 swarm coherence

## Sources
- https://www.red3d.com/cwr/boids/
- https://en.wikipedia.org/wiki/Boids

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
