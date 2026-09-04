#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SZL Holdings
"""One-use, exact-blob integrator for Killinchu Asset Exposure Wave 5."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


EXPECTED_BLOBS = {
    "szl_uds_hardening.py": "52a0bc0173cbe6f53b0d45ee7ce7e750c523856e",
    "szl_connectors/asset_exposure.py": "f6c1592978364b2eb32f4f04ed56384e2d70bb38",
    "tests/test_asset_exposure_wave5.py": "d37dced10f3c87bc526f03752c9bd038ee640d26",
    "Dockerfile": "f78bc14706cfcddf837723ebe353d3771c779e86",
    "deploy/space/Dockerfile": "f78bc14706cfcddf837723ebe353d3771c779e86",
    "deploy/image-contract.json": "1f263f95cd7de190a54e9ab1c151498da181708f",
}


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def verify_exact_blobs() -> None:
    for relative, expected in EXPECTED_BLOBS.items():
        path = Path(relative)
        actual = git_blob_sha(path.read_bytes())
        if actual != expected:
            raise SystemExit(
                f"{relative} moved: expected blob {expected}, found {actual}"
            )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count is {count}, expected 1")
    return text.replace(old, new, 1)


def patch_asset_module() -> None:
    path = Path("szl_connectors/asset_exposure.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    return value\n\n\ndef loads_strict(raw: bytes) -> dict[str, Any]:\n",
        "    return value\n\n\ndef _reject_json_constant(value: str) -> None:\n"
        "    raise ValueError(f\"non-standard JSON constant: {value}\")\n\n\n"
        "def loads_strict(raw: bytes) -> dict[str, Any]:\n",
        "strict JSON constant guard",
    )
    text = replace_once(
        text,
        "            object_pairs_hook=_strict_object,\n"
        "        )\n"
        "    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError) as exc:\n",
        "            object_pairs_hook=_strict_object,\n"
        "            parse_constant=_reject_json_constant,\n"
        "        )\n"
        "    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:\n",
        "strict JSON parser",
    )
    text = replace_once(
        text,
        "    normalized = value.strip()\n"
        "    if required and not normalized:\n",
        "    normalized = value.strip()\n"
        "    if any(ord(character) < 0x20 for character in normalized):\n"
        "        raise ExposureInputError(\n"
        "            \"INVALID_FIELD\",\n"
        "            f\"{field} contains a control character\",\n"
        "        )\n"
        "    if required and not normalized:\n",
        "control-character guard",
    )
    text = replace_once(
        text,
        "def _walk_cyclonedx(rows: Any) -> Iterable[dict[str, Any]]:\n"
        "    if rows is None:\n"
        "        return\n"
        "    if not isinstance(rows, list):\n"
        "        raise ExposureInputError(\n"
        "            \"INVALID_SBOM\",\n"
        "            \"CycloneDX components must be an array\",\n"
        "        )\n"
        "    for row in rows:\n"
        "        if not isinstance(row, dict):\n"
        "            raise ExposureInputError(\n"
        "                \"INVALID_SBOM\",\n"
        "                \"every CycloneDX component must be an object\",\n"
        "            )\n"
        "        yield row\n"
        "        nested = row.get(\"components\")\n"
        "        if nested is not None:\n"
        "            yield from _walk_cyclonedx(nested)\n",
        "def _walk_cyclonedx(rows: Any) -> Iterable[dict[str, Any]]:\n"
        "    if rows is None:\n"
        "        return\n"
        "    if not isinstance(rows, list):\n"
        "        raise ExposureInputError(\n"
        "            \"INVALID_SBOM\",\n"
        "            \"CycloneDX components must be an array\",\n"
        "        )\n"
        "    stack = list(reversed(rows))\n"
        "    while stack:\n"
        "        row = stack.pop()\n"
        "        if not isinstance(row, dict):\n"
        "            raise ExposureInputError(\n"
        "                \"INVALID_SBOM\",\n"
        "                \"every CycloneDX component must be an object\",\n"
        "            )\n"
        "        yield row\n"
        "        nested = row.get(\"components\")\n"
        "        if nested is not None:\n"
        "            if not isinstance(nested, list):\n"
        "                raise ExposureInputError(\n"
        "                    \"INVALID_SBOM\",\n"
        "                    \"nested CycloneDX components must be an array\",\n"
        "                )\n"
        "            stack.extend(reversed(nested))\n",
        "iterative CycloneDX traversal",
    )
    text = replace_once(
        text,
        "    components: list[dict[str, Any]] = []\n"
        "    seen: set[str] = set()\n"
        "    for row in _walk_cyclonedx(sbom.get(\"components\", [])):\n",
        "    metadata = (\n"
        "        sbom.get(\"metadata\")\n"
        "        if isinstance(sbom.get(\"metadata\"), dict)\n"
        "        else {}\n"
        "    )\n"
        "    root_component = (\n"
        "        metadata.get(\"component\")\n"
        "        if isinstance(metadata.get(\"component\"), dict)\n"
        "        else {}\n"
        "    )\n"
        "    rows: list[dict[str, Any]] = []\n"
        "    if root_component and (\n"
        "        root_component.get(\"bom-ref\") or root_component.get(\"purl\")\n"
        "    ):\n"
        "        rows.append(root_component)\n"
        "    rows.extend(_walk_cyclonedx(sbom.get(\"components\", [])))\n\n"
        "    components: list[dict[str, Any]] = []\n"
        "    seen: set[str] = set()\n"
        "    for row in rows:\n",
        "CycloneDX root component",
    )
    text = replace_once(
        text,
        "    metadata = sbom.get(\"metadata\") if isinstance(sbom.get(\"metadata\"), dict) else {}\n"
        "    root_component = (\n"
        "        metadata.get(\"component\")\n"
        "        if isinstance(metadata.get(\"component\"), dict)\n"
        "        else {}\n"
        "    )\n"
        "    identity = {\n",
        "    identity = {\n",
        "CycloneDX duplicate metadata block",
    )
    text = replace_once(
        text,
        "    seen: set[tuple[str, str, str]] = set()\n",
        "    seen: set[tuple[str, str]] = set()\n",
        "finding identity type",
    )
    text = replace_once(
        text,
        "        key = (component_ref, cve, status)\n"
        "        if key in seen:\n"
        "            continue\n"
        "        seen.add(key)\n",
        "        key = (component_ref, cve)\n"
        "        if key in seen:\n"
        "            raise ExposureInputError(\n"
        "                \"DUPLICATE_FINDING\",\n"
        "                f\"findings repeats component/CVE pair: {component_ref} / {cve}\",\n"
        "            )\n"
        "        seen.add(key)\n",
        "duplicate finding rejection",
    )
    text = replace_once(
        text,
        "        fusion_raw = fusion_results.get(finding[\"cve\"])\n"
        "        record, meta = _fusion_record(fusion_raw)\n"
        "        if meta[\"state\"] == \"CONNECTED\" and record is not None:\n",
        "        fusion_raw = fusion_results.get(finding[\"cve\"])\n"
        "        record, meta = _fusion_record(fusion_raw)\n"
        "        if record is not None and (\n"
        "            str(record.get(\"cve\") or \"\").upper() != finding[\"cve\"]\n"
        "        ):\n"
        "            record = None\n"
        "            meta = {\n"
        "                **meta,\n"
        "                \"state\": \"ERROR\",\n"
        "                \"coverage\": \"NONE\",\n"
        "                \"note\": \"resolver returned evidence for a different CVE\",\n"
        "            }\n"
        "        if meta[\"state\"] == \"CONNECTED\" and record is not None:\n",
        "exact resolver binding",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    path = Path("tests/test_asset_exposure_wave5.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    def test_unknown_component_fails_closed(self) -> None:\n",
        "    def test_cyclonedx_root_component_is_addressable(self) -> None:\n"
        "        payload = cyclonedx_payload()\n"
        "        root = {\n"
        "            \"type\": \"application\",\n"
        "            \"bom-ref\": \"pkg:generic/payments-api@1.0.0\",\n"
        "            \"name\": \"payments-api\",\n"
        "            \"version\": \"1.0.0\",\n"
        "        }\n"
        "        payload[\"sbom\"][\"metadata\"][\"component\"] = root\n"
        "        payload[\"sbom\"][\"components\"] = []\n"
        "        payload[\"findings\"][0][\"component_ref\"] = root[\"bom-ref\"]\n"
        "        prepared = prepare_payload(payload)\n"
        "        self.assertEqual(prepared[\"sbom\"][\"component_count\"], 1)\n"
        "        self.assertIn(root[\"bom-ref\"], prepared[\"component_map\"])\n\n"
        "    def test_unknown_component_fails_closed(self) -> None:\n",
        "root component test",
    )
    text = replace_once(
        text,
        "    def test_active_cve_bound_is_enforced(self) -> None:\n",
        "    def test_duplicate_component_cve_is_rejected(self) -> None:\n"
        "        payload = cyclonedx_payload()\n"
        "        duplicate = dict(payload[\"findings\"][0])\n"
        "        duplicate[\"status\"] = \"under_investigation\"\n"
        "        payload[\"findings\"].append(duplicate)\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            prepare_payload(payload)\n"
        "        self.assertEqual(caught.exception.code, \"DUPLICATE_FINDING\")\n\n"
        "    def test_active_cve_bound_is_enforced(self) -> None:\n",
        "duplicate finding test",
    )
    text = replace_once(
        text,
        "    def test_body_size_is_bounded(self) -> None:\n",
        "    def test_nonstandard_json_constant_is_rejected(self) -> None:\n"
        "        with self.assertRaises(ExposureInputError) as caught:\n"
        "            loads_strict(b'{\"asset\": NaN}')\n"
        "        self.assertEqual(caught.exception.code, \"INVALID_JSON\")\n\n"
        "    def test_body_size_is_bounded(self) -> None:\n",
        "non-standard JSON test",
    )
    text = replace_once(
        text,
        "    def test_evidence_digest_excludes_observation_time(self) -> None:\n",
        "    def test_mismatched_resolver_record_is_rejected(self) -> None:\n"
        "        prepared = prepare_payload(cyclonedx_payload())\n"
        "        wrong = fusion(cve=\"CVE-2024-0001\")\n"
        "        report = compose_report(\n"
        "            prepared,\n"
        "            {\"CVE-2021-44228\": wrong},\n"
        "            observed_at=\"2026-09-04T00:00:00+00:00\",\n"
        "        )\n"
        "        row = report[\"remediation_queue\"][0]\n"
        "        self.assertEqual(report[\"state\"], \"UNAVAILABLE\")\n"
        "        self.assertEqual(row[\"source_state\"], \"ERROR\")\n"
        "        self.assertEqual(row[\"remediation_lane\"], \"REVIEW\")\n"
        "        self.assertIsNone(row[\"asset_priority_score\"])\n\n"
        "    def test_evidence_digest_excludes_observation_time(self) -> None:\n",
        "resolver mismatch test",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_hardening() -> None:
    path = Path("szl_uds_hardening.py")
    text = path.read_text(encoding="utf-8")

    import_anchor = (
        '_FLAGSHIPS = ["a11oy", "amaru", "sentra", "rosie", '
        '"killinchu", "vessels", "hatun-mcp"]\n'
    )
    text = replace_once(
        text,
        import_anchor,
        import_anchor
        + "\n"
        + "try:\n"
        + "    from szl_connectors import asset_exposure as _asset_exposure\n"
        + "except Exception:  # pragma: no cover - guarded runtime integration\n"
        + "    _asset_exposure = None\n",
        "Wave 5 import",
    )

    route_anchor = "    # ---- Hardening index (manifest of every real artifact) ----\n"
    route_block = (
        "    # ---- Asset inventory + SBOM exposure correlation (Wave 5) ----\n"
        "    exposure_registration: dict[str, Any] = {\n"
        '        "module": "szl_connectors.asset_exposure",\n'
        '        "state": "UNAVAILABLE",\n'
        '        "registered": [],\n'
        '        "registered_count": 0,\n'
        '        "honesty": "asset exposure module did not import; no route fabricated",\n'
        "    }\n"
        "    if _asset_exposure is not None:\n"
        "        try:\n"
        "            exposure_registration = _asset_exposure.register(app, ns)\n"
        '            registered.extend(exposure_registration.get("registered", []))\n'
        "        except Exception as exc:  # keep the existing app available\n"
        "            exposure_registration = {\n"
        '                "module": "szl_connectors.asset_exposure",\n'
        '                "state": "ERROR",\n'
        '                "registered": [],\n'
        '                "registered_count": 0,\n'
        '                "error": type(exc).__name__,\n'
        '                "honesty": "Wave 5 registration failed closed; no success claimed",\n'
        "            }\n\n"
        + route_anchor
    )
    text = replace_once(
        text,
        route_anchor,
        route_block,
        "Wave 5 route registration",
    )
    text = replace_once(
        text,
        '                  "endpoints": registered,\n',
        '                  "endpoints": registered,\n'
        '                  "asset_exposure": exposure_registration,\n',
        "Wave 5 hardening index",
    )
    text = replace_once(
        text,
        '    return {"module": "szl_uds_hardening", "registered_count": len(registered),\n'
        '            "registered": registered, "flagships": _FLAGSHIPS,\n'
        '            "signing": bool(_dsse and _dsse.signing_available())}\n',
        '    return {"module": "szl_uds_hardening", "registered_count": len(registered),\n'
        '            "registered": registered, "flagships": _FLAGSHIPS,\n'
        '            "asset_exposure": exposure_registration,\n'
        '            "signing": bool(_dsse and _dsse.signing_available())}\n',
        "Wave 5 return summary",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_image_contract() -> None:
    copy_anchor = (
        "COPY szl_connectors/__init__.py "
        "./szl_connectors/__init__.py\n"
    )
    copy_line = (
        "COPY szl_connectors/asset_exposure.py "
        "./szl_connectors/asset_exposure.py\n"
    )
    for relative in ("Dockerfile", "deploy/space/Dockerfile"):
        path = Path(relative)
        text = path.read_text(encoding="utf-8")
        text = replace_once(
            text,
            copy_anchor,
            copy_anchor + copy_line,
            f"{relative} Wave 5 COPY",
        )
        path.write_text(text, encoding="utf-8", newline="\n")

    canonical = Path("Dockerfile").read_bytes()
    derived = Path("deploy/space/Dockerfile").read_bytes()
    if canonical != derived:
        raise SystemExit("canonical and derived Dockerfiles diverged after Wave 5 COPY")

    contract_path = Path("deploy/image-contract.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = "szl_connectors/asset_exposure.py"
    sources = contract.get("local_copy_sources")
    if not isinstance(sources, list):
        raise SystemExit("image contract local_copy_sources is not an array")
    if source in sources:
        raise SystemExit("image contract already contains Wave 5 source")
    sources.append(source)
    contract["local_copy_sources"] = sorted(sources)
    digest = hashlib.sha256(canonical).hexdigest()
    contract["canonical_dockerfile"]["sha256"] = digest
    contract["hf_deploy_dockerfile"]["sha256"] = digest
    contract_path.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    verify_exact_blobs()
    patch_asset_module()
    patch_tests()
    patch_hardening()
    patch_image_contract()
    print("Wave 5 integration patch applied")


if __name__ == "__main__":
    main()
