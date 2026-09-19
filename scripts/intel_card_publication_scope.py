"""Keep provider publication path-scoped while validating every main commit."""
import json
import os
from pathlib import Path
import re
import subprocess


EXACT_PATHS = frozenset({
    "killinchu_osint.py", "killinchu_intel_archive_card.py",
    "killinchu_intel_archive_publish.py", "Dockerfile",
    "tests/test_killinchu_intel_archive_card.py",
    "tests/test_killinchu_intel_archive_publish.py",
    ".github/workflows/publish-intel-archive-card.yml",
})
SHA = re.compile(r"[0-9a-f]{40}\Z")


def matches_publication_path(path):
    return path in EXACT_PATHS or path.startswith("datasets/killinchu-osint-corpus/")


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, timeout=30)


def publication_required(event_name, event, head, ref, changed_paths=None):
    if event_name == "pull_request":
        return False
    if ref != "refs/heads/main" or not SHA.fullmatch(head):
        raise ValueError("SOURCE_REF_INVALID")
    if event_name in {"schedule", "workflow_dispatch"}:
        return True
    if event_name != "push":
        raise ValueError("EVENT_UNSUPPORTED")
    before = event.get("before")
    if not isinstance(before, str) or not SHA.fullmatch(before) or before == "0" * 40:
        raise ValueError("PUSH_BASE_INVALID")
    if event.get("after") != head or event.get("ref") != ref:
        raise ValueError("PUSH_SOURCE_MISMATCH")
    if changed_paths is None:
        try:
            git("cat-file", "-e", before + "^{commit}")
        except subprocess.CalledProcessError:
            git("fetch", "--no-tags", "--depth=1", "origin", before)
        raw = git("diff", "--no-renames", "--name-only", "-z", before, head, "--")
        if len(raw) > 2_000_000:
            raise ValueError("DIFF_TOO_LARGE")
        changed_paths = [p.decode("utf-8", errors="strict") for p in raw.split(b"\0") if p]
    return any(matches_publication_path(path) for path in changed_paths)


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    decision = publication_required(
        os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"],
        os.environ["GITHUB_REF"],
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("publish_required=" + str(decision).lower() + "\n")


if __name__ == "__main__":
    main()
