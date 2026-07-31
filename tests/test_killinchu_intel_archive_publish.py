import json
from pathlib import Path
from types import SimpleNamespace

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


def test_source_files_are_hash_bound():
    item = publisher.source_file("datasets/killinchu-osint-corpus/LICENSE.md")
    assert item["path"].endswith("LICENSE.md")
    assert item["bytes"] == len(
        (Path(publisher.ROOT) / item["path"]).read_bytes().replace(b"\r\n", b"\n")
    )
    assert len(item["sha256"]) == 64
