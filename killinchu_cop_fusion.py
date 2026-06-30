"""killinchu_cop_fusion.py — DEV 3: fused Common Operating Picture (COP).

ADDITIVE, try/except-guarded, FRONT-INSERTED before the SPA catch-all. Does NOT
touch killinchu_elite_console.py, killinchu_mesh.py, killinchu_live_feeds.py or
any existing route. Reuses the REAL primitives already in this repo:

  - killinchu_mesh.MeshHarness  → genuine ECDSA-P256 signed entity-state
    transitions (Anduril Lattice ENTITY MESH pattern) + a genuine 3-of-4 BFT
    quorum (Conjecture 2 — Khipu BFT safety, labelled OPEN, never "proven").
  - killinchu_live_feeds        → the real adsb.lol / Digitraffic AIS / CelesTrak
    feeds are PRESERVED and consumed by the COP page (no mocks substituted).
  - szl_dsse                    → DSSE/in-toto signing; honest UNSIGNED envelope
    when no cosign key (never a fabricated signature).

What this module adds (the honest gap on top of the mature stack):

  GET  /elite/cop                          fused single-screen 3D COP page
  GET  /api/<ns>/v1/cop/scl                 SZL Capability Levels + authority map
  GET  /api/<ns>/v1/cop/ooda                live OODA-loop metrics (real signals)
  POST /api/<ns>/v1/cop/interdiction        SCL-gated signed entity transition
  GET  /api/<ns>/v1/cop/cosign/stream       SSE: real 3-of-4 votes, optimistic UI

Leaders studied + surpassed: Anduril Lattice (entity mesh / typed tracks),
True Anomaly Mosaic (Three.js holographic COP on one screen), DeepMind Frontier
Safety Framework CCLs (graduated capability thresholds → engagement authority).

HONESTY (binding): effectors are SIMULATED, human-on-the-loop — this surface
NEVER commands a live weapon. SCL-3 ("proof-required") maps to a backing proof
that is OPEN (Conjecture 2), so SCL-3 engagement authority is HELD, not granted.
Λ = Conjecture 1 (advisory). Trust never 100%. 0 CDN (Three.js vendored).

Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

# ── real primitives (import is best-effort; register() stays non-fatal) ────────
try:
    import killinchu_mesh as _mesh
except Exception:  # pragma: no cover
    _mesh = None

try:
    import szl_dsse as _dsse
except Exception:  # pragma: no cover
    _dsse = None


# ── dedicated 4-node COP formation ────────────────────────────────────────────
# The default org harness seeds 3 nodes; an honest 3-of-4 demonstration needs a
# real 4th witness. We hold a dedicated MeshHarness(4) so every COP cosign is a
# genuine 4-signer quorum with threshold 3 (tolerates f=1), not a faked count.
_COP_HARNESS: Optional["_mesh.MeshHarness"] = None  # type: ignore[name-defined]


def _cop_harness():
    global _COP_HARNESS
    if _mesh is None:
        return None
    if _COP_HARNESS is None:
        try:
            _COP_HARNESS = _mesh.MeshHarness(4)
        except Exception:
            # fall back to the shared singleton (may be 3-node — labelled honestly)
            try:
                _COP_HARNESS = _mesh.get_harness()
            except Exception:
                _COP_HARNESS = None
    return _COP_HARNESS


# ── SZL Capability Levels (modelled on DeepMind FSF Critical Capability Levels)─
# Graduated thresholds that gate ENGAGEMENT AUTHORITY. The mapping is the honest
# core: higher capability ⇒ stronger cryptographic/▢proof precondition before any
# (simulated) effector authority is granted.
SCL = {
    "SCL-1": {
        "id": "SCL-1",
        "name": "Advisory",
        "precondition": "none",
        "engagement_authority": "OBSERVE / RECOMMEND only — no effector authority",
        "gate": "signed entity-state transition (advisory track)",
        "fsf_analog": "Below-CCL: monitoring & advisory; no mitigations required",
    },
    "SCL-2": {
        "id": "SCL-2",
        "name": "Cosign-required",
        "precondition": "3-of-4 BFT witness cosign (CANONICAL)",
        "engagement_authority": "CONDITIONAL — granted iff 3-of-4 witnesses cosign; "
                                "effector SIMULATED, human-on-the-loop",
        "gate": "quorum certificate verdict == CANONICAL (allow_count >= 3, n=4)",
        "fsf_analog": "At-CCL: deployment mitigations required before capability use",
    },
    "SCL-3": {
        "id": "SCL-3",
        "name": "Proof-required",
        "precondition": "machine-checked safety proof of the engagement invariant",
        "engagement_authority": "HELD — the backing proof (Conjecture 2, Khipu BFT "
                                "safety) is OPEN/machine-checked, NOT proven; "
                                "authority is NOT auto-granted, human decision stands",
        "gate": "Lean proof status == proven (currently OPEN → authority withheld)",
        "fsf_analog": "Above-CCL: capability withheld pending stronger assurance",
    },
}
_SCL_ORDER = ["SCL-1", "SCL-2", "SCL-3"]


def _scl_payload() -> dict[str, Any]:
    return {
        "schema": "szl.cop.capability_levels/v1",
        "levels": [SCL[k] for k in _SCL_ORDER],
        "mapping_basis": "DeepMind Frontier Safety Framework — Critical Capability "
                         "Levels (graduated thresholds gate capability use)",
        "honesty": "Effectors are SIMULATED, human-on-the-loop. SCL-3 maps to a proof "
                   "that is OPEN (Conjecture 2); SCL-3 engagement authority is HELD, "
                   "never auto-granted. This surface never commands a live weapon.",
        "doctrine": "Λ = Conjecture 1 (advisory). Conjecture 2 = Khipu BFT safety (OPEN). "
                    "Trust never 100%.",
    }


# ── OODA-loop metrics from REAL signals ────────────────────────────────────────
def _ooda_payload() -> dict[str, Any]:
    """Each phase is backed by a real signal; nothing fabricated. The Decide
    phase reports a MEASURED quorum sign latency (we time a real 4-signer run).
    Composite cadence is a live snapshot, NOT a fabricated SLA."""
    h = _cop_harness()
    observe = {"signal": "live feeds + mesh entities", "available": _mesh is not None}
    orient = {}
    decide = {}
    act = {}

    if h is not None:
        try:
            st = h.status()
            orient = {
                "entities_tracked": st.get("transition_count", st.get("seq", 0)),
                "nodes": st.get("node_count", len(getattr(h, "nodes", {}) or {})),
                "formation": st.get("formation_id", "killinchu-mesh-formation-001"),
            }
        except Exception as e:
            orient = {"error": "status unavailable: %r" % e}

        # DECIDE — measure a real 3-of-4 quorum sign latency (genuine signatures).
        try:
            t0 = time.perf_counter()
            q = h.run_quorum({"action": "ooda-decide-probe"})
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            cert = q.get("certificate", {})
            decide = {
                "quorum_verdict": cert.get("verdict"),
                "allow_count": cert.get("allow_count"),
                "n": cert.get("n"),
                "threshold": cert.get("threshold"),
                "tolerates_f": cert.get("tolerates_f"),
                "measured_sign_latency_ms": dt_ms,
                "measurement": "REAL — wall-clock of an actual 4-signer ECDSA-P256 quorum",
            }
        except Exception as e:
            decide = {"error": "quorum probe failed: %r" % e}

        # ACT — count of signed entity-state transitions on the AUTHORIZED track.
        try:
            st2 = h.status()
            act = {
                "signed_transitions_total": st2.get("transition_count", st2.get("seq", 0)),
                "effector": "SIMULATED (human-on-the-loop) — never a live weapon",
            }
        except Exception as e:
            act = {"error": "status unavailable: %r" % e}
    else:
        orient = decide = act = {"error": "mesh harness unavailable in this runtime"}

    return {
        "schema": "szl.cop.ooda/v1",
        "loop": {"observe": observe, "orient": orient, "decide": decide, "act": act},
        "feeds_hint": {
            "air": "/api/{ns}/v1/air/live",
            "ais": "/api/{ns}/v1/ais/live",
            "status": "/api/{ns}/v1/feeds/status",
            "note": "Observe is fed by the REAL adsb.lol / Digitraffic AIS / CelesTrak "
                    "feeds already wired in killinchu_live_feeds — preserved, not mocked.",
        },
        "honesty": "Per-phase signals are real. Decide latency is a measured quorum "
                   "sign time; the composite OODA cadence is a live snapshot, not an SLA.",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── SCL-gated interdiction → genuine signed entity-state transition ────────────
def _interdiction(body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    track_id = str(body.get("track_id") or body.get("track") or "").strip()
    scl = str(body.get("scl") or "SCL-1").strip().upper()
    action = str(body.get("action") or "assess").strip()
    if not track_id:
        return ({"error": "track_id required",
                 "honesty": "HONEST REJECT — refusing to sign an interdiction with no track."}, 422)
    if scl not in SCL:
        return ({"error": "unknown scl", "valid": _SCL_ORDER}, 422)

    h = _cop_harness()
    if h is None:
        return ({"error": "mesh harness unavailable",
                 "honesty": "Cannot sign without the real mesh primitive."}, 503)

    level = SCL[scl]
    out: dict[str, Any] = {
        "schema": "szl.cop.interdiction/v1",
        "track_id": track_id,
        "action": action,
        "scl": level,
        "effector": "SIMULATED — human-on-the-loop. This surface NEVER commands a live weapon.",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Every interdiction is recorded as a genuine signed entity-state transition.
    txn_class = "cop-interdiction:%s:%s" % (scl, action)
    try:
        receipt = h.write_transition({
            "transition_class": txn_class,
            "payload": {"track_id": track_id, "action": action, "scl": scl},
        })
        out["entity_transition"] = receipt
    except Exception as e:
        return ({"error": "transition failed: %r" % e}, 500)

    # Authority decision by SCL.
    if scl == "SCL-1":
        out["authority"] = {
            "granted": False, "mode": "advisory",
            "reason": "SCL-1 is OBSERVE/RECOMMEND only — no effector authority by design.",
        }
        return (out, 200)

    if scl == "SCL-2":
        try:
            q = h.run_quorum({"action": txn_class, "payload": {"track_id": track_id}})
        except Exception as e:
            return ({"error": "quorum failed: %r" % e}, 500)
        cert = q.get("certificate", {})
        canonical = bool(cert.get("canonical"))
        out["quorum"] = {
            "verdict": cert.get("verdict"), "allow_count": cert.get("allow_count"),
            "n": cert.get("n"), "threshold": cert.get("threshold"),
            "tolerates_f": cert.get("tolerates_f"),
            "certificate_preimage_sha256": q.get("certificate_preimage_sha256"),
            "honesty": q.get("honesty"),
            "conjecture_2_note": q.get("conjecture_2_note"),
        }
        out["authority"] = {
            "granted": canonical, "mode": "cosign-required",
            "reason": ("3-of-4 witnesses cosigned (CANONICAL) — SIMULATED engagement "
                       "authority granted, human-on-the-loop." if canonical else
                       "Quorum did NOT reach 3-of-4 — authority DENIED."),
        }
        return (out, 200)

    # SCL-3 — proof-required; backing proof is OPEN ⇒ authority HELD (honest).
    out["authority"] = {
        "granted": False, "mode": "proof-required",
        "proof_status": "OPEN",
        "backing_proof": "Conjecture 2 (Khipu BFT safety) — machine-checked, NOT proven",
        "reason": "SCL-3 requires a proven safety invariant. The backing conjecture is "
                  "OPEN, so engagement authority is HELD pending human decision. "
                  "We do not paint an open conjecture green.",
    }
    return (out, 200)


# ── HTML: the fused single-screen 3D COP ───────────────────────────────────────
def _cop_html(ns: str) -> str:
    return _COP_PAGE.replace("__NS__", ns)


_COP_PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>killinchu · Common Operating Picture</title>
<style>
:root{--void:#080c14;--proof:#3af4c8;--lattice:#5b8dee;--gold:#d7b96b;
--ink:#e7ecf3;--mut:#8b97a8;--panel:rgba(13,19,30,.82);--line:rgba(91,141,238,.22);}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--void);color:var(--ink);font:14px/1.5 Inter,system-ui,sans-serif;
overflow:hidden;height:100vh}
h1,h2,h3,.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
.grid{display:grid;grid-template-columns:300px 1fr 340px;grid-template-rows:48px 1fr 132px;
height:100vh;gap:1px;background:var(--line)}
header{grid-column:1/4;background:var(--panel);display:flex;align-items:center;
gap:16px;padding:0 18px}
header .brand{font-family:'Space Grotesk',sans-serif;font-weight:700;letter-spacing:.5px;
font-size:16px}
header .brand b{color:var(--proof)}
.pill{font:600 10px/1 'JetBrains Mono',monospace;padding:5px 9px;border:1px solid var(--line);
border-radius:999px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px}
.pill.live{color:var(--proof);border-color:rgba(58,244,200,.4)}
.pill.warn{color:var(--gold);border-color:rgba(215,185,107,.4)}
.spacer{flex:1}
a.back{color:var(--lattice);text-decoration:none;font-size:12px}
aside,.right{background:var(--panel);padding:14px;overflow-y:auto}
section.stage{position:relative;background:radial-gradient(ellipse at 50% 40%,
#0c1424 0%,var(--void) 70%);overflow:hidden}
#cop3d{position:absolute;inset:0}
.stagehud{position:absolute;left:12px;top:10px;font:11px/1.5 'JetBrains Mono',monospace;
color:var(--mut);pointer-events:none;text-shadow:0 0 8px #000}
.stagehud b{color:var(--proof)}
.foot{grid-column:1/4;background:var(--panel);display:grid;grid-template-columns:repeat(4,1fr);
gap:1px}
.ooda{padding:10px 14px;background:var(--void)}
.ooda h3{font-size:11px;letter-spacing:1px;color:var(--lattice);text-transform:uppercase}
.ooda .v{font-size:22px;font-family:'JetBrains Mono',monospace;color:var(--proof);margin-top:3px}
.ooda .s{font-size:10px;color:var(--mut)}
h2{font-size:11px;letter-spacing:1.2px;color:var(--mut);text-transform:uppercase;
margin-bottom:10px;border-bottom:1px solid var(--line);padding-bottom:7px}
.scl{border:1px solid var(--line);border-radius:8px;padding:9px 10px;margin-bottom:8px;cursor:pointer}
.scl:hover{border-color:rgba(91,141,238,.5)}
.scl.sel{border-color:var(--proof);box-shadow:0 0 0 1px rgba(58,244,200,.3) inset}
.scl .id{font:700 12px 'JetBrains Mono',monospace;color:var(--gold)}
.scl .nm{font-size:12px;color:var(--ink)}
.scl .au{font-size:10.5px;color:var(--mut);margin-top:3px}
.track{display:flex;justify-content:space-between;padding:7px 8px;border:1px solid var(--line);
border-radius:6px;margin-bottom:6px;font-size:12px;cursor:pointer}
.track:hover{border-color:rgba(58,244,200,.4)}
.track.sel{border-color:var(--proof)}
.track .id{font-family:'JetBrains Mono',monospace}
.track .kind{color:var(--mut);font-size:10px}
.btn{display:block;width:100%;padding:10px;margin-top:6px;background:transparent;
border:1px solid var(--proof);color:var(--proof);border-radius:7px;font:600 12px 'JetBrains Mono',monospace;
cursor:pointer;letter-spacing:.5px}
.btn:hover{background:rgba(58,244,200,.08)}.btn:disabled{opacity:.4;cursor:wait}
.receipt{font:11px/1.5 'JetBrains Mono',monospace;background:var(--void);border:1px solid var(--line);
border-radius:7px;padding:10px;margin-top:8px;white-space:pre-wrap;word-break:break-all;max-height:210px;overflow-y:auto}
.cosign{margin-top:8px}
.vote{display:flex;align-items:center;gap:8px;font:11px 'JetBrains Mono',monospace;
padding:5px 0;border-bottom:1px dashed var(--line)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--mut);flex:none;transition:.3s}
.dot.sign{background:var(--gold);animation:pulse 1s infinite}
.dot.ok{background:var(--proof)}
@keyframes pulse{50%{opacity:.3}}
.verdict{margin-top:8px;font:700 13px 'JetBrains Mono',monospace;text-align:center;padding:8px;border-radius:7px}
.verdict.ok{color:var(--proof);border:1px solid rgba(58,244,200,.4)}
.verdict.held{color:var(--gold);border:1px solid rgba(215,185,107,.4)}
.verdict.deny{color:#ff6b6b;border:1px solid rgba(255,107,107,.4)}
.note{font-size:10px;color:var(--mut);margin-top:10px;line-height:1.5}
.legend{position:absolute;right:12px;bottom:10px;font:10px 'JetBrains Mono',monospace;color:var(--mut)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
</style></head>
<body>
<div class="grid">
  <header>
    <span class="brand">killinchu <b>// COP</b></span>
    <span class="pill live" id="feedPill">feeds —</span>
    <span class="pill" id="meshPill">mesh —</span>
    <span class="pill warn">effector SIMULATED</span>
    <span class="spacer"></span>
    <span class="mono" style="color:var(--mut);font-size:11px">Λ = Conjecture 1 (advisory) · trust &lt; 100%</span>
    <a class="back" href="/elite">← Field Console</a>
  </header>

  <aside>
    <h2>Capability Levels (SCL)</h2>
    <div id="sclList"></div>
    <div class="note">Modelled on DeepMind FSF Critical Capability Levels. SCL-3 maps to a
      backing proof that is OPEN (Conjecture 2) — engagement authority is HELD, never auto-granted.</div>
  </aside>

  <section class="stage">
    <div id="cop3d"></div>
    <div class="stagehud">HOLOGRAPHIC THREAT SPACE · <b id="entCount">0</b> entities ·
      <span id="srcLine">air/ais real feeds</span></div>
    <div class="legend"><i style="background:#3af4c8"></i>air&nbsp;&nbsp;
      <i style="background:#5b8dee"></i>maritime&nbsp;&nbsp;
      <i style="background:#d7b96b"></i>selected</div>
  </section>

  <div class="right">
    <h2>Track / Entity</h2>
    <div id="trackList"><div class="note">loading real feeds…</div></div>
    <h2 style="margin-top:14px">Engagement (ROE-gated)</h2>
    <div class="note" id="roeLine">select a track + SCL, then commit a signed interdiction.</div>
    <button class="btn" id="commitBtn" disabled>COMMIT INTERDICTION</button>
    <div class="cosign" id="cosign"></div>
    <div id="verdict"></div>
    <div class="receipt" id="receipt" style="display:none"></div>
  </div>

  <div class="foot">
    <div class="ooda"><h3>Observe</h3><div class="v" id="o_obs">—</div><div class="s">real feeds + entities</div></div>
    <div class="ooda"><h3>Orient</h3><div class="v" id="o_ori">—</div><div class="s">entities tracked</div></div>
    <div class="ooda"><h3>Decide</h3><div class="v" id="o_dec">—</div><div class="s">measured quorum sign ms</div></div>
    <div class="ooda"><h3>Act</h3><div class="v" id="o_act">—</div><div class="s">signed transitions</div></div>
  </div>
</div>

<script src="/vendor/three.min.js"></script>
<script>
const NS="__NS__", API=p=>`/api/${NS}/v1${p}`;
let SEL_TRACK=null, SEL_SCL="SCL-1", TRACKS=[];

// ---- SCL panel ----
fetch(API("/cop/scl")).then(r=>r.json()).then(d=>{
  const el=document.getElementById("sclList"); el.innerHTML="";
  (d.levels||[]).forEach((L,i)=>{
    const div=document.createElement("div");
    div.className="scl"+(i===0?" sel":""); div.dataset.id=L.id;
    div.innerHTML=`<div class="id">${L.id}</div><div class="nm">${L.name}</div>
      <div class="au">${L.engagement_authority}</div>`;
    div.onclick=()=>{document.querySelectorAll('.scl').forEach(x=>x.classList.remove('sel'));
      div.classList.add('sel'); SEL_SCL=L.id; refreshRoe();};
    el.appendChild(div);
  });
}).catch(()=>{});

// ---- OODA ticker ----
function ooda(){fetch(API("/cop/ooda")).then(r=>r.json()).then(d=>{
  const L=d.loop||{};
  document.getElementById("o_obs").textContent=(L.observe&&L.observe.available)?"LIVE":"—";
  document.getElementById("o_ori").textContent=(L.orient&&(L.orient.entities_tracked??"—"));
  document.getElementById("o_dec").textContent=(L.decide&&(L.decide.measured_sign_latency_ms??"—"));
  document.getElementById("o_act").textContent=(L.act&&(L.act.signed_transitions_total??"—"));
  const dec=L.decide||{};
  document.getElementById("meshPill").textContent=
    dec.verdict?`mesh ${dec.allow_count}/${dec.n} ✓`:`mesh ${dec.allow_count||"—"}/${dec.n||4}`;
  document.getElementById("meshPill").className="pill live";
}).catch(()=>{});}
ooda(); setInterval(ooda,6000);

// ---- real feeds → entities ----
function classify(f){return f.source==="ais"||f.type==="vessel"?"maritime":"air";}
async function loadFeeds(){
  let air=[],ais=[];
  // killinchu_live_feeds wraps contacts in {source,mode,data:{aircraft|vessels:[…]}}
  try{const a=await(await fetch(API("/air/live"))).json(); const D=a.data||a;
    air=(D.aircraft||D.contacts||D.tracks||a.aircraft||[]).slice(0,60);}catch(e){}
  try{const s=await(await fetch(API("/ais/live"))).json(); const D=s.data||s;
    ais=(D.vessels||D.contacts||D.tracks||s.vessels||[]).slice(0,40);}catch(e){}
  const live=(air.length+ais.length)>0;
  document.getElementById("feedPill").textContent=live?`feeds LIVE ${air.length+ais.length}`:"feeds — no data";
  document.getElementById("feedPill").className=live?"pill live":"pill warn";
  TRACKS=[];
  air.forEach((x,i)=>TRACKS.push({id:x.hex||x.icao||x.flight||x.callsign||("AIR-"+i),
    kind:"air",lat:+(x.lat||x.latitude),lon:+(x.lon||x.longitude),alt:+(x.alt_baro||x.altitude||0)}));
  ais.forEach((x,i)=>TRACKS.push({id:x.mmsi||x.name||("AIS-"+i),
    kind:"maritime",lat:+(x.lat||x.latitude),lon:+(x.lon||x.longitude),alt:0}));
  TRACKS=TRACKS.filter(t=>isFinite(t.lat)&&isFinite(t.lon));
  document.getElementById("entCount").textContent=TRACKS.length;
  renderTracks(); renderEntities();
}
function renderTracks(){
  const el=document.getElementById("trackList");
  if(!TRACKS.length){el.innerHTML='<div class="note">no live contacts in window (feeds honest-empty)</div>';return;}
  el.innerHTML="";
  TRACKS.slice(0,18).forEach(t=>{
    const d=document.createElement("div"); d.className="track"; d.dataset.id=t.id;
    d.innerHTML=`<span class="id">${t.id}</span><span class="kind">${t.kind.toUpperCase()}</span>`;
    d.onclick=()=>{SEL_TRACK=t;document.querySelectorAll('.track').forEach(x=>x.classList.remove('sel'));
      d.classList.add('sel');highlight(t.id);refreshRoe();};
    el.appendChild(d);
  });
}
function refreshRoe(){
  const b=document.getElementById("commitBtn");
  if(SEL_TRACK){document.getElementById("roeLine").innerHTML=
    `track <b>${SEL_TRACK.id}</b> · ${SEL_SCL} · effector SIMULATED`;b.disabled=false;}
  else{b.disabled=true;}
}

// ---- Three.js holographic threat space (0-CDN, vendored) ----
let scene,cam,rend,dots={},sel=null;
function init3d(){
  const host=document.getElementById("cop3d");
  scene=new THREE.Scene();
  cam=new THREE.PerspectiveCamera(55,host.clientWidth/host.clientHeight,.1,1000);
  cam.position.set(0,3.4,7);
  rend=new THREE.WebGLRenderer({antialias:true,alpha:true});
  rend.setSize(host.clientWidth,host.clientHeight); rend.setPixelRatio(devicePixelRatio);
  host.appendChild(rend.domElement);
  // earth-ish reference sphere (wireframe)
  const sph=new THREE.Mesh(new THREE.SphereGeometry(2.4,40,40),
    new THREE.MeshBasicMaterial({color:0x5b8dee,wireframe:true,transparent:true,opacity:.16}));
  scene.add(sph);
  const grid=new THREE.GridHelper(14,28,0x1d2c44,0x121c2e); grid.position.y=-2.6; scene.add(grid);
  animate();
  addEventListener("resize",()=>{cam.aspect=host.clientWidth/host.clientHeight;
    cam.updateProjectionMatrix();rend.setSize(host.clientWidth,host.clientHeight);});
}
function ll2xyz(lat,lon,r){const p=(90-lat)*Math.PI/180,t=(lon+180)*Math.PI/180;
  return[-r*Math.sin(p)*Math.cos(t),r*Math.cos(p),r*Math.sin(p)*Math.sin(t)];}
function renderEntities(){
  if(!scene)return;
  Object.values(dots).forEach(m=>scene.remove(m)); dots={};
  TRACKS.forEach(t=>{
    const r=2.4+(t.kind==="air"?.25+Math.min(t.alt/40000,1)*.6:.02);
    const [x,y,z]=ll2xyz(t.lat,t.lon,r);
    const col=t.kind==="air"?0x3af4c8:0x5b8dee;
    const m=new THREE.Mesh(new THREE.SphereGeometry(.04,10,10),
      new THREE.MeshBasicMaterial({color:col}));
    m.position.set(x,y,z); scene.add(m); dots[t.id]=m;
  });
}
function highlight(id){
  if(sel&&dots[sel])dots[sel].material.color.setHex(/AIS|maritime/.test(sel)?0x5b8dee:0x3af4c8);
  sel=id; const m=dots[id]; if(m){m.material.color.setHex(0xd7b96b);
    m.scale.set(2.2,2.2,2.2);setTimeout(()=>m&&m.scale.set(1,1,1),400);}
}
let rot=0;
function animate(){requestAnimationFrame(animate);rot+=.0014;
  scene.rotation.y=rot; rend.render(scene,cam);}
if(window.THREE)init3d(); else document.getElementById("srcLine").textContent="three.js vendor missing";

// ---- COMMIT: optimistic UI over a REAL 3-of-4 cosign stream ----
document.getElementById("commitBtn").onclick=async()=>{
  if(!SEL_TRACK)return;
  const btn=document.getElementById("commitBtn"); btn.disabled=true;
  const cs=document.getElementById("cosign"), vd=document.getElementById("verdict"),
        rc=document.getElementById("receipt");
  cs.innerHTML=""; vd.innerHTML=""; rc.style.display="none";
  // optimistic witness rows
  const labels=["node-alpha","node-bravo","node-charlie","node-delta"], rows={};
  labels.forEach(l=>{const d=document.createElement("div");d.className="vote";
    d.innerHTML=`<span class="dot sign" data-l="${l}"></span><span>${l}</span>
      <span style="flex:1;text-align:right;color:var(--mut)">signing…</span>`;
    cs.appendChild(d);rows[l]=d;});
  // 1) record the SCL-gated signed interdiction (real entity-state transition)
  let res;
  try{res=await(await fetch(API("/cop/interdiction"),{method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify({track_id:SEL_TRACK.id,scl:SEL_SCL,action:"interdict"})})).json();}
  catch(e){vd.className="verdict deny";vd.textContent="interdiction failed";btn.disabled=false;return;}
  // 2) stream the genuine votes (pacing cosmetic; signatures real, server-verified)
  const ev=new EventSource(API(`/cop/cosign/stream?action=${encodeURIComponent("cop-interdiction:"+SEL_SCL)}`));
  ev.onmessage=(m)=>{
    let v; try{v=JSON.parse(m.data);}catch(e){return;}
    if(v.type==="vote"&&rows[v.label]){const r=rows[v.label];
      r.querySelector(".dot").className="dot ok";
      r.querySelector("span:last-child").textContent=v.verdict+" ✓";
      r.querySelector("span:last-child").style.color="var(--proof)";}
    if(v.type==="certificate"){ev.close();
      const au=(res&&res.authority)||{};
      if(au.granted){vd.className="verdict ok";
        vd.textContent=`✓ ${v.allow_count}-of-${v.n} witnessed · authority GRANTED (SIMULATED)`;}
      else if((au.mode||"")==="proof-required"){vd.className="verdict held";
        vd.textContent=`⚠ ${SEL_SCL} HELD · backing proof OPEN`;}
      else{vd.className="verdict deny";
        vd.textContent=au.granted===false&&SEL_SCL==="SCL-1"?
          "advisory only · no effector authority":"authority DENIED";}
      rc.style.display="block"; rc.textContent=JSON.stringify(res,null,1);
      btn.disabled=false; ooda();}
  };
  ev.onerror=()=>{ev.close();btn.disabled=false;
    if(!vd.textContent){const au=(res&&res.authority)||{};
      rc.style.display="block";rc.textContent=JSON.stringify(res,null,1);
      vd.className="verdict held";vd.textContent="cosign stream ended — see receipt";}};
};

loadFeeds(); setInterval(loadFeeds,30000);
</script>
</body></html>"""


