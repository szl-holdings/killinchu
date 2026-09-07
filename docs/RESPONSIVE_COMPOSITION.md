# Source-native responsive composition

This follows the merged Killinchu #433 integration without replaying its branch or changing the product controller. The existing Universal Frontend v1 generator remains the sole writer for `static/szl-universal-frontend.css`.

## Ownership

`design/szl-public-experience-v3.css` is the reviewed source input for the v3.1 presentation styles, retained from the canonical SZL responsive template. The v1 generator combines its existing base with that input, emits the managed CSS, and regenerates the existing file-digest manifest. Repeating `--apply` must preserve every managed byte. Updating only a rendered stylesheet or only its digest is not a valid source upgrade.

The product prefix of `static/truth-cop.js` is byte-identical to the reviewed host. It retains the same-origin observation request and the unavailable/training disclosures. The appended presentation block is validated separately against no-network/no-storage rules, while the whole JavaScript file is syntax-checked. Unknown host-prefix changes require a separate product-authority review; there is no generic exception for a file named truth-cop.js. No second navigation, endpoint, effect, or publisher is added.

## Verification

```sh
python scripts/apply_hf_universal_frontend_v1.py --apply
python scripts/apply_hf_universal_frontend_v1.py --check
python scripts/verify_public_experience_host.py
python -m pytest -q tests/test_hf_universal_frontend_v1.py tests/test_public_experience_host.py
```

The existing Public Experience job runs these contracts and verifies that repeated generation leaves the tracked files unchanged. Existing Universal Frontend, source drift, security, Docker, and repository checks remain in force. A source-contract receipt is not a browser or deployment verdict. Protected merge, canonical publication, exact live source readback, and browser acceptance remain required before claiming operational improvement.

The lexical presentation checks catch accidental network/storage additions; they are not a JavaScript sandbox or a general malicious-code detector. Independent review and the product's other checks remain required.
