#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""One-use transport, backpressure, and evidence-boundary hardener for Wave 5."""

from __future__ import annotations

import hashlib
from pathlib import Path


EXPECTED = {
    "szl_connectors/asset_exposure.py": "0dff337e24695b55f855381046f0e777462d59b0",
    "tests/test_asset_exposure_wave5.py": "e373988ff01f541bfd63d1139173cb37d53df151",
    "docs/ASSET_EXPOSURE_WAVE5.md": "2030584fbb2d4df8530472579f2edde1ff5c79ea",
    ".github/workflows/asset-exposure-wave5.yml": "dee4d8d42e926d5ad9e22fc0109d30967631bd5a",
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
        "import math\nimport re\nfrom typing import Any, Callable, Iterable\n",
        "import math\nimport re\nimport threading\nfrom typing import Any, Callable, Iterable\n",
        "threading import",
    )
    text = replace_once(
        text,
        "MAX_ACTIVE_CVES = 10\n\n_ASSET_ID_RE",
        "MAX_ACTIVE_CVES = 10\n"
        "MAX_PARALLEL_RESOLVERS = 3\n"
        "MAX_GLOBAL_RESOLVERS = 4\n"
        "RESOLVER_SLOT_TIMEOUT_SECONDS = 1.0\n\n"
        "_GLOBAL_RESOLUTION_SLOTS = threading.BoundedSemaphore(\n"
        "    MAX_GLOBAL_RESOLVERS\n"
        ")\n\n"
        "_ASSET_ID_RE",
        "resolver bounds",
    )
    text = replace_once(
        text,
        '_CVE_RE = re.compile(r"CVE-\\d{4}-\\d{4,}")\n',
        '_CVE_RE = re.compile(r"CVE-\\d{4}-\\d{4,}")\n'
        '_SHA256_RE = re.compile(r"[0-9a-f]{64}")\n',
        "evidence digest regex",
    )

    loads_anchor = (
        "    return value\n\n\ndef _canonical_bytes(value: Any) -> bytes:\n"
    )
    bounded_reader = (
        "    return value\n\n\n"
        "async def _read_bounded_body(request: Any) -> bytes:\n"
        "    \"\"\"Read JSON incrementally so the byte limit is enforced in transit.\"\"\"\n\n"
        "    content_type = str(request.headers.get(\"content-type\") or \"\")\n"
        "    media_type = content_type.split(\";\", 1)[0].strip().casefold()\n"
        "    if media_type != \"application/json\" and not media_type.endswith(\"+json\"):\n"
        "        raise ExposureInputError(\n"
        "            \"UNSUPPORTED_MEDIA_TYPE\",\n"
        "            \"Content-Type must be application/json or application/*+json\",\n"
        "            status_code=415,\n"
        "        )\n\n"
        "    content_length = request.headers.get(\"content-length\")\n"
        "    if content_length not in (None, \"\"):\n"
        "        try:\n"
        "            declared = int(content_length)\n"
        "        except (TypeError, ValueError) as exc:\n"
        "            raise ExposureInputError(\n"
        "                \"INVALID_CONTENT_LENGTH\",\n"
        "                \"Content-Length must be a non-negative integer\",\n"
        "                status_code=400,\n"
        "            ) from exc\n"
        "        if declared < 0:\n"
        "            raise ExposureInputError(\n"
        "                \"INVALID_CONTENT_LENGTH\",\n"
        "                \"Content-Length must be a non-negative integer\",\n"
        "                status_code=400,\n"
        "            )\n"
        "        if declared > MAX_BODY_BYTES:\n"
        "            raise ExposureInputError(\n"
        "                \"BODY_TOO_LARGE\",\n"
        "                f\"request body exceeds {MAX_BODY_BYTES} bytes\",\n"
        "                status_code=413,\n"
        "            )\n\n"
        "    chunks: list[bytes] = []\n"
        "    size = 0\n"
        "    async for chunk in request.stream():\n"
        "        if not isinstance(chunk, (bytes, bytearray)):\n"
        "            raise ExposureInputError(\n"
        "                \"INVALID_BODY_STREAM\",\n"
        "                \"request body stream yielded a non-byte chunk\",\n"
        "                status_code=400,\n"
        "            )\n"
        "        size += len(chunk)\n"
        "        if size > MAX_BODY_BYTES:\n"
        "            raise ExposureInputError(\n"
        "                \"BODY_TOO_LARGE\",\n"
        "                f\"request body exceeds {MAX_BODY_BYTES} bytes\",\n"
        "                status_code=413,\n"
        "            )\n"
        "        if chunk:\n"
        "            chunks.append(bytes(chunk))\n"
        "    return b\"\".join(chunks)\n\n\n"
        "def _canonical_bytes(value: Any) -> bytes:\n"
    )
    text = replace_once(
        text,
        loads_anchor,
        bounded_reader,
        "streamed body reader",
    )

    text = replace_once(
        text,
        "    ref: str,\n",
        "    ref: Any,\n",
        "component reference type",
    )
    text = replace_once(
        text,
        "            ref=str(ref),\n",
        "            ref=ref,\n",
        "CycloneDX reference coercion",
    )

    score_anchor = (
        "def _lane(\n"
        "    source_priority: str,\n"
        "    asset_score: float | None,\n"
        ") -> str:\n"
    )
    boundary_helper = (
        "def _fusion_boundary_valid(\n"
        "    raw: Any,\n"
        "    record: dict[str, Any],\n"
        "    meta: dict[str, Any],\n"
        ") -> bool:\n"
        "    digest = record.get(\"normalized_evidence_sha256\")\n"
        "    return (\n"
        "        isinstance(raw, dict)\n"
        "        and raw.get(\"connector_id\") == \"defensive_fusion\"\n"
        "        and meta.get(\"state\") == \"CONNECTED\"\n"
        "        and meta.get(\"live\") is True\n"
        "        and meta.get(\"coverage\") in {\"FULL\", \"PARTIAL\"}\n"
        "        and record.get(\"action_authority\")\n"
        "        == \"DEFENSIVE_PRIORITIZATION_ONLY\"\n"
        "        and record.get(\"human_approval_required\") is True\n"
        "        and record.get(\"exploit_content_included\") is False\n"
        "        and record.get(\"asset_scanning_performed\") is False\n"
        "        and isinstance(digest, str)\n"
        "        and _SHA256_RE.fullmatch(digest) is not None\n"
        "    )\n\n\n"
        + score_anchor
    )
    text = replace_once(
        text,
        score_anchor,
        boundary_helper,
        "Wave 4 authority boundary helper",
    )

    validation_anchor = (
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
    )
    validation_replacement = validation_anchor + (
        "        if record is not None and not _fusion_boundary_valid(\n"
        "            fusion_raw, record, meta\n"
        "        ):\n"
        "            record = None\n"
        "            source_score = None\n"
        "            source_priority = \"UNAVAILABLE\"\n"
        "            meta = {\n"
        "                **meta,\n"
        "                \"state\": \"ERROR\",\n"
        "                \"coverage\": \"NONE\",\n"
        "                \"note\": \"resolver violated the defensive evidence boundary\",\n"
        "            }\n"
    )
    text = replace_once(
        text,
        validation_anchor,
        validation_replacement,
        "Wave 4 boundary enforcement",
    )

    resolve_anchor = (
        "def _resolve_live_fusion(cve: str) -> dict[str, Any]:\n"
    )
    batch_helpers = (
        "def _resolve_one_bounded(\n"
        "    resolver: Callable[[str], dict[str, Any]],\n"
        "    cve: str,\n"
        ") -> dict[str, Any]:\n"
        "    acquired = _GLOBAL_RESOLUTION_SLOTS.acquire(\n"
        "        timeout=RESOLVER_SLOT_TIMEOUT_SECONDS\n"
        "    )\n"
        "    if not acquired:\n"
        "        return {\n"
        "            \"connector_id\": \"defensive_fusion\",\n"
        "            \"state\": \"error\",\n"
        "            \"records\": [],\n"
        "            \"live\": False,\n"
        "            \"note\": \"global defensive-fusion capacity is temporarily unavailable\",\n"
        "        }\n"
        "    try:\n"
        "        return resolver(cve)\n"
        "    except Exception as exc:\n"
        "        return {\n"
        "            \"connector_id\": \"defensive_fusion\",\n"
        "            \"state\": \"error\",\n"
        "            \"records\": [],\n"
        "            \"live\": False,\n"
        "            \"note\": f\"resolver failed closed: {type(exc).__name__}\",\n"
        "        }\n"
        "    finally:\n"
        "        _GLOBAL_RESOLUTION_SLOTS.release()\n\n\n"
        "async def _resolve_fusion_batch(\n"
        "    cves: list[str],\n"
        "    resolver: Callable[[str], dict[str, Any]],\n"
        ") -> dict[str, Any]:\n"
        "    semaphore = asyncio.Semaphore(MAX_PARALLEL_RESOLVERS)\n\n"
        "    async def resolve_one(cve: str) -> tuple[str, dict[str, Any]]:\n"
        "        async with semaphore:\n"
        "            result = await asyncio.to_thread(\n"
        "                _resolve_one_bounded, resolver, cve\n"
        "            )\n"
        "            return cve, result\n\n"
        "    pairs = await asyncio.gather(*(resolve_one(cve) for cve in cves))\n"
        "    return dict(pairs)\n\n\n"
        + resolve_anchor
    )
    text = replace_once(
        text,
        resolve_anchor,
        batch_helpers,
        "bounded batch resolver",
    )

    text = replace_once(
        text,
        '            "active_cves": MAX_ACTIVE_CVES,\n',
        '            "active_cves": MAX_ACTIVE_CVES,\n'
        '            "parallel_resolvers_per_request": MAX_PARALLEL_RESOLVERS,\n'
        '            "global_resolver_slots": MAX_GLOBAL_RESOLVERS,\n',
        "contract backpressure limits",
    )
    text = replace_once(
        text,
        "            payload = loads_strict(await request.body())\n",
        "            payload = loads_strict(await _read_bounded_body(request))\n",
        "streamed route body",
    )
    text = replace_once(
        text,
        "        fusion_results: dict[str, Any] = {}\n"
        "        try:\n"
        "            for cve in prepared[\"active_cves\"]:\n"
        "                fusion_results[cve] = await asyncio.to_thread(\n"
        "                    live_resolver,\n"
        "                    cve,\n"
        "                )\n"
        "            report = compose_report(prepared, fusion_results)\n",
        "        try:\n"
        "            fusion_results = await _resolve_fusion_batch(\n"
        "                prepared[\"active_cves\"], live_resolver\n"
        "            )\n"
        "            report = compose_report(prepared, fusion_results)\n",
        "bounded route resolution",
    )
    text = replace_once(
        text,
        '    "compose_report",\n',
        '    "_read_bounded_body",\n'
        '    "_resolve_fusion_batch",\n'
        '    "compose_report",\n',
        "testable bounded helpers",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    path = Path("tests/test_asset_exposure_wave5.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from __future__ import annotations\n\nimport json\nfrom pathlib import Path\nimport unittest\n",
        "from __future__ import annotations\n\nimport asyncio\nimport json\nfrom pathlib import Path\nimport threading\nimport time\nimport unittest\n",
        "async test imports",
    )
    text = replace_once(
        text,
        "    ExposureInputError,\n",
        "    ExposureInputError,\n"
        "    MAX_BODY_BYTES,\n"
        "    MAX_PARALLEL_RESOLVERS,\n"
        "    _read_bounded_body,\n"
        "    _resolve_fusion_batch,\n",
        "bounded helper imports",
    )
    text = replace_once(
        text,
        '                "normalized_evidence_sha256": "a" * 64,\n',
        '                "normalized_evidence_sha256": "a" * 64,\n'
        '                "action_authority": "DEFENSIVE_PRIORITIZATION_ONLY",\n'
        '                "human_approval_required": True,\n'
        '                "exploit_content_included": False,\n'
        '                "asset_scanning_performed": False,\n',
        "Wave 4 boundary fixture",
    )

    class_anchor = "class InputContractTests(unittest.TestCase):\n"
    fake_request = (
        "class FakeRequest:\n"
        "    def __init__(\n"
        "        self,\n"
        "        chunks: list[bytes],\n"
        "        *,\n"
        "        content_type: str = \"application/json\",\n"
        "        content_length: str | None = None,\n"
        "    ) -> None:\n"
        "        self._chunks = chunks\n"
        "        self.stream_started = False\n"
        "        self.headers = {\"content-type\": content_type}\n"
        "        if content_length is not None:\n"
        "            self.headers[\"content-length\"] = content_length\n\n"
        "    async def stream(self):\n"
        "        self.stream_started = True\n"
        "        for chunk in self._chunks:\n"
        "            yield chunk\n\n\n"
        + class_anchor
    )
    text = replace_once(
        text,
        class_anchor,
        fake_request,
        "fake streaming request",
    )

    test_anchor = "    def test_body_size_is_bounded(self) -> None:\n"
    transport_tests = (
        "    def test_non_string_cyclonedx_reference_is_rejected(self) -> None:\n"
        "        payload = cyclonedx_payload()\n"
        "        payload[\"sbom\"][\"components\"][0][\"bom-ref\"] = 42\n"
        "        payload[\"findings\"][0][\"component_ref\"] = \"42\"\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            prepare_payload(payload)\n"
        "        self.assertEqual(caught.exception.code, \"INVALID_FIELD\")\n\n"
        "    def test_declared_oversize_body_is_rejected_before_streaming(self) -> None:\n"
        "        request = FakeRequest(\n"
        "            [b\"{}\"],\n"
        "            content_length=str(MAX_BODY_BYTES + 1),\n"
        "        )\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            asyncio.run(_read_bounded_body(request))\n"
        "        self.assertEqual(caught.exception.code, \"BODY_TOO_LARGE\")\n"
        "        self.assertFalse(request.stream_started)\n\n"
        "    def test_chunked_oversize_body_is_stopped_in_transit(self) -> None:\n"
        "        request = FakeRequest([b\"a\" * MAX_BODY_BYTES, b\"b\"])\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            asyncio.run(_read_bounded_body(request))\n"
        "        self.assertEqual(caught.exception.code, \"BODY_TOO_LARGE\")\n"
        "        self.assertTrue(request.stream_started)\n\n"
        "    def test_non_json_media_type_is_rejected(self) -> None:\n"
        "        request = FakeRequest([b\"{}\"], content_type=\"text/plain\")\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            asyncio.run(_read_bounded_body(request))\n"
        "        self.assertEqual(caught.exception.code, \"UNSUPPORTED_MEDIA_TYPE\")\n"
        "        self.assertEqual(caught.exception.status_code, 415)\n\n"
        + test_anchor
    )
    text = replace_once(
        text,
        test_anchor,
        transport_tests,
        "streaming transport tests",
    )

    report_anchor = "    def test_evidence_digest_excludes_observation_time(self) -> None:\n"
    resolver_tests = (
        "    def test_wave4_authority_boundary_is_required(self) -> None:\n"
        "        prepared = prepare_payload(cyclonedx_payload())\n"
        "        invalid = fusion(cve=\"CVE-2021-44228\")\n"
        "        invalid[\"records\"][0][\"action_authority\"] = \"UNBOUNDED\"\n"
        "        report = compose_report(\n"
        "            prepared,\n"
        "            {\"CVE-2021-44228\": invalid},\n"
        "            observed_at=\"2026-09-04T00:00:00+00:00\",\n"
        "        )\n"
        "        row = report[\"remediation_queue\"][0]\n"
        "        self.assertEqual(report[\"state\"], \"UNAVAILABLE\")\n"
        "        self.assertEqual(row[\"source_state\"], \"ERROR\")\n"
        "        self.assertEqual(row[\"remediation_lane\"], \"REVIEW\")\n\n"
        "    def test_batch_resolution_is_bounded_and_fail_isolated(self) -> None:\n"
        "        lock = threading.Lock()\n"
        "        active = 0\n"
        "        peak = 0\n\n"
        "        def resolver(cve: str) -> dict:\n"
        "            nonlocal active, peak\n"
        "            with lock:\n"
        "                active += 1\n"
        "                peak = max(peak, active)\n"
        "            try:\n"
        "                time.sleep(0.02)\n"
        "                if cve.endswith(\"1002\"):\n"
        "                    raise RuntimeError(\"synthetic resolver failure\")\n"
        "                return fusion(cve=cve)\n"
        "            finally:\n"
        "                with lock:\n"
        "                    active -= 1\n\n"
        "        cves = [f\"CVE-2026-{1000 + index}\" for index in range(6)]\n"
        "        results = asyncio.run(_resolve_fusion_batch(cves, resolver))\n"
        "        self.assertEqual(set(results), set(cves))\n"
        "        self.assertLessEqual(peak, MAX_PARALLEL_RESOLVERS)\n"
        "        self.assertEqual(results[\"CVE-2026-1002\"][\"state\"], \"error\")\n"
        "        self.assertEqual(results[\"CVE-2026-1000\"][\"state\"], \"connected\")\n\n"
        + report_anchor
    )
    text = replace_once(
        text,
        report_anchor,
        resolver_tests,
        "bounded resolver tests",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_docs() -> None:
    path = Path("docs/ASSET_EXPOSURE_WAVE5.md")
    text = path.read_text(encoding="utf-8")
    anchor = (
        "Unique active CVEs: 10\n"
        "```\n\n"
        "The active-CVE bound limits upstream load and prevents the public route from\n"
        "becoming an unbounded bulk-query mechanism.\n"
    )
    replacement = (
        "Unique active CVEs: 10\n"
        "Parallel resolvers per request: 3\n"
        "Global resolver slots per process: 4\n"
        "```\n\n"
        "The request body is read incrementally and rejected as soon as it crosses the\n"
        "byte bound; a declared oversized `Content-Length` is rejected before body\n"
        "streaming begins. Only JSON media types are accepted. Active CVEs resolve with\n"
        "bounded concurrency, individual resolver failures remain isolated as explicit\n"
        "unavailable evidence, and a process-wide slot limit caps upstream pressure\n"
        "across concurrent requests.\n"
    )
    text = replace_once(
        text,
        anchor,
        replacement,
        "transport and backpressure documentation",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_ci() -> None:
    path = Path(".github/workflows/asset-exposure-wave5.yml")
    text = path.read_text(encoding="utf-8")
    anchor = (
        "      - name: Prove production witness is fixed-origin and synthetic\n"
    )
    step = (
        "      - name: Prove streamed transport and bounded resolver pressure\n"
        "        run: |\n"
        "          python - <<'PY'\n"
        "          from pathlib import Path\n\n"
        "          source = Path(\"szl_connectors/asset_exposure.py\").read_text(\n"
        "              encoding=\"utf-8\"\n"
        "          )\n"
        "          required = (\n"
        "              \"async for chunk in request.stream()\",\n"
        "              \"MAX_PARALLEL_RESOLVERS = 3\",\n"
        "              \"MAX_GLOBAL_RESOLVERS = 4\",\n"
        "              \"threading.BoundedSemaphore\",\n"
        "              \"resolver violated the defensive evidence boundary\",\n"
        "          )\n"
        "          for token in required:\n"
        "              if token not in source:\n"
        "                  raise SystemExit(f\"Wave 5 transport guard drifted: {token}\")\n"
        "          if \"await request.body()\" in source:\n"
        "              raise SystemExit(\"Wave 5 regressed to unbounded body buffering\")\n"
        "          PY\n\n"
        + anchor
    )
    text = replace_once(text, anchor, step, "permanent transport CI")
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    verify()
    patch_asset()
    patch_tests()
    patch_docs()
    patch_ci()
    print("Wave 5 transport and resolver hardening applied")


if __name__ == "__main__":
    main()
