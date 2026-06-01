# Refuse non-defense overreach; cite LEGAL_BOUNDARIES

**Recipe ID:** `recipe-honest-walkback`  
**Tags:** honesty, refusal, legal, walkback  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Pattern for honestly refusing a request that exceeds Killinchu's lawful sense-and-evidence scope (e.g. 'hijack that drone', 'jam this frequency').

## Steps
1. Detect overreach: any request to control/exploit/hijack/brick/jam/spoof a NON-own-fleet target.
2. Refuse with HTTP 403 + a clear reason citing the specific control (CFAA for hijack, FCC for jamming, ITAR for offensive cyber export).
3. GET /api/killinchu/v2/legal and quote the relevant section.
4. Offer the lawful alternative: 'I can SENSE and EVIDENCE this target and hand a signed Body-of-Evidence to your authorized .mil/.gov customer who holds the engagement authority.'
5. Never partially comply. Attach disclaimer.

## Live endpoints driven
- `/api/killinchu/v2/legal`

## Sources
- https://www.law.cornell.edu/uscode/text/18/1030
- https://www.fcc.gov/general/jammer-enforcement

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
