# Warhacker demo P4: Tychee-style fragmented satellite ground software, composed in 10 minutes

**Recipe ID:** `recipe-warhacker-demo-p4`  
**Tags:** warhacker, demo, p4  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*Co-Authored-By: Perplexity Computer Agent*

## Intent
Compose four mock ground-software components into one uds-mesh pointer manifest with four pinned SHAs + cosign verify.

## Steps
1. See mission pack P4 at /api/killinchu/v2/missions/P4 for the full slot script, exact CLI, expected output, and fallback.
2. Run the matching live endpoints; capture the signed receipt; keep the fallback path ready.
3. Tie back to the visitor's org via /api/killinchu/v2/pitch?for=<org>.

## Live endpoints driven
- `/api/killinchu/v2/missions/P4`
- `/api/killinchu/v2/pitch`

## Sources
- https://defenseunicorns.com/warhacker/

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
