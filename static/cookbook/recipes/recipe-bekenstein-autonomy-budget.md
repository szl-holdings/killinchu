# Compute an autonomy budget for a mission via formula F15

**Recipe ID:** `recipe-bekenstein-autonomy-budget`  
**Tags:** F15, bekenstein, autonomy, budget  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Compute the Bekenstein-bounded autonomy budget (F15) for a mission: the information/energy ceiling on autonomous decisions before a human gate is required.

## Steps
1. Gather mission params: comms-denied duration, sensor entropy rate, energy reserve, decision criticality.
2. POST to the understudy formulas surface (F15) with these params -> autonomy_budget (bits) + max_autonomous_decisions.
3. If the plan's projected decision count exceeds the budget, insert a human-gate checkpoint (recipe-yuyay-gate-defense).
4. F15 is a CONSERVATIVE upper bound; defense posture rounds DOWN. Attach disclaimer.

## Live endpoints driven
- `/api/killinchu/v2/formulas/F15`
- `/api/killinchu/v2/mission/plan`

## Formulas
- F15 Bekenstein autonomy budget

## Sources
- https://en.wikipedia.org/wiki/Bekenstein_bound

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
