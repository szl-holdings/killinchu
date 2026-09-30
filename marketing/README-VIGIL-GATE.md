# Marketing fact gate v1.2 (Vigil, 2026-09-30)

Real code, not a plan. Two commands:

    python3 marketing/szl_pipeline_v12.py                 # live factbase -> marketing/FACTBASE-*.json
    python3 marketing/szl_pipeline_v12.py --lint DRAFT.md # exit 1 = do not publish

## What factbase() pulls live (never typed from memory)
GitHub org repos + archived + total stars; HF models / datasets / Spaces counts;
most-downloaded artifact resolved DATASET-FIRST with model fallback.

Today's pull: 120 repos (28 archived, 8 stars total) · 50 models / 34 datasets / 27 Spaces ·
headline artifact SZLHOLDINGS/killinchu-osint-corpus at 74,157 downloads.

## Four defects fixed in the original Part 5 script
1. It did not compile: `f"...{subjects} -->\n"[1]` sliced an f-string with no comma -> SyntaxError line 19.
2. URLs pasted as markdown links -> invalid Python literals; now plain constants.
3. Headline resolved to the top MODEL (chaski, 3,070 dl) instead of the top DATASET
   (killinchu-osint-corpus, 74,157 dl) -- the campaign hook would have printed a number 24x too small.
4. No User-Agent and no pagination -> GitHub 403 from a datacenter IP.

## Linter changes
- Quoted rule text is stripped before matching, so a doctrine doc does not fail its own gate
  (previously `"proven," "guaranteed," ... banned` flagged itself).
- Added banned classes the original six missed: absolute safety claims
  (`cannot be jailbroken`), `unhackable`/`tamper-proof`, `military-grade`, `world's first`,
  `never fails`/`zero false`, `outperform`/`beat the market`, defense deployment disclosure.
- Internal download figures are gated pending an explicit publish authorization.

## Boundary (honest)
This gate proves copy is compliant and numbers are live. It does NOT prove any safety claim.
Adversarial suite must run before the word "jailbreak" appears in public copy.
