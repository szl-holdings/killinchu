# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""killinchu_after_action — per-engagement AFTER-ACTION RECEIPT BUNDLE.

One self-contained JSON bundle per engagement: the engagement closure (with its
3-of-4 witness quorum certificate), every persisted ROE gate decision for the
track, the track timeline, the ROE policy hash, and the raw Khipu ledger nodes
each decision was receipted into — with the full hash chain from GENESIS and
the operator's public key when signing is armed.

CHECKABLE WITHOUT TRUSTING US:
    python tools/killinchu_verify_after_action.py bundle.json
    python tools/killinchu_verify_after_action.py bundle.json --key cosign.pub

recomputes every receipt digest + every hash link, announces the verdict
witness count, verifies DSSE signatures against /cosign.pub when an org key
signed them (and when the optional `cryptography` package is available —
without it, signature checks honestly report NOT_CHECKED). A signature proves
integrity of a claim, never its correctness (Doctrine law 5).

HONESTY (evidence-first, Zero-Bandaid):
  * Effectors remain SIMULATED — killinchu governs and receipts the decision;
    it does not fire anything.
  * Witnesses are SIMULATED in-process mesh nodes holding REAL ECDSA-P256 keys
    (genuine 3-of-4 quorum protocol run, verifiable per-vote, NOT cross-organ
    production signers). Khipu BFT safety is Conjecture 2 (OPEN).
  * The ledger slice is assembled from memory since process start — it is the
    honest same-runtime evidence window, and `verification_hints` says so.
  * When the runtime was restarted between a decision and this export, prior
    Khipu nodes no longer exist here; affected sections are marked
    NOT_VERIFIABLE_IN_THIS_RUNTIME (an audited state — never a blank).
  * Absent facts (operator identity, full closure data) are labelled UNKNOWN.
    An unsigned-honest ledger (no cosign secret) is exported as UNSIGNED —
    never dressed up as verified.

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

SCHEMA = "szl.killinchu.after-action/v1"

# Evidence sections of the bundle (audited set — every export carries all of
# them, empty sections marked, per Zero-Bandaid).
SECTIONS = ["closure", "roe_chain", "track_timeline", "policy", "ledger_chain", "witnesses"]


def _now(dsse_module: Any = None) -> str:
    # Pure-stdlib timestamp (datetime is stdlib; passing through a hook keeps
    # the shape testable without importing callers' helpers).
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _public_key_state(dsse_module: Any) -> Dict[str, Any]:
    """Honest operator public-key state for offline verification."""
    if dsse_module is None:
        return {
            "available": False,
            "state": "INVALID",
            "reason": "dsse module absent in this runtime",
            "verify_key_url": None,
        }
    try:
        if not dsse_module.signing_available():
            return {
                "available": False,
                "state": "UNAVAILABLE",
                "reason": ("no SZL_COSIGN_PRIVATE_PEM in this runtime — ledger "
                           "receipts are UNSIGNED-honest; there is no active "
                           "signing key to publish. The embedded org fallback "
                           "key remains at the URL below."),
                "verify_key_url": getattr(dsse_module, "PUB_KEY_URL", "/cosign.pub"),
            }
        pem = dsse_module.active_public_key_pem()
        return {
            "available": bool(pem),
            "state": "AVAILABLE" if pem else "UNAVAILABLE",
            "public_key_pem": pem,
            "keyid": dsse_module.keyid_for_public_pem(pem) if pem else None,
            "verify_key_url": getattr(dsse_module, "PUB_KEY_URL", "/cosign.pub"),
        }
    except Exception:
        return {
            "available": False,
            "state": "INVALID",
            "reason": "active signing key could not be verified in this runtime",
            "verify_key_url": None,
        }


