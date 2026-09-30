#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""killinchu_verify_after_action.py — OFFLINE after-action bundle verifier.

Verify a killinchu after-action receipt bundle (schema
``szl.killinchu.after-action/v1``) without trusting the operator and without
needing the Space to be up:

    python tools/killinchu_verify_after_action.py bundle.json
    python tools/killinchu_verify_after_action.py bundle.json --key cosign.pub

WHAT IT CHECKS (pure recomputation, no trust):
  1. SCHEMA            — bundle declares the after-action schema.
  2. RECEIPT DIGESTS   — every ledger node's ``digest`` is recomputed as
                         sha256(json(receipt, sort_keys) + each parent digest)
                         — the exact serve.py ``_digest_node`` construction —
                         over the receipt carried inside the node.
  3. HASH CHAIN        — the GENESIS→head link (node[i-1].digest is node[i]'s
                         first parent) holds for every consecutive pair.
  4. REFERENCED        — every receipt digest referenced by the closure and
                         ROE-decision sections resolves to a chain node.
  5. WITNESSES         — announces each closure's real witness vote count
                         (allow_count ≥ threshold ⇒ CANONICAL, per the
                         certificate — announcing, not fabricating).
  6. DSSE SIGNATURES   — for chain nodes carrying REAL DSSE signatures
                         (base64 sigs), verifies ECDSA-P256 over DSSEv1 PAE
                         against the FIRST available of:
                           a) --key PEM file,
                           b) the bundle's embedded operator public key
                              (sections will state why it is embedded),
                           c) the published org key fetched from
                              https://szlholdings-killinchu.hf.space/cosign.pub
                              (network; skipped honestly when offline).
                         Requires the optional `cryptography` package; without
                         it, signature checks honestly report NOT_CHECKED.

Doctrine law 5: a valid signature proves the INTEGRITY of a claim, never its
correctness. Missing evidence ⇒ INCOMPLETE, never PASS (law 4).

Exit code 0 only when every value-bearing check VERIFIED.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

AFTER_ACTION_SCHEMA = "szl.killinchu.after-action/v1"
COSIGN_PUB_URL = "https://szlholdings-killinchu.hf.space/cosign.pub"


def _canonical(obj: Any) -> bytes:
    # Byte-exact match to serve.py: json.dumps(receipt, sort_keys=True)
    # (default separators with spaces, default ensure_ascii=True).
    return json.dumps(obj, sort_keys=True).encode()


def _digest_node(receipt: Dict[str, Any], parents: List[str]) -> str:
    """Byte-exact copy of serve.py's _digest_node chain-digest construction."""
    h = hashlib.sha256()
    h.update(_canonical(receipt))
    for p in parents:
        h.update(p.encode())
    return h.hexdigest()


