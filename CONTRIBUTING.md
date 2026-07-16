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

## Repository architecture (read before your first PR)

The full layout is in [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) and
[`DEVELOPER_ONBOARDING.md`](./DEVELOPER_ONBOARDING.md). The essentials:

### Run it locally

```bash
git clone https://github.com/szl-holdings/killinchu.git && cd killinchu
pip install fastapi uvicorn httpx cryptography pydantic numpy
pip install pyModeS pymavlink            # optional: real protocol decoders
PORT=7860 uvicorn serve:app --host 0.0.0.0 --port 7860 --reload
# then open http://127.0.0.1:7860/elite  (the operator console)
```

### The `register()` pattern

`serve.py` is the boot entry and route-assembly point. A user-visible surface is a
self-contained module beside `serve.py` that exposes a top-level
`register(app, ns="killinchu")` function. `serve.py` imports it (try/except-guarded so a
missing optional module degrades honestly instead of crashing the Space) and calls:

```python
_szl_<name>.register(app, ns="killinchu")   # adds routes; returns an honest status dict
```

**Ordering is load-bearing:** every `register(...)` call must run **before** the SPA
catch-all (`/{path} -> index.html`). FastAPI matches routes in declaration order, so a
surface registered after the catch-all is shadowed by the SPA and 404s client-side.

### Byte-identical shared modules

Many `szl_*.py` (and a few `a11oy_*.py`) modules are vendored into **both** a11oy and
killinchu and must stay **byte-identical**. If you edit a shared module in one repo, make
the *identical* edit in the sibling repo in the same change — **including comment and
docstring edits**. The `shared-file-drift` CI guard fails the build on any new divergence;
deliberate, documented exceptions live in `.github/shared-file-drift-allow.txt`.

### Doctrine hard-gates (CI will not let you weaken these)

- **`locked = 8`** — exactly 8 locked-proven formulas `{F1,F4,F7,F11,F12,F18,F19,F22}`. Never inflate the count.
- **Λ = Conjecture 1** — Λ-uniqueness is a conjecture, never described as a theorem.
- **No user-visible codenames** and no marketing-superlative tokens — enforced by the banned-token grep gate; factual claims need an adjacent citation.
- **Never commit a key** — `gitleaks` blocks secrets; receipts are an honest PLACEHOLDER when `SZL_COSIGN_PRIVATE_PEM` is absent.

### How the CI guards work

Guards run on every PR and push to `main`. Key ones: `doctrine.yml` (banned-token /
overclaim), `shared-file-drift.yml` (shared modules identical), `copy-sync-lockstep-guard.yml`
(every imported module is in the Dockerfile COPY set + HF mirror set), `gitleaks.yml`,
`dco.yml` (sign-off), `ci.yml`, `codeql.yml`, `scorecard.yml`, `sbom.yml`. If a guard trips
on a comment or doc you added, **fix your text — never weaken the gate.**

— killinchu maintainers
