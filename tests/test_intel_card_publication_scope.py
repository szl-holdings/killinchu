import pytest

from scripts.intel_card_publication_scope import matches_publication_path, publication_required


HEAD = "a" * 40
REF = "refs/heads/main"
EVENT = {"before": "b" * 40, "after": HEAD, "ref": REF}


@pytest.mark.parametrize("path", [
    "killinchu_intel_archive_card.py", "Dockerfile",
    "datasets/killinchu-osint-corpus/nested/data.jsonl",
    ".github/workflows/publish-intel-archive-card.yml",
])
def test_original_publication_paths_still_publish(path):
    assert publication_required("push", EVENT, HEAD, REF, [path])


@pytest.mark.parametrize("path", [
    "scripts/dispatch_receipt_training.py", "szl_spaces_proxy.py",
    "README.md", "datasets/killinchu-osint-corpus-other/data.jsonl",
])
def test_unrelated_source_validates_without_provider_publication(path):
    assert not matches_publication_path(path)
    assert not publication_required("push", EVENT, HEAD, REF, [path])


def test_pull_request_never_publishes():
    assert not publication_required("pull_request", {}, HEAD, "refs/pull/10/merge")


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_explicit_and_scheduled_publication_preserved(event):
    assert publication_required(event, {}, HEAD, REF)


@pytest.mark.parametrize("patch", [
    {"before": "0" * 40}, {"before": None}, {"before": "--all"},
    {"after": "c" * 40}, {"ref": "refs/heads/other"},
])
def test_incomplete_or_mismatched_push_fails_closed(patch):
    with pytest.raises(ValueError):
        publication_required("push", EVENT | patch, HEAD, REF, ["Dockerfile"])


def test_missing_diff_fails_closed(monkeypatch):
    def fail(*args):
        raise TimeoutError("git unavailable")
    monkeypatch.setattr("scripts.intel_card_publication_scope.git", fail)
    with pytest.raises(TimeoutError):
        publication_required("push", EVENT, HEAD, REF)
