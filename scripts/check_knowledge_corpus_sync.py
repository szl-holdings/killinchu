#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings
#
# Knowledge-corpus sync + honesty guard  (killinchu <- a11oy).
#
# killinchu ships knowledge.json BYTE-IDENTICAL to a11oy's so the two organs never
# drift from the kernel-derived corpus (theorems / formulas / axioms + honesty
# labels). a11oy is the SOURCE OF TRUTH: it regenerates the corpus on a new kernel
# commit or a formula/theorem change, and killinchu must follow. The copy is
# currently manual, so without a guard killinchu silently falls behind and serves a
# stale corpus with stale honesty labels.
#
# The existing shared-file-drift guard *incidentally* keeps these two files
# byte-identical (knowledge.json is a Dockerfile COPY source in both repos), but it
# (a) treats the relationship symmetrically rather than "a11oy is canonical", and
# (b) does NOT validate the corpus's honesty content. This guard is explicit about
# both: it FAILS if killinchu's knowledge.json differs from a11oy's, AND it FAILS if
# either corpus violates a Doctrine-v11 honesty invariant (so a dishonest corpus can
# never be synced in silently).
#
# Honesty invariants enforced (Doctrine v11) — these catch OVERCLAIMS, not
# legitimate corpus growth, so a normal a11oy regen (version bump, new formulas, a
# new locked kernel commit) does NOT trip them:
#   * The corpus parses as JSON and declares a top-level `version`.
#   * The corpus self-declares Doctrine v11 (the `v11` token is present).
#   * Λ-uniqueness / Conjecture 1 stays OPEN: the Λ_uniqueness theorem (TH_L1) has
#     maturity == "conjectured" (NEVER "proven"); proof_summary.conjecture lists
#     "F23"; and "F23" is NOT in proof_summary.locked_ids. (Unconditional
#     Λ-uniqueness (Conjecture 1) is machine-FALSE under A1-A5; only the conditional theorem holds.)
#   * The locked kernel count is machine-pinned (proof_summary.locked_count_theorem
#     present) — the exact number is NOT pinned here, it evolves with the kernel.
#   * Theorem U (if the corpus mentions it) is qualified "conditional".
#
# Usage:
#   check_knowledge_corpus_sync.py --self <killinchu knowledge.json> \
#                                  --sibling <a11oy knowledge.json>
#
# Exit code 0 = in sync and honest; 1 = drift or honesty violation (fail the
# build); 2 = usage / missing-input error.

