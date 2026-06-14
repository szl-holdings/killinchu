# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. Jr. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""killinchu_platform_dynamics.py — "Platform Dynamics" capability (Lane I5).

ADOPTED-AND-GENERALIZED, not invented here. The counter-UAS interceptors and the
drones we "jack into" are rigid-body airframes under multirotor control. This module
is the PLATFORM layer of the killinchu drone puzzle: a 6DOF quadcopter/interceptor
rigid-body model + a Moore-Penrose pseudo-inverse CONTROL ALLOCATION (optimal thrust
distribution), shown alongside Dev E's active-flux sensorless drive (the ESTIMATE
layer) and Dev D's CBF-QP safety clamp + BFT multi-sensor fusion (the SAFETY/FUSION
layers). Together they complete the platform story:

    estimate (active-flux, F-η, /api/.../drive/active-flux)
      → 6DOF dynamics + control allocation (this, F-θ, /api/.../platform/*)
        → CBF-QP safety clamp (Dev D, /api/.../autonomy/cbf)
          → BFT multi-sensor fusion (Dev D, /api/.../autonomy/bft)
            → governed / ROE engage (SIMULATED human-on-loop)

The pure math lives in the SHARED byte-identical szl_cuas_formulas.py
(quad_mixing_matrix, moore_penrose_pinv, szl_control_allocation, szl_6dof_step).
This module only adds the killinchu HTTP surface + a self-contained /elite page +
an idempotent nav-link injector (its own middleware — the console source is NOT edited).

ADOPTED FROM (cited in code + UI; NOT reclaimed as an SZL theorem):
  - Ahmed Hassan — Quadcopter Modeling/Control/Simulation: full Simulink 6DOF model
    (Aerospace Blockset, block-based, clean code-gen), control ALLOCATION via the
    Moore-Penrose pseudo-inverse for optimal thrust distribution, MIL/SIL via Embedded
    Coder. https://www.linkedin.com/posts/ahmedhassan2002_aerospaceengineering-aerospace-uav-activity-7348481891039129600-TbmA
  - Moore-Penrose pseudo-inverse (minimum-norm least-squares allocation).
  - Control-allocation survey — Johansen & Fossen, Automatica 2013.
  - Model-Based Design (V-cycle, MIL/SIL/HIL, auto code-gen) — MathWorks.

HONEST LABELS (doctrine v11):
  * There is NO live airframe on the demo floor — every angular rate / attitude /
    rotor thrust is a MODELED/SIMULATED model output, NOT live telemetry. We NEVER
    claim live UAV/vessel control.
  * Effector stays SIMULATED human-on-loop; this computes a thrust allocation + a
    one-step state derivative, it NEVER actuates a motor.
  * Λ = Conjecture 1; Khipu BFT = Conjecture 2; locked-proven = EXACTLY 8 @ c7c0ba17.
    This module adds NOTHING to the locked-8 — it is an EXPERIMENTAL adopt-and-evolve.
  * Trust never 100%; 0 runtime CDN (the attitude/allocation viz is a vendored,
    dependency-free <canvas> routine).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import szl_cuas_formulas as _pd  # SHARED, byte-identical a11oy↔killinchu

SOURCES = {
    "Ahmed Hassan — Quadcopter Modeling/Control/Simulation (Simulink 6DOF; LinkedIn 2026)":
        "https://www.linkedin.com/posts/ahmedhassan2002_aerospaceengineering-aerospace-uav-activity-7348481891039129600-TbmA",
    "Moore-Penrose pseudo-inverse (control allocation)":
        "https://en.wikipedia.org/wiki/Moore%E2%80%93Penrose_inverse",
    "Control allocation survey (Johansen & Fossen, Automatica 2013)":
        "https://doi.org/10.1016/j.automatica.2013.01.035",
    "Model-Based Design / V-cycle, MIL/SIL/HIL (MathWorks)":
        "https://www.mathworks.com/solutions/model-based-design.html",
}

_HONEST = (
    "MODELED/SIMULATED — there is no live airframe on the demo floor. Every angular "
    "rate, attitude and rotor-thrust figure is a deterministic model output, NOT live "
    "telemetry, and we NEVER claim live UAV/vessel control. The effector stays "
    "SIMULATED human-on-loop; this computes a thrust allocation + a one-step 6DOF "
    "derivative, it never actuates. Adopted the Hassan quadcopter MBD 6DOF + "
    "Moore-Penrose control-allocation technique and folded it under SZL governance; "
    "this adds NOTHING to the locked-8 and Λ stays Conjecture 1. Trust never 100%."
)


def info(ns: str) -> Dict[str, Any]:
    """Headline + honest provenance for the platform-dynamics capability + the puzzle map."""
    return {
        "capability": "Platform Dynamics — 6DOF model + Moore-Penrose control allocation",
        "ns": ns,
        "summary": (
            "6DOF quadcopter/interceptor rigid-body model (Newton-Euler) + Moore-Penrose "
            "pseudo-inverse CONTROL ALLOCATION (optimal thrust distribution). Adopted from "
            "Ahmed Hassan's Simulink Quadcopter MBD project and folded under SZL governance. "
            "Completes the killinchu drone-platform puzzle next to the active-flux estimate "
            "layer and the CBF-QP safety + BFT-fusion layers."),
        "puzzle": [
            {"stage": "estimate", "what": "active-flux sensorless drive (Dev E, F-η)",
             "endpoint": f"/api/{ns}/v1/drive/active-flux"},
            {"stage": "platform", "what": "6DOF dynamics + Moore-Penrose control allocation (this, F-θ)",
             "endpoint": f"/api/{ns}/v1/platform/dynamics"},
            {"stage": "safety", "what": "CBF-QP safety clamp (Dev D)",
             "endpoint": f"/api/{ns}/v1/autonomy/cbf"},
            {"stage": "fusion", "what": "BFT multi-sensor quorum (Dev D)",
             "endpoint": f"/api/{ns}/v1/autonomy/bft"},
            {"stage": "engage", "what": "governed / ROE engage — SIMULATED human-on-loop",
             "endpoint": f"/api/{ns}/v1/cuas/engage"},
        ],
        "endpoints": {
            "dynamics": f"/api/{ns}/v1/platform/dynamics",
            "allocation": f"/api/{ns}/v1/platform/allocation",
            "info": f"/api/{ns}/v1/platform/info",
            "page": "/elite/platform-dynamics",
        },
        "doctrine": {"locked_proven": 8, "lambda": "Conjecture 1", "khipu_bft": "Conjecture 2",
                     "effector": "SIMULATED", "trust": "never 100%",
                     "data_label": "MODELED/SIMULATED — no live airframe / no live UAV control"},
        "sources": SOURCES,
        "honest": _HONEST,
        "status": "EXPERIMENTAL",
    }


# ---------------------------------------------------------------------------
# Self-contained /elite/platform-dynamics page. 0 runtime CDN — the attitude +
# rotor-allocation viz is drawn with a tiny dependency-free <canvas> routine.
# Imports the estate shared modules from /shared/* (byte-identical a11oy↔killinchu).
# ---------------------------------------------------------------------------
def _page_html(ns: str) -> str:
    return r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Platform Dynamics · 6DOF + Control Allocation — killinchu</title>
<style>
 :root{--bg:#070b10;--panel:#0d141c;--line:#1d2a36;--teal:#39d3c4;--teal-soft:rgba(57,211,196,.12);
  --gold:#e8c074;--cream:#eef3f6;--para:#9fb1bf;--ok:#6fe3a0;--warn:#ffb56b;--bad:#ff6b6b;--rot:#6fb1ff;}
 *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--cream);
  font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Helvetica,Arial}
 a{color:var(--teal);text-decoration:none}
 header{padding:14px 18px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#0a1119,#070b10)}
 h1{font-size:18px;margin:0 0 2px}.sub{color:var(--para);font-size:12.5px;max-width:1000px}
 .badge{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:6px;border:1px solid var(--line);
  margin-right:6px;color:var(--gold);background:#10171f;vertical-align:middle}
 .wrap{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:16px;max-width:1240px;margin:0 auto}
 @media(max-width:880px){.wrap{grid-template-columns:1fr}}
 .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
 .panel.full{grid-column:1/-1}
 .panel h2{font-size:14px;margin:0 0 8px;color:var(--cream)}
 .panel .pp{color:var(--para);font-size:12px;margin:0 0 10px}
 canvas{width:100%;height:260px;background:#060a0e;border:1px solid var(--line);border-radius:8px;display:block}
 .ctrl{display:flex;align-items:center;gap:10px;margin:8px 0;font-size:12.5px;flex-wrap:wrap}
 .ctrl label{color:var(--para);min-width:170px}
 input[type=range]{flex:1;accent-color:var(--teal)}
 .val{color:var(--teal);font-variant-numeric:tabular-nums;min-width:64px;text-align:right}
 .kpi{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
 .kpi div{background:#0a1117;border:1px solid var(--line);border-radius:7px;padding:8px}
 .kpi b{display:block;font-size:18px;color:var(--gold);font-variant-numeric:tabular-nums}
 .kpi span{font-size:11px;color:var(--para)}
 .out{white-space:pre-wrap;font:11.5px ui-monospace,Menlo,monospace;color:#bfe;background:#06090d;
  border:1px solid var(--line);border-radius:7px;padding:8px;max-height:200px;overflow:auto}
 .src{font-size:11px;color:var(--para);margin-top:10px;line-height:1.7}.src a{color:var(--teal)}
 footer{padding:12px 18px;border-top:1px solid var(--line);color:var(--para);font-size:11px}
 .chain{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 2px}
 .chain a,.chain span.node{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;
  padding:5px 9px;border-radius:7px;border:1px solid var(--line);background:#0a1117;color:var(--cream)}
 .chain .arrow{color:var(--para);align-self:center}
 .chain a:hover{border-color:var(--teal);color:var(--teal)}
 .tag{font-size:10px;color:var(--para);border:1px solid var(--line);border-radius:5px;padding:1px 5px;margin-left:5px}
 .rotmix{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
 .rotmix div{background:#0a1117;border:1px solid var(--line);border-radius:7px;padding:8px;text-align:center}
 .rotmix b{display:block;font-size:16px;color:var(--rot);font-variant-numeric:tabular-nums}
 .rotmix.sat b{color:var(--bad)}
 .rotmix span{font-size:10.5px;color:var(--para)}
</style></head><body>
<header>
 <h1>Platform Dynamics · 6DOF model + Moore-Penrose control allocation
   <span class="badge" id="b-modeled">MODELED / SIMULATED</span>
   <span class="badge">effector SIMULATED</span>
   <span class="badge">no live airframe</span>
   <span class="badge">Λ = Conjecture 1</span>
   <span class="badge">0 runtime CDN</span></h1>
 <div class="sub">A <b>6DOF Newton-Euler</b> quadcopter/interceptor rigid-body model + a
  <b>Moore-Penrose pseudo-inverse control allocation</b> (optimal, minimum-norm thrust distribution).
  <b>Adopted</b> from Ahmed Hassan's Simulink Quadcopter MBD project and folded under SZL governance;
  this adds NOTHING to the locked-8. <b>There is no live airframe on the demo floor — every number
  here is modeled; we never claim live UAV/vessel control.</b>
  <a href="/elite">← back to /elite</a></div>
</header>

<div class="wrap">
 <div class="panel full">
  <h2>The killinchu drone-platform puzzle — where this fits</h2>
  <p class="pp">Each stage links to a LIVE governed endpoint on this app. This surface is the
   <b>platform</b> stage: it turns a commanded body wrench into rotor thrusts (allocation) and rolls
   the rigid-body state forward one step (6DOF). Estimation is upstream (active-flux), safety/fusion are
   downstream (CBF-QP + BFT), and the final engage is governed + SIMULATED human-on-loop.</p>
  <div class="chain">
   <a href="/elite/active-flux" title="Dev E active-flux sensorless drive (estimate)"><span>① estimate</span><span class="tag">active-flux</span></a>
   <span class="arrow">→</span>
   <span class="node" style="border-color:var(--teal);color:var(--teal)">② platform<span class="tag">6DOF + allocation (here)</span></span>
   <span class="arrow">→</span>
   <a href="/elite/autonomy" title="Dev D CBF-QP safety clamp"><span>③ safety</span><span class="tag">CBF-QP</span></a>
   <span class="arrow">→</span>
   <a href="/elite/autonomy" title="Dev D BFT multi-sensor quorum"><span>④ fusion</span><span class="tag">BFT n≥3f+1</span></a>
   <span class="arrow">→</span>
   <a href="/elite/organism" title="organism / governed estate"><span>⑤ engage</span><span class="tag">governed · SIMULATED</span></a>
  </div>
 </div>

 <div class="panel">
  <h2>Moore-Penrose control allocation <span class="tag">f = B⁺·τ</span></h2>
  <p class="pp">Command a body wrench τ = [total thrust, roll, pitch, yaw] and the allocator solves for the
   <b>minimum-norm</b> rotor thrusts f = B⁺·τ, then saturates each rotor to its limit. The achieved wrench
   B·f and the residual are reported honestly. MODELED — no motor is driven.</p>
  <div class="ctrl"><label>total thrust T (N)</label>
   <input id="T" type="range" min="0" max="40" step="0.5" value="11.8"><span class="val" id="T-v">11.8</span></div>
  <div class="ctrl"><label>roll torque L</label>
   <input id="L" type="range" min="-2" max="2" step="0.05" value="0.2"><span class="val" id="L-v">0.20</span></div>
  <div class="ctrl"><label>pitch torque M</label>
   <input id="M" type="range" min="-2" max="2" step="0.05" value="0.0"><span class="val" id="M-v">0.00</span></div>
  <div class="ctrl"><label>yaw torque N</label>
   <input id="N" type="range" min="-1" max="1" step="0.02" value="0.05"><span class="val" id="N-v">0.05</span></div>
  <div class="rotmix" id="rotmix">
   <div><b id="r1">—</b><span>f1 front-right</span></div>
   <div><b id="r2">—</b><span>f2 back-left</span></div>
   <div><b id="r3">—</b><span>f3 front-left</span></div>
   <div><b id="r4">—</b><span>f4 back-right</span></div>
  </div>
  <div class="kpi" style="margin-top:8px">
   <div><b id="a-resid">—</b><span>allocation residual ‖B·f − τ‖</span></div>
   <div><b id="a-sat">—</b><span>any rotor saturated?</span></div>
  </div>
  <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--teal)">raw /platform/allocation</summary>
   <div class="out" id="alloc-raw">—</div></details>
 </div>

 <div class="panel">
  <h2>6DOF rigid-body step <span class="tag">Newton-Euler</span></h2>
  <p class="pp">One Euler step of the body-frame 6DOF model: the commanded wrench from the allocator drives
   the angular-rate + attitude derivatives. The attitude viz shows the resulting roll/pitch (top-down rotor
   disk). MODELED — Aerospace-Blockset shape (Hassan MBD), not a live airframe.</p>
  <canvas id="att" width="540" height="260"></canvas>
  <div class="kpi">
   <div><b id="d-phi">—</b><span>roll φ (deg)</span></div>
   <div><b id="d-theta">—</b><span>pitch θ (deg)</span></div>
   <div><b id="d-p">—</b><span>ṗ roll-rate accel (rad/s²)</span></div>
   <div><b id="d-w">—</b><span>ẇ vertical accel (m/s²)</span></div>
  </div>
  <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--teal)">raw /platform/dynamics</summary>
   <div class="out" id="dyn-raw">—</div></details>
 </div>
</div>
<footer>
 Doctrine v11 · locked = 8 @ c7c0ba17 · Λ = Conjecture 1 · Khipu BFT = Conjecture 2 ·
 effector SIMULATED · <b>platform dynamics MODELED/SIMULATED (no live airframe; no live UAV/vessel control)</b> ·
 0 runtime CDN · trust &lt; 100%.<br>
 Adopted &amp; generalized — sources:
 <a href="https://www.linkedin.com/posts/ahmedhassan2002_aerospaceengineering-aerospace-uav-activity-7348481891039129600-TbmA" target="_blank" rel="noopener">Ahmed Hassan — Quadcopter MBD (LinkedIn)</a> ·
 <a href="https://en.wikipedia.org/wiki/Moore%E2%80%93Penrose_inverse" target="_blank" rel="noopener">Moore-Penrose pseudo-inverse</a> ·
 <a href="https://doi.org/10.1016/j.automatica.2013.01.035" target="_blank" rel="noopener">Control allocation (Johansen &amp; Fossen, 2013)</a> ·
 <a href="https://www.mathworks.com/solutions/model-based-design.html" target="_blank" rel="noopener">Model-Based Design (MathWorks)</a>.
</footer>
<!-- Estate shared modules (byte-identical a11oy↔killinchu), served at /shared/*. NO CDN. -->
<script src="/shared/szl_label_engine.js" defer></script>
<script src="/shared/szl_receipt_cosign.js" defer></script>
<script src="/shared/szl_codename_sanitizer.js" defer></script>
<script>
"use strict";
const API = "/api/__NS__/v1/platform";
const $ = id => document.getElementById(id);
function setVals(){
  $("T-v").textContent=parseFloat($("T").value).toFixed(1);
  $("L-v").textContent=parseFloat($("L").value).toFixed(2);
  $("M-v").textContent=parseFloat($("M").value).toFixed(2);
  $("N-v").textContent=parseFloat($("N").value).toFixed(2);
}
function drawAttitude(phi, theta){
  // top-down rotor-disk viz tilted by roll(phi)/pitch(theta). Pure canvas, 0 CDN.
  const c=$("att"), ctx=c.getContext("2d"); const W=c.width,H=c.height;
  ctx.clearRect(0,0,W,H); const cx=W/2, cy=H/2;
  // grid horizon
  ctx.strokeStyle="#142029"; ctx.lineWidth=1;
  for(let i=-3;i<=3;i++){ ctx.beginPath(); ctx.moveTo(cx-200,cy+i*28); ctx.lineTo(cx+200,cy+i*28); ctx.stroke(); }
  // arm endpoints of an X-quad, projected with small-angle tilt
  const arm=90;
  const pts=[[1,1,"f1"],[-1,-1,"f2"],[1,-1,"f3"],[-1,1,"f4"]]; // x(right),y(fwd)
  ctx.save(); ctx.translate(cx,cy);
  function proj(x,y){ // tilt: roll about fwd axis -> x scaled by cos(phi); pitch about right -> y scaled by cos(theta) + shear
    const px = x*arm*Math.cos(phi);
    const py = -y*arm*Math.cos(theta) + x*arm*Math.sin(phi)*0.35 - y*arm*0 + y*0;
    const pz = y*arm*Math.sin(theta)*0.5;
    return [px, py - pz];
  }
  // body cross
  ctx.strokeStyle="#2a3a48"; ctx.lineWidth=3;
  const a=proj(1,1),b=proj(-1,-1),d=proj(1,-1),e=proj(-1,1);
  ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
  ctx.beginPath();ctx.moveTo(d[0],d[1]);ctx.lineTo(e[0],e[1]);ctx.stroke();
  // rotor disks
  const cols={f1:"#6fb1ff",f2:"#6fe3a0",f3:"#ffb56b",f4:"#e8c074"};
  pts.forEach(([x,y,lab])=>{ const [px,py]=proj(x,y);
    ctx.fillStyle=cols[lab]; ctx.beginPath(); ctx.arc(px,py,12,0,2*Math.PI); ctx.fill();
    ctx.fillStyle="#06090d"; ctx.font="9px ui-monospace,monospace"; ctx.fillText(lab,px-7,py+3);
  });
  ctx.restore();
  ctx.fillStyle="#5b6c78"; ctx.font="11px ui-monospace,monospace";
  ctx.fillText("top-down rotor disk · roll φ="+(phi*180/Math.PI).toFixed(1)+"°  pitch θ="+(theta*180/Math.PI).toFixed(1)+"°  (MODELED)", 10, H-8);
}
async function refresh(){
  setVals();
  const T=$("T").value,L=$("L").value,M=$("M").value,N=$("N").value;
  try{
    const ra=await fetch(`${API}/allocation?T=${T}&L=${L}&M=${M}&N=${N}`); const da=await ra.json();
    const rs=da.rotor_thrust_sat;
    $("r1").textContent=rs.f1_front_right.toFixed(2); $("r2").textContent=rs.f2_back_left.toFixed(2);
    $("r3").textContent=rs.f3_front_left.toFixed(2); $("r4").textContent=rs.f4_back_right.toFixed(2);
    $("a-resid").textContent=da.residual_norm.toFixed(4);
    $("a-sat").textContent=da.any_rotor_saturated?"YES (clamped)":"no";
    $("rotmix").className="rotmix"+(da.any_rotor_saturated?" sat":"");
    $("alloc-raw").textContent=JSON.stringify(da,null,1);
  }catch(e){ $("alloc-raw").textContent="endpoint unreachable: "+e; }
  try{
    const rd=await fetch(`${API}/dynamics?T=${T}&L=${L}&M=${M}&N=${N}&theta=0.1`); const dd=await rd.json();
    const sn=dd.state_next, dv=dd.derivatives;
    $("d-phi").textContent=(sn.phi*180/Math.PI).toFixed(2);
    $("d-theta").textContent=(sn.theta*180/Math.PI).toFixed(2);
    $("d-p").textContent=dv.dp.toFixed(3);
    $("d-w").textContent=dv.dw.toFixed(3);
    drawAttitude(sn.phi, sn.theta);
    $("dyn-raw").textContent=JSON.stringify(dd,null,1);
  }catch(e){ $("dyn-raw").textContent="endpoint unreachable: "+e; }
}
["T","L","M","N"].forEach(id=>$(id).addEventListener("input", refresh));
window.addEventListener("resize", refresh);
refresh();
</script>
</body></html>""".replace("__NS__", ns)


def register(app, ns: str = "killinchu", emit_receipt=None) -> Dict[str, Any]:
    """Attach the platform-dynamics surface. ADDITIVE; mounted BEFORE the SPA catch-all.
    Pure stdlib + the shared szl_cuas_formulas math. NO new dependency, 0 CDN."""
    from starlette.responses import HTMLResponse, JSONResponse
    registered: List[str] = []
    base = f"/api/{ns}/v1/platform"

    # Moore-Penrose control allocation (MODELED/SIMULATED).
    def _allocation(T: str = "11.8", L: str = "0.2", M: str = "0.0", N: str = "0.05",
                    arm: str = "0.25", k_torque: str = "0.02", f_max: str = "12.0"):
        try:
            return JSONResponse(_pd.szl_control_allocation(
                [float(T), float(L), float(M), float(N)],
                arm_length=float(arm), k_torque=float(k_torque), f_max=float(f_max)))
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/allocation", _allocation, methods=["GET"])
    registered.append(f"GET {base}/allocation")

    # 6DOF rigid-body step (MODELED/SIMULATED).
    def _dynamics(T: str = "11.77", L: str = "0.0", M: str = "0.0", N: str = "0.0",
                  p: str = "0.0", q: str = "0.0", r: str = "0.0",
                  phi: str = "0.0", theta: str = "0.1", psi: str = "0.0", dt: str = "0.01"):
        try:
            return JSONResponse(_pd.szl_6dof_step(
                state={"p": float(p), "q": float(q), "r": float(r),
                       "phi": float(phi), "theta": float(theta), "psi": float(psi)},
                tau=[float(T), float(L), float(M), float(N)], dt=float(dt)))
        except (ValueError, TypeError) as e:
            return JSONResponse({"error": {"code": "validation_error", "detail": str(e)}}, status_code=422)
    app.add_api_route(f"{base}/dynamics", _dynamics, methods=["GET"])
    registered.append(f"GET {base}/dynamics")

    # Info / provenance + puzzle map.
    app.add_api_route(f"{base}/info", lambda: JSONResponse(info(ns)), methods=["GET"])
    registered.append(f"GET {base}/info")

    # Self-contained /elite/platform-dynamics page (0 CDN).
    _html = _page_html(ns)

    async def _page():
        return HTMLResponse(_html)
    app.add_api_route("/elite/platform-dynamics", _page, methods=["GET"])
    app.add_api_route(f"/{ns}/elite/platform-dynamics", _page, methods=["GET"])
    registered.append("GET /elite/platform-dynamics")

    # --- nav-link injector (OWNED by this module; does NOT edit the console file) ---
    # Mirrors Dev E's idempotent injector pattern: a tiny middleware appends ONE <a>
    # nav-item linking to /elite/platform-dynamics into the /elite console HTML, right
    # after the active-flux nav-item if present (so the two drive/platform items sit
    # together), else after the stable MESH anchor. Idempotent (a unique marker prevents
    # double injection). Touches only served HTML bytes; the console source is untouched.
    try:
        from starlette.middleware.base import BaseHTTPMiddleware as _Base
        from starlette.responses import Response as _SResp
        _NAV_MARK = b"data-view-pd=\"platform_dynamics\""
        _ANCHOR_AF = b"Sensorless Drive (Active-Flux)</a>"   # sit right after Dev E's item
        _ANCHOR_MESH = b"MESH (live surface)</a>"            # fallback stable anchor
        _NAV_LINK = (
            b'<a class="nav-item" data-view-pd="platform_dynamics" href="/elite/platform-dynamics" '
            b'style="color:var(--gold-bright)" title="Platform Dynamics: 6DOF quadcopter/interceptor '
            b'model + Moore-Penrose pseudo-inverse control allocation (optimal thrust distribution), '
            b'shown beside the active-flux estimate layer and the CBF-QP safety + BFT-fusion layers. '
            b'Adopted from Ahmed Hassan quadcopter MBD, folded under SZL governance. '
            b'MODELED/SIMULATED - no live airframe; effector SIMULATED; no live UAV/vessel control.">'
            b'<span class="ico">&#9881;</span>Platform Dynamics (6DOF + allocation)</a>'
        )

        class _PlatformDynNavInjector(_Base):
            async def dispatch(self, request, call_next):
                resp = await call_next(request)
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    p = request.url.path
                    if "text/html" not in ct or p.startswith(("/api/", "/assets/", "/vendor/", "/shared/")):
                        return resp
                    if p == "/elite/platform-dynamics" or p.endswith("/elite/platform-dynamics"):
                        return resp  # never inject into my own page
                    body = b""
                    async for chunk in resp.body_iterator:
                        body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()
                    if _NAV_MARK in body:
                        new_body = body  # already injected — idempotent
                    elif _ANCHOR_AF in body:
                        new_body = body.replace(_ANCHOR_AF, _ANCHOR_AF + _NAV_LINK, 1)
                    elif _ANCHOR_MESH in body:
                        new_body = body.replace(_ANCHOR_MESH, _ANCHOR_MESH + _NAV_LINK, 1)
                    else:
                        new_body = body
                    headers = dict(resp.headers)
                    headers.pop("content-length", None)
                    return _SResp(content=new_body, status_code=resp.status_code,
                                  headers=headers, media_type="text/html")
                except Exception:
                    return resp

        app.add_middleware(_PlatformDynNavInjector)
        registered.append("MIDDLEWARE platform-dynamics nav-link injector")
    except Exception:  # never crash the app — additive only
        pass

    return {"registered": registered, "count": len(registered),
            "capability": "Platform Dynamics — 6DOF + Moore-Penrose control allocation",
            "data_label": "MODELED/SIMULATED"}


def _selftest() -> None:
    # math round-trips via the shared module
    al = _pd.szl_control_allocation([12.0, 0.0, 0.0, 0.0])
    assert al["residual_norm"] < 1e-6 and al["effector"] == "SIMULATED"
    st = _pd.szl_6dof_step(tau=[0.0, 0.01, 0.0, 0.0])
    assert st["derivatives"]["dp"] > 0.0 and st["status"] == "MODELED"
    i = info("killinchu")
    assert i["endpoints"]["dynamics"].endswith("/platform/dynamics")
    assert len(i["puzzle"]) == 5 and i["status"] == "EXPERIMENTAL"
    html = _page_html("killinchu")
    assert "MODELED / SIMULATED" in html and "/api/killinchu/v1/platform" in html
    assert "no live airframe" in html and "0 runtime CDN" in html
    print("killinchu_platform_dynamics: ALL OK (6 checks)")


if __name__ == "__main__":
    _selftest()
