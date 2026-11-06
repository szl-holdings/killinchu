# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""The SCAP STIG workflow must not write to main or pass with a failed scan.

``scap-scan.yml`` used to commit ``scan_summary.json`` and run
``git push || echo "push skipped"`` on every push to main. main is protected,
so the push was rejected on every run from 2026-06-02 on and the echo kept the
run green. The scan had also stopped producing results (oscap-docker crashes on
the image's absolute symlinks, and the offline fallback cannot chroot as the
runner user), yet the step wrote ``rules_passed: 0`` / ``score_pct: 0`` and the
run passed.

This drives the REAL ``run:`` scripts of the scan step and the run-summary step,
extracted from the workflow YAML, under ``bash -e`` (the Actions default shell).
``oscap-docker``, ``oscap`` and ``docker`` are fakes on PATH; the counting, the
JSON and the pass/fail decision are the workflow's own.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - CI installs pyyaml
    pytest.skip("pyyaml not installed", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SCAP = WORKFLOWS / "scap-scan.yml"
RECORD_STEP = "Record the scan outcome in the run summary"
PROFILE = "xccdf_org.ssgproject.content_profile_stig"

# One fake serves as both oscap-docker and oscap (it dispatches on its name).
# FAKE_SCAP picks what the scanner does:
#   crash       - the 2026-11-03 run: oscap-docker raises and the offline
#                 fallback cannot chroot, so neither writes XCCDF results
#   results     - oscap-docker writes XCCDF with 3 pass, 2 fail and a score
#   unevaluated - XCCDF is written but no rule is evaluated as pass or fail
FAKE_SCANNER = r"""#!/usr/bin/env bash
name="$(basename "$0")"
if [ "$name" = "oscap" ] && [ "${1:-}" = "xccdf" ] && [ "${2:-}" = "generate" ]; then
  [ -f "${4:-}" ] || { echo "OpenSCAP Error:: Unable to open file: '${4:-}'" >&2; exit 1; }
  echo "<html>report</html>"; exit 0
fi
results=""; prev=""
for arg in "$@"; do
  [ "$prev" = "--results" ] && results="$arg"
  prev="$arg"
done
case "${FAKE_SCAP:-crash}" in
  crash)
    if [ "$name" = "oscap-docker" ]; then
      echo "tarfile.AbsoluteLinkError: 'etc/alternatives/libnssckbi.so.x86_64' is a link to an absolute path" >&2
    else
      echo "E: oscap: chroot failed: Operation not permitted" >&2
    fi
    exit 1 ;;
  results)
    [ "$name" = "oscap-docker" ] || exit 1
    {
      echo '<TestResult>'
      for r in pass pass pass fail fail notapplicable; do
        echo "<rule-result><result>$r</result></rule-result>"
      done
      echo '<score system="urn:xccdf:scoring:default" maximum="100.000000">60.000000</score>'
      echo '</TestResult>'
    } > "$results"
    exit 2 ;;
  unevaluated)
    [ "$name" = "oscap-docker" ] || exit 1
    echo '<TestResult><rule-result><result>notapplicable</result></rule-result></TestResult>' > "$results"
    exit 0 ;;
esac
"""

# `docker export` must emit a valid (empty) tar stream for the fallback's
# `| tar -x`; create and rm are no-ops.
FAKE_DOCKER = r"""#!/usr/bin/env bash
if [ "${1:-}" = "export" ]; then tar -cf - -T /dev/null; fi
exit 0
"""


def _job() -> dict:
    return yaml.safe_load(SCAP.read_text(encoding="utf-8"))["jobs"]["scap"]


def _step(*, step_id: str | None = None, name: str | None = None) -> dict:
    for step in _job()["steps"]:
        if (step_id and step.get("id") == step_id) or (name and step.get("name") == name):
            return step
    raise AssertionError(f"scap-scan.yml: step {step_id or name!r} not found")


def _job_env() -> dict:
    env = _job()["env"]
    # PROFILE is a workflow expression; the default is what a push run uses.
    return {"SSG_VERSION": env["SSG_VERSION"], "IMAGE": env["IMAGE"], "PROFILE": PROFILE}


def _bash(script: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    path = cwd / "step.sh"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(["bash", "-e", str(path)], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=60)


def _run(mode: str):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bindir = tmp / "bin"
        bindir.mkdir()
        for tool, body in (("oscap-docker", FAKE_SCANNER), ("oscap", FAKE_SCANNER),
                           ("docker", FAKE_DOCKER)):
            (bindir / tool).write_text(body, encoding="utf-8")
            (bindir / tool).chmod(0o755)
        gh_output = tmp / "github_output"
        gh_output.write_text("", encoding="utf-8")
        base = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", **_job_env()}

        scan = _bash(_step(step_id="scan")["run"], tmp,
                     {**base, "GITHUB_OUTPUT": str(gh_output), "GITHUB_SHA": "0" * 40,
                      "FAKE_SCAP": mode})
        outputs = dict(line.split("=", 1) for line in gh_output.read_text().splitlines()
                       if "=" in line)
        summary_json = json.loads(
            (tmp / ".compliance" / "scap-reports" / "scan_summary.json").read_text())

        # The record step reads the scan outputs through its `env:` block.
        step_summary = tmp / "step_summary.md"
        step_summary.write_text("", encoding="utf-8")
        record = _bash(_step(name=RECORD_STEP)["run"], tmp,
                       {**base, "GITHUB_STEP_SUMMARY": str(step_summary),
                        "COMPLETED": outputs.get("completed", ""),
                        "PASS": outputs.get("pass", ""), "FAIL": outputs.get("fail", ""),
                        "SCORE": outputs.get("score", "")})
        return scan, outputs, summary_json, record, step_summary.read_text()


def test_record_step_reads_the_scan_outputs():
    assert _step(name=RECORD_STEP)["env"] == {
        "COMPLETED": "${{ steps.scan.outputs.completed }}",
        "PASS": "${{ steps.scan.outputs.pass }}",
        "FAIL": "${{ steps.scan.outputs.fail }}",
        "SCORE": "${{ steps.scan.outputs.score }}",
    }


def test_crashed_scanner_reports_no_counts_and_fails_the_run():
    scan, outputs, summary, record, step_summary = _run("crash")
    # The scan step itself still succeeds, so the artifact upload runs.
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "offline rootfs fallback" in scan.stdout
    assert outputs == {"pass": "", "fail": "", "score": "", "completed": "false"}
    assert summary["scan_completed"] is False
    assert summary["rules_passed"] is None and summary["rules_failed"] is None
    assert summary["score_pct"] is None
    assert record.returncode != 0, "a scan with no result must fail the run"
    assert "::error title=SCAP scan produced no result::" in record.stdout
    assert "No scan result" in step_summary
    assert "| rules passed |" not in step_summary


def test_scan_with_results_is_recorded_and_passes():
    scan, outputs, summary, record, step_summary = _run("results")
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "offline rootfs fallback" not in scan.stdout
    assert outputs == {"pass": "3", "fail": "2", "score": "60.000000", "completed": "true"}
    assert summary["scan_completed"] is True
    assert (summary["rules_passed"], summary["rules_failed"], summary["score_pct"]) == (3, 2, 60.0)
    assert record.returncode == 0, record.stdout + record.stderr
    assert "| 3 | 2 | 60.000000 |" in step_summary


def test_xccdf_without_evaluated_rules_is_not_a_result():
    _scan, outputs, summary, record, step_summary = _run("unevaluated")
    assert outputs["completed"] == "false"
    # Real zero counts from a file that exists, but not a scan result.
    assert (summary["rules_passed"], summary["rules_failed"]) == (0, 0)
    assert summary["scan_completed"] is False
    assert record.returncode != 0
    assert "No scan result" in step_summary


def test_workflow_never_commits_or_pushes():
    steps = _job()["steps"]
    for step in steps:
        run = step.get("run", "")
        assert "git push" not in run and "git commit" not in run, step.get("name")
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout.get("with", {}).get("persist-credentials") is False


def test_no_workflow_swallows_a_failed_git_push():
    """Static guard for the next copy of `git push || echo ...`."""
    pattern = re.compile(r"git\s+push\b[^\n]*\|\|")
    offenders = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.lstrip().startswith("#") and pattern.search(line):
                offenders.append(f"{path.name}:{number}")
    assert offenders == [], f"a rejected git push is swallowed: {offenders}"
