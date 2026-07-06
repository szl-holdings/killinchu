#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
#
# Registered-organ COPY guard (the reverse of dockerfile-copy-check.py).
#
# dockerfile-copy-check.py catches `COPY foo.py` lines whose source file is
# missing. This guard catches the OPPOSITE, subtler drift that broke wave 14:
# an organ module is REGISTERED in serve.py (listed in a `_WAVEn_ORGANS` block
# or otherwise `__import__`-ed / imported as a szl_* organ) and its file EXISTS
# in the repo, but there is NO `COPY <module>.py` line in the Dockerfile. Result:
# hf-sync mirrors the .py file to the Space, but `docker build` never bakes it
# into the image, so at runtime `__import__` fails, the organ falls into its
# try/except "NOT registered" path, and its /api/<ns>/v1/<organ>/... endpoint
# 404s — silently, with the Space still reporting RUNNING.
#
# What it checks: for every organ module named in a `_WAVEn_ORGANS` tuple in
# serve.py, assert the Dockerfile has a COPY whose source list includes
# `<module>.py` (or a glob that matches it). Exit 1 on any registered-but-not-
# copied organ; exit 0 when every registered organ is baked.
#
# Usage: python3 organ_copy_check.py [serve.py] [Dockerfile]

import re
import sys


def logical_lines(text):
    """Yield Dockerfile logical instructions, joining backslash continuations."""
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        buf += line
        yield buf
        buf = ""
    if buf:
        yield buf


def copied_sources(dockerfile_text):
    """Set of every local source token appearing in COPY/ADD lines (excludes
    --from=, remote ADD, and flag tokens)."""
    sources = set()
    for inst in logical_lines(dockerfile_text):
        m = re.match(r"\s*(COPY|ADD)\s+(.*)", inst, re.IGNORECASE)
        if not m:
            continue
        rest = m.group(2)
        if re.search(r"--from=", rest, re.IGNORECASE):
            continue  # multi-stage / external image source, not the repo
        # drop flags like --chown= --chmod= --link
        toks = [t for t in rest.split() if not t.startswith("--")]
        if len(toks) < 2:
            continue
        # last token is the destination; the rest are sources
        for src in toks[:-1]:
            if src.startswith(("http://", "https://")):
                continue
            sources.add(src)
    return sources


def registered_organs(serve_text):
    """Module names listed in any `_WAVEn_ORGANS = [ (\"szl_x\", ...), ... ]`
    block in serve.py. Returns a set of module names (no .py)."""
    organs = set()
    # find each _WAVE<n>_ORGANS = [ ... ] literal (possibly multi-line)
    for m in re.finditer(r"_WAVE\d+_ORGANS\s*=\s*\[(.*?)\]", serve_text, re.DOTALL):
        block = m.group(1)
        # first string in each tuple is the module name
        for tup in re.finditer(r'\(\s*["\']([A-Za-z0-9_]+)["\']', block):
            organs.add(tup.group(1))
    return organs


def source_matches(module, sources):
    """True if `<module>.py` is covered by any COPY source token (exact or glob)."""
    target = module + ".py"
    for s in sources:
        base = s.rsplit("/", 1)[-1]
        if base == target:
            return True
        # glob source e.g. szl_*.py or *.py
        if "*" in base:
            pat = "^" + re.escape(base).replace(r"\*", ".*") + "$"
            if re.match(pat, target):
                return True
    return False


def main():
    serve_path = sys.argv[1] if len(sys.argv) > 1 else "serve.py"
    dockerfile_path = sys.argv[2] if len(sys.argv) > 2 else "Dockerfile"
    serve_text = open(serve_path, encoding="utf-8", errors="ignore").read()
    df_text = open(dockerfile_path, encoding="utf-8", errors="ignore").read()

    organs = registered_organs(serve_text)
    sources = copied_sources(df_text)

    if not organs:
        print("organ-copy-guard: no _WAVEn_ORGANS blocks found in "
              f"{serve_path} (nothing to check).")
        return 0

    missing = sorted(o for o in organs if not source_matches(o, sources))
    print(f"organ-copy-guard: {len(organs)} registered organ(s) in {serve_path}; "
          f"{len(missing)} missing a Dockerfile COPY.")
    if missing:
        for o in missing:
            print(f"  MISSING-COPY {o}.py -- registered in a _WAVEn_ORGANS block "
                  f"but no `COPY {o}.py` in {dockerfile_path}; it would sync to the "
                  f"Space but never be baked into the image -> endpoint 404s.",
                  file=sys.stderr)
        print("FAIL: registered organ(s) not baked by the Dockerfile. Add the "
              "`COPY <organ>.py ./` line(s).", file=sys.stderr)
        return 1
    print("OK: every registered organ has a Dockerfile COPY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
