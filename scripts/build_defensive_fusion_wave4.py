#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover and execute the reviewed Wave 4 generator from its staging workflow.

The initial staging commit preserved the complete generator, but YAML could not
parse unindented lines embedded inside Python raw strings. This runner extracts
the Python heredoc as plain text, removes only the outer YAML indentation, and
executes the exact payload. Both temporary builder files remove themselves.
"""
from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/build-defensive-fusion-wave4.yml")
SELF = Path(__file__)
START = "          from pathlib import Path\n"
END = "\n          PY\n\n      - name: Run focused deterministic gates"


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise RuntimeError("reviewed generator markers are missing")
    body = text.split(START, 1)[1].split(END, 1)[0]
    lines = ["from pathlib import Path"]
    for line in body.splitlines():
        lines.append(line[10:] if line.startswith("          ") else line)
    code = "\n".join(lines) + "\n"
    compile(code, str(WORKFLOW), "exec")
    namespace = {"__name__": "__wave4_builder__", "__file__": str(WORKFLOW)}
    exec(code, namespace, namespace)
    SELF.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
