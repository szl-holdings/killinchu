import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import killinchu_intel_archive_publish as publisher


class FakeApi:
    def dataset_info(self, repo_id, files_metadata=False):
        assert repo_id == publisher.REPO_ID
        assert files_metadata is True
        return SimpleNamespace(
            sha="a" * 40,
            siblings=[
                SimpleNamespace(
                    rfilename="README.md", size=10, blob_id="card"
                ),
                SimpleNamespace(
                    rfilename="intel/2026-07-30.ndjson",
                    size=123,
                    blob_id="b" * 40,
                ),
            ],
        )


class FakeCommitAdd:
    def __init__(self, *, path_in_repo, path_or_fileobj):
        self.path_in_repo = path_in_repo
        self.path_or_fileobj = path_or_fileobj


class PublishingApi(FakeApi):
    def __init__(self, *, commit_revision="d" * 40, create_error=None, recovery="e" * 40):
        self.commit_revision = commit_revision
        self.create_error = create_error
        self.recovery = recovery
        self.create_calls = 0
        self.uploaded = {}

    def dataset_info(self, repo_id, files_metadata=False):
        if files_metadata:
            return super().dataset_info(repo_id, files_metadata=True)
        assert repo_id == publisher.REPO_ID
        return SimpleNamespace(sha=self.recovery)

    def create_commit(self, *, repo_id, repo_type, operations, commit_message):
        assert repo_id == publisher.REPO_ID
        assert repo_type == "dataset"
        assert commit_message.startswith("Bind archive snapshot to killinchu ")
        self.create_calls += 1
        self.uploaded = {
            operation.path_in_repo: operation.path_or_fileobj.getvalue()
            for operation in operations
        }
        if self.create_error is not None:
            raise self.create_error
        return SimpleNamespace(oid=self.commit_revision)


class FakeResponse:
    def __init__(self, payload, *, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, _size):
        return self.payload


def tip_sequence(*revisions):
    remaining = list(revisions)

    def read_tip(**kwargs):
        assert kwargs["token"] == "github-read-token"
        assert kwargs["api_url"] == "https://api.github.test"
        assert kwargs["repository"] == publisher.SOURCE_REPOSITORY
        assert kwargs["timeout_seconds"] == publisher.GITHUB_TIMEOUT_SECONDS
        return remaining.pop(0)

    return read_tip


def install_hf_mocks(monkeypatch, tmp_path, api):
    monkeypatch.setattr(publisher, "CommitOperationAdd", FakeCommitAdd)
    existing = tmp_path / "existing-provenance.json"
    existing.write_text("{}\n", encoding="utf-8")

    def download(*, filename, revision, **_kwargs):
        if revision == "a" * 40:
            assert filename == "DATASET_PROVENANCE.json"
            return str(existing)
        target = tmp_path / filename.replace("/", "-")
        target.write_bytes(api.uploaded[filename])
        return str(target)

    monkeypatch.setattr(publisher, "hf_hub_download", download)


def publish_args(tmp_path, api, tip_reader):
    return {
        "source_revision": "c" * 40,
        "token": "hf-write-token",
        "github_token": "github-read-token",
        "github_repository": publisher.SOURCE_REPOSITORY,
        "github_api_url": "https://api.github.test",
        "report_path": tmp_path / "publication.json",
        "api": api,
        "github_tip_reader": tip_reader,
    }


def test_archive_snapshot_binds_only_raw_shards():
    revision, shards = publisher.archive_snapshot(FakeApi())
    assert revision == "a" * 40
    assert shards == [
        {
            "path": "intel/2026-07-30.ndjson",
            "bytes": 123,
            "git_blob_id": "b" * 40,
            "git_blob_hash_algorithm": "sha1",
            "rights_status": "MIXED_SOURCE_ROW_LEVEL_RIGHTS_NOT_ESTABLISHED",
            "training_eligible": False,
        }
    ]


