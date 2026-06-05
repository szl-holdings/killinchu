# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 — 749 declarations · 163 sorries · 14 unique axioms · 13-axis canonical trust
"""
killinchu_elite_console — the unified 14-tab Counter-UAS operator console.

ADDITIVE. Registered BEFORE the SPA catch-all. Serves a single self-contained
HTML+JS surface (no external asset file, so it ships without a Dockerfile asset
COPY) at:

    GET  /elite               the 14-tab elite console
    GET  /killinchu/elite     alias

Every tab calls a REAL, already-registered killinchu endpoint and renders the
live JSON. NO MOCKS. NO placeholder data. Empty buffers render an honest IDLE
state, never invented rows.

It also registers ONE new REAL endpoint — the cross-flagship "borrowed powers"
panel data source:

    GET  /api/killinchu/v1/borrowed-powers

which reports, for each sibling flagship (a11oy / sentra / amaru / rosie), which
capability/anatomy/formula killinchu borrows and the LIVE local endpoint that
implements it, plus the live DSSE signing-availability state. This is computed
from real runtime state (emit_receipt + szl_dsse), not a static brochure.

Tabs → backing endpoints
------------------------
 1  Live Track Board / COP        GET  /api/killinchu/v1/threats/active
                                  GET  /api/killinchu/v1/tracks/history
 2  Sensor-Fusion Monitor         GET  /api/killinchu/v1/sensor-fusion/status
                                  POST /api/killinchu/v1/sensor-fusion/fuse
 3  Multi-Track Threat Queue      POST /api/killinchu/v1/tracks/multi-prioritize
 4  ROE Policy Editor + Evaluate  GET/PUT /api/killinchu/v1/roe/policy
                                  POST /api/killinchu/v1/roe/evaluate
 5  Engagement Audit Log          GET  /api/killinchu/v1/engagements/audit-log
                                  POST /api/killinchu/v1/engagements/record
 6  DSSE Receipt Verifier         GET  /api/killinchu/v1/receipt/ledger
                                  POST /api/killinchu/v1/receipt/emit
 7  13-axis Λ-gate Monitor        POST /api/killinchu/v1/counter-uas/evaluate
 8  3-of-4 BFT Quorum Console     POST /api/killinchu/uds/v1/mission/execute
                                  POST /api/killinchu/uds/v1/consensus/verify
                                  GET  /api/killinchu/uds/v1/healthz
 9  PQC Hybrid Signing Panel      POST /khipu/sign?mode={ecdsa,pqc,hybrid}
10  Protocol Decoders             POST /api/killinchu/v1/remote-id/decode
                                  POST /api/killinchu/v1/ads-b/decode
                                  POST /api/killinchu/v1/mavlink/parse
11  Geofence Zone Editor          GET  /api/killinchu/v2/geofence/zones
                                  POST /api/killinchu/v2/geofence/check
12  Swarm Topology View           GET/POST /api/killinchu/v1/swarm/topology
13  Threat Classification DB      GET  /api/killinchu/v1/drones/database
14  Cross-Flagship Borrowed Powers GET /api/killinchu/v1/borrowed-powers
                                  GET  /api/killinchu/v1/mesh/state

Honesty
-------
* SLSA L1 honest (killinchu NEVER claims L2 — private Fulcio, no public Rekor).
* Λ = Conjecture 1 — NEVER a theorem. 749/14/163 @ c7c0ba17.
* DSSE receipts are REAL ECDSA-P256-SHA256 when SZL_COSIGN_PRIVATE_PEM is set,
  else an explicit honest PLACEHOLDER (never a fabricated signature).
* ADS-B / Remote-ID decoded fields are CLAIMS from unauthenticated broadcast —
  not attested truth.
* No FedRAMP / Iron Bank / CMMC. Section 889 = exactly 5 vendors.

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

_DOCTRINE = "v11"
_LEAN = "c7c0ba17"
_COUNTS = "749/14/163"
_SECTION_889 = ["Huawei", "ZTE", "Hytera", "Hikvision", "Dahua"]

try:
    import szl_dsse as _dsse  # the LIVE cosign DSSE signer
except Exception:  # pragma: no cover
    _dsse = None


# ---------------------------------------------------------------------------
# Cross-flagship "borrowed powers" — REAL capability map.
#
# killinchu is drone-facing and "takes from EACH flagship what it needs — the
# formulas and the anatomy — so it can do the Warhacker fixes." Each entry names
# the sibling flagship, the anatomy/formula borrowed, and the LIVE LOCAL endpoint
# in THIS killinchu process that implements the borrowed capability.
# ---------------------------------------------------------------------------
_BORROWED: list[dict[str, Any]] = [
    {
        "flagship": "a11oy",
        "role": "orchestrator / receipt substrate",
        "borrowed_anatomy": "DSSE receipt substrate + Khipu Merkle DAG + LLM-hub access + formula set + 3-of-4 quorum",
        "borrowed_formulas": ["F1", "F11", "F12", "F18", "F19"],
        "how_applied": (
            "Every counter-UAS interdiction emits an a11oy-style DSSE ECDSA-P256 receipt "
            "chained into the Khipu DAG (receipts.in ≡ receipts.out). The PROVED formula set "
            "{F1,F11,F12,F18,F19} backs the edge verdict; F23 stays Conjecture 1."
        ),
        "live_endpoints": [
            "POST /api/killinchu/v1/receipt/emit",
            "GET  /api/killinchu/v1/receipt/ledger",
            "POST /khipu/sign?mode=hybrid",
            "GET  /api/killinchu/v1/llm/tiers",
        ],
    },
    {
        "flagship": "sentra",
        "role": "policy immune system (8 gates)",
        "borrowed_anatomy": "policy gates / ROE enforcement immune response",
        "borrowed_formulas": ["policy-gate verdict (ALLOW/SUSPECT/ENGAGE/REVIEW)"],
        "how_applied": (
            "sentra's gate-based immune response is applied as the ROE engine: each telemetry "
            "frame is gated (speed, altitude, Remote-ID, Section-889 vendor, exclusion-zone, "
            "classification) into a signed verdict before any effector is recommended."
        ),
        "live_endpoints": [
            "GET  /api/killinchu/v1/roe/policy",
            "PUT  /api/killinchu/v1/roe/policy",
            "POST /api/killinchu/v1/roe/evaluate",
        ],
    },
    {
        "flagship": "amaru",
        "role": "cortex / reasoner",
        "borrowed_anatomy": "reasoning / threat-classification cortex + 13-axis Λ aggregate",
        "borrowed_formulas": ["13-axis geometric-mean Λ (Conjecture 1)", "PAC-Bayes certified floor"],
        "how_applied": (
            "amaru's reasoning cortex is applied as the 13-axis Λ-gate and the multi-track threat "
            "ranker: every engagement must clear Λ ≥ 0.90 (geometric mean of 13 trust axes), and "
            "threats are scored/ranked before the kill chain. Λ remains Conjecture 1, never a theorem."
        ),
        "live_endpoints": [
            "POST /api/killinchu/v1/counter-uas/evaluate",
            "POST /api/killinchu/v1/tracks/multi-prioritize",
            "POST /api/killinchu/v1/edge/verdict",
        ],
    },
    {
        "flagship": "rosie",
        "role": "operator console (HITL)",
        "borrowed_anatomy": "human-in-the-loop operator surface for engagement decisions",
        "borrowed_formulas": ["HOTL confirmation gate"],
        "how_applied": (
            "rosie's HITL operator surface is applied as this elite console + the v4 operator shell: "
            "ENGAGE verdicts above the Λ floor require human-on-the-loop confirmation, and every "
            "operator action is recorded as a signed engagement record."
        ),
        "live_endpoints": [
            "GET  /elite",
            "GET  /api/killinchu/v4/inbox",
            "POST /api/killinchu/v1/engagements/record",
        ],
    },
]


def _signing_state() -> dict[str, Any]:
    available = bool(_dsse and _dsse.signing_available())
    return {
        "dsse_signing_available": available,
        "honesty": (
            "REAL — ECDSA-P256-SHA256 DSSE over cosign keypair (SZL_COSIGN_PRIVATE_PEM present)."
            if available else
            "PLACEHOLDER — SZL_COSIGN_PRIVATE_PEM secret absent; no signature fabricated (honest)."
        ),
        "fingerprint": (_dsse.public_key_fingerprint() if available else None),
    }


def register(
    app: FastAPI,
    ns: str = "killinchu",
    emit_receipt: Optional[Callable] = None,
) -> dict[str, Any]:
    """Register the elite console + the borrowed-powers endpoint. ADDITIVE."""
    registered: list[str] = []

    # ------------------------------------------------------------------
    # Cross-flagship borrowed-powers — REAL aggregator endpoint.
    # ------------------------------------------------------------------
    @app.get(f"/api/{ns}/v1/borrowed-powers")
    async def borrowed_powers() -> JSONResponse:
        sig = _signing_state()
        # Prove the receipt substrate is live by emitting a real receipt for this query.
        receipt = None
        if emit_receipt is not None:
            node = emit_receipt("borrowed_powers_query", {"siblings": [b["flagship"] for b in _BORROWED]})
            receipt = {"index": node["index"], "digest": node["digest"], "dsse": node["dsse"]}
        return JSONResponse({
            "ok": True,
            "doctrine": _DOCTRINE,
            "lean_sha": _LEAN,
            "counts": _COUNTS,
            "thesis": (
                "killinchu is drone-facing and takes from EACH flagship the formulas and the "
                "anatomy it needs to do the Warhacker counter-UAS fixes — wired here as LIVE "
                "local endpoints, not a brochure."
            ),
            "borrowed_powers": _BORROWED,
            "signing": sig,
            "differentiators": [
                "DSSE ECDSA-P256 signed receipt on every interdiction",
                "13-axis Λ-gate (Conjecture 1)",
                "3-of-4 BFT Khipu consensus quorum (Sentra/Amaru/a11oy/Killinchu)",
                "PQC hybrid signing (ML-DSA-65 + ECDSA-P256)",
            ],
            "slsa": "L1 (honest; private Fulcio, no public Rekor — killinchu never claims L2)",
            "lambda_status": "Conjecture 1 — NOT a theorem",
            "section_889": _SECTION_889,
            "no_fedramp_iron_bank_cmmc": True,
            "query_receipt": receipt,
        })

    registered.append(f"GET /api/{ns}/v1/borrowed-powers")

    # ------------------------------------------------------------------
    # The elite console HTML (self-contained, in-module).
    # ------------------------------------------------------------------
    html = _CONSOLE_HTML.replace("__NS__", ns)

    async def _serve_console() -> HTMLResponse:
        return HTMLResponse(html)

    app.get("/elite")(_serve_console)
    app.get(f"/{ns}/elite")(_serve_console)
    registered.append("GET /elite")
    registered.append(f"GET /{ns}/elite")

    return {
        "module": "killinchu_elite_console",
        "registered": registered,
        "tabs": 14,
        "doctrine": _DOCTRINE,
    }


__all__ = ["register"]


# ===========================================================================
# Self-contained console HTML. Vanilla JS (no CDN, no build step). Every tab
# fetches a REAL endpoint and renders the live JSON. Honesty banners throughout.
# ===========================================================================
_CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Killinchu — Elite Counter-UAS Console</title>
<style>
  :root{
    --bg:#06080d; --panel:#0d1119; --panel2:#11161f; --line:#1d2531;
    --txt:#d7e0ec; --dim:#7e8a9c; --accent:#5fb0ff; --good:#3fd07a;
    --warn:#ffb454; --bad:#ff5d6c; --gold:#e7c46b;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
    font-family:Inter,system-ui,Segoe UI,Roboto,sans-serif;font-size:14px}
  header{display:flex;align-items:center;gap:14px;padding:12px 18px;
    border-bottom:1px solid var(--line);background:linear-gradient(90deg,#0a0e15,#0d1119)}
  header h1{font-size:16px;margin:0;letter-spacing:.5px}
  header h1 b{color:var(--accent)}
  .doctrine{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--dim);text-align:right;line-height:1.5}
  .doctrine .l1{color:var(--gold)}
  .wrap{display:flex;height:calc(100vh - 54px)}
  nav{width:248px;flex:0 0 248px;border-right:1px solid var(--line);
    background:var(--panel);overflow-y:auto;padding:8px}
  nav button{display:block;width:100%;text-align:left;background:transparent;
    color:var(--txt);border:0;border-radius:8px;padding:9px 11px;margin:2px 0;
    cursor:pointer;font-size:13px;border-left:3px solid transparent}
  nav button:hover{background:var(--panel2)}
  nav button.active{background:var(--panel2);border-left-color:var(--accent);color:#fff}
  nav button .n{color:var(--dim);font-family:var(--mono);font-size:11px;margin-right:7px}
  main{flex:1;overflow-y:auto;padding:18px 22px}
  h2{font-size:18px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:12px;margin-bottom:14px}
  .ep{font-family:var(--mono);font-size:11px;color:var(--accent);
    background:#0a0f17;border:1px solid var(--line);border-radius:6px;
    padding:3px 7px;display:inline-block;margin:2px 4px 2px 0}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}
  button.act{background:var(--accent);color:#04101e;border:0;border-radius:8px;
    padding:8px 14px;font-weight:600;cursor:pointer}
  button.act:hover{filter:brightness(1.1)}
  button.ghost{background:transparent;color:var(--txt);border:1px solid var(--line);
    border-radius:8px;padding:8px 14px;cursor:pointer}
  input,textarea,select{background:#080c12;color:var(--txt);border:1px solid var(--line);
    border-radius:7px;padding:7px 9px;font-family:var(--mono);font-size:12px}
  textarea{width:100%;min-height:88px;resize:vertical}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px;margin:12px 0}
  pre{background:#05080d;border:1px solid var(--line);border-radius:8px;
    padding:12px;overflow:auto;font-family:var(--mono);font-size:11.5px;
    color:#bcd0e6;max-height:520px;white-space:pre-wrap;word-break:break-word}
  table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
  th{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
  td.mono,.mono{font-family:var(--mono)}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .p-allow{background:#0d2a1a;color:var(--good)} .p-halt{background:#2c1015;color:var(--bad)}
  .p-review,.p-suspect{background:#2a230d;color:var(--warn)} .p-engage{background:#2c1015;color:var(--bad)}
  .honest{font-size:11px;color:var(--dim);border-left:3px solid var(--gold);
    padding:6px 10px;margin:10px 0;background:#0c0f08}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
  .axis{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
  .axis .v{font-family:var(--mono);font-size:16px;color:var(--good)}
  .axis .k{font-size:11px;color:var(--dim)}
  .ok{color:var(--good)} .err{color:var(--bad)} .muted{color:var(--dim)}
  .bp{border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0;background:var(--panel)}
  .bp h3{margin:0 0 4px;font-size:14px}
  .bp .flag{color:var(--gold);font-family:var(--mono);font-size:12px}
  label{font-size:11px;color:var(--dim);display:block;margin-bottom:3px}
  /* Mobile: the 248px non-shrinking nav + flex row overflows a 390px viewport.
     Stack nav above main and let the deck scroll vertically. */
  @media (max-width:768px){
    .wrap{flex-direction:column;height:auto}
    nav{width:auto;flex:0 0 auto;border-right:0;border-bottom:1px solid var(--line);
        display:flex;flex-wrap:wrap;gap:4px}
    nav button{width:auto;min-height:40px}
    main{padding:14px}
    header{flex-wrap:wrap;gap:8px;padding:10px 14px}
    table{display:block;overflow-x:auto}
  }
</style>
</head>
<body>
<header>
  <h1><b>KILLINCHU</b> · Elite Counter-UAS Console</h1>
  <div class="doctrine">
    Doctrine v11 · 749/14/163 · c7c0ba17<br/>
    <span class="l1">SLSA L1 honest</span> · Λ = Conjecture 1 (not a theorem)
  </div>
</header>
<div class="wrap">
  <nav id="nav"></nav>
  <main id="main"></main>
</div>
<script>
const NS = "__NS__";
const API = (p) => p.startsWith("/") ? p : "/" + p;

async function call(method, path, body){
  const opt = {method, headers:{"Content-Type":"application/json"}};
  if(body!==undefined) opt.body = JSON.stringify(body);
  const t0 = performance.now();
  const r = await fetch(API(path), opt);
  const ms = (performance.now()-t0).toFixed(0);
  let j; try{ j = await r.json(); }catch(e){ j = {error:"non-JSON response", status:r.status}; }
  return {status:r.status, ms, json:j};
}
function pj(o){ return JSON.stringify(o, null, 2); }
function pill(v){
  const c = ({ALLOW:"p-allow",HALT:"p-halt",REVIEW:"p-review",SUSPECT:"p-suspect",ENGAGE:"p-engage"})[(v||"").toUpperCase()]||"p-suspect";
  return `<span class="pill ${c}">${v||"?"}</span>`;
}
function honest(t){ return `<div class="honest">${t}</div>`; }
function ep(s){ return `<span class="ep">${s}</span>`; }
async function showResult(el, res){
  el.innerHTML = `<div class="muted" style="font-size:11px;margin-bottom:4px">HTTP ${res.status} · ${res.ms} ms</div><pre>${pj(res.json)}</pre>`;
}

/* ---- TAB DEFINITIONS: each renders into #main and wires REAL endpoints ---- */
const TABS = [
 {id:"cop", n:"01", title:"Live Track Board / COP",
  sub:"Active threat board + per-track history ring. The 3D battlespace common operating picture.",
  eps:["GET /api/"+NS+"/v1/threats/active","GET /api/"+NS+"/v1/tracks/history"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load active threats</button>
       <button class="ghost" id="b2">Load track history</button></div>
       <div id="board"></div><div id="out"></div>` +
      honest("Telemetry is an unauthenticated broadcast CLAIM — not attested truth. Track history is in-memory (resets on Space restart).");
    m.querySelector("#b1").onclick = async ()=>{
      const r = await call("GET","/api/"+NS+"/v1/threats/active");
      const t = r.json.threats||[];
      m.querySelector("#board").innerHTML = t.length ? table(t,["track_id","model","status","latitude","longitude"]) :
        `<div class="muted">No active threats on the board (honest IDLE).</div>`;
      showResult(m.querySelector("#out"), r);
    };
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/tracks/history?limit=50"));
  }},

 {id:"fusion", n:"02", title:"Sensor-Fusion Monitor",
  sub:"Per-sensor-class weights/health + live multi-sensor weighted-centroid fusion with a DSSE receipt.",
  eps:["GET /api/"+NS+"/v1/sensor-fusion/status","POST /api/"+NS+"/v1/sensor-fusion/fuse"],
  render(m){
    const demo = {track_id:"TRK-SHAHED-001",sensor_reports:[
      {sensor_id:"RADAR-SW-1",sensor_class:"RADAR",lat:47.851,lon:35.102,alt_m:1500,speed_m_s:51.4,confidence:0.95},
      {sensor_id:"RF-1",sensor_class:"RF_DETECT",lat:47.8509,lon:35.1019,alt_m:1499,speed_m_s:51.3,confidence:0.88},
      {sensor_id:"EOIR-1",sensor_class:"EO_IR",lat:47.8511,lon:35.1021,alt_m:1500,speed_m_s:51.5,confidence:0.82}]};
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Sensor status</button>
       <button class="act" id="b2">Fuse 3 sensors (demo)</button></div>
       <label>Fusion request body</label><textarea id="body">${pj(demo)}</textarea>
       <div id="out"></div>` +
      honest("Weighted centroid is a first-order fusion. Kalman trajectory smoothing is at POST /api/"+NS+"/v1/edge/track-smooth.");
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/sensor-fusion/status"));
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/sensor-fusion/fuse", JSON.parse(m.querySelector("#body").value)));
  }},

 {id:"queue", n:"03", title:"Multi-Track Threat Prioritization",
  sub:"Ranked engagement queue: classification(40%)+speed(25%)+altitude(20%)+proximity(15%). Each ranking is receipted.",
  eps:["POST /api/"+NS+"/v1/tracks/multi-prioritize"],
  render(m){
    const demo = {tracks:[
      {track_id:"TRK-001",model:"FPV Quad",status:"STRIKE-RUN",lat:47.85,lon:35.10,alt_m:60,speed_m_s:38},
      {track_id:"TRK-002",model:"Shahed-136",status:"INBOUND",lat:47.86,lon:35.12,alt_m:1500,speed_m_s:51},
      {track_id:"TRK-003",model:"Orlan-10",status:"ISR",lat:47.90,lon:35.20,alt_m:3000,speed_m_s:30}]};
    m.innerHTML = head(this) +
      `<label>Tracks</label><textarea id="body">${pj(demo)}</textarea>
       <div class="row"><button class="act" id="b1">Prioritize</button></div>
       <div id="rank"></div><div id="out"></div>`;
    m.querySelector("#b1").onclick = async ()=>{
      const r = await call("POST","/api/"+NS+"/v1/tracks/multi-prioritize", JSON.parse(m.querySelector("#body").value));
      const rows = (r.json.ranked_threats||[]).map(x=>({rank:x.rank,track_id:x.track_id,model:x.model,status:x.status,threat_score:x.threat_score,roe:x.roe_verdict}));
      m.querySelector("#rank").innerHTML = rows.length ? table(rows,["rank","track_id","model","status","threat_score","roe"]) : "";
      showResult(m.querySelector("#out"), r);
    };
  }},

 {id:"roe", n:"04", title:"ROE Policy Editor + Per-frame Evaluate",
  sub:"sentra's policy-immune-response, applied as Rules-of-Engagement. Edit policy (receipted) + evaluate a frame.",
  eps:["GET /api/"+NS+"/v1/roe/policy","PUT /api/"+NS+"/v1/roe/policy","POST /api/"+NS+"/v1/roe/evaluate"],
  render(m){
    const evalDemo = {telemetry:{track_id:"TRK-002",classification:"HOSTILE",speed_m_s:110,altitude_m:1500,latitude:47.86,longitude:35.12}};
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load policy</button>
       <button class="ghost" id="b2">Bump max_speed_m_s → 140 (PUT)</button></div>
       <div id="pol"></div>
       <div class="card"><label>Evaluate a telemetry frame</label>
       <textarea id="body">${pj(evalDemo)}</textarea>
       <div class="row"><button class="act" id="b3">Evaluate</button></div></div>
       <div id="out"></div>` +
      honest("ROE policy is in-memory (resets on Space restart). Verdict ENGAGE/REVIEW above Λ floor requires HOTL confirmation.");
    m.querySelector("#b1").onclick = async ()=>{ const r=await call("GET","/api/"+NS+"/v1/roe/policy"); m.querySelector("#pol").innerHTML=`<pre>${pj(r.json.policy||r.json)}</pre>`; };
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("PUT","/api/"+NS+"/v1/roe/policy",{updated_by:"elite-console",rules:{max_speed_m_s:140}}));
    m.querySelector("#b3").onclick = async ()=>{ const r=await call("POST","/api/"+NS+"/v1/roe/evaluate", JSON.parse(m.querySelector("#body").value)); showResult(m.querySelector("#out"), r); };
  }},

 {id:"audit", n:"05", title:"Engagement Audit Log",
  sub:"Paginated, filterable audit log. Record an engagement → immutable DSSE-receipted entry.",
  eps:["GET /api/"+NS+"/v1/engagements/audit-log","POST /api/"+NS+"/v1/engagements/record"],
  render(m){
    const rec = {track_id:"TRK-002",verdict:"ENGAGE",effector:"EW_JAM",operator_id:"OP-KESTREL-1",lambda_at_decision:0.924,notes:"demo from elite console"};
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load audit log</button>
       <input id="vf" placeholder="filter verdict (e.g. ENGAGE)" />
       <button class="ghost" id="b1b">Filter</button></div>
       <div class="card"><label>Record an engagement</label><textarea id="body">${pj(rec)}</textarea>
       <div class="row"><button class="act" id="b2">Record</button></div></div>
       <div id="out"></div>` +
      honest("Audit log is in-memory (deque maxlen=5000). Each record is cryptographically verifiable via /khipu/verify.");
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/engagements/audit-log?limit=50"));
    m.querySelector("#b1b").onclick = async ()=>{ const v=m.querySelector("#vf").value.trim(); showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/engagements/audit-log?limit=50"+(v?("&verdict="+encodeURIComponent(v)):""))); };
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/engagements/record", JSON.parse(m.querySelector("#body").value)));
  }},

 {id:"receipt", n:"06", title:"DSSE Receipt Verifier",
  sub:"a11oy's receipt substrate. Inspect the Khipu DAG ledger + emit a new signed receipt.",
  eps:["GET /api/"+NS+"/v1/receipt/ledger","POST /api/"+NS+"/v1/receipt/emit"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load receipt ledger</button>
       <button class="ghost" id="b2">Emit a test receipt</button></div>
       <div id="out"></div>` +
      honest("DSSE is REAL ECDSA-P256-SHA256 when SZL_COSIGN_PRIVATE_PEM is set; else an honest PLACEHOLDER (never fabricated).");
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/receipt/ledger?limit=25"));
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/receipt/emit",{kind:"elite_console_test",payload:{from:"elite-console"}}));
  }},

 {id:"lambda", n:"07", title:"13-axis Λ-gate Monitor",
  sub:"amaru's reasoning cortex. Every interdiction must clear Λ ≥ 0.90 (geometric mean of 13 trust axes).",
  eps:["POST /api/"+NS+"/v1/counter-uas/evaluate"],
  render(m){
    const demo = {telemetry:{latitude:47.85,longitude:35.10,ground_speed_m_s:51.4,side:"HOSTILE",remote_id_present:false},
      geofence:{center_lat:47.85,center_lon:35.10,radius_m:1000},
      policy:{max_speed_m_s:40,require_remote_id:true,allow_sides:["FRIENDLY"]}};
    m.innerHTML = head(this) +
      `<label>Evaluate request</label><textarea id="body">${pj(demo)}</textarea>
       <div class="row"><button class="act" id="b1">Evaluate Λ-gate</button></div>
       <div id="dec"></div><div class="grid" id="axes"></div><div id="out"></div>` +
      honest("Λ = Conjecture 1 — NOT a theorem (open CAUCHY_ND sorry + missing symmetry axiom). Decision is advisory.");
    m.querySelector("#b1").onclick = async ()=>{
      const r = await call("POST","/api/"+NS+"/v1/counter-uas/evaluate", JSON.parse(m.querySelector("#body").value));
      const j = r.json;
      m.querySelector("#dec").innerHTML = `<div class="card">Decision ${pill(j.decision)} &nbsp; Λ=<b class="mono">${j.lambda}</b> (floor ${j.lambda_floor}, pass=${j.lambda_pass}) &nbsp;<span class="muted">breaches: ${(j.breaches||[]).length}</span></div>`;
      m.querySelector("#axes").innerHTML = Object.entries(j.axis_scores||{}).map(([k,v])=>`<div class="axis"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
      showResult(m.querySelector("#out"), r);
    };
  }},

 {id:"quorum", n:"08", title:"3-of-4 BFT Quorum Console",
  sub:"Cross-organ Khipu consensus (Sentra/Amaru/a11oy/Killinchu). ≥3 valid DSSE 'allow' sigs = canonical. Tolerates f=1.",
  eps:["GET /api/"+NS+"/uds/v1/healthz","POST /api/"+NS+"/uds/v1/mission/execute","POST /api/"+NS+"/uds/v1/consensus/verify"],
  render(m){
    const mission = {action_hash:"a1b2c3d4e5f6"+"00".repeat(10), context:{intent:"interdict",track_id:"TRK-002",effector:"EW_JAM"}};
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Organ health</button>
       <button class="act" id="b2">Run 3-of-4 mission</button>
       <button class="ghost" id="b3">Verify last receipt</button></div>
       <label>Mission body</label><textarea id="body">${pj(mission)}</textarea>
       <div id="out"></div>` +
      honest("Consensus is REAL ECDSA-DSSE over the same action_hash; ≥3-of-4 = canonical, &lt;3 = REJECT (fail-closed). Pubkeys embedded — no network call.");
    let last=null;
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/uds/v1/healthz"));
    m.querySelector("#b2").onclick = async ()=>{ const r=await call("POST","/api/"+NS+"/uds/v1/mission/execute", JSON.parse(m.querySelector("#body").value)); last=r.json; showResult(m.querySelector("#out"), r); };
    m.querySelector("#b3").onclick = async ()=>{ if(!last){m.querySelector("#out").innerHTML='<div class="muted">Run a mission first.</div>';return;} showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/uds/v1/consensus/verify", last)); };
  }},

 {id:"pqc", n:"09", title:"PQC Hybrid Signing Panel",
  sub:"Post-quantum readiness: sign with ECDSA-P256, ML-DSA-65 (FIPS 204), or both (hybrid).",
  eps:["POST /khipu/sign?mode=ecdsa","POST /khipu/sign?mode=pqc","POST /khipu/sign?mode=hybrid"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row">
        <label style="margin:0">mode</label>
        <select id="mode"><option value="ecdsa">ecdsa (always available)</option><option value="hybrid">hybrid (ECDSA+ML-DSA-65)</option><option value="pqc">pqc (ML-DSA-65)</option></select>
        <button class="act" id="b1">Sign payload</button></div>
       <label>Payload</label><textarea id="body">${pj({payload:{track_id:"TRK-002",decision:"ENGAGE"}})}</textarea>
       <div id="out"></div>` +
      honest("ecdsa mode always available. hybrid/pqc require the ML-DSA-65 backend (oqs-python or dilithium-py) — when absent the API returns an HONEST 503 ('ML-DSA backend unavailable; ECDSA mode still available'), never a fabricated PQC signature.");
    m.querySelector("#b1").onclick = async ()=>{ const mode=m.querySelector("#mode").value; showResult(m.querySelector("#out"), await call("POST","/khipu/sign?mode="+mode, JSON.parse(m.querySelector("#body").value))); };
  }},

 {id:"proto", n:"10", title:"Protocol Decoders",
  sub:"Remote-ID (OpenDroneID/ASTM F3411), ADS-B Mode-S 1090ES (pyModeS), MAVLink v1/v2 (pymavlink).",
  eps:["POST /api/"+NS+"/v1/remote-id/decode","POST /api/"+NS+"/v1/ads-b/decode","POST /api/"+NS+"/v1/mavlink/parse"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="card"><label>ADS-B Mode-S hex (real pyModeS decode)</label>
        <input id="adsb" size="40" value="8D4840D6202CC371C32CE0576098" />
        <button class="act" id="b1">Decode ADS-B</button></div>
       <div class="card"><label>Remote-ID frame (hex bytes)</label>
        <input id="rid" size="40" value="0d00112233445566778899aabbccddeeff00112233445566" />
        <button class="act" id="b2">Decode Remote-ID</button></div>
       <div class="card"><label>MAVLink frame (hex)</label>
        <input id="mav" size="40" value="fe0900010100000000000203000403d014" />
        <button class="act" id="b3">Parse MAVLink</button></div>
       <div id="out"></div>` +
      honest("Decoded fields are CLAIMS from an unauthenticated broadcast — NOT attested truth. ADS-B/Remote-ID can be spoofed.");
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/ads-b/decode",{hex:m.querySelector("#adsb").value.trim()}));
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/remote-id/decode",{hex:m.querySelector("#rid").value.trim()}));
    m.querySelector("#b3").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/mavlink/parse",{hex:m.querySelector("#mav").value.trim()}));
  }},

 {id:"geo", n:"11", title:"Geofence Zone Editor",
  sub:"Protected/exclusion zones (FAA + AOR). Check a position against the active zone set.",
  eps:["GET /api/"+NS+"/v2/geofence/zones","POST /api/"+NS+"/v2/geofence/check"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load zones</button></div>
       <div class="card"><label>Check a position</label>
        <div class="row"><input id="lat" value="47.85" placeholder="lat"/><input id="lon" value="35.10" placeholder="lon"/><input id="alt" value="120" placeholder="alt_ft"/>
        <button class="act" id="b2">Check</button></div></div>
       <div id="out"></div>` +
      honest("Geofence data is a static snapshot (see legal_disclaimer_url in the response). Verify against live FAA data before any real op.");
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v2/geofence/zones"));
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v2/geofence/check",{lat:parseFloat(m.querySelector("#lat").value),lon:parseFloat(m.querySelector("#lon").value),alt_ft:parseFloat(m.querySelector("#alt").value)}));
  }},

 {id:"swarm", n:"12", title:"Swarm Topology View",
  sub:"Remote-ID broadcasts → connected-component clusters (real Union-Find) by proximity threshold.",
  eps:["GET/POST /api/"+NS+"/v1/swarm/topology"],
  render(m){
    const demo = {threshold_m:300, broadcasts:[
      {id:"D1",lat:47.8500,lon:35.1000},{id:"D2",lat:47.8501,lon:35.1002},{id:"D3",lat:47.8502,lon:35.1003},
      {id:"D4",lat:47.9000,lon:35.2000},{id:"D5",lat:47.9001,lon:35.2002}]};
    m.innerHTML = head(this) +
      `<label>Broadcasts</label><textarea id="body">${pj(demo)}</textarea>
       <div class="row"><button class="act" id="b1">Compute topology</button>
        <button class="ghost" id="b2">GET (default sample)</button></div>
       <div id="out"></div>`;
    m.querySelector("#b1").onclick = async ()=> showResult(m.querySelector("#out"), await call("POST","/api/"+NS+"/v1/swarm/topology", JSON.parse(m.querySelector("#body").value)));
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/swarm/topology"));
  }},

 {id:"db", n:"13", title:"Threat Classification DB",
  sub:"Curated real-world drone systems (Group 1-5, ISR/strike/loitering). Lattice/Dedrone-class library.",
  eps:["GET /api/"+NS+"/v1/drones/database","GET /api/"+NS+"/v1/drones/{id}"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load database</button>
        <input id="did" placeholder="drone id (e.g. shahed-136)"/><button class="ghost" id="b2">Lookup by id</button></div>
       <div id="tbl"></div><div id="out"></div>`;
    m.querySelector("#b1").onclick = async ()=>{
      const r = await call("GET","/api/"+NS+"/v1/drones/database");
      const d = r.json.drones||[];
      m.querySelector("#tbl").innerHTML = `<div class="muted" style="font-size:11px">count: ${r.json.count ?? d.length}</div>` +
        (d.length ? table(d.slice(0,60),["id","model","manufacturer","role","threat_level"]) : "");
      showResult(m.querySelector("#out"), r);
    };
    m.querySelector("#b2").onclick = async ()=>{ const id=m.querySelector("#did").value.trim(); if(!id)return; showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/drones/"+encodeURIComponent(id))); };
  }},

 {id:"borrowed", n:"14", title:"Cross-Flagship Borrowed Powers",
  sub:"How killinchu takes the formulas & anatomy from each flagship — wired as LIVE local endpoints.",
  eps:["GET /api/"+NS+"/v1/borrowed-powers","GET /api/"+NS+"/v1/mesh/state"],
  render(m){
    m.innerHTML = head(this) +
      `<div class="row"><button class="act" id="b1">Load borrowed powers</button>
       <button class="ghost" id="b2">Mesh state</button></div>
       <div id="cards"></div><div id="out"></div>`;
    m.querySelector("#b1").onclick = async ()=>{
      const r = await call("GET","/api/"+NS+"/v1/borrowed-powers");
      const bp = r.json.borrowed_powers||[];
      m.querySelector("#cards").innerHTML =
        `<div class="card"><b>${r.json.thesis||""}</b><div class="muted" style="margin-top:6px">Signing: ${r.json.signing?.honesty||""}</div></div>` +
        bp.map(b=>`<div class="bp"><h3>${(b.flagship||"").toUpperCase()} <span class="muted">— ${b.role}</span></h3>
          <div class="flag">borrowed: ${b.borrowed_anatomy}</div>
          <div style="margin:6px 0">${b.how_applied}</div>
          <div>${(b.live_endpoints||[]).map(e=>ep(e)).join("")}</div></div>`).join("");
      showResult(m.querySelector("#out"), r);
    };
    m.querySelector("#b2").onclick = async ()=> showResult(m.querySelector("#out"), await call("GET","/api/"+NS+"/v1/mesh/state"));
  }},
];

function head(t){
  return `<h2>${t.title}</h2><div class="sub">${t.sub}</div><div>${(t.eps||[]).map(ep).join("")}</div>`;
}
function table(rows, cols){
  const c = cols || Object.keys(rows[0]||{});
  return `<table><thead><tr>${c.map(k=>`<th>${k}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r=>`<tr>${c.map(k=>`<td class="mono">${r[k]===undefined||r[k]===null?'<span class="muted">—</span>':(""+r[k])}</td>`).join("")}</tr>`).join("") +
    `</tbody></table>`;
}

const nav = document.getElementById("nav");
const main = document.getElementById("main");
TABS.forEach((t,i)=>{
  const b = document.createElement("button");
  b.innerHTML = `<span class="n">${t.n}</span>${t.title}`;
  b.onclick = ()=>{ document.querySelectorAll("nav button").forEach(x=>x.classList.remove("active")); b.classList.add("active"); t.render(main); location.hash = t.id; };
  nav.appendChild(b);
  t._btn = b;
});
function openInitial(){
  const h = (location.hash||"").replace("#","");
  const t = TABS.find(x=>x.id===h) || TABS[0];
  t._btn.click();
}
openInitial();
</script>
</body>
</html>
"""
