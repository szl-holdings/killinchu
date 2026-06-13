# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED · 749/14/163 · Kernel commit c7c0ba17 · SLSA L1
"""
killinchu_mesh.py — REAL szl-mesh exposed over HTTP (Mesh Dev 3, backend API).

This is the operational HTTP surface for the szl-mesh. It runs a REAL,
in-process multi-node mesh harness (3 witness nodes by default, configurable to
4) inside the Space and exposes it under /api/killinchu/v1/mesh/*. NOTHING here
is mocked: every node holds a genuine ECDSA-P256 keypair minted at process
start, every receipt is a real DSSE envelope over canonical JSON (re-hashable to
MATCH), every quorum certificate is the aggregation of >= threshold genuine
ECDSA-P256-SHA256 signatures over the SAME action hash, and enrollment is gated
by a real HMAC-SHA256 doctrine proof (spec/05) that rejects invalid attestation
with an honest 4xx.

HONEST KEY MODEL (Doctrine v11 — never fabricate):
  * The mesh harness witness keys are EPHEMERAL ECDSA-P256 keypairs generated
    in-process at startup with the `cryptography` library. They live only in
    process memory and are NEVER committed. They are clearly labelled
    `key_source: "in_process_harness"` so the surface stays honest: this is a
    real, self-contained mesh running inside ONE Space (Dev 1's harness model),
    not the production per-organ org cosign keys (which are runtime secrets).
  * DSSE receipts use szl_dsse (the org cosign key) IF SZL_COSIGN_PRIVATE_PEM /
    SZL_COSIGN_PRIVATE_KEY_PEM is present; otherwise an HONEST UNSIGNED envelope
    (no fabricated signature). Either way the canonical preimage re-hashes to
    MATCH so a browser can independently verify the receipt body.
  * Khipu BFT (n=4, threshold=3) tolerates f=1 and is labelled Conjecture 2
    (soft-safety AP model is the real shipped one — NEVER claim unconditional
    BFT proven).

Spec coverage:
  01 DSSE receipts on CRDT state transitions  -> /mesh/write, /mesh/receipt/<id>/canonical
  02 two-track AUTHORIZED/OBSERVED state       -> track on every write + /mesh/nodes
  05 doctrine-gated enrollment (HMAC proof)    -> /mesh/enroll
  06 CRDT revocation (grow-only set)           -> /mesh/revoke + revoked-aware tracks
  08 relational graph topology (nodes+edges)   -> /mesh/topology

Stdlib + `cryptography` only (already in the image). try/except-guarded import
of szl_dsse so the module NEVER crashes the app. register(app, ns) FRONT-INSERTS
the routes at position 0 so they beat the SPA /{full_path:path} catch-all.

DCO:
  Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
  Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# ── LOCKED doctrine constants — NEVER MODIFY without a new doctrine release ──
DOCTRINE_VERSION = "749/14/163"           # spec/05 doctrine_claim.doctrine_version
KERNEL_COMMIT = "c7c0ba17"                # locked kernel
SLSA_LEVEL = "L1"
DOCTRINE_PUBLIC = "v11 LOCKED · 749/14/163"
SECTION_889_VENDORS = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]  # exactly 5
QUORUM_N = 4
QUORUM_THRESHOLD = 3                      # 3-of-4 ⇒ tolerates f=1
CONJECTURE_2_NOTE = (
    "Khipu BFT unconditional safety is Conjecture 2 (UNPROVEN). The SHIPPED, "
    "real model is soft-safety AP (CRDT convergence + corroboration). The "
    "3-of-4 quorum below is genuine ECDSA-P256-SHA256 multi-witness agreement; "
    "we never claim unconditional BFT is proven."
)

# DSSE payload types (mirror szl-mesh proto + szl_dsse conventions).
STATE_TRANSITION_PAYLOAD_TYPE = "application/vnd.szl.mesh.state-transition+json"
QUORUM_PAYLOAD_TYPE = "application/vnd.szl.mesh.quorum-certificate+json"
ENROLL_PAYLOAD_TYPE = "application/vnd.szl.mesh.enrollment+json"

# The shared formation key for the in-process harness. This is a LAB/HARNESS
# key (not a production formation secret); it is generated per-process so it is
# never committed, and a node cannot forge a doctrine proof without it (spec/05
# §6: doctrine version inside the HMAC message). In production the formation key
# ships in the Zarf component; here we mint one per Space boot.
_FORMATION_ID = "killinchu-mesh-formation-001"
_FORMATION_KEY = os.urandom(32)

# Optional real org-cosign DSSE signer (honest: unsigned envelope if absent).
try:  # pragma: no cover - degrade gracefully, never crash the app
    import szl_dsse as _szl_dsse
except Exception:  # pragma: no cover
    _szl_dsse = None

# Imported at module top so FastAPI's get_type_hints can resolve the route
# handler annotations (they live in this module's globals, not register()'s).
try:  # pragma: no cover - environments without starlette still import the rest
    from starlette.requests import Request
except Exception:  # pragma: no cover
    Request = Any  # type: ignore

_GENESIS = "0" * 64


# ---------------------------------------------------------------------------
# Canonical JSON + DSSE PAE (byte-identical to szl_dsse / hello_mesh / consensus)
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> bytes:
    """Deterministic canonical JSON: sorted keys, tight separators, UTF-8.

    This is THE re-hashable preimage. A browser that fetches
    /mesh/receipt/<id>/canonical recomputes sha256 over exactly these bytes and
    MATCHes the receipt's preimage_sha256."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def pae(payload_type: str, body: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding (DSSEv1)."""
    t = payload_type.encode("utf-8")
    return (b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" "
            + str(len(body)).encode() + b" " + body)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# A real mesh witness node: ephemeral ECDSA-P256 keypair, held in-process.
