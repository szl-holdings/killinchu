# Score a target via the Policy gate (dual-use check)

**Recipe ID:** `recipe-threat-assess`  
**Tags:** threat, policy, dual-use, classification  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*ORCID 0009-0001-0110-4173*

## Intent
Assess a detected airframe against the killinchu **Policy gate** (the honest role formerly codenamed internally; the policy/security-gate logic ships inside the product): classify side, run a dual-use check, and return a threat score + recommended posture (sense/evidence only).

## Steps
1. POST /api/killinchu/v2/threat/assess with {model or signature, telemetry}.
2. The Policy gate returns {side: adversary|dual-use|allied, threat_score, dual_use_flag}.
3. If dual_use_flag, DO NOT escalate to any control action: dual-use airframes (e.g. DJI Mavic) require human review.
4. Cross-check against the 53-drone DB via GET /api/killinchu/v1/drones/{id}.
5. Output is advisory evidence only; no engagement. Attach disclaimer.

## Live endpoints driven
- `/api/killinchu/v2/threat/assess`
- `/api/killinchu/v1/drones/database`

## Sources
- https://www.epirusinc.com/electronic-warfare

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
