"""Execute the real workflow shell with inert validation commands."""

import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/publish-intel-archive-card.yml"


def step_script(name):
    step = WORKFLOW.read_text(encoding="utf-8").split(f"      - name: {name}\n", 1)[1]
    step = step.split("\n      - name: ", 1)[0]
    lines = []
    for line in step.split("        run: |\n", 1)[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("\n".join(lines))


def bash_executable():
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required to execute the Ubuntu workflow contract")
    return bash


@pytest.mark.parametrize("failure_at", range(7))
def test_each_validation_failure_survives_logging_and_blocks_publication(tmp_path, failure_at):
    run_validation(tmp_path, failure_at=failure_at)


def test_log_capture_failure_blocks_publication(tmp_path):
    run_validation(tmp_path, failure_at=0, fail_tee=True)


def run_validation(tmp_path, *, failure_at, fail_tee=False):
    env = dict(os.environ)
    env.update(
        EVIDENCE_DIR=(tmp_path / "evidence").as_posix(),
        GITHUB_OUTPUT=(tmp_path / "output").as_posix(),
        CALL_LOG=(tmp_path / "calls").as_posix(),
        FAIL_AT=str(failure_at),
        HF_PUBLISHER_SITE="inert-test-site",
    )
    # No package install, Python execution, Git operation, or network call occurs.
    stubs = """
    n=0
    validation_command() {
      n=$((n + 1))
      printf '%s\\n' "$n" >> "$CALL_LOG"
      if [ "$n" = "$FAIL_AT" ]; then return 37; fi
      return 0
    }
    python() { validation_command; }
    git() { validation_command; }
    """
    if fail_tee:
        stubs += '\ntee() { cat > /dev/null; return 43; }\n'
    observed = subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-c", stubs + step_script("Render and test the exact source contract")],
        env=env, capture_output=True, text=True, timeout=20,
    )
    # The recording step intentionally succeeds so the artifact can upload;
    # the separate always-run enforcement step must retain the real failure.
    assert observed.returncode == 0, observed.stderr
    output = (tmp_path / "output").read_text(encoding="utf-8")
    expected = 37 if failure_at else (43 if fail_tee else 0)
    assert output.strip() == f"exit_code={expected}"
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    assert len(calls) == (failure_at or 6)
    env["VALIDATION_EXIT"] = str(expected)
    enforced = subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-c", step_script("Enforce the source contract")],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert enforced.returncode == expected


def test_missing_validation_result_blocks_publication(tmp_path):
    env = dict(os.environ)
    env.pop("VALIDATION_EXIT", None)
    result = subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-c", step_script("Enforce the source contract")],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 2
