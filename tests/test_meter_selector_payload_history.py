"""Keep prior sandbox source proof intact when the paired meter slot advances."""
import hashlib
import json
from pathlib import Path

import szl_meter_access


ROOT = Path(__file__).resolve().parents[1]


def test_meter_selector_preserves_attested_sandbox_payload():
    archive = ROOT / ".github/shared-source-payloads/code-engine-attested-sandbox-20261013-v1.json"
    raw = archive.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "e22e38f740b2b0279a52f5caba6f99362b89f01575e44e9a32b3f2643cbb46bb"
    )
    payload = json.loads(raw)
    assert payload["schema"] == "szl-shared-source-payload/v1"
    assert payload["payload_id"] == "code-engine-attested-sandbox-20261013-v1"
    predecessor = ".github/shared-source-payloads/code-engine-mandatory-rlimits-20261013-v1.json"
    assert hashlib.sha256((ROOT / predecessor).read_bytes()).hexdigest() == payload["files"][predecessor]


def test_prior_meter_manifest_fixture_retains_its_original_content_address():
    # Reproduce the earlier exact public manifest bytes, independently of the
    # new active slot. Historical source remains in Git, not in this active slot.
    prior = {
        "files": {"szl_meter_access.py": hashlib.sha256((ROOT / "szl_meter_access.py").read_bytes()).hexdigest()},
        "payload_id": "meter-selector-20261011-v1",
        "schema": "szl-shared-source-payload/v1",
    }
    raw = (json.dumps(prior, indent=2) + "\n").encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == (
        "ceebae9b24d32f5011a67ddcf8c0802a5d35467eb3e950236547b1938ff38705"
    )


def test_paired_meter_and_bounded_engine_do_not_activate_a_credential():
    # The write-admission successor occupies the active slot. Keep verifying
    # this exact predecessor manifest; the new engine keeps its historical digest.
    raw = (ROOT / ".github/shared-source-payloads/"
           "code-engine-bounded-model-20261015-v1.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "051d4a832b7bcb318e3a743da4c373a1499919a5b0284825273818c54db7b52e"
    )
    payload = json.loads(raw)
    assert payload["schema"] == "szl-shared-source-payload/v1"
    assert payload["payload_id"] == "code-engine-bounded-model-20261015-v1"
    assert payload["files"] == {
        "a11oy_code_engine.py": "a03aa1c294b69c8dfe3ce20d85aaf2347fac93ad7cba3544c1697d381639ac6f",
        "szl_meter_access.py": hashlib.sha256((ROOT / "szl_meter_access.py").read_bytes()).hexdigest(),
    }
    for relative, expected in payload["files"].items():
        if relative == "a11oy_code_engine.py":
            continue  # Historical engine bytes remain pinned above.
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    assert szl_meter_access.ACTIVE_METER2_TARGETS_SECRET is None
