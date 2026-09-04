#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""One-use numerical and disclosure finalizer for Wave 5."""

from __future__ import annotations

import hashlib
from pathlib import Path


EXPECTED = {
    "szl_connectors/asset_exposure.py": "2f4846fc273f83a8e0d8f2222f4e062d4a5291d5",
    "tests/test_asset_exposure_wave5.py": "144b8204fff0f43a39be9629fe6d659fd3070f55",
    "szl_uds_hardening.py": "f0487a394dc020ebe2bc1c7e02eea3b2f6c022f1",
    "docs/ASSET_EXPOSURE_WAVE5.md": "cd6474d09de28ebd026fa7ab09efecf477fba522",
}


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def verify() -> None:
    for relative, expected in EXPECTED.items():
        actual = git_blob_sha(Path(relative).read_bytes())
        if actual != expected:
            raise SystemExit(
                f"{relative} moved: expected {expected}, found {actual}"
            )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count is {count}, expected 1")
    return text.replace(old, new, 1)


def patch_asset() -> None:
    path = Path("szl_connectors/asset_exposure.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import json\nimport re\n",
        "import json\nimport math\nimport re\n",
        "finite-number import",
    )
    text = replace_once(
        text,
        "        ensure_ascii=False,\n"
        "    ).encode(\"utf-8\")\n",
        "        ensure_ascii=False,\n"
        "        allow_nan=False,\n"
        "    ).encode(\"utf-8\")\n",
        "canonical finite JSON",
    )
    text = replace_once(
        text,
        "_LANE_ORDER = {\"P0\": 0, \"P1\": 1, \"P2\": 2, \"P3\": 3, \"REVIEW\": 4}\n",
        "_LANE_ORDER = {\"P0\": 0, \"P1\": 1, \"P2\": 2, \"P3\": 3, \"REVIEW\": 4}\n"
        "_SOURCE_PRIORITIES = {\"IMMEDIATE\", \"HIGH\", \"ELEVATED\", \"ROUTINE\"}\n",
        "source priority allowlist",
    )
    text = replace_once(
        text,
        "    if number < 0.0 or number > 0.99:\n"
        "        return None\n",
        "    if not math.isfinite(number) or number < 0.0 or number > 0.99:\n"
        "        return None\n",
        "finite score guard",
    )
    text = replace_once(
        text,
        "        if meta[\"state\"] == \"CONNECTED\" and record is not None:\n"
        "            connected += 1\n"
        "        if meta[\"coverage\"] == \"FULL\":\n"
        "            full += 1\n\n"
        "        source_score = _score((record or {}).get(\"priority_score\"))\n"
        "        asset_score = (\n"
        "            round(min(0.99, source_score * multiplier), 4)\n"
        "            if source_score is not None\n"
        "            else None\n"
        "        )\n"
        "        source_priority = str(\n"
        "            (record or {}).get(\"priority\") or \"UNAVAILABLE\"\n"
        "        ).upper()\n"
        "        lane = _lane(source_priority, asset_score)\n",
        "        source_score = _score((record or {}).get(\"priority_score\"))\n"
        "        source_priority = str(\n"
        "            (record or {}).get(\"priority\") or \"UNAVAILABLE\"\n"
        "        ).upper()\n"
        "        if record is not None and (\n"
        "            source_score is None or source_priority not in _SOURCE_PRIORITIES\n"
        "        ):\n"
        "            record = None\n"
        "            source_score = None\n"
        "            source_priority = \"UNAVAILABLE\"\n"
        "            meta = {\n"
        "                **meta,\n"
        "                \"state\": \"ERROR\",\n"
        "                \"coverage\": \"NONE\",\n"
        "                \"note\": \"resolver returned an invalid priority record\",\n"
        "            }\n"
        "        if meta[\"state\"] == \"CONNECTED\" and record is not None:\n"
        "            connected += 1\n"
        "        if meta[\"coverage\"] == \"FULL\" and record is not None:\n"
        "            full += 1\n\n"
        "        asset_score = (\n"
        "            round(min(0.99, source_score * multiplier), 4)\n"
        "            if source_score is not None\n"
        "            else None\n"
        "        )\n"
        "        lane = _lane(source_priority, asset_score)\n",
        "validated priority composition",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    path = Path("tests/test_asset_exposure_wave5.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    def test_evidence_digest_excludes_observation_time(self) -> None:\n",
        "    def test_invalid_priority_records_are_rejected(self) -> None:\n"
        "        prepared = prepare_payload(cyclonedx_payload())\n"
        "        cases = (\n"
        "            (float(\"nan\"), \"IMMEDIATE\"),\n"
        "            (0.50, \"URGENT\"),\n"
        "        )\n"
        "        for score, priority in cases:\n"
        "            with self.subTest(score=score, priority=priority):\n"
        "                invalid = fusion(\n"
        "                    cve=\"CVE-2021-44228\",\n"
        "                    score=score,\n"
        "                    priority=priority,\n"
        "                )\n"
        "                report = compose_report(\n"
        "                    prepared,\n"
        "                    {\"CVE-2021-44228\": invalid},\n"
        "                    observed_at=\"2026-09-04T00:00:00+00:00\",\n"
        "                )\n"
        "                row = report[\"remediation_queue\"][0]\n"
        "                self.assertEqual(report[\"state\"], \"UNAVAILABLE\")\n"
        "                self.assertEqual(row[\"source_state\"], \"ERROR\")\n"
        "                self.assertEqual(row[\"remediation_lane\"], \"REVIEW\")\n"
        "                self.assertIsNone(row[\"asset_priority_score\"])\n\n"
        "    def test_evidence_digest_excludes_observation_time(self) -> None:\n",
        "invalid priority record test",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_hardening_disclosure() -> None:
    path = Path("szl_uds_hardening.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "Every endpoint here is backed by REAL artifacts committed to .compliance/:\n",
        "The original hardening endpoints are backed by REAL artifacts committed to\n"
        ".compliance/. Wave 5 additionally accepts an inline operator-supplied SBOM and\n"
        "explicit component-to-CVE findings; those associations are never inferred:\n",
        "hardening evidence disclosure",
    )
    text = replace_once(
        text,
        "  GET  /api/killinchu/uds/v1/hardening/index   (manifest of all real artifacts)\n",
        "  GET  /api/killinchu/uds/v1/hardening/index   (manifest of all real artifacts)\n"
        "  GET  /api/killinchu/uds/v1/sbom/exposure/schema\n"
        "  POST /api/killinchu/uds/v1/sbom/exposure/evaluate\n",
        "Wave 5 endpoint disclosure",
    )
    text = replace_once(
        text,
        "Honesty: real oscap numbers only; Iron Bank images not pushed (creds required);\n"
        "Big Bang chart lints/renders clean (verified). No fabrication.\n",
        "Honesty: real oscap numbers only; Iron Bank images not pushed (creds required);\n"
        "Big Bang chart lints/renders clean (verified). SBOM/CVE associations are\n"
        "operator supplied and official-source gaps remain explicit. No fabrication.\n",
        "Wave 5 honesty disclosure",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_docs() -> None:
    path = Path("docs/ASSET_EXPOSURE_WAVE5.md")
    text = path.read_text(encoding="utf-8")
    anchor = (
        "The suite covers CycloneDX and SPDX parsing, strict JSON, exact-reference\n"
        "validation, VEX closure, request bounds, deterministic evidence hashes, formula\n"
        "bounds, honest unavailable states, and source scans proving that the Wave 5\n"
        "module has no direct HTTP, socket, subprocess, or shell primitive.\n\n"
    )
    addition = anchor + (
        "### Production witness\n\n"
        "After governed Hugging Face publication, the `Asset Exposure Wave 5 Live\n"
        "Witness` submits only a fixed synthetic SBOM, verifies that the running build\n"
        "matches protected GitHub `main`, checks every authority boundary, and uploads\n"
        "an immutable response-hash artifact. It runs after successful publication and\n"
        "every six hours. `MEASURED`, `PARTIAL`, and honest `UNAVAILABLE` source states\n"
        "are distinguished; the witness never converts an upstream outage into evidence.\n\n"
    )
    text = replace_once(text, anchor, addition, "production witness documentation")
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    verify()
    patch_asset()
    patch_tests()
    patch_hardening_disclosure()
    patch_docs()
    print("Wave 5 final numerical and disclosure guards applied")


if __name__ == "__main__":
    main()
