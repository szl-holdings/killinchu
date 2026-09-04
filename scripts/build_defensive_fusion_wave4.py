#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover and execute the reviewed Wave 4 generator.

The initial staging commit preserved the complete generator, but YAML could not
parse unindented lines inside Python raw strings. The current workflow is small
and valid; this runner reads the original payload from its immutable Git commit,
dedents only the outer generator, executes it, applies two fail-closed hardening
edits, and removes both temporary builder files.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


STAGING_COMMIT = "b5759c4a54a56a48f64f428d86793cc6f50e4c72"
STAGING_PATH = ".github/workflows/build-defensive-fusion-wave4.yml"
CURRENT_WORKFLOW = Path(STAGING_PATH)
SELF = Path(__file__)
START = "          from pathlib import Path"
END = "\n          PY\n\n      - name: Run focused deterministic gates"


def _staged_workflow() -> str:
    return subprocess.check_output(
        ["git", "show", f"{STAGING_COMMIT}:{STAGING_PATH}"],
        text=True,
        encoding="utf-8",
    )


def _extract_generator(text: str) -> str:
    start = text.find(START)
    end = text.find(END, start)
    if start < 0 or end < 0:
        raise RuntimeError("reviewed generator markers are missing from staging commit")
    block = text[start:end]
    normalized: list[str] = []
    inside_raw_template = False
    for line in block.splitlines():
        if inside_raw_template:
            normalized.append(line)
            if line.count("'''") % 2 == 1:
                inside_raw_template = False
            continue
        outer = line[10:] if line.startswith("          ") else line
        normalized.append(outer)
        if outer.count("'''") % 2 == 1:
            inside_raw_template = True
    if inside_raw_template:
        raise RuntimeError("unterminated raw source template in staging payload")
    code = "\n".join(normalized) + "\n"
    compile(code, f"{STAGING_COMMIT}:{STAGING_PATH}", "exec")
    return code


def _harden_generated_files() -> None:
    security_path = Path("szl_connectors/data_sources/security.py")
    tests_path = Path("tests/test_defensive_fusion_wave4.py")
    security = security_path.read_text(encoding="utf-8")

    old_preview = (
        'schema_preview = ["cveID", "vendorProject", "product", '
        '"vulnerabilityName", "dateAdded", "knownRansomwareCampaignUse"]'
    )
    new_preview = (
        'schema_preview = ["cveID", "vendorProject", "product", '
        '"vulnerabilityName", "dateAdded", "knownRansomwareCampaignUse", '
        '"requiredAction"]'
    )
    if old_preview not in security:
        raise RuntimeError("CISA schema preview hardening boundary not found")
    security = security.replace(old_preview, new_preview, 1)

    priority_boundary = '''        cvss = nvd.get("cvss") if nvd else None
        epss_score = epss.get("epss") if epss else None
        priority_score, priority, components = self._priority(
'''
    hardened_priority = '''        cvss = nvd.get("cvss") if nvd else None
        epss_score = epss.get("epss") if epss else None
        exact_evidence_observed = any(
            value is not None for value in (kev_entry, nvd, epss)
        )
        if measured > 0 and not exact_evidence_observed:
            result = Records(
                connector_id=self.id,
                category=self.category,
                state=State.READY,
                records=[],
                source=self.provider_base,
                live=False,
                note=(
                    f"{coverage.lower()} transport coverage, but the exact CVE was not "
                    "present in returned official records; no priority fabricated"
                ),
                schema_preview=list(self.schema_preview),
            )
            _put(cache_key, result)
            return result
        priority_score, priority, components = self._priority(
'''
    if priority_boundary not in security:
        raise RuntimeError("exact-CVE hardening boundary not found")
    security = security.replace(priority_boundary, hardened_priority, 1)
    security_path.write_text(security, encoding="utf-8", newline="\n")

    tests = tests_path.read_text(encoding="utf-8")
    test_append = r'''


def test_measured_transports_without_exact_cve_do_not_create_a_priority():
    security._CACHE.clear()

    def empty_http(url: str, *args, **kwargs):
        if "services.nvd.nist.gov" in url:
            return 200, {"vulnerabilities": []}
        if "api.first.org" in url:
            return 200, {"data": []}
        raise AssertionError(url)

    with mock.patch.object(
        security.CisaKevConnector, "read", return_value=cisa_records(hit=False)
    ), mock.patch.object(security, "http_json", side_effect=empty_http):
        result = security.DefensiveFusionConnector().read({"q": CVE})
    assert result.state == State.READY
    assert result.records == []
    assert result.live is False
    assert "exact CVE was not present" in result.note
    assert "no priority fabricated" in result.note
'''
    if "test_measured_transports_without_exact_cve" in tests:
        raise RuntimeError("exact-CVE absence test already exists")
    tests_path.write_text(tests.rstrip() + test_append + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    code = _extract_generator(_staged_workflow())
    namespace = {
        "__name__": "__wave4_builder__",
        "__file__": f"{STAGING_COMMIT}:{STAGING_PATH}",
    }
    exec(code, namespace, namespace)
    _harden_generated_files()
    CURRENT_WORKFLOW.unlink(missing_ok=True)
    SELF.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
