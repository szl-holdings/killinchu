# Receipt-model training operator runbook

This runbook covers the generic, source-bound SFT workflow implemented by
`scripts/dispatch_receipt_training.py`, `scripts/receipt_training_worker.py`,
and `.github/workflows/hf-estate-ops.yml`.

The workflow can produce an evaluated **candidate** under an immutable commit.
It does not approve that candidate, promote it, deploy it, route production
traffic to it, or establish a clinical, biological, safety, efficacy, or other
real-world claim. A passing training-loss threshold is an internal technical
gate only.

As checked into source on 2026-09-12, this lane is deliberately **not runnable
against a real provider**. `APPROVED_RUNTIMES` is intentionally empty. The only
schema-admitted runtime is the reserved `training.invalid/receipt-training`
sentinel used by provider-free tests, and the dispatcher rejects that sentinel
before any provider input read, reservation, or paid job submission. A real
image/job cannot pass until a separately reviewed source change adds one exact,
attested image digest and its exact dependency/flavor contract.

## Non-negotiable operating boundary

- Run the training operation only through the manual GitHub Actions workflow on
  the exact signed `main` commit named in the manifest.
- Do not launch from a pull request, branch, local shell, scheduled workflow, or
  mutable remote script URL.
- Do not substitute a branch, tag, `latest` image, floating package version, or
  unpinned Hub revision for an exact digest or commit.
- Do not retry automatically after a reservation or submission outcome becomes
  uncertain. Investigate provider and repository state first.
- Treat every output as `CANDIDATE_EVALUATED` with `promotion: NOT_GRANTED`.
- Never paste `TRAINING_HF_TOKEN`, another token, a private key, or raw private
  data into the manifest, workflow inputs, logs, approvals, or receipts.

## What must exist before an operator considers submission

### GitHub control plane

1. The intended source commit is merged to `main` in
   `szl-holdings/killinchu` and GitHub reports its signature as verified.
2. All 14 source-admission Check Runs below have passed for that exact commit:

   - `Canonical mixed-source card contract`
   - `test (3.11)`
   - `test (3.12)`
   - `public-experience-contract`
   - `Gitleaks secret scan`
   - `Trivy filesystem scan`
   - `Grype CVE gate (fail on HIGH/CRITICAL)`
   - `Analyze (python)`
   - `Analyze (actions)`
   - `High-severity security regressions`
   - `Shared source files in sync with a11oy`
   - `check / doctrine`
   - `overclaim / Governed surfaces are honest (Theorem U citation rule)`
   - `offline-contract`

   Each exact name must occur once in the bounded latest-check snapshot, bind
   the manifest's exact head SHA, report `completed`/`success`, and identify the
   GitHub Actions app with app ID `15368`. Legacy commit statuses are not
   accepted as substitutes. Each gate reads the full bounded latest-check
   snapshot twice and requires the two canonical snapshots to be identical.
   The dispatcher then runs that app-bound gate twice: once before provider
   preflight and reservation, and again after the durable reservation
   immediately before paid submission. It also verifies the signed current
   `main` commit and exact worker bytes on both passes. This is exact-source
   evidence; it does not independently prove that the repository has an
   adequate branch-protection or ruleset configuration.
3. A GitHub Environment named `hf-training` exists. Confirm its current
   deployment protections, allowed branches, reviewers or other approval rules,
   and secret scope in GitHub itself. Merely naming the environment in YAML does
   not prove that provider-side protections are configured.

   A live readback on **2026-09-12** returned HTTP 404 for `hf-training`. That
   time-stamped observation may drift, and a 404 alone cannot distinguish an
   absent environment from insufficient visibility. It nevertheless means this
   build has not established current independent-reviewer protection or a
   correctly scoped environment token; those remain external submission
   blockers until an authorized readback proves them.
4. The environment contains a secret named `TRAINING_HF_TOKEN`. The workflow
   maps it to `HF_TOKEN`; the dispatcher then supplies it to the Hugging Face Job
   as a secret. The token must be least-privilege and capable of:

   - reading the exact base-model and dataset revisions;
   - reading and committing to the one profile-mapped output model repository;
   - submitting, inspecting, and cancelling Jobs in the `SZLHOLDINGS`
     namespace.

   Secret presence does not prove that those permissions are correct. Provider
   preflight and readback provide the first operational evidence.
5. The workflow's org-wide provider-mutation concurrency group remains enabled
   with `cancel-in-progress: false`. This serializes this workflow with other
   mutations using the same group; it is not a universal lock on every possible
   Hugging Face writer.
