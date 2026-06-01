# Warhacker demo P3: Mission plan with live geofence check

**Recipe ID:** `recipe-warhacker-demo-p3`  
**Tags:** warhacker, demo, p3  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Plan a counter-UAS ISR mission inside FAA TFR + NPS no-fly + 5nm airport boundaries; emit a signed plan (see recipe-mission-plan-with-geofence).

## Steps
1. See mission pack P3 at /api/killinchu/v2/missions/P3 for the full slot script, exact CLI, expected output, and fallback.
2. Run the matching live endpoints; capture the signed receipt; keep the fallback path ready.
3. Tie back to the visitor's org via /api/killinchu/v2/pitch?for=<org>.

## Live endpoints driven
- `/api/killinchu/v2/missions/P3`
- `/api/killinchu/v2/pitch`

## Sources
- https://defenseunicorns.com/warhacker/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
