from pathlib import Path


def test_release_receipt_publication_is_serialized_and_rejects_stale_source() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "hf-sync.yml"
    ).read_text(encoding="utf-8")

    for contract in (
        "group: killinchu-hf-release-receipt",
        "cancel-in-progress: false",
        "reusable-hf-deploy.yml@391f67e28dd966d9e42f88c6e3f852f3c63add84",
        "require-default-branch-tip: true",
        "GITHUB_TOKEN: ${{ github.token }}",
        'f"/repos/{os.environ[\'GITHUB_REPOSITORY\']}/commits/main"',
        "current_main != source_sha",
        "live_revision != source_sha",
        'key="RELEASE_ATTESTATION"',
    ):
        assert contract in workflow

    assert "\n    paths:\n" not in workflow
    assert "\n  preflight:\n" not in workflow
