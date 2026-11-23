# killinchu domain leader study r1 (propose-only)

Date: 2026-11-22. Method: web-verified 2026 leaders. Documentation only: no code, CI, config, or existing-PR status changes. All absorb actions are FUTURE and non-authorizing; implementation and merges remain separately reviewed and gated by the signature wall.

## Domain: runtime DSSE signer capability reporting

## Leaders studied (web-verified 2026-11-22)

1. **in-toto Attestation Framework**: DSSE envelope standard + predicate types for verification. [Normative spec](https://in-toto.io/specification/).
2. **Sigstore cosign** attestation verification. [Normative docs](https://docs.sigstore.dev/cosign/attest/).

## Absorb actions (FUTURE PROPOSALS, non-authorizing)

1. (in-toto) Capability reports derive from verified attestation envelopes, never self-asserted.
2. (cosign policy) Verify signer capability against a stated policy; fail closed with a receipted reason when the signer capability is unproven, stale, or un-verifiable.
Read-only alignment: open PR #655 (report runtime DSSE signer capability fail closed) encodes this family; no status or validation claim is made here.

## Sources (accessed 2026-11-22)

- in-toto specification: https://in-toto.io/specification/ (normative spec)
- Sigstore cosign attest docs: https://docs.sigstore.dev/cosign/attest/ (normative docs)

## Do not do

Do not merge, bypass the signature wall, or claim implementation beyond this card.