def _pae(payload_type: str, body: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding (DSSEv1)."""
    t = payload_type.encode("utf-8")
    return (b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" "
            + str(len(body)).encode() + b" " + body)


class Report:
    def __init__(self) -> None:
        self.checks: List[Tuple[str, str, str]] = []  # (name, state, detail)

    def add(self, name: str, ok: Optional[bool], detail: str) -> None:
        state = "VERIFIED" if ok is True else ("INCOMPLETE" if ok is None else "FAILED")
        self.checks.append((name, state, detail))

    @property
    def ok(self) -> bool:
        # Law 4: an INCOMPLETE or FAILED value-bearing check blocks PASS.
        value_checks = [c for c in self.checks if c[1] != "NOT_APPLICABLE"]
        return all(c[1] == "VERIFIED" for c in value_checks)

    def render(self) -> str:
        lines = []
        for name, state, detail in self.checks:
            glyph = {"VERIFIED": "[OK]  ", "FAILED": "[FAIL]",
                     "INCOMPLETE": "[....]", "NOT_APPLICABLE": "[ n/a]"}.get(state, "[????]")
            lines.append(f"{glyph} {name:34s} {state:26s} {detail}")
        return "\n".join(lines)


def _load_bundle(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _collect_chain_nodes(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    return ((bundle.get("sections") or {}).get("ledger_chain") or {}).get("nodes") or []


def _publisher_key_material(bundle: Dict[str, Any], key_path: Optional[str]) -> Tuple[List[str], str]:
    """Return (candidate PEMs, source-label). Never raises."""
    if key_path:
        try:
            with open(key_path, encoding="utf-8") as f:
                return [f.read()], f"--key {key_path}"
        except OSError as e:
            return [], f"--key unreadable: {e}"
    # Bundle-embedded operator key, published by the exporter when signing was
    # armed (witness keys live per-vote; the org signer key is separate).
    pks = bundle.get("public_key_state") or {}
    if isinstance(pks, dict) and pks.get("public_key_pem"):
        return [pks["public_key_pem"]], "bundle-embedded operator key"
    return [], "no local key material"


def _verify_dsse_sig(env: Dict[str, Any], pem: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pub = serialization.load_pem_public_key(pem.encode())
    body = base64.b64decode(env["payload"])
    to_verify = _pae(env["payloadType"], body)
    for sig in env.get("signatures") or []:
        raw = sig.get("sig", "")
        try:
            base64.b64decode(raw)
        except Exception:
            continue  # not a real signature (placeholder marker) — skip
        try:
            pub.verify(base64.b64decode(raw), to_verify, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            continue
        except Exception:
            continue
    return False


def verify_bundle(bundle: Dict[str, Any], key_path: Optional[str] = None,
                  allow_network: bool = False) -> Report:
    rep = Report()

    # 1. Schema
    rep.add("schema", bundle.get("schema") == AFTER_ACTION_SCHEMA,
            f"schema={bundle.get('schema')!r}")

    sections = bundle.get("sections") or {}
    nodes = _collect_chain_nodes(bundle)

    # 2. Receipt digests recomputed
    if not nodes:
        rep.add("chain nodes", None,
                "ledger_chain section empty — NOT_VERIFIABLE_IN_THIS_RUNTIME")
    else:
        bad = []
        for n in nodes:
            receipt = n.get("receipt") or {}
            parents = n.get("parents") or []
            expect = _digest_node(receipt, parents)
            if n.get("digest") != expect:
                bad.append(n.get("index"))
        rep.add("receipt digests", not bad,
                (f"{len(nodes)} node digests recomputed OK"
                 if not bad else f"digest mismatch at node(s) {bad}"))

    # 3. Hash chain intact (GENESIS→head)
    if nodes:
        breaks = []
        for prev, cur in zip(nodes, nodes[1:]):
            cur_parents = cur.get("parents") or []
            if not cur_parents or cur_parents[0] != prev.get("digest"):
                breaks.append(cur.get("index"))
        rep.add("hash chain", not breaks,
                (f"{len(nodes)-1} links verified GENESIS→head"
                 if not breaks else f"chain break before node(s) {breaks}"))

    # 4. Referenced receipts resolve in the chain
    digests = {n.get("digest") for n in nodes}
    referenced: List[str] = []
    for e in (sections.get("closure") or {}).get("records") or []:
        d = (e.get("receipt") or {}).get("digest")
        if d:
            referenced.append(d)
    for d0 in (sections.get("roe_chain") or {}).get("decisions") or []:
        d = (d0.get("receipt") or {}).get("digest")
        if d:
            referenced.append(d)
    unresolved = [d for d in referenced if d not in digests]
    rep.add("referenced receipts",
            (None if not referenced else not unresolved),
            (f"{len(referenced)} referenced, all resolve in chain"
             if referenced and not unresolved else
             f"{len(unresolved)}/{len(referenced)} referenced digests unresolved"))

    # 5. Witness quorum announcement
    quorums = ((sections.get("witnesses") or {}).get("quorums")) or []
    if not quorums:
        rep.add("witness quorum", None, "no closures carry witness material")
    else:
        parts = []
        all_canonical = True
        for q in quorums:
            wq = q.get("witness_quorum") or {}
            cert = wq.get("certificate") or {}
            allow = cert.get("allow_count")
            thr = cert.get("threshold")
            state = wq.get("state", "UNKNOWN")
            parts.append(f"{q.get('record_id')}: {state} ({allow}/{thr} allow)")
            if state != "CANONICAL":
                all_canonical = False
        rep.add("witness quorum", all_canonical if parts else None,
                "; ".join(parts) + " — SIMULATED in-process witnesses")

    # 6. DSSE signature verification (real sigs only, when key obtainable)
    signed_nodes = [
        n for n in nodes
        if n.get("signed") and any(
            (s.get("sig") or "") and len(s.get("sig", "")) > 64
            for s in (n.get("dsse") or {}).get("signatures") or []
        )
    ]
    if not signed_nodes:
        rep.add("dsse signatures", None,
                "no signed receipts in chain (UNSIGNED-honest runtime or "
                "placeholder keyid) — signature check NOT_APPLICABLE")
        return rep
    try:
        import cryptography  # noqa: F401
    except Exception:
        rep.add("dsse signatures", None,
                f"{len(signed_nodes)} signed receipts but `cryptography` not "
                "installed — pip install cryptography to check signatures")
        return rep

    pems, src = _publisher_key_material(bundle, key_path)
    if not pems and allow_network:
        try:
            import urllib.request
            with urllib.request.urlopen(COSIGN_PUB_URL, timeout=10) as r:
                pems = [r.read().decode()]
            src = COSIGN_PUB_URL
        except Exception as e:
            rep.add("dsse signatures", None,
                    f"could not fetch {COSIGN_PUB_URL}: {type(e).__name__}")
            return rep
    if not pems:
        rep.add("dsse signatures", None,
                f"{len(signed_nodes)} signed receipts but no usable key "
                f"({src}); pass --key cosign.pub or --fetch")
        return rep

    # Verify each signed node against every candidate key; fail if any node
    # verifies against NONE of them.
    unverifiable = []
    for n in signed_nodes:
        env = dict(n.get("dsse") or {})
        receipt = n.get("receipt") or {}
        env["payload"] = base64.b64encode(
            json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")).decode("ascii")
        env.setdefault("payloadType", "application/vnd.szl.receipt+json")
        if not any(_verify_dsse_sig(env, pem) for pem in pems):
            unverifiable.append(n.get("index"))
    rep.add("dsse signatures", not unverifiable,
            (f"{len(signed_nodes)} receipts verify under key from {src}"
             if not unverifiable else
             f"FAILURE: node(s) {unverifiable} do not verify under any "
             f"candidate key ({src})"))
    return rep


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline verifier for killinchu after-action bundles.")
    ap.add_argument("bundle", help="path to the after-action bundle JSON")
    ap.add_argument("--key", help="path to a PEM public key (e.g. cosign.pub)")
    ap.add_argument("--fetch", action="store_true",
                    help=f"allow fetching the published org key from {COSIGN_PUB_URL}")
    args = ap.parse_args(argv)

    try:
        bundle = _load_bundle(args.bundle)
    except Exception as e:
        print(f"FAILED: cannot load bundle: {type(e).__name__}: {e}")
        return 2

    print(f"bundle: {args.bundle} · schema={bundle.get('schema')} "
          f"· track={((bundle.get('scope') or {}).get('track_id'))}")
    rep = verify_bundle(bundle, key_path=args.key, allow_network=args.fetch)
    print(rep.render())
    verdict = "VERIFIED" if rep.ok else "INCOMPLETE_OR_FAILED"
    print(f"\nVERDICT: {verdict}")
    print("Doctrine law 5: a valid signature proves integrity of a claim, "
          "never its correctness. Effectors and witnesses in this bundle are "
          "SIMULATED and so labelled.")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
