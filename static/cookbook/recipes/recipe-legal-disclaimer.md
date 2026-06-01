# When and how to attach the LEGAL_BOUNDARIES disclaimer to a response

**Recipe ID:** `recipe-legal-disclaimer`  
**Tags:** legal, compliance, disclaimer  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Define exactly when the LEGAL_BOUNDARIES disclaimer must be attached and how to fetch the canonical text + linked controlling law.

## Steps
1. RULE: every response that handles a drone-domain ACTION (plan/swarm/decode-of-live-feed/threat/twin/control) MUST embed the disclaimer.
2. GET /api/killinchu/v2/legal for the full LEGAL_BOUNDARIES.md text + linked sources (CFAA, ITAR, Wassenaar, FCC, SCITT).
3. Place the disclaimer string in a top-level `disclaimer` field of the JSON response.
4. Never imply Killinchu can take control of a third-party drone. Sense + evidence framing only.

## Live endpoints driven
- `/api/killinchu/v2/legal`

## Sources
- https://www.law.cornell.edu/uscode/text/18/1030
- https://www.ecfr.gov/current/title-22/chapter-I/subchapter-M

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