def test_payload_exposes_homogeneous_manifest_without_relicensing_raw_rows():
    payloads = publisher.build_payloads(
        source_revision="c" * 40,
        archive_revision="a" * 40,
        shards=[
            {
                "path": "intel/day.ndjson",
                "bytes": 123,
                "git_blob_id": "b" * 40,
                "git_blob_hash_algorithm": "sha1",
                "rights_status": "MIXED_SOURCE_ROW_LEVEL_RIGHTS_NOT_ESTABLISHED",
                "training_eligible": False,
            }
        ],
    )
    assert set(payloads) == {
        "README.md",
        "LICENSE.md",
        "viewer/archive_manifest.jsonl",
        "DATASET_PROVENANCE.json",
    }
    row = json.loads(payloads["viewer/archive_manifest.jsonl"])
    provenance = json.loads(payloads["DATASET_PROVENANCE.json"])
    assert row["training_eligible"] is False
    assert provenance["license"]["blanket_training_rights"] is False
    assert provenance["claims"]["reproducible_historical_generation"] == "NOT_CLAIMED"
    assert provenance["claims"]["source_binding"] == "PRE_MUTATION_PROTECTED_MAIN_AUTHORIZED"
    assert "CURRENT" not in provenance["source"]["relation"]
    assert len(provenance["archive"]["shard_state_sha256"]) == 64
    assert "archive_manifest" in payloads["README.md"].decode("utf-8")


def test_unchanged_source_and_shards_are_noop_eligible():
    shards = [
        {
            "path": "intel/day.ndjson",
            "bytes": 123,
            "git_blob_id": "b" * 40,
            "git_blob_hash_algorithm": "sha1",
            "rights_status": "MIXED_SOURCE_ROW_LEVEL_RIGHTS_NOT_ESTABLISHED",
            "training_eligible": False,
        }
    ]
    source = "c" * 40
    existing = json.dumps(
        {
            "source": {"revision": source},
            "archive": {"shard_state_sha256": publisher.shard_state_sha256(shards)},
        }
    ).encode()
    assert publisher.binding_is_current(
        existing, source_revision=source, shards=shards
    )
    assert not publisher.binding_is_current(
        existing, source_revision="d" * 40, shards=shards
    )


def test_workflow_refuses_non_main_publication_source():
    workflow = (
        Path(publisher.ROOT) / ".github/workflows/publish-intel-archive-card.yml"
    ).read_text(encoding="utf-8")
    assert "git fetch --no-tags --depth=1 origin main" in workflow
    assert "git rev-parse origin/main" in workflow


def test_activation_reauthorizes_inside_secret_step_immediately_before_mutation():
    workflow = (
        Path(publisher.ROOT) / ".github/workflows/activate-intel-archive.yml"
    ).read_text(encoding="utf-8")
    activation = workflow.split("- name: Activate and verify Space controls", 1)[1]
    read_index = activation.index("existing_secrets = api.get_space_secrets")
    guard_index = activation.index("github_request = urllib.request.Request")
    first_mutation = activation.index("api.add_space_variable")
    assert read_index < guard_index < first_mutation
    assert "GITHUB_TOKEN: ${{ github.token }}" in activation
    assert '"Authorization": f"Bearer {github_token}"' in activation
    assert "urlopen(github_request, timeout=10.0)" in activation
    assert 'r"[0-9a-f]{40}", observed_main' in activation


def test_github_tip_is_authenticated_bounded_and_strict():
    captured = {}

    def opener(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"sha": "c" * 40}).encode())

    revision = publisher.github_default_branch_tip(
        token="github-read-token",
        api_url="https://api.github.test",
        repository=publisher.SOURCE_REPOSITORY,
        timeout_seconds=4.5,
        opener=opener,
    )
    assert revision == "c" * 40
    assert captured["timeout"] == 4.5
    assert captured["request"].full_url.endswith(
        "/repos/szl-holdings/killinchu/commits/main"
    )
    assert captured["request"].get_header("Authorization") == "Bearer github-read-token"


@pytest.mark.parametrize(
    "payload", [b"not-json", b'{"sha":"short"}', b'[]', b'{"sha":"C' + b'"}']
)
def test_github_tip_rejects_malformed_responses(payload):
    with pytest.raises(publisher.PublicationError):
        publisher.github_default_branch_tip(
            token="github-read-token",
            api_url="https://api.github.test",
            repository=publisher.SOURCE_REPOSITORY,
            opener=lambda _request, timeout: FakeResponse(payload),
        )


def test_github_tip_failure_never_logs_token():
    token = "-".join(("synthetic", "redaction", "sentinel"))

    def unavailable(_request, *, timeout):
        raise TimeoutError("transport timeout")

    with pytest.raises(publisher.PublicationError) as caught:
        publisher.github_default_branch_tip(
            token=token,
            api_url="https://api.github.test",
            repository=publisher.SOURCE_REPOSITORY,
            opener=unavailable,
        )
    assert token not in str(caught.value)