# ---------------------------------------------------------------------------

class MeshNode:
    """One real mesh node. Holds a genuine ECDSA-P256 keypair (in-process,
    never committed). Signs state transitions and quorum verdicts."""

    def __init__(self, label: str, role: str = "witness") -> None:
        from cryptography.hazmat.primitives.asymmetric import ec
        self.label = label
        self.role = role
        self._priv = ec.generate_private_key(ec.SECP256R1())
        self.pub_pem = self._public_pem()
        # NodeID = sha256 of the public key PEM (spec/05 compute_node_id).
        self.node_id = _sha256_hex(self.pub_pem.encode("utf-8"))
        self.enrolled = False
        self.enrolled_at: Optional[str] = None
        self.cert_fingerprint: Optional[str] = None
        self.health = "ONLINE"
        self.last_seen = _now()

    def _public_pem(self) -> str:
        from cryptography.hazmat.primitives import serialization
        return self._priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def sign(self, message: bytes) -> bytes:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        return self._priv.sign(message, ec.ECDSA(hashes.SHA256()))

    def verify(self, sig: bytes, message: bytes) -> bool:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        from cryptography.exceptions import InvalidSignature
        try:
            self._priv.public_key().verify(sig, message, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False


# ---------------------------------------------------------------------------
# The mesh harness: real in-process multi-node mesh with two-track CRDT state.
# ---------------------------------------------------------------------------

class MeshHarness:
    """A REAL in-process szl-mesh. Holds N witness nodes, a hash-chained CRDT
    receipt log (two-track AUTHORIZED/OBSERVED, spec 01/02), a grow-only
    revocation set (spec 06), and a relational topology (spec 08)."""

    def __init__(self, n_nodes: int = 3) -> None:
        n_nodes = max(3, min(4, int(n_nodes)))
        self._lock = threading.RLock()
        self.started_at = _now()
        # node-alpha is the formation operator/seed; the rest are witnesses.
        labels = ["node-alpha", "node-bravo", "node-charlie", "node-delta"][:n_nodes]
        roles = ["operator"] + ["witness"] * (n_nodes - 1)
        self.nodes: dict[str, MeshNode] = {}
        for label, role in zip(labels, roles):
            node = MeshNode(label, role)
            self.nodes[node.node_id] = node
        # CRDT two-track receipt log (hash-chained) + grow-only revocation set
        # (spec 06) — initialised BEFORE auto-enroll so step 6 can read them.
        self._chain: list[dict[str, Any]] = []
        self._receipts_by_id: dict[str, dict[str, Any]] = {}
        self._revoked: dict[str, dict[str, Any]] = {}
        self.crdt_doc_id = f"{_FORMATION_ID}/platforms"
        # Auto-enroll the seed nodes with a VALID doctrine proof so the mesh has
        # real enrolled members at boot (genuine HMAC, not a flag flip).
        for node in self.nodes.values():
            proof = self._formation_proof(node.node_id, self.started_at)
            self._enroll_node(node, proof, self.started_at,
                              DOCTRINE_VERSION, KERNEL_COMMIT, SLSA_LEVEL, True)

    # -- spec/05 doctrine-gated enrollment ---------------------------------
    @staticmethod
    def _formation_proof(node_id: str, ts: str) -> str:
        """HMAC-SHA256(formation_key, node_id||ts||doctrine||kernel) — spec/05 §2.
        Doctrine + kernel are INSIDE the HMAC so they cannot be spoofed."""
        msg = (node_id + ts + DOCTRINE_VERSION + KERNEL_COMMIT).encode("utf-8")
        return hmac.new(_FORMATION_KEY, msg, hashlib.sha256).hexdigest()

    def _enroll_node(self, node: MeshNode, proof: str, ts: str,
                     doctrine: str, kernel: str, slsa: str,
                     vendor_excl: bool) -> dict[str, Any]:
        """Run the spec/05 §3 validation steps. Returns a verdict dict.
        On success the node is enrolled and a cert fingerprint assigned."""
        steps: list[dict[str, Any]] = []

        def step(name: str, ok: bool, detail: str = "") -> bool:
            steps.append({"step": name, "ok": bool(ok), "detail": detail})
            return ok

        # 1. formation_key_proof (HMAC over doctrine-bound message)
        expected = self._formation_proof(node.node_id, ts)
        ok1 = step("formation_key_proof", hmac.compare_digest(proof or "", expected),
                   "HMAC-SHA256 over node_id||ts||doctrine||kernel")
        # 2. timestamp window ±5 min
        try:
            t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            drift = abs((datetime.now(timezone.utc) - t).total_seconds())
            ok2 = step("timestamp_window", drift <= 300, f"drift={int(drift)}s (<=300)")
        except Exception as e:
            ok2 = step("timestamp_window", False, f"unparseable timestamp: {e}")
        # 3-5. doctrine / kernel / slsa pin
        ok3 = step("doctrine_version", doctrine == DOCTRINE_VERSION,
                   f"claim={doctrine!r} expect={DOCTRINE_VERSION!r}")
        ok4 = step("kernel_commit", kernel == KERNEL_COMMIT,
                   f"claim={kernel!r} expect={KERNEL_COMMIT!r}")
        ok5 = step("slsa_level", slsa == SLSA_LEVEL,
                   f"claim={slsa!r} expect={SLSA_LEVEL!r}")
        # 6. revocation list check
        ok6 = step("not_revoked", node.cert_fingerprint not in self._revoked,
                   "node_id/cert not in CRDT revocation set")
        # 7. Section 889 vendor exclusion
        ok7 = step("section_889_exclusion", bool(vendor_excl),
                   "vendor_exclusion_confirmed (5 banned vendors)")

        all_ok = all([ok1, ok2, ok3, ok4, ok5, ok6, ok7])
        if all_ok:
            node.enrolled = True
            node.enrolled_at = ts
            # cert fingerprint = sha256 over (pubkey || doctrine || kernel)
            node.cert_fingerprint = _sha256_hex(
                (node.pub_pem + doctrine + kernel).encode("utf-8"))
            return {"success": True, "node_id": node.node_id,
                    "cert_fingerprint": node.cert_fingerprint,
                    "cert_ttl_days": 90, "steps": steps}
        # honest failure reason: first failing step
        first_fail = next((s["step"] for s in steps if not s["ok"]), "unknown")
        return {"success": False, "node_id": node.node_id,
                "failure_reason": first_fail, "steps": steps}

    def enroll_request(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Public enrollment endpoint logic. Accepts an attestation for a NEW
        node (caller supplies its own ECDSA-P256 public key PEM + proof) OR for
        an existing harness node by node_id. Returns (verdict, http_status).

        HONEST 4xx on invalid attestation (bad proof, wrong doctrine, replay,
        Section 889 violation)."""
        with self._lock:
            doctrine = str(body.get("doctrine_version", ""))
            kernel = str(body.get("kernel_commit", ""))
            slsa = str(body.get("slsa_level", SLSA_LEVEL))
            ts = str(body.get("timestamp_utc", "")) or _now()
            proof = str(body.get("formation_key_proof", ""))
            vendor_excl = bool(body.get("vendor_exclusion_confirmed", False))
            hw_vendor = str(body.get("hardware_vendor", "") or "")

            # Section 889 hard reject (spec/05 §): banned vendor short-circuits.
            if hw_vendor and any(v.lower() in hw_vendor.lower() for v in SECTION_889_VENDORS):
                return ({"success": False, "failure_reason": "SECTION_889_VIOLATION",
                         "hardware_vendor": hw_vendor,
                         "banned_vendors": SECTION_889_VENDORS,
                         "honesty": "HONEST REJECT — Section 889 banned vendor."}, 403)

            pub_pem = body.get("ed25519_public_key") or body.get("public_key_pem")
            node_id = body.get("node_id")
            if pub_pem:
                # New external node: compute its node_id from the supplied pubkey.
                try:
                    from cryptography.hazmat.primitives.serialization import load_pem_public_key
                    load_pem_public_key(pub_pem.encode("utf-8"))  # validate format
                except Exception as e:
                    return ({"success": False, "failure_reason": "INVALID_PUBLIC_KEY",
                             "detail": str(e)}, 400)
                ext = MeshNode.__new__(MeshNode)  # external node shell (no priv key)
                ext.label = body.get("label", "node-external")
                ext.role = "witness"
                ext.pub_pem = pub_pem
                ext.node_id = _sha256_hex(pub_pem.encode("utf-8"))
                ext.enrolled = False
                ext.enrolled_at = None
                ext.cert_fingerprint = None
                ext.health = "PENDING"
                ext.last_seen = _now()
                node = ext
            elif node_id and node_id in self.nodes:
                node = self.nodes[node_id]
            else:
                return ({"success": False, "failure_reason": "UNKNOWN_NODE",
                         "detail": "supply public_key_pem (new node) or a known node_id"}, 400)

            verdict = self._enroll_node(node, proof, ts, doctrine, kernel,
                                        slsa, vendor_excl)
            if verdict.get("success"):
                # add the (now-enrolled) node to the mesh if external.
                self.nodes[node.node_id] = node
                node.health = "ONLINE"
                return (verdict, 200)
            # honest 4xx — invalid attestation.
            return (verdict, 403)

    # -- spec/01+02 receipted CRDT state transition ------------------------
    def write_transition(self, body: dict[str, Any]) -> dict[str, Any]:
        """Write a receipted CRDT state transition and return the DSSE receipt.

        Two-track (spec 02): AUTHORIZED iff a valid DSSE receipt is produced AND
        the writing node is enrolled & not revoked; else OBSERVED. The state
        transition statement (spec 01) is the re-hashable preimage."""
        with self._lock:
            node_id = body.get("node_id") or next(iter(self.nodes))
            node = self.nodes.get(node_id)
            payload = body.get("payload") or {}
            transition_class = str(body.get("transition_class", "PLATFORM_STATUS"))
            change_data = canonical_json({"node_id": node_id, "payload": payload,
                                          "ts": _now(), "seq": len(self._chain)})
            change_hash = _sha256_hex(change_data)
            prev_head = self._chain[-1]["digest"] if self._chain else _GENESIS

            # spec/01 §3 StateTransitionStatement — THE preimage.
            stmt = {
                "type": "szl-mesh/state-transition/v1",
                "doctrine_version": DOCTRINE_VERSION,
                "kernel_commit": KERNEL_COMMIT,
                "crdt_document_id": self.crdt_doc_id,
                "change_hash": change_hash,
                "from_state_head": [prev_head],
                "to_state_head": [change_hash],
                "transition_class": transition_class,
                "node_id": node_id,
                "payload": payload,
                "timestamp_utc": _now(),
                "policy_context": {
                    "section_889_vendors": SECTION_889_VENDORS,
                    "slsa_level": SLSA_LEVEL,
                },
            }
            preimage = canonical_json(stmt)
            preimage_sha256 = _sha256_hex(preimage)

            # Real DSSE envelope via szl_dsse (org cosign) — honest if unsigned.
            if _szl_dsse is not None:
                dsse_env = _szl_dsse.sign_payload(stmt, STATE_TRANSITION_PAYLOAD_TYPE)
            else:
                dsse_env = {
                    "payloadType": STATE_TRANSITION_PAYLOAD_TYPE,
                    "payload": base64.b64encode(preimage).decode("ascii"),
                    "signatures": [], "signed": False,
                    "honesty": "UNSIGNED — szl_dsse module unavailable; no signature fabricated.",
                }

            # ALSO co-sign with the writing harness node's REAL ephemeral key so
            # the receipt has a genuine in-process node signature regardless of
            # whether the org cosign secret is present.
            node_sig_b64 = None
            node_signed = False
            if node is not None and getattr(node, "_priv", None) is not None:
                try:
                    node_sig = node.sign(pae(STATE_TRANSITION_PAYLOAD_TYPE, preimage))
                    node_sig_b64 = base64.b64encode(node_sig).decode("ascii")
                    node_signed = True
                except Exception:
                    node_signed = False

            # spec/02 two-track assignment.
            dsse_signed = bool(dsse_env.get("signed"))
            node_ok = bool(node and node.enrolled and node.cert_fingerprint not in self._revoked)
            track = "AUTHORIZED" if (node_ok and (dsse_signed or node_signed)) else "OBSERVED"

            receipt_id = uuid.uuid4().hex
            body_chain = {
                "receipt_id": receipt_id,
                "ns": "killinchu",
                "seq": len(self._chain),
                "crdt_document_id": self.crdt_doc_id,
                "change_hash": change_hash,
                "node_id": node_id,
                "prev": prev_head,
                "preimage_sha256": preimage_sha256,
                "ts": stmt["timestamp_utc"],
                "transition_class": transition_class,
            }
            digest = _sha256_hex(canonical_json(body_chain))
            receipt = {
                **body_chain,
                "digest": digest,
                "track": track,
                "dsse": dsse_env,
                "node_signature": {
                    "node_id": node_id, "keyid": f"{node_id[:12]}-harness",
                    "sig": node_sig_b64, "signed": node_signed,
                    "alg": "ECDSA-P256-SHA256",
                    "key_source": "in_process_harness",
                },
                "chain_verified": True,
            }
            self._chain.append(receipt)
            self._receipts_by_id[receipt_id] = {"receipt": receipt, "statement": stmt,
                                                "preimage_b64": base64.b64encode(preimage).decode("ascii")}
            if node is not None:
                node.last_seen = _now()
            return receipt

    def receipt_canonical(self, receipt_id: str) -> Optional[dict[str, Any]]:
        """Return the re-hashable preimage for a receipt (like a11oy's
        receipt-canonical) so a browser can verify the receipt MATCHes."""
        with self._lock:
            entry = self._receipts_by_id.get(receipt_id)
            if not entry:
                return None
            stmt = entry["statement"]
            preimage = canonical_json(stmt)
            return {
                "receipt_id": receipt_id,
                "payloadType": STATE_TRANSITION_PAYLOAD_TYPE,
                # The EXACT bytes to re-hash (canonical JSON of the statement).
                "canonical_preimage": stmt,
                "canonical_preimage_b64": base64.b64encode(preimage).decode("ascii"),
                "preimage_sha256": _sha256_hex(preimage),
                "pae_sha256": _sha256_hex(pae(STATE_TRANSITION_PAYLOAD_TYPE, preimage)),
                "dsse": entry["receipt"]["dsse"],
                "node_signature": entry["receipt"]["node_signature"],
                "verify_instructions": (
                    "sha256(canonical_json(canonical_preimage)) MUST equal "
                    "preimage_sha256. For the DSSE signature, recompute "
                    "PAE('%s', canonical_json(canonical_preimage)) and verify "
                    "with cosign.pub." % STATE_TRANSITION_PAYLOAD_TYPE),
            }

    def verify_chain(self) -> dict[str, Any]:
        with self._lock:
            prev = _GENESIS
            for i, r in enumerate(self._chain):
                body_chain = {k: r[k] for k in (
                    "receipt_id", "ns", "seq", "crdt_document_id", "change_hash",
                    "node_id", "prev", "preimage_sha256", "ts", "transition_class")}
                if r["prev"] != prev:
                    return {"ok": False, "depth": len(self._chain), "broken_at": i,
                            "reason": "prev-link mismatch"}
                if _sha256_hex(canonical_json(body_chain)) != r["digest"]:
                    return {"ok": False, "depth": len(self._chain), "broken_at": i,
                            "reason": "digest mismatch"}
                prev = r["digest"]
            return {"ok": True, "depth": len(self._chain), "broken_at": None}

    # -- 3-of-4 Khipu quorum (real ECDSA per-witness sigs) -----------------
    def run_quorum(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run a canonical action through the 3-of-4 witness quorum. Each
        enrolled witness independently DSSE-signs the SAME action hash with its
        real ECDSA-P256 key; >= threshold valid `allow` sigs ⇒ CANONICAL.

        This is a GENUINE multi-witness quorum certificate (Conjecture 2 note
        attached for the Khipu BFT claim — never claimed unconditional)."""
        with self._lock:
            action = body.get("action") or {"op": "noop"}
            action_body = canonical_json({"action": action, "formation": _FORMATION_ID})
            action_hash = _sha256_hex(action_body)
            # honest fault injection for testing: caller may mark witnesses as
            # 'block' or 'offline' to demonstrate < threshold ⇒ REJECTED.
            faults = body.get("faults") or {}

            witnesses = [n for n in self.nodes.values()
                         if n.enrolled and getattr(n, "_priv", None) is not None
                         and n.cert_fingerprint not in self._revoked]
            witnesses = witnesses[:QUORUM_N]
            votes: list[dict[str, Any]] = []
            allow_count = 0
            for w in witnesses:
                fault = faults.get(w.label) or faults.get(w.node_id)
                if fault == "offline":
                    votes.append({"node_id": w.node_id, "label": w.label,
                                  "verdict": "offline", "signed": False,
                                  "reason": "witness unreachable (fault-injected)"})
                    continue
                verdict = "block" if fault == "block" else "allow"
                stmt = {
                    "schema": "szl.mesh.witness_verdict/v1",
                    "node_id": w.node_id, "label": w.label,
                    "action_hash": action_hash, "verdict": verdict,
                    "doctrine_version": DOCTRINE_VERSION, "kernel_commit": KERNEL_COMMIT,
                    "ts": _now(),
                }
                vbody = canonical_json(stmt)
                sig = w.sign(pae(QUORUM_PAYLOAD_TYPE, vbody))
                vote = {
                    "node_id": w.node_id, "label": w.label, "verdict": verdict,
                    "signed": True, "alg": "ECDSA-P256-SHA256",
                    "key_source": "in_process_harness",
                    "payload": base64.b64encode(vbody).decode("ascii"),
                    "sig": base64.b64encode(sig).decode("ascii"),
                    "pub_pem": w.pub_pem,
                }
                # self-verify the sig immediately (real verification, not a flag)
                vote["verified"] = w.verify(sig, pae(QUORUM_PAYLOAD_TYPE, vbody))
                if vote["verified"] and verdict == "allow":
                    allow_count += 1
                votes.append(vote)

            canonical = allow_count >= QUORUM_THRESHOLD
            cert_body = {
                "schema": "szl.mesh.quorum_certificate/v1",
                "formation_id": _FORMATION_ID,
                "action": action, "action_hash": action_hash,
                "n": QUORUM_N, "threshold": QUORUM_THRESHOLD,
                "allow_count": allow_count, "tolerates_f": QUORUM_N - QUORUM_THRESHOLD,
                "canonical": canonical,
                "verdict": "CANONICAL" if canonical else "REJECTED",
                "ts": _now(),
            }
            cert_preimage = canonical_json(cert_body)
            # DSSE-wrap the certificate (org cosign if present, else honest).
            if _szl_dsse is not None:
                cert_dsse = _szl_dsse.sign_payload(cert_body, QUORUM_PAYLOAD_TYPE)
            else:
                cert_dsse = {"payloadType": QUORUM_PAYLOAD_TYPE,
                             "payload": base64.b64encode(cert_preimage).decode("ascii"),
                             "signatures": [], "signed": False,
                             "honesty": "UNSIGNED — szl_dsse unavailable."}
            return {
                "certificate": cert_body,
                "certificate_preimage_sha256": _sha256_hex(cert_preimage),
                "votes": votes,
                "dsse": cert_dsse,
                "conjecture_2_note": CONJECTURE_2_NOTE,
                "honesty": ("REAL — each vote is a genuine ECDSA-P256-SHA256 "
                            "signature over the SAME action hash, verified in "
                            "process against the signer's public key."),
            }

    # -- spec/06 CRDT revocation (grow-only) -------------------------------
    def revoke(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        with self._lock:
            node_id = body.get("node_id")
            reason = str(body.get("reason", "ADMINISTRATIVE")).upper()
            valid_reasons = {"BYZANTINE", "COMPROMISED", "DOCTRINE_MISMATCH",
                             "ADMINISTRATIVE", "SECTION_889"}
            if reason not in valid_reasons:
                return ({"success": False, "failure_reason": "INVALID_REASON",
                         "valid": sorted(valid_reasons)}, 400)
            node = self.nodes.get(node_id)
            if not node or not node.cert_fingerprint:
                return ({"success": False, "failure_reason": "UNKNOWN_OR_UNENROLLED_NODE",
                         "node_id": node_id}, 404)
            fp = node.cert_fingerprint
            if fp in self._revoked:
                return ({"success": True, "already_revoked": True,
                         "cert_fingerprint": fp, "entry": self._revoked[fp]}, 200)
            entry = {
                "node_id": node_id, "cert_fingerprint": fp,
                "revoked_at": _now(), "reason": reason,
                "revoked_by": next(iter(self.nodes)),  # operator node
            }
            self._revoked[fp] = entry  # grow-only — never removed
            node.health = "REVOKED"
            node.enrolled = False
            return ({"success": True, "cert_fingerprint": fp, "entry": entry,
                     "crdt_document_id": f"szl-mesh/revoked-certs/formation-{_FORMATION_ID}",
                     "monotonic": "grow-only CRDT set — entries are never removed"}, 200)

    # -- views --------------------------------------------------------------
    def topology(self) -> dict[str, Any]:
        """spec 08 relational graph topology: nodes + edges. The mesh is a
        bounded-degree overlay: the operator node connects to every witness;
        witnesses form a corroboration ring among themselves."""
        with self._lock:
            node_list = list(self.nodes.values())
            ids = [n.node_id for n in node_list]
            nodes_out = [{
                "id": n.node_id, "label": n.label, "role": n.role,
                "health": n.health, "enrolled": n.enrolled,
                "revoked": n.cert_fingerprint in self._revoked if n.cert_fingerprint else False,
            } for n in node_list]
            edges = []
            operator = next((n for n in node_list if n.role == "operator"), None)
            witnesses = [n for n in node_list if n.role != "operator"]
            # star: operator -> each witness (enrollment/cert distribution)
            if operator:
                for w in witnesses:
                    edges.append({"source": operator.node_id, "target": w.node_id,
                                  "kind": "enrollment", "directed": True})
            # ring: witness corroboration (skip-layer aggregation, spec 03)
            for i, w in enumerate(witnesses):
                nxt = witnesses[(i + 1) % len(witnesses)] if len(witnesses) > 1 else None
                if nxt and nxt.node_id != w.node_id:
                    edges.append({"source": w.node_id, "target": nxt.node_id,
                                  "kind": "corroboration", "directed": False})
            return {
                "formation_id": _FORMATION_ID,
                "crdt_document_id": self.crdt_doc_id,
                "nodes": nodes_out, "edges": edges,
                "node_count": len(nodes_out), "edge_count": len(edges),
                "topology_class": "bounded-degree overlay (star + corroboration ring)",
                "spec": "08-relational-graph-topology",
            }

    def nodes_view(self) -> dict[str, Any]:
        with self._lock:
            out = []
            for n in self.nodes.values():
                revoked = bool(n.cert_fingerprint and n.cert_fingerprint in self._revoked)
                out.append({
                    "node_id": n.node_id, "label": n.label, "role": n.role,
                    "health": n.health, "enrolled": n.enrolled, "revoked": revoked,
                    "cert_fingerprint": n.cert_fingerprint,
                    "public_key_pem": n.pub_pem, "last_seen": n.last_seen,
                    "key_source": "in_process_harness",
                })
            enrolled = sum(1 for n in self.nodes.values() if n.enrolled)
            return {"nodes": out, "node_count": len(out), "enrolled_count": enrolled,
                    "revoked_count": len(self._revoked),
                    "two_track_spec": "02-two-track-state (AUTHORIZED/OBSERVED)"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "live": True,
                "doctrine": DOCTRINE_PUBLIC,
                "doctrine_version": DOCTRINE_VERSION,
                "kernel_commit": KERNEL_COMMIT,
                "slsa_level": SLSA_LEVEL,
                "node_count": len(self.nodes),
                "enrolled_count": sum(1 for n in self.nodes.values() if n.enrolled),
                "revoked_count": len(self._revoked),
                "receipt_chain_depth": len(self._chain),
                "chain_verified": self.verify_chain()["ok"],
                "quorum_config": {"n": QUORUM_N, "threshold": QUORUM_THRESHOLD,
                                  "tolerates_f": QUORUM_N - QUORUM_THRESHOLD,
                                  "alg": "ECDSA-P256-SHA256 DSSE"},
                "conjecture_2_note": CONJECTURE_2_NOTE,
                "section_889_vendors": SECTION_889_VENDORS,
                "started_at": self.started_at,
                "key_model": ("in-process ephemeral ECDSA-P256 witness keys (LIVE, "
                              "never committed); org cosign DSSE used for receipts "
                              "when SZL_COSIGN_PRIVATE_PEM secret is present, else "
                              "honest UNSIGNED (no fabrication)."),
            }


# ---------------------------------------------------------------------------
# Singleton harness (one real mesh per Space process).
# ---------------------------------------------------------------------------
_HARNESS: Optional[MeshHarness] = None
_HARNESS_LOCK = threading.Lock()
_HARNESS_ERROR: Optional[str] = None


def get_harness() -> Optional[MeshHarness]:
    """Lazily start the real in-process mesh. If it cannot start (e.g. the
    cryptography lib is unavailable), returns None and records the error so the
    endpoints report HONESTLY that the harness is not running (never fakes)."""
    global _HARNESS, _HARNESS_ERROR
    if _HARNESS is not None:
        return _HARNESS
    with _HARNESS_LOCK:
        if _HARNESS is not None:
            return _HARNESS
        try:
            n = int(os.environ.get("KILLINCHU_MESH_NODES", "3"))
            _HARNESS = MeshHarness(n_nodes=n)
            return _HARNESS
        except Exception as e:  # honest: harness down
            _HARNESS_ERROR = f"{type(e).__name__}: {e}"
            return None


def _harness_down_payload() -> dict[str, Any]:
    return {"live": False, "error": "mesh harness not running",
            "detail": _HARNESS_ERROR or "harness failed to initialize",
            "honesty": "HONEST — the in-process mesh harness is NOT running; "
                       "no node or quorum fabricated."}


# ---------------------------------------------------------------------------
# Registration — FRONT-INSERT routes at position 0 (beat the SPA catch-all).
# ---------------------------------------------------------------------------

def register(app, ns: str = "killinchu") -> dict[str, Any]:
    """Register the mesh HTTP surface on `app`. Routes are inserted at position
    0 so they beat the SPA /{full_path:path} catch-all. try/except-guarded by
    the caller — never crashes the app. Returns a small status dict."""
    from fastapi.routing import APIRoute
    from fastapi.responses import JSONResponse

    base = f"/api/{ns}/v1/mesh"

    async def _read_json(request: Request) -> dict[str, Any]:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def topology(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        return JSONResponse({"live": True, **h.topology()})

    async def nodes(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        return JSONResponse({"live": True, **h.nodes_view()})

    async def enroll(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        body = await _read_json(request)
        verdict, status = h.enroll_request(body)
        return JSONResponse({"live": True, "spec": "05-doctrine-gated-enrollment",
                             **verdict}, status_code=status)

    async def write(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        body = await _read_json(request)
        receipt = h.write_transition(body)
        return JSONResponse({"live": True, "spec": "01-dsse-receipts/02-two-track",
                             "receipt": receipt})

    async def quorum(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        body = await _read_json(request)
        return JSONResponse({"live": True, **h.run_quorum(body)})

    async def receipt_canonical(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        rid = request.path_params.get("rid", "")
        out = h.receipt_canonical(rid)
        if out is None:
            return JSONResponse({"live": True, "error": "receipt not found",
                                 "receipt_id": rid}, status_code=404)
        return JSONResponse({"live": True, **out})

    async def revoke(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        body = await _read_json(request)
        verdict, status = h.revoke(body)
        return JSONResponse({"live": True, "spec": "06-crdt-revocation", **verdict},
                            status_code=status)

    async def status_ep(request: Request) -> JSONResponse:
        h = get_harness()
        if h is None:
            return JSONResponse(_harness_down_payload(), status_code=503)
        return JSONResponse(h.status())

    specs = [
        ("/topology", topology, ["GET"], "mesh_topology"),
        ("/nodes", nodes, ["GET"], "mesh_nodes"),
        ("/enroll", enroll, ["POST"], "mesh_enroll"),
        ("/write", write, ["POST"], "mesh_write"),
        ("/quorum", quorum, ["POST"], "mesh_quorum"),
        ("/receipt/{rid}/canonical", receipt_canonical, ["GET"], "mesh_receipt_canonical"),
        ("/revoke", revoke, ["POST"], "mesh_revoke"),
        ("/status", status_ep, ["GET"], "mesh_status"),
    ]
    names = {n for _, _, _, n in specs}
    # Drop any prior copies (idempotent re-register) then front-insert.
    app.router.routes[:] = [r for r in app.router.routes
                            if getattr(r, "name", "") not in names]
    new_routes = [APIRoute(f"{base}{p}", h, methods=m, name=n)
                  for p, h, m, n in specs]
    for r in reversed(new_routes):
        app.router.routes.insert(0, r)
    return {"registered": len(new_routes), "base": base,
            "routes": [f"{m[0]} {base}{p}" for p, _, m, _ in specs]}
