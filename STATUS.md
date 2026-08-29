# STATUS.md — killinchu (Defense / Counter-UAS)

**Updated:** 2026-08-29
**Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17**

HF Space: <https://huggingface.co/spaces/SZLHOLDINGS/killinchu>

---

## What's Live

- **HF Space** — killinchu is deployed and operational on Hugging Face Spaces
- **`/api/killinchu/healthz`** — returns service liveness
- **`/api/build-info`** — reports `OBSERVED` only for a valid 40-hex
  `SZL_GIT_SHA`; the source-bound deploy verifies it against the exact GitHub
  commit before declaring success
- **`/api/public-risk-status`** — publishes the dated conditional Option A
  public-Space exception, enforced controls, startup-captured source identity,
  and the exceptions that remain explicitly unavailable
- **`/console`** — existing Killinchu Edge Verdict Console
- **`/code` and `/chat`** — explicit HTTP 302 compatibility aliases to
  `/console`, not separate products
- **`/sign`** — Wire D DSSE signing endpoint
- **FAA Remote ID decoder** — live
- **ADS-B Mode-S decoder** — live
- **MAVLink decoder** — live
- **STANAG 4609 decoder** — live
- **Geofence + policy scoring** — telemetry scored as claim against geofence polygons; Λ-receipt emitted
- **`/viz/*`** — Map panel SPA with live telemetry feed

## What's Experimental

- **STANAG 4609 full-frame decode** — partial implementation; metadata extraction live, full video analytics experimental
- **Adaptive geofence updates** — geofence polygons currently static; dynamic update mechanism under development

## Evidence Boundaries

- **`/.well-known/szl-source.json`** — startup-captured runtime source revision with an explicit GitHub OIDC receipt reference when available; Hugging Face repository revision remains unclaimed unless the platform exposes it
  and `/api/build-info` is the companion runtime identity probe. The historical
  2026-07-16 structural snapshot remains in the repository as preserved evidence;
  it is not served as the current runtime identity.
- **Runtime source identity receipt** — after an exact-source deployment, the
  deploy workflow attests the generated deployment manifest with GitHub OIDC
  and writes only its non-secret reference to the Space. `/api/build-info`
  reports `receipt_minted=true` only when that reference matches the
  startup-captured source SHA, manifest digest, attestation ID, and canonical
  GitHub attestation URL. Before that post-deploy gate completes, the receipt
  remains explicitly `UNAVAILABLE`.
- **Conditional public-risk decision** — the dated Option A authority artifact
  still records its original pre-attestation exception and remains fail-closed
  while its other CI, rights, image, organ-inventory, and branch-protection
  evidence is unproved. A live release receipt does not silently rewrite that
  separate authority record.
- **Historical archive privacy** — pre-v2 backing shards are not claimed
  rewritten or erased; the public recent API withholds legacy platform rows.
- Human on the loop; physical effector action is SIMULATED. The public Space
  does not command a live weapon.

## What's Deprecated

- **Earlier track-decoder reference** — an earlier track-decoder reference predates killinchu; its decoder architecture is preserved but it is not the primary defense flagship.

---

*Doctrine v11 — 749/14/163 — c7c0ba17*
*2026-08-28: live Space probes of `/api/killinchu/healthz`, `/drones/database`, and `/lambda` timed out while runtime stage still reported RUNNING. Merging this to main retriggers `hf-sync.yml` (workflow_dispatch / push to main) so the Space is source-bound and restarted.*
*2026-08-29: anonymous probes of `https://szlholdings-killinchu.hf.space/api/build-info`, `/healthz`, and `/api/killinchu/readyz` timed out. Hub runtime stage still reported RUNNING. GitHub main `62cb7359edd7b49cb62eacc76d71a29f2cfa7ee4`. Hub SHA `bf5a6c3cb03b2e0c098f9b30b0f1454094f8e402`. hf-sync run `33226520547` (push) published files then failed `Attest exact running commit, bytes, and smoke routes`. Physical effector remains SIMULATED. Merging this to main retriggers `hf-sync.yml` via push only.*