6. The separate estate-operations job names a GitHub Environment called
   `hf-provider-mutation`. That environment also requires actual configured and
   currently read-back deployment protections; the YAML name is not proof of
   reviewers, branch restrictions, token isolation, or provider authority.
7. The dispatcher installation uses a 13-wheel, direct-and-transitive closure
   pinned in `.github/requirements-dispatch.lock` for CPython 3.12/Linux x86-64.
   Installation requires hashes and binary wheels, then runs `pip check`.
   The provider-free `offline-contract` source-admission job separately installs
   its five-wheel `pytest==8.4.2` closure from
   `.github/requirements-training-contract.lock` with the same hash-required,
   wheel-only, `pip check` controls. Thus both the dispatcher and contract-test
   installs are hash locked; their distinct lock files cover distinct jobs.
   `TRAINING_HF_TOKEN` and the workflow `GH_TOKEN` are scoped only to the later
   reserve/submit/monitor step, after dependency installation; they are not
   exposed to the installer step. This reduces exposure but does not attest the
   image, runner, packages, account, or tokens.

### Evidence and approvals outside the manifest validator

The manifest contains an `authorization.reference` and the SHA-256 digest of an
authorization artifact. Those fields are operator assertions. The software
checks their syntax and binds them into receipts; it does **not** retrieve the
artifact, validate its signer, prove independent human identity, verify data
rights, or enforce a provider budget.

Accordingly, provider budget authority and the claimed external authorization
remain **unverified** in this build even when manifest validation succeeds.
They require current provider/account evidence and an independently verifiable
approval record outside this workflow before any paid submission.

Before submission, retain evidence for all applicable rows below in an
access-controlled system of record. Hash the final, immutable artifact bytes,
not a rendered preview or mutable URL.

| Evidence or approval | Minimum content | Enforced by this workflow? |
| --- | --- | --- |
| Source approval | Exact Git commit, reviewed diff, required-check result, verified signature | Partly. Exact signed current `main` and worker bytes are checked; reviewer identity and policy sufficiency are external. |
| Base-model approval | Exact Hub repo and commit, license/terms, access authority, intended-use restrictions | Exact revision is checked; rights and terms are not. |
| Dataset provenance and rights | Exact repo/commit/files, origin, license, consent or other lawful basis, redistribution/training rights, retention/deletion duties, accountable owner | Exact bytes, rows, and schema are checked; rights and provenance are not. |
| Privacy and sensitive-data review | Classification, minimization, de-identification evidence, prohibited-content screening, incident path, applicable legal or regulatory review | No. |
| Split and evaluation plan | Split-construction method, independence rationale, contamination review, task metrics, acceptance criteria, known limitations | Duplicate text and identical effective token sequences are rejected across splits; semantic independence and metric adequacy are not proved. |
| Image and dependency supply chain | Image digest, build provenance, SBOM, vulnerability scan, signatures/attestations, exact installed distribution versions | Digest and exact runtime versions are checked; SBOM, signer trust, and vulnerability policy are external. |
| Budget authorization | Named accountable operator, approved hardware, current provider price evidence with timestamp, maximum duration, incident/cancellation owner | Numeric assertions are checked for consistency; price, spend, and authority are not provider-enforced here. |
| Candidate evaluation authority | Named evaluator, required offline/safety/domain tests, evaluation datasets and versions, independent witness when required | No. This workflow checks only finite train/eval loss and the declared eval-loss ceiling. |
| Promotion and deployment approval | Candidate commit, evaluation bundle, rollback plan, deployment target, change/release decision, signatures | No. Publication explicitly records `NOT_GRANTED`. |

If two-person or independent approval is required, use a detached-signing,
KMS/HSM, or approval provider that authenticates distinct principals and retain
its verification receipt. A reference plus a digest entered by one workflow
operator is not multi-person approval.

## Exact manifest bindings

The JSON input must use schema `szl.training.v1` and remain at or below the
dispatcher's 32 KiB input limit. The worker also has a 64 KiB manifest limit,
but the smaller dispatcher limit controls this workflow.

### Source

- `source.repository` is exactly `szl-holdings/killinchu`.
- `source.revision` is the nonzero, 40-lowercase-hex SHA of the current signed
  `main` commit. The dispatcher checks current `main` twice: before reservation
  and immediately before the billable submission.
- `source.worker_sha256` is the SHA-256 of the exact bytes of
  `scripts/receipt_training_worker.py` at that revision. Local checkout bytes,
  GitHub content readback, and the manifest digest must agree.

