# Proposal: killinchu upgrade plan from leader-study loop-1

- Date: 2026-11-23 (UTC)
- Status: PROPOSE-ONLY. This document does not authorize any merge or deploy. DO NOT MERGE without owner signature; the estate merge wall is owner-gated.
- Provenance: typed by the W26 leader-study loop-1 council (Kimi governing; Astra + Sol advisory), grounded in repo facts (GitHub GraphQL) and domain-leader research dated 2026-11-22/23. Published receipts: HF SZLHOLDINGS/wave-logs mesh/2026-11-22/frontier-push/w26-solo-build/ commit 8c01e7ed. Leader research marked DRAFT until independently verified.
- Honest scope: authored from the README head + repo facts only; no code changed; secrets-free; no unbacked claims.

## Measured archetype
Governed counter-UAS command-and-evidence platform: synthetic public tracks, fusion, ROE/BFT/DSSE interdiction records, and OSINT receipting, with no public effector.

## Prior art: normative publications
- (none cited by the governing seat for this repo; canonical leader links below)

## Prior art: community/framework leaders
- Lattice (Anduril) - DRAFT domain notes describe an autonomous sensor-fusion C2 mesh with software-defined defense and an open SDK architecture, making it a comparison point for killinchu's tracks, fusion, and command surface.
- Leonidas (Epirus) - DRAFT domain notes describe a high-power microwave counter-swarm hard-kill family, relevant as an effector-side boundary and integration comparison rather than evidence that killinchu has an effector.
- Dedrone (Dedrone) - DRAFT domain notes describe RF and visual drone detection, tracking, and airspace awareness, providing a sensor and detection comparison for killinchu's fusion and evidence workflows.

## Measured gaps vs the leaders
- No verified hardware-in-the-loop or live sensor-integration evidence is provided for comparison with operational detection and C2 systems.
- The public repository explicitly has no public effector; authorized effector adapters, interlocks, and hardware integration evidence remain outside the supplied material.
- RF and visual detection performance, track quality, latency, false-alarm rates, and counter-swarm capacity are not measured in the supplied facts.
- The relationship between the counter-UAS description and the README's OSINT/evidence-collection positioning needs a verified architecture and capability matrix.
- Human authorization gates, fail-closed behavior, doctrine enforcement, airgap operation, and red-team coverage are not demonstrated by the supplied repository facts.
- Kill-chain provenance and receipt integrity are described, but factual accuracy, measurement, production readiness, and end-to-end audit verification remain unestablished.
- Open SDK, third-party sensor interoperability, deployment scale, and multi-node fusion behavior are not verified against Lattice or Dedrone.
- The repository's test command and operational ecosystem-stage label are not evidence of passing tests, field performance, or production readiness.

## Ranked upgrade plan (dosed, small-PR sized)
1. Add a small CI workflow that runs the documented pytest command on a clean checkout and publishes the exact commit, command, environment, and result as a receipt; report failures without converting them into capability claims. | expected effect: Creates reproducible readback for the repository's basic verification claim while preserving the distinction between MEASURED and PASS. | effort: small | priority: 1
2. Add a versioned capability-and-boundary matrix mapping tracks, fusion, ROE, BFT, DSSE, OSINT receipts, airgap claims, and effector exclusions to concrete source modules and tests; mark unsupported entries DRAFT. | expected effect: Resolves positioning ambiguity and prevents documentation or badges from being mistaken for verified operational capability. | effort: small | priority: 2
3. Implement one synthetic sensor-to-track-to-fusion-to-ROE-decision fixture with a schema-validated provenance receipt, including source identity, timestamps, authorization state, and hashes. | expected effect: Provides an executable end-to-end evidence path for kill-chain provenance without introducing real targeting or effector capability. | effort: small-to-medium | priority: 3
4. Add fail-closed contract tests for missing identity, stale or malformed observations, hash mismatch, unavailable policy state, and absent human authorization; assert denial and an explicit audit outcome. | expected effect: Turns governance doctrine into testable behavior and exposes silent degradation or unsafe default-allow paths. | effort: small-to-medium | priority: 4
5. Define a vendor-neutral sensor adapter interface and one synthetic RF or visual adapter fixture with recorded inputs, normalization rules, and uncertainty fields. | expected effect: Creates a concrete interoperability baseline for comparison with sensor-fusion and detection leaders without claiming live RF or visual performance. | effort: medium | priority: 5
6. Add a deterministic hardware-in-the-loop simulation seam using recorded sensor frames and a mock effector that can only report authorization requests, never actuate hardware. | expected effect: Enables repeatable timing and integration experiments while retaining the operator-owned effector boundary. | effort: medium | priority: 6
7. Publish a benchmark harness for synthetic detection and fusion scenarios that reports track continuity, latency, false associations, and missed detections with datasets and commit identifiers. | expected effect: Replaces ungrounded performance comparisons with reproducible measurements and explicit limitations. | effort: medium | priority: 7
8. Add an offline/airgap test profile that blocks network access, uses local fixtures and dependencies, and records any attempted external connection as a failure. | expected effect: Provides evidence for the airgap topic and identifies hidden network dependencies. | effort: small-to-medium | priority: 8
9. Create a minimal adversarial test pack for spoofed source identity, replayed observations, conflicting tracks, receipt tampering, and ROE boundary cases. | expected effect: Establishes an initial red-team harness focused on evidence integrity and authorization rather than unverified operational resilience. | effort: medium | priority: 9
10. Document a separate, disabled-by-default effector integration contract requiring customer authorization, operator confirmation, hardware interlocks, and independent safety review; include no weapon-control implementation. | expected effect: Clarifies the path and prerequisites for future authorized integration without implying that a public effector exists. | effort: small | priority: 10

## Advisory seat notes
- ASTRA verdict: REJECT; 
- SOL verdict: REJECT; 

## DRAFT warnings
- All domain-leader descriptions and takeaways are CTO-lane web research dated 2026-11-22 and remain DRAFT until independently verified.
- No publication title, author list, or year was supplied; the publications list is therefore empty rather than populated with inferred NATO, NIST, or academic citations.
- Only repository metadata and a README excerpt were supplied; source code, tests, CI results, receipts, schemas, and deployment configuration were not inspected.
- The README's verify-in-60-seconds command is an instruction, not evidence that cloning or tests succeed.
- The ecosystem-stage value operational, doctrine-v11 topics, SLSA-L1 tags, and pinned status are metadata claims, not verified assurance or readiness evidence.
- The description's counter-UAS capabilities and \u039b = Conjecture 1 are not technically defined or validated by the supplied material.
- The README calls killinchu an OSINT and evidence-collection organ; its equivalence to a complete counter-UAS platform is unverified.
- No supplied evidence verifies sensor fusion quality, ROE correctness, BFT behavior, DSSE semantics, cryptographic signing, receipt verification, airgap enforcement, or fail-closed authorization.
- Comparisons with Anduril Lattice, Epirus Leonidas, and Dedrone are architectural hypotheses only; no benchmark or hands-on product evaluation was provided.
- No public effector is claimed by the repository facts, and this audit does not establish safe or authorized integration with any counter-UAS effector.
- External URLs, commit-pinned links, brand hashes, datasets, and demo availability were not independently fetched or validated.
- Proposed upgrade actions and effort estimates are DRAFT recommendations, not statements that the corresponding controls already exist.
