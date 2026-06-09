# Hand off to the Operator role for an operator decision when the gate fails

**Recipe ID:** `recipe-cross-organ-rosie-handoff`  
**Tags:** operator, handoff, wire-i  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Attribution: ORCID 0009-0001-0110-4173*

> The "Operator" role (retired internal codename `rosie`) is not a standalone
> shipping product or Space; it is a roadmap role that surfaces inside a11oy. The
> killinchu endpoints below are the live, served killinchu API surface that invoke
> the operator-companion behaviour.

## Intent
When the Yuyay gate returns REVIEW or classifier confidence is low, hand off to the Operator role (operator-companion) for human-in-the-loop reasoning.

## Steps
1. Detect REVIEW (gate) or top classifier confidence < 0.7 (possibly novel airframe).
2. POST /api/killinchu/v1/identify/with-rosie with the signature -> the Operator role consults only on low confidence.
3. Or POST /api/killinchu/v1/rosie-companion/brain-jack with the decision context for deeper reasoning.
4. The Operator role is CO-PILOT, not pilot: it proposes; Killinchu + the 2-person Yuyay gate decide.
5. Both the identify result and the Operator reasoning carry cross-linked Khipu receipts. Attach disclaimer.

## Live endpoints driven (served by killinchu)
- `/api/killinchu/v1/identify/with-rosie`
- `/api/killinchu/v1/rosie-companion/brain-jack`
- `/api/killinchu/v1/rosie-companion`

## Sources
- Live product: https://szlholdings-killinchu.hf.space (the Operator role surfaces inside a11oy: https://szlholdings-a11oy.hf.space)

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
