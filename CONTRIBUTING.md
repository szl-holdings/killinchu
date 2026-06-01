# Contributing to killinchu

Thank you for your interest in **killinchu** — the Andean Drone Intelligence
counter-UAS rule engine. This repository is part of the
[SZL Holdings](https://github.com/szl-holdings) platform: physics-grounded,
governed AI decision infrastructure for regulated environments.

## Contribution model

killinchu is **source-available** software, published for evaluation, audit,
and reference under the terms in [`LICENSE`](./LICENSE). It is governed by
[SZL Doctrine v11](https://github.com/szl-holdings/.github/blob/main/DOCTRINE_V11.md).

## Reporting issues

- **Bugs / correctness:** open an issue with a minimal reproduction.
- **Security:** do NOT open a public issue. See [`SECURITY.md`](./SECURITY.md).

## Pull requests

1. Sign your commits with the Developer Certificate of Origin
   (`git commit -s`). The DCO check enforces a `Signed-off-by` trailer whose
   author matches the commit author.
2. Keep changes additive and minimal; do not alter Doctrine-locked numbers.
3. Ensure all CI workflows pass (CI, CodeQL, Scorecard, SBOM, DCO) before
   requesting review.

## Governance pre-flight

Every claim in code, docs, or PR description must be citable. We do not merge
"fake green" — skipped or stubbed checks presented as passing will be rejected
per Doctrine v11.

— killinchu maintainers
