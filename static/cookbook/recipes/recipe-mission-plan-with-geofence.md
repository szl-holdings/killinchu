# Plan a mission inside FAA TFR + NPS no-fly + airport 5nm boundaries; emit signed plan

**Recipe ID:** `recipe-mission-plan-with-geofence`  
**Tags:** mission, geofence, planning, F7  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Given an objective and a corridor, produce a flight plan that respects FAA TFRs, National Park Service no-fly, and 5nm airport boundaries, then emit a Wire-D signed plan receipt.

## Steps
1. POST /api/killinchu/v2/geofence/check with each waypoint {lat,lon} to test against active zones (TFR/NPS/airport).
2. If any waypoint breaches, re-route: shift the breaching leg outside the polygon (the planner returns the nearest legal vertex).
3. POST /api/killinchu/v2/mission/plan with {objective, corridor, drone_id} -> PURIQ F7 feasibility score + ordered legs.
4. Compute autonomy budget via F15 (see recipe-bekenstein-autonomy-budget) to confirm the plan fits the drone's energy/comms envelope.
5. POST /khipu/sign over the final plan object -> real ECDSA-P256 DSSE receipt (keyid szlholdings-cosign).
6. Attach LEGAL_BOUNDARIES disclaimer; return {plan, feasibility, signed_receipt, disclaimer}.

## Live endpoints driven
- `/api/killinchu/v2/geofence/check`
- `/api/killinchu/v2/mission/plan`
- `/khipu/sign`
- `/api/killinchu/v2/geofence/zones`

## Formulas
- F7 mission feasibility
- F15 Bekenstein autonomy budget

## Sources
- https://www.faa.gov/uas/getting_started/temporary_flight_restrictions
- https://www.nps.gov/articles/unmanned-aircraft-in-the-national-parks.htm
- https://www.faa.gov/uas/recreational_flyers/where_can_i_fly

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