If `main` moves after reservation but before submission, submission fails and
the reservation remains consumed. Create a newly reviewed manifest with a new
run ID and refreshed bindings only after investigation.

### Base model and dataset

- `base_model.revision` and `dataset.revision` are exact nonzero 40-hex Hub
  commits, not `main`, a tag, or a branch.
- Dataset files are UTF-8 JSON Lines. Each nonempty line is exactly
  `{"text":"..."}` with no extra fields.
- `train_sha256` and `eval_sha256` cover the exact raw file bytes. Row counts and
  file sizes must match the manifest.
- Train and evaluation paths and hashes must differ. Normalized duplicate text
  within a split, normalized overlap across splits, duplicate effective token
  sequences, and effective token overlap across splits fail closed. Exact
  token-sequence equality is a mechanical leakage check; it is not evidence of
  semantic held-out independence or absence of related/contaminated examples.
- These mechanical checks do not prove factual quality, consent, lawful use,
  representative sampling, absence of memorization risk, or independent
  evaluation.

### Runtime

There is currently no source-approved production runtime. The source-reviewed
`APPROVED_RUNTIMES` mapping is empty, so no real image digest is admissible.
The `training.invalid/receipt-training` reference followed by `@sha256:` and 64
consecutive lowercase `4` digits is a reserved, non-runnable unit-test fixture:
it can exercise validation-only contracts with the fixture dependency set and
flavor, but provider preflight always rejects it. Do not interpret validation of
that sentinel as launch readiness.

- `runtime.image` must be a lowercase container reference pinned by
  `@sha256:<64 lowercase hex>`. A tag-only reference is rejected.
- `runtime.dependencies` lists the exact installed versions for `torch`,
  `transformers`, `trl`, `peft`, `datasets`, `huggingface-hub`, `trackio`,
  `accelerate`, and `safetensors`. The worker compares the complete set before
  training. The image must already contain them; there is no runtime `pip`
  installation.
- Allowed hardware flavors are `t4-small`, `t4-medium`, `l4x1`, `a10g-small`,
  `a10g-large`, and `a100-large`.
- `timeout_seconds` is between 300 and 14,400 seconds. Select it from a measured
  dry-run estimate that includes model/dataset loading, evaluation, and
  candidate publication time.

The training implementation disables remote model code, requires safetensors,
applies the manifest's LoRA/SFT parameters, logs Trackio locally, checks the
declared step count, and evaluates before publication. Those controls improve
reproducibility; they do not make the resulting model production-approved.

### Profile and output

The output repository is fixed by profile:

| Profile | Required `output.repo_id` |
| --- | --- |
| `khipu-frontier-35-2b` | `SZLHOLDINGS/khipu-frontier-35-2b` |
| `forge-frontier-35-2b` | `SZLHOLDINGS/forge-frontier-35-2b` |
| `willay-3` | `SZLHOLDINGS/willay-3` |

`output.parent_commit` is the exact current `main` commit of that output model
repository before reservation. The dispatcher uses compare-and-swap commits;
drift fails closed.

### Authorization and cost fields

- `authorization.reference` names the external approval or budget record.
- `authorization.sha256` binds its exact immutable bytes.
- `max_hourly_usd` and `max_cost_usd` are JSON numbers. The validator requires
  `max_cost_usd` to cover at least `max_hourly_usd * timeout_seconds / 3600`.

These fields are an operator-declared planning envelope. The workflow does not
query a current provider tariff, reserve funds, watch a billing meter, or impose
a provider-side monetary hard cap. The provider can bill according to its
actual plan and runtime. Verify current pricing and account limits at submission
time and retain that evidence with the authorization artifact.

## Deliberately invalid manifest template

The template below is valid JSON but intentionally fails admission. Every
`REPLACE_ME` value must be replaced from reviewed evidence. Numeric placeholders
must become JSON numbers, not quoted strings. Do not paste this template into a
training dispatch as-is.

