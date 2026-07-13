#!/usr/bin/env python3
"""Reject FastAPI response-class return annotations imported only in register()."""
from __future__ import annotations

import argparse
import json
import pathlib
import re


FILES = (
    "killinchu_frontier_wave_surfaces.py",
    "szl_yupay.py",
    "szl_waqay.py",
    "killinchu_mesh.py",
    "a11oy_hf_assets.py",
)
PATTERN = re.compile(
    r"^\s*async\s+def\s+\w+\([^\n]*\)\s*->\s*[\"']?(?:JSONResponse|HTMLResponse|Response)[\"']?\s*:",
    re.MULTILINE,
)


def scan(repo_root: pathlib.Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for relative in FILES:
        path = repo_root / relative
        text = path.read_text(encoding="utf-8")
        for match in PATTERN.finditer(text):
            findings.append(
                {
                    "path": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "definition": match.group(0).strip(),
                }
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path("."))
    args = parser.parse_args(argv)
    findings = scan(args.repo_root.resolve())
    print(json.dumps({"checked": list(FILES), "findings": findings}, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