import argparse
import hashlib
import json
import os
import sys


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_corpus(path):
    """Return (text, parsed_or_None). Never raises on bad JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        obj = json.loads(text)
    except Exception:
        obj = None
    return text, obj


def validate_honesty(text, corpus, label):
    """Return a list of Doctrine-v11 honesty violations for one corpus."""
    errors = []

    if not isinstance(corpus, dict):
        return [f"{label}: corpus is not a valid JSON object"]

    # 1. version present
    if not corpus.get("version"):
        errors.append(f"{label}: missing top-level 'version'")

    # 2. Doctrine v11 self-declared
    if "v11" not in text:
        errors.append(f"{label}: corpus does not declare Doctrine v11 ('v11' token absent)")

    # 3. Λ-uniqueness / Conjecture 1 must remain OPEN (never marked proven)
    theorems = corpus.get("theorems") or []
    lam = None
    for t in theorems:
        if not isinstance(t, dict):
            continue
        name = (t.get("name") or "")
        if t.get("id") == "TH_L1" or "uniqueness" in name.lower():
            lam = t
            break
    if lam is None:
        errors.append(
            f"{label}: Λ-uniqueness entry (TH_L1, Conjecture 1) not found — cannot verify "
            f"Conjecture 1 honesty"
        )
    else:
        mat = (lam.get("maturity") or "").strip().lower()
        if mat != "conjectured":
            errors.append(
                f"{label}: Λ-uniqueness (TH_L1) maturity is "
                f"'{lam.get('maturity')}', must be 'conjectured' — Conjecture 1 is "
                f"OPEN (unconditional uniqueness is machine-FALSE under A1-A5)"
            )

    # 4. proof_summary honesty ledger: F23 is a conjecture, not a locked proof
    ps = corpus.get("proof_summary") or {}
    if not isinstance(ps, dict):
        ps = {}
    conjecture = ps.get("conjecture") or []
    locked_ids = ps.get("locked_ids") or []
    if "F23" not in conjecture:
        errors.append(
            f"{label}: proof_summary.conjecture must include 'F23' "
            f"(Conjecture 1 / Λ-uniqueness is OPEN)"
        )
    if "F23" in locked_ids:
        errors.append(
            f"{label}: 'F23' must NOT appear in proof_summary.locked_ids "
            f"(Conjecture 1 is not proven)"
        )
    if not ps.get("locked_count_theorem"):
        errors.append(
            f"{label}: proof_summary.locked_count_theorem missing — the locked "
            f"kernel count is not machine-pinned"
        )

    # 5. Theorem U (if present) must be qualified conditional
    if "Theorem U" in text and "conditional" not in text.lower():
        errors.append(
            f"{label}: 'Theorem U' is mentioned but the corpus never qualifies it "
            f"as 'conditional'"
        )

    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Guard: killinchu knowledge.json byte-identical to a11oy's + "
        "Doctrine-v11 honesty invariants."
    )
    ap.add_argument("--self", dest="self_path", required=True,
                    help="path to this repo's (killinchu) knowledge.json")
    ap.add_argument("--sibling", dest="sibling_path", required=True,
                    help="path to a11oy's (canonical) knowledge.json")
    ap.add_argument("--self-name", default="killinchu")
    ap.add_argument("--sibling-name", default="a11oy")
    args = ap.parse_args(argv)

    for p, who in ((args.self_path, args.self_name),
                   (args.sibling_path, args.sibling_name)):
        if not os.path.isfile(p):
            print(f"::error::{who} knowledge.json not found at {p}")
            return 2

    self_sha = sha256_file(args.self_path)
    sib_sha = sha256_file(args.sibling_path)

    print(f"Knowledge-corpus sync guard: {args.self_name} <- {args.sibling_name} "
          f"(a11oy is the source of truth)")
    print(f"  {args.self_name:<10} {args.self_path}  sha256={self_sha}")
    print(f"  {args.sibling_name:<10} {args.sibling_path}  sha256={sib_sha}")
    print()

    failed = False

    # 1) byte-identity (sync)
    if self_sha != sib_sha:
        failed = True
        print(f"::error::knowledge.json has DRIFTED: {args.self_name} is not "
              f"byte-identical to {args.sibling_name}.")
        print(f"::error::  a11oy regenerated its corpus; sync killinchu to match. "
              f"From the killinchu repo root, with a11oy checked out alongside:")
        print(f"::error::    cp ../a11oy/knowledge.json ./knowledge.json")
        print(f"::error::  (then commit). Both files must be byte-identical so the "
              f"two organs never drift from the kernel.")
        print()
    else:
        print(f"OK: knowledge.json is byte-identical across {args.self_name} and "
              f"{args.sibling_name} (sha256={self_sha}).")
        print()

    # 2) honesty invariants on BOTH corpora (so a dishonest corpus can't be synced
    #    in silently, and a dishonest canonical is surfaced even before killinchu
    #    catches up).
    seen = set()
    for path, name in ((args.sibling_path, args.sibling_name),
                       (args.self_path, args.self_name)):
        text, obj = load_corpus(path)
        for err in validate_honesty(text, obj, name):
            if err in seen:
                continue
            seen.add(err)
            failed = True
            print(f"::error::{err}")

    if not seen:
        print("OK: Doctrine-v11 honesty invariants satisfied (Conjecture 1 OPEN, "
              "locked kernel count pinned, Theorem U conditional).")

    print()
    if failed:
        print("FAIL: knowledge corpus is out of sync or violates a Doctrine-v11 "
              "honesty invariant.")
        return 1
    print("PASS: knowledge corpus in sync with a11oy and honest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
