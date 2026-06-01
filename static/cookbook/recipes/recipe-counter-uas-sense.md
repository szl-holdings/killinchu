# Sense + evidence + report; we do NOT jack into third-party drones

**Recipe ID:** `recipe-counter-uas-sense`  
**Tags:** counter-uas, sense, evidence, passive  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
The core counter-UAS workflow: passively detect, classify, geolocate, and evidence an adversary drone, then hand a signed Body-of-Evidence to the authorized customer.

## Steps
1. Detect: decode Remote-ID/ADS-B/MAVLink/RF passively (recipe-decode-*). RF-geolocate Remote-ID-OFF 'dark drones'.
2. Classify: POST /api/killinchu/v2/threat/assess -> side + dual-use check against the 53-drone DB.
3. Cluster: GET /api/killinchu/v1/swarm/topology to detect coordinated swarms (Union-Find over proximity).
4. Evidence: every detection emits a signed Khipu receipt -> a court-admissible Body-of-Evidence.
5. Report: hand the signed BoE to the authorized .mil/.gov customer. Killinchu does NOT jam, spoof, hijack, or engage.
6. Attach disclaimer on EVERY step.

## Live endpoints driven
- `/api/killinchu/v2/threat/assess`
- `/api/killinchu/v1/swarm/topology`
- `/api/killinchu/v2/remote-id/decode`
- `/khipu/sign`

## Sources
- https://www.cisa.gov/topics/physical-security/counter-unmanned-aircraft-systems
- https://datatracker.ietf.org/wg/scitt/about/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
