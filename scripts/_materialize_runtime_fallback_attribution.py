#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply the source-accurate IMMUNE Field fallback attribution repair."""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, observed {count}")
    return text.replace(old, new, 1)


def patch_immune() -> None:
    path = ROOT / "szl_immune.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("def _field(")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Registration", start)
    block = text[start:end]

    if "    primary_status = status\n" not in block:
        block = replace_once(
            block,
            (
                "    status, data, err = probe(field_url)\n"
                "    body = data if isinstance(data, dict) else {}\n"
                "    reachable = status == 200 and isinstance(data, dict)\n"
                "    fallback_state = False\n"
            ),
            (
                "    status, data, err = probe(field_url)\n"
                "    primary_status = status\n"
                "    primary_error = err\n"
                "    body = data if isinstance(data, dict) else {}\n"
                "    reachable = status == 200 and isinstance(data, dict)\n"
                "    fallback_state = False\n"
            ),
            "field primary-probe attribution",
        )

    if '        "fallback_from": (' not in block:
        block = replace_once(
            block,
            (
                '        "upstream_http": status,\n'
                '        "error": None if reachable else (err or "field unobserved"),\n'
                '        "channel": "B",\n'
                '        "space": "SZLHOLDINGS/immune-lattice",\n'
                '        "contract": "/api/immune/state" if fallback_state else "/api/field",\n'
            ),
            (
                '        "upstream_http": status,\n'
                '        "error": None if reachable else (err or "field unobserved"),\n'
                '        "fallback_from": (\n'
                '            {\n'
                '                "channel": "B",\n'
                '                "space": "SZLHOLDINGS/immune-lattice",\n'
                '                "contract": "/api/field",\n'
                '                "url": field_url,\n'
                '                "upstream_http": primary_status,\n'
                '                "error": primary_error or "field unobserved",\n'
                '            }\n'
                '            if fallback_state\n'
                '            else None\n'
                '        ),\n'
                '        "channel": "A" if fallback_state else "B",\n'
                '        "space": "SZLHOLDINGS/immune" if fallback_state else "SZLHOLDINGS/immune-lattice",\n'
                '        "contract": "/api/immune/state" if fallback_state else "/api/field",\n'
            ),
            "field fallback-source attribution",
        )

    path.write_text(text[:start] + block + text[end:], encoding="utf-8")


def write_tests() -> None:
    content = textwrap.dedent(
        '''\
        # SPDX-License-Identifier: Apache-2.0
        """Regression coverage for IMMUNE Field fallback source attribution."""
        from __future__ import annotations

        import szl_immune as immune


        def _clear_cache() -> None:
            immune._FIELD_CACHE.clear()


        def test_primary_field_response_stays_channel_b() -> None:
            _clear_cache()

            def probe(url: str):
                assert url.endswith("/api/field")
                return 200, {
                    "lambda_status": "Conjecture 1 (NOT a theorem)",
                    "actuation": "SIMULATED",
                    "rule": "observe only",
                    "cells": [],
                    "hunts": [],
                }, None

            result = immune._field(now=10_000.0, probe=probe)
            assert result["channel"] == "B"
            assert result["space"] == "SZLHOLDINGS/immune-lattice"
            assert result["contract"] == "/api/field"
            assert result["fallback_from"] is None
            _clear_cache()


        def test_fallback_reports_channel_a_and_preserves_primary_failure() -> None:
            _clear_cache()
            calls: list[str] = []

            def probe(url: str):
                calls.append(url)
                if url.endswith("/api/field"):
                    return 503, None, "field overlay unavailable"
                assert url.endswith("/api/immune/state")
                return 200, {
                    "estate": [
                        {"id": "cell-1", "title": "Observed cell", "role": "sensor"}
                    ],
                    "ledger": {"count": 7},
                    "readiness": "OBSERVED",
                    "mesh": "DEGRADED",
                }, None

            result = immune._field(now=20_000.0, probe=probe)
            assert len(calls) == 2
            assert result["ok"] is True
            assert result["channel"] == "A"
            assert result["space"] == "SZLHOLDINGS/immune"
            assert result["contract"] == "/api/immune/state"
            assert result["url"].endswith("/api/immune/state")
            assert result["cell_count"] == 1
            assert result["ledger"] == {"count": 7}
            assert result["fallback_from"] == {
                "channel": "B",
                "space": "SZLHOLDINGS/immune-lattice",
                "contract": "/api/field",
                "url": calls[0],
                "upstream_http": 503,
                "error": "field overlay unavailable",
            }
            _clear_cache()
        '''
    )
    (ROOT / "tests/test_runtime_boundary_fallback_attribution.py").write_text(
        content,
        encoding="utf-8",
    )


def write_manifest() -> str:
    files = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in ("szl_agentic_loop.py", "szl_immune.py")
    }
    manifest = {
        "files": dict(sorted(files.items())),
        "payload_id": "runtime-boundary-1994-v2",
        "schema": "szl-shared-source-payload/v1",
    }
    raw = (json.dumps(manifest, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    (ROOT / ".github/shared-source-payload-manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    print(f"shared_manifest_sha256={digest}")
    return digest


def main() -> int:
    patch_immune()
    write_tests()
    write_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