def _collect_witness_material(
    engagements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the witnesses section across ALL of the track's closures.

    Every closure that carries a witness_quorum block is listed (verdict,
    allow/threshold, votes) so the verifier can ANNOUNCE the real count.
    Per-vote public keys travel inside each vote — embedded where the runtime
    retained them, honestly absent where it did not. Nothing is invented.
    """
    quorums = [
        {
            "record_id": e.get("record_id"),
            "witness_quorum": e.get("witness_quorum"),
        }
        for e in engagements
        if isinstance(e.get("witness_quorum"), dict)
    ]
    if not quorums:
        return {
            "state": "NOT_RECORDED",
            "key_material": "NOT_RETAINED",
            "honesty": ("No engagement in this window carries a witness quorum; "
                        "nothing fabricated."),
            "quorums": [],
        }
    signed_votes = sum(
        1
        for q in quorums
        for v in (q["witness_quorum"].get("votes") or [])
        if v.get("signed") and v.get("pub_pem")
    )
    return {
        "state": "KEY_MATERIAL_EMBEDDED" if signed_votes else "VERDICT_ONLY",
        "closure_count": len(quorums),
        "embedded_signed_votes": signed_votes,
        "honesty": (
            "Every closure's quorum verdict is listed with its real "
            "allow/threshold count. Per-vote ECDSA public keys are embedded "
            "where the runtime retained them (in-process witness keys are "
            "per-process); VERDICT_ONLY means the certificate verdict stands "
            "without retained vote keys — labelled, never blank."
        ),
        "quorums": quorums,
    }


def build_after_action_bundle(
    *,
    track_id: str,
    engagements: List[Dict[str, Any]],
    roe_decisions: List[Dict[str, Any]],
    track_updates: List[Dict[str, Any]],
    ledger_nodes: Optional[List[Dict[str, Any]]],
    policy_version: Optional[str],
    policy_hash: Optional[str],
    dsse_module: Any = None,
    doctrine: str = "v11",
) -> Dict[str, Any]:
    """Assemble the after-action receipt bundle for ONE track's engagements.

    All inputs are plain dicts/lists (already-snapshotted by the caller); the
    function is pure — no I/O, no clock beyond the banner timestamp — so the
    bundle shape is testable offline (mirrors killinchu_receipt_export's
    design).

    Parameters
    ----------
    track_id:
        The track this after-action covers.
    engagements:
        Closure records for the track (chronological), each optionally
        carrying ``witness_quorum`` and ``receipt`` coordinates.
    roe_decisions:
        Persisted ROE gate evaluations for the track (chronological), each
        carrying ``receipt`` coordinates.
    track_updates:
        Ingest/fusion timeline entries for the track (chronological).
    ledger_nodes:
        The full in-memory Khipu ledger snapshot (GENESIS→head) when the
        runtime ledger is ready, else None (chain section marked
        NOT_VERIFIABLE_IN_THIS_RUNTIME).
    policy_version / policy_hash:
        The active ROE policy identity at export time (hash=None → UNKNOWN).
    dsse_module:
        The live szl_dsse module when importable (for the public-key state);
        pass None in offline tests.
    """
    digest_index: Dict[str, Dict[str, Any]] = {}
    chain_nodes: List[Dict[str, Any]] = []
    ledger_ready = isinstance(ledger_nodes, list)
    if ledger_ready:
        for node in ledger_nodes:
            digest = node.get("digest")
            if digest:
                digest_index[digest] = node
                chain_nodes.append(node)

    def _section_state(needs: List[Optional[str]]) -> str:
        if not ledger_ready:
            return "NOT_VERIFIABLE_IN_THIS_RUNTIME"
        if all(d and d in digest_index for d in needs):
            return "VERIFIABLE"
        return "INCOMPLETE"

    # Cover EVERY decision/receipt digest referenced by the bundle, last
    # (heaviest) section first so resolution is uniform.
    roe_needs = [((d.get("receipt") or {}).get("digest")) for d in roe_decisions]
    eng_needs = [((e.get("receipt") or {}).get("digest")) for e in engagements]
    sections = {
        "closure": {
            "state": "VERIFIABLE" if engagements else "EMPTY",
            "records": engagements,
        },
        "roe_chain": {
            "state": _section_state(roe_needs) if roe_decisions else "EMPTY",
            "decisions": roe_decisions,
        },
        "track_timeline": {
            "state": "PRESENT" if track_updates else "EMPTY",
            "updates": track_updates,
        },
        "policy": {
            "version": policy_version if policy_version else "UNKNOWN",
            "hash_sha256": policy_hash if policy_hash else "UNKNOWN",
        },
        "ledger_chain": {
            "state": "INCLUDED" if chain_nodes else (
                "NOT_VERIFIABLE_IN_THIS_RUNTIME" if ledger_ready is False else "EMPTY"
            ),
            "node_count": len(chain_nodes),
            "nodes": chain_nodes,
        },
        "witnesses": _collect_witness_material(engagements),
    }

    # Escalate section states: a VERIFIABLE payload section is downgraded by
    # the chain state — if the chain is absent, nothing can be checked.
    if not chain_nodes:
        for key in ("closure", "roe_chain"):
            if sections[key]["state"] == "VERIFIABLE":
                sections[key]["state"] = "NOT_VERIFIABLE_IN_THIS_RUNTIME"

    closure_eng = engagements[0] if engagements else {}
    closure_wq = closure_eng.get("witness_quorum") or {}
    pub = _public_key_state(dsse_module)

    receipt_refs = [
        ref for ref in (eng_needs + roe_needs) if ref
    ]
    resolved = sum(1 for ref in receipt_refs if ref in digest_index)

    return {
        "schema": SCHEMA,
        "ok": True,
        "generated_at": _now(),
        "bundle_id": f"AAR-{track_id}-{len(engagements)}",
        "scope": {"track_id": track_id, "doctrine": doctrine},
        "truth_states": {
            "effectors": "SIMULATED",
            "witnesses": closure_wq.get("quorum_mode", "SIMULATED_IN_PROCESS")
            if engagements else "SIMULATED_IN_PROCESS",
            "operator": closure_eng.get("operator_id") or "UNKNOWN",
            "signing": "ARMED" if pub.get("available") else "UNSIGNED_HONEST",
            "bft_safety": "CONJECTURE_2_OPEN",
        },
        "engagement": {
            "closure_count": len(engagements),
            "latest_record_id": closure_eng.get("record_id"),
            "latest_verdict": closure_eng.get("verdict"),
            "latest_closure_state": closure_wq.get("state"),
            "witness_allow_count": closure_wq.get("allow_count"),
            "witness_threshold": closure_wq.get("threshold"),
        },
        "sections": sections,
        "receipt_resolution": {
            "referenced_receipts": len(receipt_refs),
            "resolved_in_chain": resolved,
            "signed_receipts": sum(
                1 for ref in receipt_refs
                if (digest_index.get(ref) or {}).get("signed")
            ),
        },
        "public_key_state": pub,
        "verification": {
            "offline_verifier": "tools/killinchu_verify_after_action.py",
            "command": ("python tools/killinchu_verify_after_action.py "
                        "bundle.json --key cosign.pub"),
            "checks": [
                "receipt_digest_recompute",
                "hash_chain_genesis_to_head",
                "witness_quorum_announcement",
                "dsse_signature_verify (when signed + key available + cryptography installed)",
            ],
        },
        "verification_hints": (
            "Ledger slice assembled from in-memory state since process start "
            f"({'ready' if ledger_ready else 'unavailable'} in this runtime). "
            "Sections referencing receipts minted before a runtime restart are "
            "marked NOT_VERIFIABLE_IN_THIS_RUNTIME rather than dropped."
        ),
        "honesty": (
            "Effectors SIMULATED. Witnesses SIMULATED (in-process, real ECDSA-"
            "P256 keys — genuine 3-of-4 protocol run, not cross-organ "
            "production signers). Operator identity UNKNOWN unless supplied. A "
            "valid signature proves integrity of a claim, never its "
            "correctness (Doctrine law 5). Khipu BFT safety = Conjecture 2 "
            "(OPEN)."
        ),
    }


def register(app: Any, emit_receipt: Callable, ns: str = "killinchu",
             ledger_readiness: Optional[Callable[[], Dict[str, Any]]] = None,
             ledger_snapshot: Optional[Callable[[], List[Dict[str, Any]]]] = None,
             ) -> Dict[str, Any]:
    """Register the after-action export endpoints. Call BEFORE the SPA catch-all.

    Routes
    ------
    GET /api/{ns}/v1/engagements/after-action?track_id=…
        After-action bundle covering every closure of the track in this runtime.
    GET /api/{ns}/v1/engagements/{record_id}/after-action
        The after-action bundle pinned to one closure record.

    GET and HEAD export existing evidence without minting a new receipt.
    ``export_receipt`` retains its object shape with null coordinates and an
    explicit UNSIGNED_READ_ONLY state. Existing closure/decision receipt
    references remain in their evidence sections. ``ledger_readiness`` /
    ``ledger_snapshot`` are the host's passive ``_LEDGER_RUNTIME`` callables;
    ``emit_receipt`` is retained for registration API compatibility, never
    called by these read routes.
    when omitted (offline tests) the chain section degrades to the honest
    NOT_VERIFIABLE_IN_THIS_RUNTIME state.
    """
    from fastapi.responses import JSONResponse

    import killinchu_parity as _parity

    try:
        import szl_dsse as _dsse_mod
    except Exception:  # pragma: no cover - degrade to unsigned-honest state
        _dsse_mod = None

    base = f"/api/{ns}/v1"
    registered: List[str] = []

    def _bundle_for(track_id: str, limit_to_record: Optional[str] = None):
        engagements = [
            e for e in _parity.audit_log_snapshot()
            if e.get("track_id") == track_id
        ]
        if limit_to_record:
            engagements = [e for e in engagements if e.get("record_id") == limit_to_record]
        roe_decisions = [
            d for d in _parity.roe_decisions_snapshot()
            if d.get("track_id") == track_id
        ]
        track_hist = getattr(_parity, "_TRACK_HISTORY", {})
        track_updates = list(reversed(track_hist.get(track_id, [])))

        ledger = _ledger_readiness()
        nodes = _ledger_snapshot() if ledger.get("ready") is True else None
        policy = _parity._ROE_POLICY
        bundle = build_after_action_bundle(
            track_id=track_id,
            engagements=engagements,
            roe_decisions=roe_decisions,
            track_updates=track_updates,
            ledger_nodes=nodes,
            policy_version=policy.get("version"),
            policy_hash=None,  # policy hash is per-decision; live rules copied below
            dsse_module=_dsse_mod,
        )
        # Policy section upgrade: include the LIVE rules so an auditor can see
        # the thresholds that governed the decisions (bounded, non-secret).
        bundle["sections"]["policy"]["rules_snapshot"] = policy.get("rules", {})
        bundle["sections"]["policy"]["honesty"] = (
            "ROE policy is in-memory; this snapshot is the policy AT EXPORT "
            "TIME. Per-decision policy_hash values in roe_chain bind each gate "
            "evaluation to the rule bytes it was decided under."
        )
        bundle["export_receipt"] = {
            "index": None, "digest": None, "signed": False,
            "state": "UNSIGNED_READ_ONLY",
        }
        bundle["receipt_minted"] = False
        bundle["export_read_only"] = True
        bundle["ledger"] = ledger
        return bundle, ledger

    # Ledger runtime: host-provided callables, or the honest absent state when
    # this module is exercised standalone (offline tests).
    def _default_readiness() -> Dict[str, Any]:
        return {"ready": False, "durability_state": "UNAVAILABLE",
                "production_ready": False,
                "error": "ledger runtime not wired (standalone import)"}

    _ledger_readiness: Callable[[], Dict[str, Any]] = ledger_readiness or _default_readiness

    def _default_snapshot() -> List[Dict[str, Any]]:
        return []

    _ledger_snapshot: Callable[[], List[Dict[str, Any]]] = ledger_snapshot or _default_snapshot

    @app.api_route(f"{base}/engagements/after-action", methods=["GET", "HEAD"])
    async def after_action(track_id: str) -> JSONResponse:
        """Export the after-action receipt bundle for one track (all closures)."""
        if not track_id:
            return JSONResponse({"ok": False, "error": "provide ?track_id="},
                                status_code=400)
        bundle, ledger = _bundle_for(track_id)
        if ledger.get("ready") is not True:
            bundle.update(ok=False, error="receipt ledger unavailable")
            return JSONResponse(bundle, status_code=503,
                                headers={"cache-control": "no-store"})
        if bundle["engagement"]["closure_count"] == 0 and not bundle["sections"]["roe_chain"]["decisions"]:
            bundle["ok"] = False
            bundle["empty_state"] = (
                f"no engagements or ROE decisions recorded for track "
                f"'{track_id}' in this runtime (in-memory, resets on restart)"
            )
            return JSONResponse(bundle, status_code=404,
                                headers={"cache-control": "no-store"})
        return JSONResponse(bundle, headers={"cache-control": "no-store"})

    registered.append(f"GET {base}/engagements/after-action")

    @app.api_route(f"{base}/engagements/{{record_id}}/after-action", methods=["GET", "HEAD"])
    async def after_action_for_record(record_id: str) -> JSONResponse:
        """Export the after-action bundle pinned to one closure record."""
        match = [e for e in _parity.audit_log_snapshot()
                 if e.get("record_id") == record_id]
        if not match:
            return JSONResponse(
                {"ok": False,
                 "error": f"engagement record '{record_id}' not found in this "
                          "runtime (in-memory audit ring, resets on restart)"},
                status_code=404)
        bundle, ledger = _bundle_for(match[0].get("track_id", "UNKNOWN"),
                                     limit_to_record=record_id)
        if ledger.get("ready") is not True:
            bundle.update(ok=False, error="receipt ledger unavailable")
            return JSONResponse(bundle, status_code=503,
                                headers={"cache-control": "no-store"})
        return JSONResponse(bundle, headers={"cache-control": "no-store"})

    registered.append(f"GET {base}/engagements/{{record_id}}/after-action")

    return {
        "module": "killinchu_after_action",
        "registered": registered,
        "schema": SCHEMA,
        "honesty": ("Bundles are assembled from in-memory evidence since "
                    "process start; offline-verifiable via "
                    "tools/killinchu_verify_after_action.py. Effectors "
                    "SIMULATED; witnesses SIMULATED in-process."),
    }


__all__ = ["SCHEMA", "SECTIONS", "build_after_action_bundle", "register"]
