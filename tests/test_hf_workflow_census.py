"""Census of every workflow in this repository that holds a Hugging Face secret.

The rules are read from the workflow files themselves, so a new or renamed HF
workflow is covered without editing this test:

* One Hub credential. ``secrets.HF_TOKEN`` is the only HF secret name, except
  the receipt-training job, which keeps its environment-scoped
  ``TRAINING_HF_TOKEN`` (docs/RECEIPT_TRAINING_RUNBOOK.md).
* One lock key per asset. Every job that can see an HF secret runs under a
  ``hf-write/<type>/SZLHOLDINGS/<id>`` or ``hf-write/org/SZLHOLDINGS`` group
  (workflow level or job level), never keyed by ``github.event_name`` and
  never cancel-in-progress. Read-only jobs are the only exception, and they
  must not join a ``hf-write/*`` group or call a Hub write API.
* One Hub client. Every workflow that installs the shared hash-locked Hub
  client pins the same ``szl-holdings/.github`` commit and lock blob as the
  reusable Space deployer.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

HF_SECRET = re.compile(r"secrets\.([A-Z0-9_]*(?:HF|HUGGING)[A-Z0-9_]*)")
ALLOWED_SECRET = "HF_TOKEN"
# Environment-scoped least-privilege training credential (hf-training).
SECRET_EXCEPTIONS = {"TRAINING_HF_TOKEN": {("hf-estate-ops.yml", "receipt-training")}}
# Jobs that authenticate to read only. They never write the Hub.
READ_ONLY_JOBS = {
    ("hf-drift-check.yml", "drift-check"),
    ("hf-token-preflight.yml", "assert-hf-token"),
}
LOCK = re.compile(
    r"^hf-write/(?:org/SZLHOLDINGS|(?:model|dataset|space|kernel)/SZLHOLDINGS/[A-Za-z0-9._-]+)$"
)
HUB_WRITE_CALLS = re.compile(
    r"\b(?:upload_file|upload_folder|create_commit|create_repo|delete_repo|delete_file|"
    r"restart_space|pause_space|add_space_secret|add_space_variable|request_space_hardware|"
    r"update_repo_settings|super_squash_history)\s*\("
)


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _group(concurrency: Any) -> tuple[str | None, Any]:
    if concurrency is None:
        return None, None
    if isinstance(concurrency, str):
        return concurrency, None
    return concurrency.get("group"), concurrency.get("cancel-in-progress")


def _hf_jobs() -> list[tuple[str, str, dict[str, Any], dict[str, Any], set[str]]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        workflow = _load(path)
        for job_id, job in (workflow.get("jobs") or {}).items():
            text = yaml.safe_dump(job, sort_keys=True)
            names = set(HF_SECRET.findall(text))
            # Workflow-level env is visible to every job.
            names |= set(HF_SECRET.findall(yaml.safe_dump(workflow.get("env") or {})))
            if names:
                found.append((path.name, job_id, workflow, job, names))
    return found


def test_census_finds_the_space_deployer() -> None:
    jobs = {(name, job_id) for name, job_id, *_ in _hf_jobs()}
    assert ("hf-sync.yml", "deploy") in jobs
    assert READ_ONLY_JOBS <= jobs


def test_every_hf_job_uses_the_one_hub_credential() -> None:
    for name, job_id, _workflow, _job, secrets in _hf_jobs():
        for secret in secrets:
            if secret == ALLOWED_SECRET:
                continue
            assert (name, job_id) in SECRET_EXCEPTIONS.get(secret, set()), (
                f"{name}:{job_id} uses secrets.{secret}; the one Hub credential is secrets.HF_TOKEN"
            )


def test_every_hf_writing_job_holds_a_canonical_asset_lock() -> None:
    for name, job_id, workflow, job, _secrets in _hf_jobs():
        workflow_group, workflow_cancel = _group(workflow.get("concurrency"))
        job_group, job_cancel = _group(job.get("concurrency"))
        groups = [g for g in (workflow_group, job_group) if g]
        for group in groups:
            assert "event_name" not in group, f"{name}:{job_id} lock is keyed by event_name"
        if (name, job_id) in READ_ONLY_JOBS:
            assert not any(g.startswith("hf-write/") for g in groups), (
                f"read-only {name}:{job_id} must not join a hf-write lock"
            )
            source = (WORKFLOWS / name).read_text(encoding="utf-8")
            assert not HUB_WRITE_CALLS.search(source), f"read-only {name} calls a Hub write API"
            continue
        held = []
        if workflow_group and LOCK.match(workflow_group):
            assert workflow_cancel is False, f"{name} hf-write lock must not cancel in progress"
            held.append(workflow_group)
        if job_group and job_group.startswith("hf-write/"):
            assert job_cancel is False, f"{name}:{job_id} hf-write lock must not cancel in progress"
            if LOCK.match(job_group):
                held.append(job_group)
        assert held, f"{name}:{job_id} sees an HF secret but holds no hf-write/<type>/<id> lock"


def test_the_space_is_serialized_by_one_lock_across_its_writers() -> None:
    space_lock = "hf-write/space/SZLHOLDINGS/killinchu"
    for name in ("hf-sync.yml", "activate-intel-archive.yml"):
        assert _group(_load(WORKFLOWS / name).get("concurrency"))[0] == space_lock
    transfer = _load(WORKFLOWS / "hf-cpu-basic-capacity-transfer.yml")
    assert _group(transfer.get("concurrency"))[0] == "hf-write/org/SZLHOLDINGS"
    assert _group(transfer["jobs"]["transfer"].get("concurrency"))[0] == space_lock


def test_one_pinned_hub_client_across_hf_workflows() -> None:
    deploy = (WORKFLOWS / "hf-sync.yml").read_text(encoding="utf-8")
    pin = re.search(r"reusable-hf-deploy\.yml@([0-9a-f]{40})", deploy)
    assert pin, "hf-sync.yml must call the reusable deployer pinned by a 40-hex commit"
    shas: set[str] = set()
    blobs: set[str] = set()
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        shas |= set(re.findall(r"SHARED_PUBLISHER_SHA:\s*([0-9a-f]{40})", text))
        blobs |= set(re.findall(r"SHARED_LOCK_BLOB:\s*([0-9a-f]{40})", text))
        for line in text.splitlines():
            if re.search(r"pip install", line) and re.search(r"huggingface[-_]hub", line, re.I):
                raise AssertionError(f"{path.name} installs the Hub client outside the shared lock")
    assert shas == {pin.group(1)}, f"shared publisher commits drifted: {sorted(shas)}"
    assert len(blobs) == 1, f"shared lock blobs drifted: {sorted(blobs)}"


def test_space_deploy_proves_the_public_health_route() -> None:
    import json

    deploy = _load(WORKFLOWS / "hf-sync.yml")["jobs"]["deploy"]["with"]
    assert deploy["hf-repo"] == "SZLHOLDINGS/killinchu"
    smoke = json.loads(deploy["smoke-paths"])
    assert "/healthz" in smoke and "/api/killinchu/healthz" in smoke
