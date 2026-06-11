#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_flow_compartments.py — honest "Flow Compartments" capability.

Feeds a maritime / wind / wake **velocity field** into `yarqa.compartmentalize`
(SZL's own clean-room plug-flow compartmentalization, vendored under
``vendor_yarqa/``) and surfaces the resulting plug-flow compartments plus a
signed receipt digest under ``/api/{ns}/v1/flow/*`` and a self-contained tab at
``/flow-compartments``.

ADDITIVE, self-contained, register(app, ns="killinchu")-style; routes inserted
BEFORE the SPA catch-all. Degrades gracefully — never crashes the app.

HONESTY DOCTRINE — never violated
---------------------------------
* yarqa is an **engineering method (CFD)** tier — NOT a locked theorem. It is
  NEVER folded into the locked-proven count (stays EXACTLY 8
  {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17). It carries NO "kernel-verified /
  proven" badge. Surfaced verbatim as:
  "Flow compartments — engineering method (CFD), not a locked theorem."
* The locked-8 governance theorems are NOT routed "through" yarqa — yarqa
  models fluid flow, they are trust/governance theorems. No relationship is
  asserted.
* The a11oy<->killinchu connection is NOT re-implemented on yarqa. That stays on
  the real signed-receipt / mesh bus (szl_khipu_consensus / szl_live_wires).
* yarqa receipts are emitted into the **EXISTING** Khipu/receipt chain
  (szl_khipu_lmdb.KhipuLMDB) — NOT a parallel chain. Signing reuses the existing
  cosign DSSE mechanism (szl_dsse) when the Space secret is present; otherwise an
  HONEST chain-verified digest (never a fabricated signature).
* No fabricated data. The bundled maritime wake field is clearly SAMPLE /
  SIMULATED labeled (no live maritime velocity-field source is verified in
  LIVE_SOURCES_VERIFIED.md). Effector / sim status is labeled. PAUSED / 503
  shows the real state.

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from typing import Any

# --- vendored yarqa (SZL clean-room, Apache-2.0) ----------------------------
# Make ./vendor_yarqa importable without polluting global sys.path order.
_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, "vendor_yarqa")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

_YARQA_OK = False
_YARQA_ERR: str | None = None
try:  # pragma: no cover - import guard
    import numpy as _np  # yarqa needs numpy; killinchu already ships it
    from yarqa import (  # type: ignore
        Mesh,
        compartmentalize_with_receipt,
        verify as _yarqa_verify,
        __version__ as _YARQA_VERSION,
    )
    from yarqa.core import compartment_summary  # type: ignore
    _YARQA_OK = True
except Exception as _e:  # pragma: no cover
    _YARQA_ERR = repr(_e)
    _YARQA_VERSION = "unavailable"

# --- existing Khipu receipt chain (NOT a parallel one) ----------------------
_KHIPU_OK = False
_KHIPU_ERR: str | None = None
try:
    from szl_khipu_lmdb import KhipuLMDB  # the real durable hash-chained store
    _KHIPU_OK = True
except Exception as _e:  # pragma: no cover
    _KHIPU_ERR = repr(_e)

# --- existing cosign DSSE signer (reused, never reinvented) -----------------
try:
    import szl_dsse as _szl_dsse  # real cosign DSSE signer
except Exception:  # pragma: no cover
    _szl_dsse = None

# ---------------------------------------------------------------------------
# Honesty constants — surfaced verbatim on every payload and the tab.
# ---------------------------------------------------------------------------
METHOD_TIER = "engineering method (CFD)"
HONEST_LABEL = "Flow compartments — engineering method (CFD), not a locked theorem"
LOCKED_PROVEN = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]  # EXACTLY 8
LOCKED_SHA = "c7c0ba17"
DATA_STATUS = "SAMPLE/SIMULATED"  # no verified live maritime velocity-field source
DATA_NOTE = (
    "Maritime wake / wind velocity field is SAMPLE/SIMULATED — no live "
    "maritime velocity-field source is verified in LIVE_SOURCES_VERIFIED.md. "
    "When a verified live field is wired, this label flips to LIVE and the same "
    "yarqa receipt is emitted. PAUSED/503 shows the real state."
)

_KHIPU_DIR = os.environ.get("KILLINCHU_KHIPU_DIR", os.path.join(_HERE, "live_snapshots", "khipu_flow"))


# ---------------------------------------------------------------------------
# SAMPLE/SIMULATED maritime wake velocity field.
# A 2-D structured grid; velocities model a hull wake: a downstream advective
# core with two diverging shear shoulders + a quiescent far field. Deterministic
# (seeded), reproducible, and clearly labeled — NOT a live feed.
# ---------------------------------------------------------------------------
def sample_wake_field(nx: int = 14, ny: int = 10, hull_speed: float = 6.0) -> dict:
    """Build a deterministic SAMPLE/SIMULATED 2-D maritime wake velocity field.

    Returns a JSON-able dict with cell centers, velocities, and grid adjacency.
    No randomness, no live source — reproducible by content hash.
    """
    nx = max(4, min(int(nx), 40))
    ny = max(4, min(int(ny), 40))
    centers: list[list[float]] = []
    velocities: list[list[float]] = []
    cx = (nx - 1) / 2.0
    for j in range(ny):  # downstream axis (flow travels +y)
        for i in range(nx):  # cross-stream axis
            x = float(i)
            y = float(j)
            centers.append([x, y])
            # Cross-stream offset from the wake centerline.
            off = (x - cx)
            # Advective core: strong +y near centerline, decaying outward.
            core = hull_speed * math.exp(-(off * off) / (2.0 * (nx / 5.0) ** 2))
            # Diverging shear shoulders: small cross-stream component, sign of off.
            shear = 0.35 * core * math.tanh(off / 2.0)
            # Far field downstream relaxes the wake (Kelvin-like decay with y).
            decay = math.exp(-y / (ny * 1.6))
            vy = core * decay + 0.15  # small ambient drift downstream
            vx = shear * decay
            velocities.append([round(vx, 6), round(vy, 6)])
    # 4-neighbour structured-grid adjacency.
    neighbors: list[list[int]] = []
    for j in range(ny):
        for i in range(nx):
            idx = j * nx + i
            nb: list[int] = []
            if i > 0:
                nb.append(idx - 1)
            if i < nx - 1:
                nb.append(idx + 1)
            if j > 0:
                nb.append(idx - nx)
            if j < ny - 1:
                nb.append(idx + nx)
            neighbors.append(nb)
    return {
        "grid": {"nx": nx, "ny": ny},
        "centers": centers,
        "velocities": velocities,
        "neighbors": neighbors,
        "status": DATA_STATUS,
        "note": DATA_NOTE,
        "scenario": "hull wake (maritime) — diverging shear shoulders + advective core",
    }


# ---------------------------------------------------------------------------
# Existing Khipu chain emit (durable) — reuse the real store, not a new one.
# ---------------------------------------------------------------------------
def _emit_to_khipu(action: str, payload: dict) -> dict | None:
    """Append a yarqa receipt into the EXISTING durable Khipu hash-chain.

    Returns the chain receipt dict (with seq/prev/digest) or None if the chain
    store is unavailable in this environment (degrade honestly, never crash).
    """
    if not _KHIPU_OK:
        return None
    try:
        store = KhipuLMDB(_KHIPU_DIR, organ="killinchu", ns="killinchu")
        return store.append(action, payload)
    except Exception as e:  # pragma: no cover - durability optional in CI
        return {"error": f"khipu append unavailable: {e!r}", "chain_verified": False}


def _sign_digest(receipt_obj: dict) -> tuple[list[dict], bool]:
    """Reuse the existing cosign DSSE signer; honest placeholder if absent.

    NEVER fabricates a signature. Returns (signatures, signed)."""
    if _szl_dsse is not None:
        try:
            if _szl_dsse.signing_available():
                env = _szl_dsse.sign_payload(receipt_obj, "application/vnd.szl.receipt+json")
                sigs = env.get("signatures") or []
                if sigs:
                    return sigs, True
        except Exception:
            pass
    return [{"sig": "PENDING — Space cosign secret absent; receipt is chain-verified, not signed",
             "keyid": "PENDING"}], False


# ---------------------------------------------------------------------------
# Core capability: field -> yarqa.compartmentalize -> compartments + receipt.
# ---------------------------------------------------------------------------
def compute_flow_compartments(field: dict | None = None, *, align_threshold: float = 0.0,
                              emit_chain: bool = True) -> dict:
    """Run yarqa on a velocity field and return compartments + a signed receipt.

    The receipt is emitted into the EXISTING Khipu chain (when available) and a
    cosign DSSE digest is produced via the existing signer (honest placeholder
    otherwise). Honest tier/data labels are always present.
    """
    if not _YARQA_OK:
        return {
            "ok": False,
            "status": "503",
            "real_state": "PAUSED — yarqa engine unavailable in this environment",
            "error": _YARQA_ERR,
            "method_tier": METHOD_TIER,
            "honest_label": HONEST_LABEL,
            "locked_proven_count": len(LOCKED_PROVEN),
            "locked_proven": LOCKED_PROVEN,
            "locked_sha": LOCKED_SHA,
            "yarqa_in_locked_count": False,
        }

    field = field or sample_wake_field()
    centers = _np.asarray(field["centers"], dtype=float)
    velocities = _np.asarray(field["velocities"], dtype=float)
    neighbors = [_np.asarray(nb, dtype=int) for nb in field["neighbors"]]

    mesh = Mesh(centers=centers, velocities=velocities, neighbors=neighbors)
    labels, receipt = compartmentalize_with_receipt(mesh, align_threshold=float(align_threshold))
    summary = compartment_summary(mesh, labels)

    # Verify reproduces (the crux of the integrity claim).
    verdict = _yarqa_verify(mesh, receipt)

    receipt_obj = json.loads(receipt.to_canonical_json())
    receipt_digest = receipt.receipt_digest()
    signatures, signed = _sign_digest(receipt_obj)

    # Emit into the EXISTING Khipu hash-chain (durable). Honest payload.
    chain_receipt = None
    if emit_chain:
        chain_receipt = _emit_to_khipu(
            "flow.yarqa.compartmentalize",
            {
                "method_tier": METHOD_TIER,
                "honest_label": HONEST_LABEL,
                "yarqa_version": _YARQA_VERSION,
                "yarqa_receipt": receipt_obj,
                "yarqa_receipt_digest": receipt_digest,
                "n_compartments": summary["n_compartments"],
                "data_status": field.get("status", DATA_STATUS),
                "claim": "integrity/reproducibility, NOT correctness; NOT a locked theorem",
            },
        )

    return {
        "ok": True,
        "status": "200",
        "real_state": "LIVE (engine) on SAMPLE/SIMULATED data" if field.get("status") == DATA_STATUS
                      else "LIVE",
        "method_tier": METHOD_TIER,
        "honest_label": HONEST_LABEL,
        "claim_tier": receipt.claim_tier,
        # Honesty guardrails surfaced on the wire so the UI cannot misrepresent.
        "locked_proven_count": len(LOCKED_PROVEN),
        "locked_proven": LOCKED_PROVEN,
        "locked_sha": LOCKED_SHA,
        "yarqa_in_locked_count": False,
        "routes_locked8_through_yarqa": False,
        "data": {
            "status": field.get("status", DATA_STATUS),
            "note": field.get("note", DATA_NOTE),
            "scenario": field.get("scenario"),
            "grid": field.get("grid"),
            "n_cells": int(mesh.n),
        },
        "compartments": {
            "n_compartments": summary["n_compartments"],
            "detail": summary["compartments"],
            "labels": labels.tolist(),
        },
        "receipt": {
            "schema": receipt_obj.get("schema"),
            "yarqa_version": _YARQA_VERSION,
            "receipt_digest": receipt_digest,
            "signed": signed,
            "signatures": signatures,
            "verify": verdict,
            "emitted_to_existing_khipu_chain": bool(chain_receipt),
            "khipu_chain_receipt": chain_receipt,
        },
    }


def index_payload(ns: str = "killinchu") -> dict:
    """Machine-readable capability manifest — honest tier + endpoints."""
    return {
        "capability": "Flow Compartments",
        "honest_label": HONEST_LABEL,
        "method_tier": METHOD_TIER,
        "engine": "yarqa (SZL clean-room, Apache-2.0)",
        "yarqa_version": _YARQA_VERSION,
        "yarqa_available": _YARQA_OK,
        "khipu_chain_available": _KHIPU_OK,
        "locked_proven_count": len(LOCKED_PROVEN),
        "yarqa_in_locked_count": False,
        "routes_locked8_through_yarqa": False,
        "data_status": DATA_STATUS,
        "data_note": DATA_NOTE,
        "endpoints": {
            "index": f"/api/{ns}/v1/flow/index",
            "field": f"/api/{ns}/v1/flow/field",
            "compartmentalize": f"/api/{ns}/v1/flow/compartmentalize",
            "selftest": f"/api/{ns}/v1/flow/selftest",
            "tab": "/flow-compartments",
        },
        "citation": "Reactor-engineering compartmental reduction of CFD fields "
                    "(plug-flow / well-mixed networks). Cited as concept only; no "
                    "third-party source copied. See vendor_yarqa/PROVENANCE.md.",
    }


def self_test() -> dict:
    """Run the engine end-to-end on the bundled SAMPLE field (eyes-on)."""
    res = compute_flow_compartments(emit_chain=False)
    return {
        "yarqa_available": _YARQA_OK,
        "yarqa_error": _YARQA_ERR,
        "khipu_chain_available": _KHIPU_OK,
        "khipu_error": _KHIPU_ERR,
        "n_compartments": res.get("compartments", {}).get("n_compartments"),
        "receipt_digest": res.get("receipt", {}).get("receipt_digest"),
        "verify_ok": res.get("receipt", {}).get("verify", {}).get("ok"),
        "honest_label": HONEST_LABEL,
        "yarqa_in_locked_count": False,
    }


# ---------------------------------------------------------------------------
# Self-contained, mobile/tablet-first tab (bottom-sheet drawer + FAB, 0 CDN).
# Sovereign: no external network, inline CSS/JS only, prefers-reduced-motion.
# ---------------------------------------------------------------------------
def _tab_html(ns: str = "killinchu") -> str:
    base = f"/api/{ns}/v1/flow"
    return r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Flow Compartments — engineering method (CFD)</title>
<style>
:root{
  --bg:#0a0e14; --panel:#10151f; --line:#1d2735; --ink:#e8eef6; --mut:#8aa0b8;
  --accent:#3fb6d6; --warn:#e8b33f; --ok:#46d39a; --bad:#e8615f;
  --r:14px; --sp:clamp(12px,3vw,20px);
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%;overflow-x:hidden}
.wrap{max-width:1100px;margin:0 auto;padding:var(--sp);padding-bottom:96px}
header{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
h1{font-size:clamp(20px,5vw,30px);margin:0;letter-spacing:-.02em}
.tier{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;
  font-size:12px;font-weight:600;color:#06212b;background:var(--accent);
  padding:5px 11px;border-radius:999px;width:max-content;max-width:100%}
.tier.method{background:var(--warn);color:#241c00}
.banner{border:1px solid var(--line);background:var(--panel);border-radius:var(--r);
  padding:var(--sp);font-size:13px;color:var(--mut)}
.banner b{color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.chip{font-size:11px;font-weight:600;padding:4px 9px;border-radius:999px;
  border:1px solid var(--line);color:var(--mut);background:#0c121b}
.chip.sample{color:var(--warn);border-color:#3a3010}
.chip.notlocked{color:var(--accent);border-color:#103642}
.grid{display:grid;grid-template-columns:1fr;gap:var(--sp);margin-top:var(--sp)}
@media(min-width:760px){.grid{grid-template-columns:1.2fr .8fr}}
.card{border:1px solid var(--line);background:var(--panel);border-radius:var(--r);
  padding:var(--sp);min-width:0}
.card h2{font-size:14px;margin:0 0 10px;color:var(--mut);text-transform:uppercase;
  letter-spacing:.08em;font-weight:700}
.fieldwrap{width:100%;overflow:hidden;border-radius:10px;border:1px solid var(--line);background:#070b11}
svg{display:block;width:100%;height:auto;touch-action:pan-y}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;font-size:12px;color:var(--mut)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:13px;height:13px;border-radius:3px;display:inline-block}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:13px;margin:0}
.kv dt{color:var(--mut)}
.kv dd{margin:0;font-variant-numeric:tabular-nums;word-break:break-word}
.digest{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
  color:var(--accent);word-break:break-all;background:#070b11;border:1px solid var(--line);
  border-radius:8px;padding:8px;margin-top:6px}
.state{font-weight:700}
.state.ok{color:var(--ok)} .state.bad{color:var(--bad)} .state.warn{color:var(--warn)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:10px}
label.rng{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--mut);flex:1 1 160px}
input[type=range]{width:100%}
button{font:inherit;font-weight:600;border:1px solid var(--line);background:#0c121b;
  color:var(--ink);border-radius:10px;padding:10px 16px;cursor:pointer;min-height:44px}
button.primary{background:var(--accent);color:#06212b;border-color:transparent}
button:active{transform:translateY(1px)}
details{margin-top:10px;border:1px solid var(--line);border-radius:10px;background:#0c121b}
summary{cursor:pointer;padding:10px 12px;font-size:12px;color:var(--mut)}
pre{margin:0;padding:0 12px 12px;font-size:11px;overflow:auto;color:var(--mut);max-height:280px}
.fab{position:fixed;right:16px;bottom:16px;z-index:40;border-radius:999px;
  width:auto;padding:14px 20px;background:var(--accent);color:#06212b;border:none;
  font-weight:700;box-shadow:0 8px 24px rgba(0,0,0,.45)}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:50;background:var(--panel);
  border-top:1px solid var(--line);border-radius:18px 18px 0 0;padding:18px var(--sp) 28px;
  transform:translateY(110%);transition:transform .28s ease;max-height:82vh;overflow:auto}
.sheet.open{transform:translateY(0)}
.sheet .grab{width:42px;height:5px;border-radius:3px;background:#33425a;margin:0 auto 12px}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:45;opacity:0;
  pointer-events:none;transition:opacity .24s}
.scrim.show{opacity:1;pointer-events:auto}
.sheetclose{margin-top:14px}
@media(prefers-reduced-motion:reduce){
  .sheet,.scrim,button:active{transition:none;transform:none}
  .sheet{transition:none}
}
</style></head>
<body>
<div class="wrap">
  <header>
    <h1>Flow Compartments</h1>
    <span class="tier method" id="tierLabel">engineering method (CFD) — not a locked theorem</span>
  </header>

  <div class="banner">
    <b>__HONEST_LABEL__</b><br>
    Powered by <b>yarqa</b> (SZL clean-room, Apache-2.0) — plug-flow compartmentalization of a CFD
    velocity field. This is an <b>engineering method</b>, not a kernel-verified theorem; it is
    <b>never</b> folded into the locked-proven count.
    <div class="chips">
      <span class="chip notlocked" id="lockedChip">locked-proven = 8 (yarqa NOT counted)</span>
      <span class="chip sample" id="dataChip">data: SAMPLE/SIMULATED</span>
      <span class="chip" id="engineChip">engine: …</span>
      <span class="chip" id="chainChip">khipu chain: …</span>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Compartmentalized wake field</h2>
      <div class="fieldwrap"><svg id="viz" viewBox="0 0 560 400" preserveAspectRatio="xMidYMid meet"
           role="img" aria-label="Plug-flow compartments over a sample maritime wake velocity field"></svg></div>
      <div class="legend" id="legend"></div>
      <div class="controls">
        <label class="rng">Alignment threshold <span id="alnVal">0.00</span>
          <input id="aln" type="range" min="0" max="0.95" step="0.05" value="0">
        </label>
        <button class="primary" id="runBtn" type="button">Recompute</button>
      </div>
      <p style="font-size:12px;color:var(--mut);margin:10px 0 0" id="dataNote"></p>
    </div>

    <div class="card">
      <h2>Signed receipt digest</h2>
      <dl class="kv">
        <dt>State</dt><dd class="state" id="state">…</dd>
        <dt>Compartments</dt><dd id="nComp">—</dd>
        <dt>Cells</dt><dd id="nCells">—</dd>
        <dt>yarqa</dt><dd id="ver">—</dd>
        <dt>Verify</dt><dd id="verify">—</dd>
        <dt>Signed</dt><dd id="signed">—</dd>
        <dt>In existing Khipu chain</dt><dd id="inchain">—</dd>
      </dl>
      <div class="digest" id="digest">receipt digest …</div>
      <details><summary>raw /flow/compartmentalize response</summary><pre id="raw">—</pre></details>
    </div>
  </div>
</div>

<button class="fab" id="fab" type="button" aria-haspopup="dialog" aria-controls="sheet">Method & honesty</button>
<div class="scrim" id="scrim"></div>
<aside class="sheet" id="sheet" role="dialog" aria-modal="true" aria-label="Method and honesty">
  <div class="grab"></div>
  <h2 style="margin-top:0;font-size:16px">Flow compartments — engineering method (CFD)</h2>
  <p style="color:var(--mut);font-size:14px">
    <b>What this is:</b> yarqa partitions a resolved velocity field into plug-flow compartments
    (region-growing of velocity-aligned cells across a flow front) — the classic reactor-engineering
    reduction of a 3-D field to a network of ideal compartments. Concept cited from reactor-engineering
    literature; no third-party source copied (see <code>vendor_yarqa/PROVENANCE.md</code>).
  </p>
  <p style="color:var(--mut);font-size:14px">
    <b>Honesty:</b> this is an <b>engineering method (CFD)</b>, <b>not</b> a locked theorem. Locked-proven
    stays exactly <b>8</b> {F1,F4,F7,F11,F12,F18,F19,F22} @ <code>c7c0ba17</code> — yarqa is never counted
    among them, and the governance theorems are never routed "through" yarqa. The receipt asserts
    <b>integrity / reproducibility</b> (replay the mesh, hashes match) — not correctness.
  </p>
  <p style="color:var(--mut);font-size:14px">
    <b>Data:</b> the maritime wake field is <b>SAMPLE/SIMULATED</b> — no live maritime velocity-field
    source is verified yet. When one is wired, this label flips to LIVE and the same yarqa receipt is
    emitted into the existing Khipu chain. PAUSED/503 shows the real state.
  </p>
  <button class="sheetclose" id="sheetClose" type="button">Close</button>
</aside>

<script>
"use strict";
var BASE = "__BASE__";
var PAL = ["#3fb6d6","#e8b33f","#46d39a","#b06fe0","#e8615f","#5f8de8","#e88f3f","#6fe0c0","#d65fb0","#9ad63f"];
var $ = function(id){return document.getElementById(id);};
function fmt(x){return (Math.round(x*1000)/1000);}

function drawField(field, labels){
  var svg = $("viz"); while(svg.firstChild) svg.removeChild(svg.firstChild);
  var nx=field.grid.nx, ny=field.grid.ny, c=field.centers, v=field.velocities;
  var W=560,H=400,pad=24;
  var sx=(W-2*pad)/Math.max(1,(nx-1)), sy=(H-2*pad)/Math.max(1,(ny-1));
  function X(i){return pad+i*sx;} function Y(j){return H-pad-j*sy;}
  // max speed for arrow scaling
  var vmax=1e-6; for(var k=0;k<v.length;k++){var s=Math.hypot(v[k][0],v[k][1]); if(s>vmax)vmax=s;}
  var ns="http://www.w3.org/2000/svg";
  for(var idx=0; idx<c.length; idx++){
    var i=idx%nx, j=Math.floor(idx/nx);
    var cx=X(i), cy=Y(j);
    var lab=labels[idx]; var col=PAL[lab%PAL.length];
    var cell=document.createElementNS(ns,"rect");
    cell.setAttribute("x",cx-sx/2+1); cell.setAttribute("y",cy-sy/2+1);
    cell.setAttribute("width",Math.max(2,sx-2)); cell.setAttribute("height",Math.max(2,sy-2));
    cell.setAttribute("rx","3"); cell.setAttribute("fill",col); cell.setAttribute("opacity","0.16");
    svg.appendChild(cell);
    var sp=Math.hypot(v[idx][0],v[idx][1]); var L=6+ (sp/vmax)*Math.min(sx,sy)*0.9;
    var ux=v[idx][0]/(sp||1), uy=v[idx][1]/(sp||1);
    var ex=cx+ux*L, ey=cy-uy*L; // svg y is down; field +y is up
    var ln=document.createElementNS(ns,"line");
    ln.setAttribute("x1",cx); ln.setAttribute("y1",cy); ln.setAttribute("x2",ex); ln.setAttribute("y2",ey);
    ln.setAttribute("stroke",col); ln.setAttribute("stroke-width","2"); ln.setAttribute("stroke-linecap","round");
    svg.appendChild(ln);
    var dot=document.createElementNS(ns,"circle");
    dot.setAttribute("cx",ex); dot.setAttribute("cy",ey); dot.setAttribute("r","2.2"); dot.setAttribute("fill",col);
    svg.appendChild(dot);
  }
}

function drawLegend(detail){
  var leg=$("legend"); leg.innerHTML="";
  Object.keys(detail).forEach(function(id){
    var d=detail[id]; var col=PAL[(+id)%PAL.length];
    var s=document.createElement("span");
    s.innerHTML='<i class="sw" style="background:'+col+'"></i>compartment '+id+' ('+d.n_cells+' cells)';
    leg.appendChild(s);
  });
}

function setState(res){
  var st=$("state");
  if(res.ok){ st.textContent=res.real_state; st.className="state ok"; }
  else { st.textContent=res.real_state||("PAUSED/"+(res.status||"503")); st.className="state bad"; }
}

var lastField=null;
function run(){
  var aln=parseFloat($("aln").value)||0;
  $("alnVal").textContent=aln.toFixed(2);
  $("runBtn").disabled=true; $("runBtn").textContent="…";
  fetch(BASE+"/compartmentalize",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({align_threshold:aln})})
   .then(function(r){return r.json();})
   .then(function(res){
     $("raw").textContent=JSON.stringify(res,null,2);
     setState(res);
     $("engineChip").textContent="engine: "+(res.ok?("yarqa "+(res.receipt&&res.receipt.yarqa_version||"")):"unavailable");
     if(!res.ok){ $("digest").textContent=(res.error||"engine unavailable"); $("runBtn").disabled=false; $("runBtn").textContent="Recompute"; return; }
     var comp=res.compartments, rec=res.receipt, d=res.data;
     $("nComp").textContent=comp.n_compartments;
     $("nCells").textContent=d.n_cells;
     $("ver").textContent=rec.yarqa_version;
     $("verify").innerHTML = rec.verify && rec.verify.ok
        ? '<span class="state ok">reproduces ✓</span>' : '<span class="state bad">FAILED</span>';
     $("signed").innerHTML = rec.signed
        ? '<span class="state ok">cosign DSSE ✓</span>'
        : '<span class="state warn">chain-verified (cosign secret absent)</span>';
     $("inchain").innerHTML = rec.emitted_to_existing_khipu_chain
        ? '<span class="state ok">yes — existing Khipu chain</span>'
        : '<span class="state warn">chain store not mounted here</span>';
     $("digest").textContent=rec.receipt_digest;
     $("dataChip").textContent="data: "+d.status;
     $("chainChip").textContent="khipu chain: "+(rec.emitted_to_existing_khipu_chain?"emitted":"n/a");
     $("dataNote").textContent=d.note;
     // build field for redraw (reuse last field if available, else fetch)
     if(lastField){ drawField(lastField, comp.labels); drawLegend(comp.detail); }
     $("runBtn").disabled=false; $("runBtn").textContent="Recompute";
   })
   .catch(function(e){ $("digest").textContent="request failed: "+e; $("runBtn").disabled=false; $("runBtn").textContent="Recompute"; });
}

function boot(){
  fetch(BASE+"/field").then(function(r){return r.json();}).then(function(f){
    lastField=f; run();
  }).catch(function(e){ $("digest").textContent="field unavailable: "+e; });
}

// bottom sheet
function openSheet(){ $("sheet").classList.add("open"); $("scrim").classList.add("show");
  $("sheet").focus&&$("sheet").focus(); }
function closeSheet(){ $("sheet").classList.remove("open"); $("scrim").classList.remove("show"); }
$("fab").addEventListener("click",openSheet);
$("scrim").addEventListener("click",closeSheet);
$("sheetClose").addEventListener("click",closeSheet);
document.addEventListener("keydown",function(e){if(e.key==="Escape")closeSheet();});
$("runBtn").addEventListener("click",run);
$("aln").addEventListener("input",function(){$("alnVal").textContent=(parseFloat($("aln").value)||0).toFixed(2);});
boot();
</script>
</body></html>
""".replace("__BASE__", base).replace("__HONEST_LABEL__", HONEST_LABEL)


# ---------------------------------------------------------------------------
# register(app, ns) — mount routes BEFORE the SPA catch-all (mirrors wave910).
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu") -> str:
    from starlette.routing import Route
    from starlette.responses import JSONResponse, HTMLResponse

    base = f"/api/{ns}/v1/flow"

    async def _body(request):
        try:
            return await request.json()
        except Exception:
            return {}

    async def _index(request):
        return JSONResponse(index_payload(ns))

    async def _field(request):
        try:
            nx = int(request.query_params.get("nx", "14"))
            ny = int(request.query_params.get("ny", "10"))
        except Exception:
            nx, ny = 14, 10
        return JSONResponse(sample_wake_field(nx, ny))

    async def _compartmentalize(request):
        b = await _body(request)
        field = b.get("field")  # optional caller-supplied field
        aln = float(b.get("align_threshold", 0.0) or 0.0)
        res = compute_flow_compartments(field=field, align_threshold=aln, emit_chain=True)
        code = 200 if res.get("ok") else 503
        return JSONResponse(res, status_code=code)

    async def _selftest(request):
        return JSONResponse(self_test())

    async def _tab(request):
        return HTMLResponse(_tab_html(ns))

    routes = [
        Route(f"{base}/index", _index, methods=["GET"], name=f"{ns}_flow_index"),
        Route(f"{base}/field", _field, methods=["GET"], name=f"{ns}_flow_field"),
        Route(f"{base}/compartmentalize", _compartmentalize, methods=["POST"], name=f"{ns}_flow_compartmentalize"),
        Route(f"{base}/selftest", _selftest, methods=["GET"], name=f"{ns}_flow_selftest"),
        Route("/flow-compartments", _tab, methods=["GET"], name=f"{ns}_flow_tab"),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return f"flow-compartments-wired:yarqa={_YARQA_VERSION}:khipu={_KHIPU_OK}"


__all__ = [
    "register", "index_payload", "self_test", "compute_flow_compartments",
    "sample_wake_field", "HONEST_LABEL", "METHOD_TIER",
]

# Doctrine: locked-proven = EXACTLY 8 {F1,F4,F7,F11,F12,F18,F19,F22}; yarqa is an
# engineering method (CFD), NOT locked and NEVER counted; receipts go into the
# EXISTING Khipu chain; a11oy<->killinchu is NOT routed through yarqa.
# Sovereign 0-CDN tab. SAMPLE/SIMULATED data clearly labeled; PAUSED/503 = real state.
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