def test_pre_mutation_drift_writes_failure_without_hf_mutation(monkeypatch, tmp_path):
    api = PublishingApi()
    install_hf_mocks(monkeypatch, tmp_path, api)
    args = publish_args(tmp_path, api, tip_sequence("f" * 40))
    with pytest.raises(publisher.PublicationError, match="no longer current"):
        publisher.publish(**args)
    report = json.loads(args["report_path"].read_text(encoding="utf-8"))
    assert api.create_calls == 0
    assert report["status"] == "FAILED_BEFORE_MUTATION_STALE_SOURCE"
    assert report["mutation_outcome"] == "NOT_ENTERED"
    assert report["github_main_revision_observed"] == "f" * 40
    assert report["current_main_publication"] is False


def test_unchanged_tip_allows_commit_and_final_current_main_receipt(monkeypatch, tmp_path):
    api = PublishingApi()
    install_hf_mocks(monkeypatch, tmp_path, api)
    args = publish_args(
        tmp_path, api, tip_sequence("c" * 40, "c" * 40, "c" * 40)
    )
    report = publisher.publish(**args)
    assert api.create_calls == 1
    assert report["status"] == "PUBLISHED_AND_IMMUTABLE_READBACK_VERIFIED"
    assert report["hf_revision_after"] == "d" * 40
    assert report["current_main_publication"] is True
    assert report["source_binding"] == "EXACT_CURRENT_WRITER_REVISION"
    uploaded_provenance = json.loads(api.uploaded["DATASET_PROVENANCE.json"])
    assert uploaded_provenance["claims"]["source_binding"] != "EXACT_CURRENT_WRITER_REVISION"


def test_post_mutation_drift_preserves_revision_as_partial(monkeypatch, tmp_path):
    api = PublishingApi()
    install_hf_mocks(monkeypatch, tmp_path, api)
    args = publish_args(tmp_path, api, tip_sequence("c" * 40, "f" * 40))
    with pytest.raises(publisher.PublicationError, match="drifted"):
        publisher.publish(**args)
    report_bytes = args["report_path"].read_bytes()
    report = json.loads(report_bytes)
    assert report["status"] == "PARTIAL_AFTER_MUTATION_STALE_SOURCE"
    assert report["mutation_outcome"] == "KNOWN"
    assert report["hf_revision_observed_after_mutation"] == "d" * 40
    assert report["current_main_publication"] is False
    assert b"EXACT_CURRENT_WRITER_REVISION" not in report_bytes


def test_ambiguous_mutation_drift_preserves_observed_revision(monkeypatch, tmp_path):
    api = PublishingApi(create_error=TimeoutError("ambiguous transport"), recovery="e" * 40)
    install_hf_mocks(monkeypatch, tmp_path, api)
    args = publish_args(tmp_path, api, tip_sequence("c" * 40, "f" * 40))
    with pytest.raises(publisher.PublicationError, match="outcome is unknown"):
        publisher.publish(**args)
    report_bytes = args["report_path"].read_bytes()
    report = json.loads(report_bytes)
    assert report["status"] == "PARTIAL_AFTER_AMBIGUOUS_MUTATION_STALE_SOURCE"
    assert report["mutation_outcome"] == "UNKNOWN"
    assert report["hf_revision_observed_after_mutation"] == "e" * 40
    assert report["github_main_revision_observed"] == "f" * 40
    assert report["current_main_publication"] is False
    assert b"EXACT_CURRENT_WRITER_REVISION" not in report_bytes


def test_github_api_unavailable_before_mutation_fails_closed(monkeypatch, tmp_path):
    api = PublishingApi()
    install_hf_mocks(monkeypatch, tmp_path, api)

    def unavailable(**_kwargs):
        raise publisher.PublicationError("GitHub protected-main lookup failed (TimeoutError)")

    args = publish_args(tmp_path, api, unavailable)
    with pytest.raises(publisher.PublicationError, match="reauthorization failed"):
        publisher.publish(**args)
    report = json.loads(args["report_path"].read_text(encoding="utf-8"))
    assert api.create_calls == 0
    assert report["status"] == "FAILED_BEFORE_MUTATION"
    assert report["stage"] == "PRE_MUTATION_GITHUB_REAUTHORIZATION"
    assert report["current_main_publication"] is False


def test_source_files_are_hash_bound():
    item = publisher.source_file("datasets/killinchu-osint-corpus/LICENSE.md")
    assert item["path"].endswith("LICENSE.md")
    assert item["bytes"] == len(
        (Path(publisher.ROOT) / item["path"]).read_bytes().replace(b"\r\n", b"\n")
    )
    assert len(item["sha256"]) == 64
