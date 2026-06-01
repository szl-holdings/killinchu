# Get real-time state of drone N (location, battery, mission, geofence, threat)

**Recipe ID:** `recipe-drone-digital-twin`  
**Tags:** twin, telemetry, state  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Query the digital twin for own-fleet drone N: position, battery, current mission leg, geofence status, and any nearby threats.

## Steps
1. GET /api/killinchu/v2/twin/{drone_id} -> {position, battery, mission, geofence_status, integrity}.
2. Cross-reference /api/killinchu/v1/drones/{drone_id} for the airframe spec.
3. If geofence_status == BREACH, trigger recipe-yuyay-gate-defense before any own-fleet maneuver.
4. Twin state is event-sourced; replay via recipe-mission-replay.

## Live endpoints driven
- `/api/killinchu/v2/twin/{drone_id}`
- `/api/killinchu/v1/drones/{drone_id}`

## Sources
- https://en.wikipedia.org/wiki/Digital_twin

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
