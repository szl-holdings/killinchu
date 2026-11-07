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

The scan step now exports the image with GNU tar and runs ``oscap`` as root
(``sudo OSCAP_PROBE_ROOT=...``). An empty export is not evaluated. A result
file with no pass or fail still fails the run.

This drives the REAL ``run:`` scripts of the scan step and the run-summary step,
extracted from the workflow YAML, under ``bash -e`` (the Actions default shell).
``sudo``, ``oscap`` and ``docker`` are fakes on PATH; the counting, the JSON
and the pass/fail decision are the workflow's own.
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

# FAKE_SCAP picks what the scanner does when invoked as oscap (via sudo):
#   crash       - chroot is denied, the failure mode of a non-root scan, so
#                 no XCCDF results are written
#   results     - XCCDF with 3 pass, 2 fail and a score; exit 2 (rules failed)
#   unevaluated - XCCDF is written but no rule is evaluated as pass or fail
# Calling oscap-docker is a regression: the results and unevaluated modes
# refuse it.
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
    [ "$name" = "oscap" ] || exit 1
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
    [ "$name" = "oscap" ] || exit 1
    echo '<TestResult><rule-result><result>notapplicable</result></rule-result></TestResult>' > "$results"
    exit 0 ;;
esac
"""

# sudo on the runner is passwordless and accepts `sudo VAR=value command`.
# The fake drops sudo's own flags, exports VAR=value arguments, and execs the rest.
FAKE_SUDO = r"""#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; break ;;
    -*) shift ;;
    *=*) export "$1"; shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

# `docker export` must emit a tar the scan can accept. FAKE_EXPORT=empty is the
# failed-export case (no rootfs). The default is a minimal rootfs with the two
# paths the workflow requires before it will run oscap.
FAKE_DOCKER = r"""#!/usr/bin/env bash
if [ "${1:-}" = "export" ]; then
  if [ "${FAKE_EXPORT:-rootfs}" = "empty" ]; then
    tar -cf - -T /dev/null
  else
    tmp=$(mktemp -d)
    mkdir -p "$tmp/etc" "$tmp/usr/lib" "$tmp/var/lib/rpm"
    printf 'NAME="Red Hat Enterprise Linux"\n' > "$tmp/usr/lib/os-release"
    ln -s ../usr/lib/os-release "$tmp/etc/os-release"
    printf 'sqlite\n' > "$tmp/var/lib/rpm/rpmdb.sqlite"
    tar -C "$tmp" -cf - .
    rm -rf "$tmp"
  fi
fi
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


def _run(mode: str, *, export: str = "rootfs"):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bindir = tmp / "bin"
        bindir.mkdir()
        for tool, body in (("oscap-docker", FAKE_SCANNER), ("oscap", FAKE_SCANNER),
                           ("sudo", FAKE_SUDO), ("docker", FAKE_DOCKER)):
            (bindir / tool).write_text(body, encoding="utf-8")
            (bindir / tool).chmod(0o755)
        gh_output = tmp / "github_output"
        gh_output.write_text("", encoding="utf-8")
        base = {"PATH": f"{bindir}:{os.environ.get('PATH', '')}", **_job_env()}

        scan = _bash(_step(step_id="scan")["run"], tmp,
                     {**base, "GITHUB_OUTPUT": str(gh_output), "GITHUB_SHA": "0" * 40,
                      "FAKE_SCAP": mode, "FAKE_EXPORT": export})
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
                        "SCORE": outputs.get("score", ""),
                        "REASON": outputs.get("reason", "")})
        return scan, outputs, summary_json, record, step_summary.read_text()


def _executable_lines(script: str) -> str:
    return "\n".join(line for line in script.splitlines()
                     if line.strip() and not line.lstrip().startswith("#"))


def test_record_step_reads_the_scan_outputs():
    assert _step(name=RECORD_STEP)["env"] == {
        "COMPLETED": "${{ steps.scan.outputs.completed }}",
        "PASS": "${{ steps.scan.outputs.pass }}",
        "FAIL": "${{ steps.scan.outputs.fail }}",
        "SCORE": "${{ steps.scan.outputs.score }}",
        "REASON": "${{ steps.scan.outputs.reason }}",
    }


def test_scan_evaluates_exported_rootfs_as_root():
    script = _executable_lines(_step(step_id="scan")["run"])
    assert "oscap-docker" not in script
    assert "sudo tar --xattrs --xattrs-include='*' -x -C rootfs" in script
    assert 'sudo OSCAP_PROBE_ROOT="$PWD/rootfs" oscap xccdf eval' in script
    assert "not an evaluable rootfs" in script
    install = _executable_lines(_step(name="Install OpenSCAP + SCAP Security Guide")["run"])
    assert "openscap-utils" not in install
    assert "openscap-scanner" in install


def test_crashed_scanner_reports_no_counts_and_fails_the_run():
    scan, outputs, summary, record, step_summary = _run("crash")
    # The scan step itself still succeeds, so the artifact upload runs.
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "chroot failed" in scan.stdout
    assert "Evaluating" in scan.stdout
    assert outputs["completed"] == "false"
    assert outputs["pass"] == "" and outputs["fail"] == "" and outputs["score"] == ""
    assert "chroot" in outputs["reason"]
    assert summary["scan_completed"] is False
    assert summary["rules_passed"] is None and summary["rules_failed"] is None
    assert summary["score_pct"] is None
    assert summary["failure_reason"] == outputs["reason"]
    assert record.returncode != 0, "a scan with no result must fail the run"
    assert "::error title=SCAP scan produced no result::" in record.stdout
    assert "chroot" in record.stdout
    assert "No scan result" in step_summary
    assert "chroot" in step_summary
    assert "| rules passed |" not in step_summary


def test_scan_with_results_is_recorded_and_passes():
    scan, outputs, summary, record, step_summary = _run("results")
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "Refusing to evaluate an empty tree" not in scan.stdout
    assert outputs["pass"] == "3" and outputs["fail"] == "2"
    assert outputs["score"] == "60.000000" and outputs["completed"] == "true"
    assert outputs["reason"] == ""
    assert summary["scan_completed"] is True
    assert summary["failure_reason"] is None
    assert (summary["rules_passed"], summary["rules_failed"], summary["score_pct"]) == (3, 2, 60.0)
    assert record.returncode == 0, record.stdout + record.stderr
    assert "| 3 | 2 | 60.000000 |" in step_summary


def test_xccdf_without_evaluated_rules_is_not_a_result():
    _scan, outputs, summary, record, step_summary = _run("unevaluated")
    assert outputs["completed"] == "false"
    # Real zero counts from a file that exists, but not a scan result.
    assert (summary["rules_passed"], summary["rules_failed"]) == (0, 0)
    assert summary["scan_completed"] is False
    assert "no rule evaluated as pass or fail" in outputs["reason"]
    assert record.returncode != 0
    assert "No scan result" in step_summary


def test_empty_image_export_is_not_scanned():
    scan, outputs, summary, record, step_summary = _run("results", export="empty")
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "Refusing to evaluate an empty tree" in scan.stdout
    assert "Evaluating" not in scan.stdout
    assert outputs["completed"] == "false"
    assert outputs["pass"] == "" and outputs["fail"] == ""
    assert "empty tree" in outputs["reason"]
    assert summary["scan_completed"] is False
    assert summary["rules_passed"] is None
    assert record.returncode != 0
    assert "empty tree" in step_summary
    assert "| rules passed |" not in step_summary


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
