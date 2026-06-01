# Event-source replay of mission X for after-action review

**Recipe ID:** `recipe-mission-replay`  
**Tags:** replay, ayni, after-action, khipu  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Replay a completed mission from the AYNI-OS event log + Khipu DAG for after-action review, with every decision receipt re-verified.

## Steps
1. GET /api/killinchu/v1/receipt/ledger to pull the Khipu DAG for the mission window.
2. Walk the hash-chained nodes in order; each node's digest includes its parent -> reordering/cutting is observable.
3. POST /khipu/verify over each signed receipt to confirm ECDSA-P256 signatures still validate.
4. Reconstruct the timeline: plan -> geofence checks -> swarm commands -> gate decisions -> outcome.
5. Produce an after-action Body-of-Evidence bundle (court-admissible).

## Live endpoints driven
- `/api/killinchu/v1/receipt/ledger`
- `/khipu/verify`
- `/api/killinchu/v1/wires/D`

## Sources
- https://martinfowler.com/eaaDev/EventSourcing.html
- https://datatracker.ietf.org/wg/scitt/about/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
