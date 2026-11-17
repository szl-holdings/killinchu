# SPDX-License-Identifier: Apache-2.0
"""Exercise the real image-input workflow step against temporary PR merge commits.

The fixture repositories have no remotes, and no image build or network call runs.
These checks cover added, removed, and renamed runtime dependency inputs, plus
the base-parent boundary used by GitHub's pull-request test merge.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/dockerfile-copy-guard.yml"
RUNTIME_INPUT = "deploy/space/requirements/space-cryptography.in"
RUNTIME_LOCK = "deploy/space/requirements/space-cryptography.txt"


def selection_script() -> str:
    step = WORKFLOW.read_text(encoding="utf-8").split(
        "      - name: List image inputs changed by this PR\n", 1
    )[1]
    lines = []
    for line in step.split("        run: |\n", 1)[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("\n".join(lines))


def bash_executable() -> str:
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    bash = shutil.which("bash")
    if bash is None:
        raise RuntimeError("Bash is required to exercise the workflow's actual shell")
    return bash


def write(repo: Path, path: str, content: str = "changed\n") -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def git(repo: Path, *args: str) -> None:
    # Only the disposable fixture commits are unsigned; repository policy is untouched.
    subprocess.run(
        [
            "git",
            "-c", "user.name=Workflow contract",
            "-c", "user.email=workflow-contract@example.invalid",
            "-c", "commit.gpgsign=false",
            "-c", "core.autocrlf=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


def initialize_fixture(repo: Path) -> None:
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    for path in (
        "Dockerfile",
        "deploy/space/Dockerfile",
        ".dockerignore",
        ".github/workflows/dockerfile-copy-guard.yml",
        RUNTIME_INPUT,
        RUNTIME_LOCK,
        "README.md",
        ".github/requirements/ci-signing.txt",
    ):
        write(repo, path, "before\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture base")
    git(repo, "checkout", "-b", "feature")


def run_selection(repo: Path, runner: Path) -> tuple[subprocess.CompletedProcess, str]:
    runner.mkdir()
    output = runner / "output"
    output.touch()
    env = dict(os.environ)
    env.update(RUNNER_TEMP=runner.as_posix(), GITHUB_OUTPUT=output.as_posix())
    observed = subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-c", selection_script()],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return observed, output.read_text(encoding="utf-8")


class ImageInputSelectionTests(unittest.TestCase):
    def assert_selection(self, change, expected: bool, *, advance_base=None) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            initialize_fixture(repo)
            change(repo)
            git(repo, "add", "-A")
            git(repo, "commit", "-m", "fixture feature")
            git(repo, "checkout", "main")
            if advance_base is not None:
                advance_base(repo)
                git(repo, "add", "-A")
                git(repo, "commit", "-m", "fixture base advance")
            git(repo, "merge", "--no-ff", "-m", "fixture PR merge", "feature")
            observed, output = run_selection(repo, root / "runner")
            self.assertEqual(observed.returncode, 0, observed.stdout + observed.stderr)
            self.assertEqual(output.strip(), f"changed={str(expected).lower()}")

    def test_existing_image_definitions_select_build(self):
        for path in (
            "Dockerfile",
            "deploy/space/Dockerfile",
            ".dockerignore",
            ".github/workflows/dockerfile-copy-guard.yml",
        ):
            with self.subTest(path=path):
                self.assert_selection(lambda repo: write(repo, path), True)

    def test_runtime_dependency_inputs_and_locks_select_build(self):
        for path in (
            RUNTIME_INPUT,
            RUNTIME_LOCK,
            "deploy/space/requirements/new-profile.in",
            "deploy/space/requirements/new-profile.txt",
        ):
            with self.subTest(path=path):
                self.assert_selection(lambda repo: write(repo, path), True)

    def test_removed_runtime_lock_selects_build(self):
        self.assert_selection(lambda repo: (repo / RUNTIME_LOCK).unlink(), True)

    def test_runtime_lock_renamed_outside_directory_selects_build(self):
        def rename(repo):
            (repo / RUNTIME_LOCK).rename(repo / "retired-lock.txt")
        self.assert_selection(rename, True)

    def test_docs_and_ci_only_changes_do_not_select_build(self):
        for path in ("README.md", ".github/requirements/ci-signing.txt"):
            with self.subTest(path=path):
                self.assert_selection(lambda repo: write(repo, path), False)

    def test_base_branch_image_change_does_not_count_as_pr_change(self):
        self.assert_selection(
            lambda repo: write(repo, "README.md"),
            False,
            advance_base=lambda repo: write(repo, "Dockerfile"),
        )

    def test_diff_failure_does_not_publish_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            initialize_fixture(repo)
            # The initial commit has no HEAD^1; a failed diff must not emit false.
            observed, output = run_selection(repo, root / "runner")
            self.assertNotEqual(observed.returncode, 0)
            self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
