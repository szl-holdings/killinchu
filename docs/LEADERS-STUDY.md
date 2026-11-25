# Domain Leader Study — killinchu (counter-UAS edge)

OUROBOROS phase-3, cohort-02 tranche-3, Kimi ruling W26-C2T3-EXEC-20261123 (GO, 7 conditions). PROPOSE-ONLY, DRAFT. Documentation only, no implementation in this PR.

## Current state (repo inspection 2026-11-23, W26G receipts)
Counter-UAS edge: ASTM F3411-22a Remote ID, pyModeS and pymavlink decoders, DSSE Khipu receipts, Doctrine v11.

## Domain leaders studied
| Leader | What they have | Key sources |
| --- | --- | --- |
| in-toto DSSE envelope | The DSSE v1 envelope spec binding attestation payloads and signatures with type prefixes; the interop pattern the repo's Khipu receipts build on | secure-systems-lab/dsse envelope spec (https://github.com/secure-systems-lab/dsse) |
| pyModeS | The reference open-source ADS-B/Mode-S decoder library used for live air-traffic observation Python tooling | junzis/pyModeS (https://github.com/junzis/pyModeS) |
| ASTM F3411-22a | The standard Remote ID and tracking definition for unmanned aircraft: the normative decoding target for counter-UAS telemetry | ASTM F3411-22a (https://www.astm.org/f0341-22a.html) |

## Complements, not duplicates
Sibling PR #657 (fix(killinchu): fail-closed DSSE envelope inspection, dsse_verify) is the IMPLEMENTATION-class card: it implements DSSE v1 PAE verification. This card is the STUDY-class counterpart citing the same in-toto DSSE envelope spec. Per the W26G measurement and this ruling's condition 4, the two are complementary (spec study vs implementation of the same spec), not duplicates. If #657 changes classification, this card is to be reassessed before merge.

## Absorption notes (proposal only)
killinchu already decodes Remote ID and signs receipts via DSSE; the leaders above are the normative sources (envelope spec, decoder reference, Remote ID standard) for future decoder and verification work. No code change proposed in this PR.

## Provenance
Pre-write probes 2026-11-23: no docs/LEADERS-STUDY.md on main; #657 reconfirmed open as the sibling implementation card (complementary classification preserved); open dependabot/CI PRs #661/#660/#659 untouched; sources web-verified live 2026-11-23 (W26G citation receipts).

PROPOSE-ONLY: merge requires a separate explicit owner go. Ruling nonce: W26-C2T3-EXEC-20261123.