```json
{
  "schema_version": "szl.training.v1",
  "run_id": "REPLACE_ME_NEW_UUID_V4",
  "profile": "REPLACE_ME_PROFILE",
  "source": {
    "repository": "szl-holdings/killinchu",
    "revision": "REPLACE_ME_40_HEX_SIGNED_CURRENT_MAIN_SHA",
    "worker_sha256": "REPLACE_ME_64_HEX_EXACT_WORKER_BYTES"
  },
  "base_model": {
    "repo_id": "REPLACE_ME_OWNER/REPLACE_ME_BASE_MODEL",
    "revision": "REPLACE_ME_40_HEX_BASE_MODEL_COMMIT"
  },
  "dataset": {
    "repo_id": "REPLACE_ME_OWNER/REPLACE_ME_DATASET",
    "revision": "REPLACE_ME_40_HEX_DATASET_COMMIT",
    "train_file": "REPLACE_ME_TRAIN.jsonl",
    "train_sha256": "REPLACE_ME_64_HEX_EXACT_TRAIN_BYTES",
    "train_rows": "REPLACE_ME_INTEGER_ROW_COUNT",
    "eval_file": "REPLACE_ME_EVAL.jsonl",
    "eval_sha256": "REPLACE_ME_64_HEX_EXACT_EVAL_BYTES",
    "eval_rows": "REPLACE_ME_INTEGER_ROW_COUNT",
    "max_file_bytes": "REPLACE_ME_INTEGER_1_TO_67108864"
  },
  "runtime": {
    "image": "REPLACE_ME_IMAGE@sha256:REPLACE_ME_64_HEX_IMAGE_DIGEST",
    "flavor": "REPLACE_ME_ALLOWED_FLAVOR",
    "timeout_seconds": "REPLACE_ME_INTEGER_300_TO_14400",
    "dependencies": {
      "torch": "REPLACE_ME_X.Y.Z",
      "transformers": "REPLACE_ME_X.Y.Z",
      "trl": "REPLACE_ME_X.Y.Z",
      "peft": "REPLACE_ME_X.Y.Z",
      "datasets": "REPLACE_ME_X.Y.Z",
      "huggingface-hub": "REPLACE_ME_X.Y.Z",
      "trackio": "REPLACE_ME_X.Y.Z",
      "accelerate": "REPLACE_ME_X.Y.Z",
      "safetensors": "REPLACE_ME_X.Y.Z"
    }
  },
  "hyperparameters": {
    "seed": "REPLACE_ME_INTEGER",
    "r": "REPLACE_ME_INTEGER_1_TO_256",
    "lora_alpha": "REPLACE_ME_INTEGER_1_TO_1024",
    "lora_dropout": "REPLACE_ME_NUMBER_0_TO_0.5",
    "lr": "REPLACE_ME_NUMBER_1E-8_TO_0.01",
    "max_steps": "REPLACE_ME_INTEGER_1_TO_100000",
    "max_seq": "REPLACE_ME_INTEGER_16_TO_32768",
    "batch_size": "REPLACE_ME_INTEGER_1_TO_64",
    "gradient_accumulation_steps": "REPLACE_ME_INTEGER_1_TO_1024",
    "weight_decay": "REPLACE_ME_NUMBER_0_TO_1",
    "warmup_ratio": "REPLACE_ME_NUMBER_0_TO_0.5",
    "target_modules": [
      "REPLACE_ME_ONE_OR_MORE_ALLOWED_MODULES"
    ],
    "precision": "REPLACE_ME_BF16_FP16_OR_FP32"
  },
  "evaluation": {
    "max_eval_loss": "REPLACE_ME_REVIEWED_NUMERIC_THRESHOLD"
  },
  "output": {
    "repo_id": "REPLACE_ME_EXACT_PROFILE_MAPPED_OUTPUT_REPO",
    "parent_commit": "REPLACE_ME_40_HEX_CURRENT_OUTPUT_MAIN_COMMIT"
  },
  "authorization": {
    "reference": "REPLACE_ME_IMMUTABLE_APPROVAL_REFERENCE",
    "sha256": "REPLACE_ME_64_HEX_APPROVAL_ARTIFACT_BYTES",
    "max_cost_usd": "REPLACE_ME_JSON_NUMBER_NOT_PROVIDER_HARD_CAP",
    "max_hourly_usd": "REPLACE_ME_JSON_NUMBER_FROM_CURRENT_PRICE_EVIDENCE"
  }
}
```

Allowed `target_modules` values are `q_proj`, `k_proj`, `v_proj`, `o_proj`,
`gate_proj`, `up_proj`, and `down_proj`. The list must contain unique values.

## Review and validation before the billable boundary

1. Have the accountable operator compare every manifest value against the
   retained evidence bundle. Do not copy hashes from an earlier run.
2. Recompute all SHA-256 values over exact bytes. Confirm all 40-hex revisions
   resolve to the expected immutable commits.
3. Confirm `run_id` is a new nonzero canonical UUID and has never been used in
   the output repository.
