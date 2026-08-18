# Killinchu Hugging Face Universal Frontend v1

This contract applies the estate-wide SZLHOLDINGS frontend doctrine to the canonical Killinchu source tree without introducing a second Hugging Face writer.

## Source-native integration

The adapter reads the existing Hugging Face `README.md` front matter and discovers the declared application entry point. It supports Static, Gradio, Streamlit, and React/Vite source layouts and refuses an ambiguous or unsupported tree.

The committed manifest records:

- observed SDK and framework
- exact application entry point
- exact universal CSS location
- bounded card metadata
- viewport and accessibility invariants
- SHA-256 digests for every managed file

## User-interface contract

The frontend must provide:

- five viewport classes: 360, 390, 768, 1024, and 1440 CSS pixels
- 44-pixel minimum interactive targets
- no document-level horizontal overflow
- safe wrapping for hashes, revisions, receipts, and evidence identifiers
- mobile-safe action stacking
- keyboard-visible focus
- reduced-motion behavior
- responsive images, media, tables, dialogs, and framework containers

## Hugging Face card contract

- `short_description` is at most 60 characters.
- `fullWidth` is enabled.
- the Hub header uses the compact `mini` presentation.
- existing SDK and app-file ownership remain authoritative.

## Promotion boundary

This change does not alter model weights, datasets, secrets, signer keys, runtime hardware, persistent storage, visibility, branch protection, or training state. It also does not add a Hugging Face deployment writer. The existing canonical source-to-Space workflow remains the only promotion path.

Completion requires protected merge, canonical deployment, and public five-viewport readback through the estate-wide Space frontend census.
