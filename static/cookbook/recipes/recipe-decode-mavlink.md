# Parse a MAVLink v2 frame, extract msg_id + payload

**Recipe ID:** `recipe-decode-mavlink`  
**Tags:** mavlink, decoder, pymavlink  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Decode a MAVLink v1/v2 frame (pymavlink) into msg_id, system/component id, and typed payload (e.g. HEARTBEAT).

## Steps
1. GET /api/killinchu/v1/samples for a known HEARTBEAT frame.
2. POST /api/killinchu/v2/mavlink/decode (or v1/mavlink/parse) with {hex:'<frame>'}.
3. Read msgid, sysid, compid, and the decoded fields; confirm magic byte 0xFD (v2) vs 0xFE (v1).
4. See /api/killinchu/v2/specs/mavlink for the frame layout reference.

## Live endpoints driven
- `/api/killinchu/v2/mavlink/decode`
- `/api/killinchu/v1/mavlink/parse`
- `/api/killinchu/v2/specs/mavlink`
- `/api/killinchu/v1/samples`

## Sources
- https://mavlink.io/en/guide/serialization.html
- https://github.com/ArduPilot/pymavlink

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
