# Warhacker demo P5: Lean kernel proof — UDSSensorReceiptChain.total_order

**Recipe ID:** `recipe-warhacker-demo-p5`  
**Tags:** warhacker, demo, p5  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Display the theorem statement + axiom dependency list: the chain is total-ordered, cutting/reordering is observable.

## Steps
1. See mission pack P5 at /api/killinchu/v2/missions/P5 for the full slot script, exact CLI, expected output, and fallback.
2. Run the matching live endpoints; capture the signed receipt; keep the fallback path ready.
3. Tie back to the visitor's org via /api/killinchu/v2/pitch?for=<org>.

## Live endpoints driven
- `/api/killinchu/v2/missions/P5`
- `/api/killinchu/v2/pitch`

## Sources
- https://defenseunicorns.com/warhacker/

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
