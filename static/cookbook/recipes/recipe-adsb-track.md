# Track ADS-B aircraft in current airspace, integrate with mission planner

**Recipe ID:** `recipe-adsb-track`  
**Tags:** ads-b, mode-s, deconfliction, decoder  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Decode ADS-B Mode-S 1090ES (pyModeS) identity + CPR position pairs and feed live tracks into the mission planner for deconfliction.

## Steps
1. GET /api/killinchu/v1/samples for an even/odd CPR pair + ident frame.
2. POST /api/killinchu/v2/adsb/decode with {even,odd} for global CPR position, or {hex} for a single ident frame.
3. Build a track table {icao24, callsign, lat, lon, alt}.
4. POST /api/killinchu/v2/mission/plan including the ADS-B tracks as no-go cylinders for deconfliction.
5. HONESTY: ADS-B is unauthenticated -> treat as claim.

## Live endpoints driven
- `/api/killinchu/v2/adsb/decode`
- `/api/killinchu/v2/mission/plan`
- `/api/killinchu/v1/samples`

## Sources
- https://mode-s.org/decode/
- https://mode-s.org/pymodes/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