4. Confirm the selected profile maps to the exact output repository in the table
   above.
5. Confirm the output head still equals `output.parent_commit`.
6. Confirm dataset record schema, row counts, rights, privacy review, split
   rationale, and evaluation plan.
7. Confirm the image digest, exact installed dependency versions, hardware fit,
   timeout, current provider pricing, and approved cost envelope.
8. Confirm the GitHub Environment and token scope by current provider readback.
9. Review the manifest in validation-only mode first. Omitting `--submit` emits
   `VALIDATED_NOT_SUBMITTED` and performs no training or Hub mutation:

   ```powershell
   python -m scripts.dispatch_receipt_training --manifest .\reviewed-manifest.json --receipt-dir .\validation-receipts
   ```

   A successful syntax validation is not source, provider, rights, budget, or
   deployment approval.

## Manual GitHub Actions dispatch

There is intentionally no copy-paste command in this runbook that launches a
paid job.

At the final operator checkpoint, open **Actions → HF estate ops (manual) → Run
workflow** in GitHub and verify all of the following before using the UI's final
submit control:

- branch is `main`;
- operation is `launch-train-job`;
- profile equals the manifest's `profile`;
- `training_manifest` is the complete, reviewed compact JSON;
- the displayed current commit equals `source.revision`;
- environment approval and current budget authority are present.

The dispatcher independently requires `workflow_dispatch`, repository
`szl-holdings/killinchu`, ref `refs/heads/main`, and `GITHUB_SHA` equal to the
manifest source revision. A mismatch fails before provider submission.

## Reservation, submission, and uncertainty semantics

The first provider mutation is a durable compare-and-swap reservation in the
output model repository:

```text
.training-reservations/<run_id>.json
```

It binds the run ID, canonical manifest SHA-256, and source revision. The worker
must pass the reservation commit as `parent_commit` for candidate publication;
the separate provider-readback limitation is documented below. The reservation
is never deleted or rewritten, including after failure or uncertainty.

The dispatcher then re-verifies signed current GitHub `main` and exact worker
bytes immediately before calling the billable Jobs API. Once it reaches either
`RESERVATION_INTENT` or `SUBMISSION_INTENT`, an exception can mean the remote
operation succeeded even when no response returned. Consequently:

- `RESERVATION_OUTCOME_UNKNOWN` means **do not reserve or submit again**;
- `SUBMISSION_OUTCOME_UNKNOWN` means **do not submit again**;
- `FAILED_OR_UNKNOWN` means cancellation was requested or unconfirmed and
  automatic retry is forbidden.

Investigate the output repository, Hugging Face Jobs list and logs, GitHub run,
and phase receipts. Reconcile an observed remote job or commit. If a fresh run
is later approved, create a new UUID, refresh every mutable binding, and issue a
new authorization record. Never reuse the old run ID or overwrite its
reservation.

## Timeouts, cancellation, and the hard-kill limitation

There are multiple bounded layers:

- Hugging Face receives `runtime.timeout_seconds` as the provider-side timeout.
- The dispatcher monitors until that timeout plus 120 seconds.
- The dispatcher process guard allows the runtime timeout plus 600 seconds.
- The GitHub training job is bounded at 270 minutes, which is above the
  manifest's four-hour maximum.

On an observed terminal failure, unknown state, verification failure, or monitor
timeout, the dispatcher attempts provider cancellation and records whether the
request was made. Cancellation is not guaranteed. `SIGKILL`, abrupt runner
loss, host failure, or a network partition can prevent cleanup and receipt
upload. In those cases, the provider-side timeout is the independent backstop,
but there can be delay and billable runtime before it takes effect. Neither the
GitHub timeout nor the declared cost fields is a monetary hard kill.

## Phase receipts and their meaning

The dispatcher writes create-only JSON phase receipts and the workflow uploads
them even when a later step fails. Possible states include:

- `VALIDATED_NOT_SUBMITTED`
- `RESERVATION_INTENT`, `RESERVED`, or `RESERVATION_OUTCOME_UNKNOWN`
- `SUBMISSION_INTENT`, `SUBMITTED`, or `SUBMISSION_OUTCOME_UNKNOWN`
- `FAILED_OR_UNKNOWN`
- `CANDIDATE_VERIFIED`
- `DISPATCH_FAILED`

Each receipt binds the state, timestamp, run ID when known, canonical manifest
digest, `authority: OPERATOR_SUPPLIED_UNVERIFIED`, and
`promotion: NOT_GRANTED`. Relevant provider IDs and immutable commits are added
by phase. Receipts are sanitized and uploaded with a 90-day GitHub Actions
artifact retention setting.

