# 13-axis Yuyay gate with legal-heavy weights for defense actions

**Recipe ID:** `recipe-yuyay-gate-defense`  
**Tags:** yuyay-13, gate, legal, governance, lambda  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Run the Yuyay-13 trust gate with defense-tuned weights (legality and authority weighted heavily) before any own-fleet control action.

## Steps
1. Assemble the 13 axis scores (soundness, calibration, robustness, provenance, consent, reversibility, transparency, fairness, containment, attestation, freshness, authority, auditability).
2. Apply defense weights: legality/authority/containment up-weighted; a legality=0 axis is an unconditional hard-reject.
3. POST /api/killinchu/v1/counter-uas/evaluate (or the understudy yuyay surface) -> Lambda aggregate (geometric mean) vs floor 0.90.
4. ALLOW only if Lambda >= floor AND no hard-reject; otherwise REVIEW (human) — never auto-escalate.
5. Two-person rule: own-fleet control needs 2 approvers. Emit signed gate receipt. Attach disclaimer.

## Live endpoints driven
- `/api/killinchu/v1/counter-uas/evaluate`
- `/api/killinchu/v1/lambda`
- `/khipu/sign`

## Formulas
- 13-axis Lambda (geometric mean)

## Sources
- https://datatracker.ietf.org/wg/scitt/about/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
