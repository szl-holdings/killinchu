# Parse an incoming Remote-ID broadcast frame per ASTM F3411-22a

**Recipe ID:** `recipe-decode-remote-id`  
**Tags:** remote-id, ASTM-F3411, decoder  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Decode an OpenDroneID / ASTM F3411-22a 25-byte Remote-ID frame into structured fields (UA type, lat/lon int32x1e7, alt, speed, operator-id).

## Steps
1. GET /api/killinchu/v1/samples to grab a known-good Remote-ID location frame for testing.
2. POST /api/killinchu/v2/remote-id/decode (or v1/remote-id/decode) with {hex:'<frame>'}.
3. Inspect the decoded message_type, lat/lon (int32 scaled 1e7), height, speed, and basic-id (operator).
4. HONESTY: Remote-ID is an unauthenticated broadcast -> decoded fields are CLAIMS, not attested truth.
5. See recipe-decode-remote-id spec at /api/killinchu/v2/specs/remote-id.

## Live endpoints driven
- `/api/killinchu/v2/remote-id/decode`
- `/api/killinchu/v1/remote-id/decode`
- `/api/killinchu/v2/specs/remote-id`
- `/api/killinchu/v1/samples`

## Sources
- https://www.astm.org/f3411-22a.html
- https://github.com/opendroneid/opendroneid-core-c
- https://www.faa.gov/sites/faa.gov/files/2021-08/RemoteID_Final_Rule.pdf

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
