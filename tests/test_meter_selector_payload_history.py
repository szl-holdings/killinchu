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


def test_paired_meter_source_does_not_activate_a_credential():
    raw = (ROOT / ".github/shared-source-payload-manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "b8be768d9a012a941375ca852a7559dac02bdef530cfcd4e32abecfc0d74c1e0"
    )
    payload = json.loads(raw)
    assert payload["files"] == {
        "szl_meter_access.py": "e28179c88e3b41ab6ea58364ba3229246ef43c9137473fdd52fbff83f7bb8ec4"
    }
    assert hashlib.sha256((ROOT / "szl_meter_access.py").read_bytes()).hexdigest() == (
        payload["files"]["szl_meter_access.py"]
    )
    assert szl_meter_access.ACTIVE_METER2_TARGETS_SECRET is None
