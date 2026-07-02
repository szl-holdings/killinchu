# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
#
# test_corpus_autosync_notify.py — REAL, committed guard for the knowledge-corpus
# auto-sync notify classification.
#
# The "Notify the team of the auto-sync outcome" step in
# .github/workflows/knowledge-corpus-autosync.yml picks exactly ONE of three
# Slack/ntfy messages (PR opened / BLOCKED by the honesty gate / PR refused —
# open manually) from `steps.pr.outputs.result` and `steps.gate.outcome`, and
# stays SILENT on the no-op paths (branch already exists, no drift, webhook not
# configured). That branching was untested: a future refactor of the PR/gate
# steps could silently mis-classify — post "opened PR" with an empty URL, go
# silent when it should alert, or double-announce an already-open PR — and
# nobody would notice until a real incident.
#
# This drives the ACTUAL bash classifier — extracted verbatim from the workflow
# YAML, not a re-implementation — under `bash` for every outcome, with `curl`
# shadowed by a fake on PATH (so no network is touched) that records the POSTed
# payload. `jq` (used to JSON-encode the message) is the real one, so the test
# also proves the payload is valid JSON with a `text` field. Asserts, per
# outcome:
#   * pr_opened      -> posts the ":arrows_counterclockwise:" PR message w/ URL
#   * gate failure   -> posts the ":no_entry:" BLOCKED message
#   * pr_refused     -> posts the ":warning:" open-manually message w/ compare URL
#   * branch_exists  -> stays SILENT (that PR was already announced)
#   * no drift       -> stays SILENT
#   * no webhook set -> stays SILENT and does NOT error
#   * non-2xx webhook-> fails loud (delivery failure is never swallowed)
#
# NO MOCK of the logic under test: the real `if/elif/else` classifier runs
# exactly as it does on the runner. Only the final HTTP POST is intercepted.
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
    pytest.skip("pyyaml not installed", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "knowledge-corpus-autosync.yml"
NOTIFY_STEP_NAME = "Notify the team of the auto-sync outcome"

# A fake `curl` placed first on PATH: it records the --data payload to
# $CURL_CAPTURE, writes the response body to the -o target, and prints the HTTP
# code from $FAKE_CURL_CODE (default 200) — mimicking `curl -w '%{http_code}'`.
FAKE_CURL = r"""#!/usr/bin/env bash
outfile=""
data=""
prev=""
for arg in "$@"; do
  case "$prev" in
    -o) outfile="$arg" ;;
    --data) data="$arg" ;;
  esac
  prev="$arg"
done
[ -n "$outfile" ] && printf '%s' "fake-curl-response-body" > "$outfile"
if [ -n "${CURL_CAPTURE:-}" ] && [ -n "$data" ]; then
  printf '%s' "$data" > "$CURL_CAPTURE"
fi
printf '%s' "${FAKE_CURL_CODE:-200}"
"""


def _load_notify_step() -> dict:
    """Return the real notify step dict from the workflow YAML."""
    assert WORKFLOW.is_file(), f"workflow not found: {WORKFLOW}"
    data = yaml.safe_load(WORKFLOW.read_text())
    steps = data["jobs"]["auto-sync"]["steps"]
    for step in steps:
        if step.get("name") == NOTIFY_STEP_NAME:
            return step
    raise AssertionError(
        f"notify step {NOTIFY_STEP_NAME!r} not found — did the step get renamed?"
    )


def _run_notify(env_overrides: dict, code: str = "200"):
    """Execute the real notify `run:` script under bash with a fake curl.

    Returns (CompletedProcess, payload_dict_or_None). payload is the JSON body
    that would have been POSTed to the webhook, or None if the classifier stayed
    silent (no POST attempted).
    """
    step = _load_notify_step()
    script = step["run"]
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        bindir = tdp / "bin"
        bindir.mkdir()
        curl = bindir / "curl"
        curl.write_text(FAKE_CURL)
        curl.chmod(0o755)

        capture = tdp / "capture.json"
        script_file = tdp / "notify.sh"
        script_file.write_text(script)

        # Every var the step's `env:` block would set — provided (possibly
        # empty) so the script's `set -u` never trips on an unbound reference.
        env = {
            "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
            "CURL_CAPTURE": str(capture),
            "FAKE_CURL_CODE": code,
            "SLACK_WEBHOOK_URL": "https://hooks.example/relay",
            "RUN_URL": "https://github.com/szl-holdings/killinchu/actions/runs/123",
            "REPO": "szl-holdings/killinchu",
            "GATE_OUTCOME": "",
            "PR_RESULT": "",
            "PR_URL": "",
            "COMPARE_URL": "",
        }
        env.update(env_overrides)

        proc = subprocess.run(
            ["bash", str(script_file)],
            env=env,
            capture_output=True,
            text=True,
        )
        payload = None
        if capture.exists():
            payload = json.loads(capture.read_text())
        return proc, payload


# ---------------------------------------------------------------------------
# The three "alerting" outcomes: each must post exactly its own message.


def test_pr_opened_posts_the_pr_message_with_url():
    pr_url = "https://github.com/szl-holdings/killinchu/pull/7"
    proc, payload = _run_notify(
        {"PR_RESULT": "pr_opened", "GATE_OUTCOME": "success", "PR_URL": pr_url}
    )
    assert proc.returncode == 0, proc.stderr
    assert payload is not None, "pr_opened must POST a message"
    text = payload["text"]
    assert ":arrows_counterclockwise:" in text
    assert "opened sync PR" in text
    assert pr_url in text, "the PR URL must be in the message, not empty"
    # Must not be mis-classified as either other message.
    assert ":no_entry:" not in text
    assert ":warning:" not in text


def test_gate_failure_posts_the_blocked_message():
    # Gate fails -> pr step is skipped, so PR_RESULT is empty and gate=failure.
    proc, payload = _run_notify({"GATE_OUTCOME": "failure", "PR_RESULT": ""})
    assert proc.returncode == 0, proc.stderr
    assert payload is not None, "a gate failure must POST the BLOCKED message"
    text = payload["text"]
    assert ":no_entry:" in text
    assert "BLOCKED" in text
    assert ":arrows_counterclockwise:" not in text


def test_pr_refused_posts_the_open_manually_message_with_compare_url():
    compare = (
        "https://github.com/szl-holdings/killinchu/compare/"
        "main...auto/knowledge-corpus-sync-deadbeef?expand=1"
    )
    proc, payload = _run_notify(
        {"PR_RESULT": "pr_refused", "GATE_OUTCOME": "success", "COMPARE_URL": compare}
    )
    assert proc.returncode == 0, proc.stderr
    assert payload is not None, "pr_refused must POST the open-manually message"
    text = payload["text"]
    assert ":warning:" in text
    assert "refused" in text
    assert compare in text, "the compare URL must be in the message"
    assert ":arrows_counterclockwise:" not in text


# ---------------------------------------------------------------------------
# The silent (no-op) outcomes: never post.


def test_branch_exists_stays_silent():
    # The idempotent path: a PR for this exact sha was already opened/announced.
    proc, payload = _run_notify(
        {"PR_RESULT": "branch_exists", "GATE_OUTCOME": "success"}
    )
    assert proc.returncode == 0, proc.stderr
    assert payload is None, "branch_exists must NOT re-announce an open PR"


def test_no_drift_stays_silent():
    # No drift -> gate step skipped (outcome 'skipped'), pr step skipped (empty).
    proc, payload = _run_notify({"PR_RESULT": "", "GATE_OUTCOME": "skipped"})
    assert proc.returncode == 0, proc.stderr
    assert payload is None, "an in-sync run must not post any message"


def test_no_webhook_configured_is_silent_and_not_an_error():
    proc, payload = _run_notify(
        {"SLACK_WEBHOOK_URL": "", "PR_RESULT": "pr_opened", "GATE_OUTCOME": "success"}
    )
    assert proc.returncode == 0, proc.stderr
    assert payload is None, "no webhook secret => no POST, and must not fail"


# ---------------------------------------------------------------------------
# Delivery integrity.


def test_non_2xx_webhook_response_fails_loud():
    proc, payload = _run_notify(
        {
            "PR_RESULT": "pr_opened",
            "GATE_OUTCOME": "success",
            "PR_URL": "https://github.com/szl-holdings/killinchu/pull/9",
        },
        code="500",
    )
    assert payload is not None, "the POST is still attempted"
    assert proc.returncode != 0, "a non-2xx webhook response must fail the step"


def test_step_level_guard_keeps_no_op_paths_silent():
    """Belt-and-suspenders: the step's own `if:` must exclude the branch_exists
    and no-drift runs (so the classifier never even runs for them), while
    always() keeps the BLOCKED/refused failure paths posting."""
    cond = _load_notify_step()["if"]
    assert "always()" in cond
    assert "drift" in cond and "'true'" in cond
    assert "branch_exists" in cond
