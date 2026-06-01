# Render N drones on a globe with telemetry traces

**Recipe ID:** `recipe-cesium-visualize`  
**Tags:** cesium, globe, viz, telemetry  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Visualize own-fleet drones + detected tracks on the CesiumJS globe (Ion free tier) with live telemetry traces and geofence overlays.

## Steps
1. Open /globe (CesiumJS, tokenless OpenFreeMap/Ion-free-tier terrain).
2. Feed tracks from GET /api/killinchu/v1/threats/active and own-fleet from /api/killinchu/v2/twin/{id}.
3. Overlay geofence polygons from GET /api/killinchu/v2/geofence/zones.
4. Each entity links to its signed Khipu receipt for provenance (click -> /khipu/verify).
5. Mobile-first: the globe degrades to a 2D map panel on small viewports.

## Live endpoints driven
- `/globe`
- `/api/killinchu/v1/threats/active`
- `/api/killinchu/v2/geofence/zones`
- `/api/killinchu/v2/twin/{drone_id}`

## Sources
- https://cesium.com/platform/cesiumjs/
- https://cesium.com/learn/ion/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