These files are an operational audit trail, not an independently signed witness
or immutable ledger. The artifact can expire or be deleted, its 90-day setting
does not establish external write-once retention, and a missing final receipt
can mean runner loss rather than proof that a remote operation did not occur.
Export it to an approved durable evidence system and retain the GitHub run
identity, artifact digest, provider readbacks, output commits, and independent
approval receipts together.

## Candidate publication and verification

Training happens before publication. Finite `train_loss` and `eval_loss` must be
present, and `eval_loss` must not exceed the manifest threshold. Only then may
the worker create one compare-and-swap commit beneath:

```text
candidates/<run_id>/
```

The commit contains safetensors LoRA adapter material and allowlisted tokenizer
or configuration artifacts, plus:

- `manifest.json` — canonical admitted manifest;
- `evaluation.json` — measured loss record and passed threshold;
- `artifacts.json` — exact size and SHA-256 inventory for the bounded candidate
  artifacts it covers;
- `receipt.json` — source, manifest, output parent, reservation commit,
  evaluation, artifact-manifest digest, unverified authority label, and explicit
  non-promotion state.

The dispatcher does not trust `COMPLETED` alone. It requires one bound worker
result, reads the immutable output commit, verifies the receipt digest and
bindings, validates finite metrics, independently reads and hashes each
allowlisted candidate artifact, and compares the published manifest and
evaluation record with expected values. It structurally parses the safetensors
header and payload without deserializing tensors: the eight-byte little-endian
header length must name a duplicate-free JSON header no larger than 8 MiB, and
only floating F16/BF16/F32 tensors with consistent positive shapes, offsets,
non-overlap, and complete contiguous payload coverage pass. It separately binds
the published PEFT adapter config's LoRA/causal-LM type, no-bias mode, rank,
alpha, dropout, and exact target-module membership to the admitted
hyperparameters. Before inventory and publication, the worker replaces PEFT's
local snapshot reference with the manifest's exact base-model repo and commit,
atomically writes and re-reads that normalized config, and the dispatcher
independently requires those exact `base_model_name_or_path` and `revision`
bindings. Benign extra PEFT metadata is permitted.

The provider adapter also takes bounded, full recursive tree snapshots at the
reservation and candidate revisions. It requires output `main` to equal the
candidate commit both before and after those snapshot reads, requires the run
prefix to be absent at the reservation, preserves every reservation file
identity (path, size, Git blob ID, and LFS SHA-256/size when present), and
permits exactly the inventoried candidate files plus `artifacts.json` and
`receipt.json` as new files. Each snapshot is capped at 20,000 entries and 2 MiB
of aggregate path bytes. Any deletion, modification, unrelated addition,
duplicate/invalid path, unexpected SDK entry, or oversized tree fails closed.

This tree-delta closure is not independent proof that the reservation is the
candidate commit's direct Git parent. The pinned `huggingface-hub==0.36.2` API
used here does not expose commit-parent metadata. The worker submits a
compare-and-swap publication with `parent_commit` set to the reservation, while
the dispatcher independently proves the resulting bounded content delta. If
direct-parent proof is a policy requirement, capture it from a separately
trusted Git-graph/provider interface that exposes and authenticates parent
metadata. A successful automated final state is `CANDIDATE_VERIFIED`.

`CANDIDATE_VERIFIED` proves only that the automated source/input/output contract
completed for those exact bytes and that the declared loss gate passed. It does
not prove model quality, robustness, security, absence of memorization,
domain-specific fitness, scientific validity, legal approval, independent human
witnessing, production readiness, or deployment.

## Required post-run decision

After any run, preserve and reconcile:

1. the GitHub workflow run, exact source SHA, and required-check evidence;
2. all phase receipts and the GitHub artifact digest;
3. the reservation commit and, if present, immutable candidate commit;
4. Hugging Face job identity, terminal provider state, and bounded relevant
   logs;
5. exact candidate artifact hashes and evaluation receipt;
6. the external authorization, rights, privacy, supply-chain, budget, and
   evaluation evidence bundle.

A separate governed process must evaluate the candidate and issue any promotion
or deployment approval. That process must name the exact candidate commit and
artifacts. Until that happens, leave the candidate under its run-scoped prefix
with `promotion: NOT_GRANTED`; do not copy it to a production root, deploy it to
Ollama or another serving stack, publish it as an approved model, or use it to
support clinical or biological claims.