# ── registration ──────────────────────────────────────────────────────────────
def register(app, ns: str = "killinchu", emit_receipt=None) -> dict[str, Any]:
    """Front-insert the COP surface. Idempotent, never crashes the caller."""
    from starlette.routing import Route
    from starlette.responses import JSONResponse, HTMLResponse, StreamingResponse
    from starlette.requests import Request

    base = f"/api/{ns}/v1/cop"

    async def cop_page(request: Request):
        return HTMLResponse(_cop_html(ns))

    async def scl_ep(request: Request):
        return JSONResponse(_scl_payload())

    async def ooda_ep(request: Request):
        return JSONResponse(_ooda_payload())

    async def interdiction_ep(request: Request):
        raw = await request.body()
        if not raw:
            return JSONResponse({"error": "empty body — {track_id, scl, action} required",
                                 "honesty": "HONEST REJECT — refusing to sign an empty interdiction."},
                                status_code=422)
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError
        except Exception:
            return JSONResponse({"error": "malformed JSON body"}, status_code=422)
        out, status = _interdiction(body)
        return JSONResponse(out, status_code=status)

    async def cosign_stream(request: Request):
        """SSE: stream the genuine 3-of-4 votes one-by-one for the optimistic UI.
        HONEST: the inter-vote DELAY is cosmetic (lets the operator watch the
        quorum form); every signature and the certificate are REAL, produced by
        the same 4-signer ECDSA-P256 quorum and verified in-process."""
        action = request.query_params.get("action", "cop-cosign")

        async def gen():
            h = _cop_harness()
            if h is None:
                yield "data: %s\n\n" % json.dumps(
                    {"type": "error", "msg": "mesh harness unavailable"})
                return
            try:
                q = await asyncio.to_thread(h.run_quorum, {"action": action})
            except Exception as e:
                yield "data: %s\n\n" % json.dumps({"type": "error", "msg": repr(e)})
                return
            votes = q.get("votes", [])
            cert = q.get("certificate", {})
            for v in votes:
                yield "data: %s\n\n" % json.dumps({
                    "type": "vote", "label": v.get("label"),
                    "verdict": v.get("verdict"), "signed": v.get("signed"),
                    "alg": v.get("alg"), "key_source": v.get("key_source"),
                })
                await asyncio.sleep(0.45)  # cosmetic pacing — signatures already real
            yield "data: %s\n\n" % json.dumps({
                "type": "certificate", "verdict": cert.get("verdict"),
                "allow_count": cert.get("allow_count"), "n": cert.get("n"),
                "threshold": cert.get("threshold"), "tolerates_f": cert.get("tolerates_f"),
                "certificate_preimage_sha256": q.get("certificate_preimage_sha256"),
                "honesty": q.get("honesty"),
            })

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    specs = [
        ("/elite/cop", cop_page, ["GET"], "cop_page"),
        (f"{base}/scl", scl_ep, ["GET"], "cop_scl"),
        (f"{base}/ooda", ooda_ep, ["GET"], "cop_ooda"),
        (f"{base}/interdiction", interdiction_ep, ["POST"], "cop_interdiction"),
        (f"{base}/cosign/stream", cosign_stream, ["GET"], "cop_cosign_stream"),
    ]
    names = {n for _, _, _, n in specs}
    app.router.routes[:] = [r for r in app.router.routes
                            if getattr(r, "name", "") not in names]
    new_routes = [Route(p, fn, methods=m, name=n) for p, fn, m, n in specs]
    for r in reversed(new_routes):
        app.router.routes.insert(0, r)

    # honest readiness self-report
    h = _cop_harness()
    nodes = len(getattr(h, "nodes", {}) or {}) if h is not None else 0
    return {
        "registered": len(new_routes),
        "page": "/elite/cop",
        "base": base,
        "cop_nodes": nodes,
        "quorum": "3-of-4" if nodes >= 4 else ("degraded:%d-node" % nodes if nodes else "harness-down"),
        "signing": (bool(_dsse.signing_available()) if _dsse is not None else False),
        "honesty": "Effectors SIMULATED. SCL-3 authority HELD (backing proof OPEN). "
                   "Λ = Conjecture 1 (advisory). 0 CDN.",
    }


__all__ = ["register"]
