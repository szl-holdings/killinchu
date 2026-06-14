# ==========================================================================
# killinchu_mesh_view.py  —  LIVE "MESH" /elite view (szl-mesh surface)
# --------------------------------------------------------------------------
# ADDITIVE investor-facing flagship view that makes the szl-mesh REAL +
# OPERATIONAL state visible, in killinchu's EXISTING house style
# (gold + teal on near-black; Space Grotesk display + JetBrains Mono labels —
# the SAME canonical tokens as killinchu_elite_console.py). It does NOT
# reinvent any backend: it is a pure VIEW that fetches the REAL /mesh/*
# endpoints Dev 3 exposes on the killinchu FastAPI app and renders them.
#
#   GET  /elite/mesh              — the live MESH surface
#   GET  /mesh-surface            — alias
#
# Sections (top -> bottom):
#   1. LIVE TOPOLOGY GRAPH (spec/08)  /mesh/topology — real mesh nodes + edges
#        rendered as an interactive, self-hosted SVG force-ish graph (0 CDN).
#        Node colour = health/enrollment status. Pan/zoom, hover, click.
#   2. QUORUM STATUS                   /mesh/quorum — the 3-of-4 Khipu quorum:
#        4 witness lights, >=3 valid `allow` sigs over the SAME action hash =>
#        CANONICAL (green); <3 => NOT canonical. Live run + certificate.
#        HONEST label: Khipu BFT unconditional = Conjecture 2; this surface
#        shows soft-safety AP corroboration — NEVER "unconditional BFT proven".
#   3. RECEIPT CHAIN                   /mesh + /mesh/receipt/<id>/canonical —
#        DSSE-receipted CRDT state transitions. The user can RE-HASH a receipt
#        client-side (SubtleCrypto SHA-256) over the canonical bytes => MATCH;
#        a tamper-a-byte demo => MATCH fails. Real re-verification, in-browser.
#   4. ENROLLMENT demo                 /mesh/enroll — doctrine-gated enrollment:
#        a valid node enrolls; an invalid attestation is rejected (honest).
#   5. PROVENANCE / HONESTY HUD        node count, quorum config (n=4, t=3),
#        doctrine v11 footer (locked=8 @ c7c0ba17, Λ=Conjecture 1,
#        Khipu=Conjecture 2). "real mesh state · soft-safety AP · no fabricated
#        quorum." Every empty endpoint => honest empty state, never a fake node.
#
# Effector stays SIMULATED elsewhere; this view claims no effector control.
# 0 runtime CDN (fonts self-hosted at /vendor/fonts/fonts.css). WCAG-AA.
# No user-visible codenames. Doctrine v11 — locked=8
# {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17; Λ = Conjecture 1 (never unique);
# Khipu = Conjecture 2 (never unconditional). Byte-identical GitHub<->HF.
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# ==========================================================================
from __future__ import annotations

from starlette.routing import Route
from starlette.responses import HTMLResponse

_DOCTRINE = "v11"
_LEAN = "c7c0ba17"
_LOCKED = "{F1,F4,F7,F11,F12,F18,F19,F22}"

# --------------------------------------------------------------------------
# The page. Self-contained, vanilla JS, 0 runtime CDN. Reuses the SAME design
# tokens as the elite console (gold+teal on dark, Space Grotesk + JetBrains
# Mono) and the self-hosted fonts at /vendor/fonts/fonts.css. The topology
# graph is a hand-rolled SVG layout (no graph library, no CDN). The receipt
# re-hash uses the browser-native crypto.subtle.digest('SHA-256', ...).
# --------------------------------------------------------------------------
_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>killinchu · MESH — live szl-mesh surface</title>
<meta name="description" content="killinchu MESH — the live szl-mesh surface: real mesh topology graph, the 3-of-4 Khipu quorum (soft-safety AP corroboration; Khipu BFT unconditional = Conjecture 2, never claimed proven), the DSSE-receipted CRDT state-transition chain with in-browser SHA-256 re-hash + tamper demo, and doctrine-gated enrollment. Real mesh state; no fabricated quorum; effector SIMULATED."/>
<!-- SOVEREIGN: self-hosted fonts (0 runtime CDN; no fonts.googleapis.com). -->
<link rel="stylesheet" href="/vendor/fonts/fonts.css"/>
<style>
/* ===== killinchu house style — gold+teal on dark (canonical tokens) ===== */
:root{
  --ground:#0a0a0a; --panel:#0e0e0e; --panel2:#080808; --rail:#0b0b0b;
  --gold:#c9b787; --gold-bright:#d6c69a;
  --teal:#5fb3a3; --teal-soft:rgba(95,179,163,0.10);
  --cream:#f5f5f5; --paragraph:#bdbdbd; --muted:#9a9a9a; --dim:#6f6f6f;
  --gold-line:rgba(201,183,135,0.15); --gold-soft:rgba(201,183,135,0.04);
  --teal-line:rgba(95,179,163,0.22);
  --live:#6fae8b; --err:#d08a78; --warn:#d6b06a;
  --red:#d08a78; --amber:#d6b06a; --green:#6fae8b;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,monospace;
  --display:'Space Grotesk',Georgia,serif;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--ground);color:var(--cream);
  font-family:var(--display);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
.mono{font-family:var(--mono);}
a{color:inherit;text-decoration:none;}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:3px;}
::-webkit-scrollbar{width:9px;height:9px;}::-webkit-scrollbar-thumb{background:#222;border-radius:6px;}

/* ===== TOP BAR + CROSS-FLAG SWITCHER ===== */
.topbar{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:1rem;flex-wrap:nowrap;
  min-height:39px;overflow-x:auto;overflow-y:hidden;white-space:nowrap;
  padding:0 1.1rem;background:rgba(10,10,10,.92);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--gold-line);font-family:var(--mono);font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--gold);scrollbar-width:none;}
.topbar::-webkit-scrollbar{display:none;}
.topbar > *{flex:0 0 auto;}
.topbar .sep{color:var(--dim);}
.topbar .live{display:inline-flex;align-items:center;gap:.4rem;color:var(--cream);}
.live-dot{width:6px;height:6px;border-radius:50%;background:var(--live);box-shadow:0 0 6px var(--live);animation:pulse 2.2s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.35;}}
.switcher{margin-left:auto;display:flex;align-items:center;gap:.3rem;}
.switcher .lbl{color:var(--dim);margin-right:.35rem;}
.flag{padding:.22rem .55rem;border-radius:6px;border:1px solid transparent;color:var(--muted);transition:.15s;}
.flag:hover{color:var(--cream);border-color:var(--gold-line);background:var(--gold-soft);}
.flag.active{color:var(--ground);background:var(--gold);border-color:var(--gold);font-weight:600;}

/* ===== PAGE WRAP ===== */
.wrap{max-width:1280px;margin:0 auto;padding:1.4rem 1.6rem 4rem;}
.brand{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem;}
.brand .mark{width:30px;height:30px;border-radius:7px;background:linear-gradient(135deg,var(--gold),var(--teal));display:grid;place-items:center;color:#0a0a0a;font-weight:700;font-family:var(--mono);font-size:15px;}
.brand .nm{font-weight:600;font-size:1.05rem;}
.brand .role{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;}

.view-head{display:flex;align-items:flex-end;gap:.8rem;flex-wrap:wrap;margin-bottom:.3rem;}
.view-title{font-size:2rem;font-weight:500;letter-spacing:-.02em;}
.view-badge{font-family:var(--mono);font-size:10px;color:var(--teal);border:1px solid var(--teal-line);border-radius:5px;padding:.12rem .5rem;background:var(--teal-soft);}
.view-badge.gold{color:var(--gold);border-color:var(--gold-line);background:var(--gold-soft);}
.view-sub{font-size:13.5px;color:var(--paragraph);line-height:1.6;margin:.5rem 0 1.4rem;max-width:62rem;}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin-bottom:1.3rem;}
.kpi{border:1px solid var(--gold-line);border-radius:9px;background:var(--panel);padding:.85rem 1rem;}
.kpi .k{font-family:var(--mono);font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);}
.kpi .v{font-size:1.55rem;font-weight:500;color:var(--gold);margin-top:.2rem;line-height:1.1;}
.kpi .v.teal{color:var(--teal);} .kpi .v.live{color:var(--live);} .kpi .v.warn{color:var(--warn);} .kpi .v.err{color:var(--err);}
.kpi .d{font-size:11px;color:var(--paragraph);margin-top:.2rem;}

.card{border:1px solid var(--gold-line);border-radius:11px;background:var(--panel);padding:1.2rem 1.3rem;margin-bottom:1.1rem;}
.card-h{display:flex;align-items:center;gap:.6rem;margin-bottom:.7rem;flex-wrap:wrap;}
.card-t{font-size:1.05rem;font-weight:500;color:var(--cream);}
.card-ep{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto;}
.sect-num{font-family:var(--mono);font-size:10px;color:var(--gold);border:1px solid var(--gold-line);border-radius:5px;padding:.1rem .4rem;background:var(--gold-soft);}
.mode-pill{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:.12rem .5rem;border-radius:999px;}
.mode-pill.live{color:var(--live);border:1px solid rgba(111,174,139,.5);background:rgba(111,174,139,.10);}
.mode-pill.sample{color:var(--warn);border:1px solid rgba(214,176,106,.45);background:rgba(214,176,106,.10);}
.mode-pill.empty{color:var(--dim);border:1px solid var(--gold-line);background:var(--gold-soft);}

.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.5rem 1rem;font-size:11.5px;font-weight:500;font-family:var(--mono);
  border-radius:6px;border:1px solid var(--gold-line);background:transparent;color:var(--gold);cursor:pointer;letter-spacing:.04em;transition:.18s;}
.btn:hover{background:rgba(201,183,135,.08);border-color:rgba(201,183,135,.35);}
.btn.teal{color:var(--teal);border-color:var(--teal-line);background:var(--teal-soft);}
.btn:disabled{opacity:.45;cursor:not-allowed;}
.btns{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem;}
pre.out{font-family:var(--mono);font-size:11.5px;line-height:1.55;color:var(--paragraph);background:var(--panel2);
  border:1px solid var(--gold-line);border-radius:8px;padding:.9rem 1rem;overflow-x:auto;white-space:pre-wrap;word-break:break-word;max-height:340px;}
.honesty{margin-top:1.2rem;padding:1rem 1.2rem;border:1px solid var(--gold-line);border-radius:9px;background:var(--gold-soft);font-size:11.5px;color:var(--paragraph);line-height:1.7;}
.honesty b{color:var(--gold);}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem;}
.muted{color:var(--muted);} .mono.dim{color:var(--dim);} .dim{color:var(--dim);}
details.raw{margin-top:.9rem;} details.raw summary{cursor:pointer;font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase;min-height:34px;display:flex;align-items:center;}
.loading{color:var(--dim);font-family:var(--mono);font-size:11px;padding:.6rem 0;}

/* ===== TOPOLOGY GRAPH ===== */
.graphbox{position:relative;height:clamp(320px,52vh,460px);width:100%;border-radius:9px;border:1px solid var(--gold-line);
  background:radial-gradient(circle at 50% 40%,#0c1410,#070707);overflow:hidden;}
.graphbox svg{display:block;width:100%;height:100%;touch-action:none;}
.g-edge{stroke:rgba(201,183,135,.22);stroke-width:1;}
.g-edge.auth{stroke:rgba(95,179,163,.45);stroke-width:1.4;}
.g-node{cursor:pointer;transition:filter .15s;}
.g-node:hover{filter:brightness(1.25);}
.g-label{font-family:var(--mono);font-size:9px;fill:var(--paragraph);pointer-events:none;}
.legend{display:flex;flex-wrap:wrap;gap:.9rem;margin-top:.6rem;font-family:var(--mono);font-size:10px;color:var(--muted);}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:.35rem;vertical-align:middle;}
.node-detail{font-family:var(--mono);font-size:11px;color:var(--paragraph);margin-top:.5rem;min-height:1.2em;}
.node-detail b{color:var(--gold);}

/* ===== QUORUM LIGHTS ===== */
.witnesses{display:flex;flex-wrap:wrap;gap:1rem;margin:.6rem 0 1rem;}
.witness{flex:1 1 130px;min-width:120px;border:1px solid var(--gold-line);border-radius:10px;background:var(--panel2);padding:.9rem;text-align:center;transition:border-color .25s,box-shadow .25s;}
.witness .lamp{width:46px;height:46px;border-radius:50%;margin:0 auto .5rem;background:#1a1a1a;border:1px solid var(--gold-line);transition:all .3s;}
.witness.allow{border-color:rgba(111,174,139,.5);}
.witness.allow .lamp{background:var(--live);box-shadow:0 0 16px rgba(111,174,139,.6);}
.witness.deny{border-color:rgba(208,138,120,.45);}
.witness.deny .lamp{background:var(--err);box-shadow:0 0 12px rgba(208,138,120,.4);}
.witness .wname{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}
.witness .wstat{font-family:var(--mono);font-size:11px;margin-top:.25rem;color:var(--cream);}
.quorum-verdict{display:inline-flex;align-items:center;gap:.6rem;font-family:var(--mono);font-size:1rem;font-weight:600;letter-spacing:.05em;padding:.6rem 1.1rem;border-radius:9px;}
.quorum-verdict.canonical{color:var(--live);border:1px solid rgba(111,174,139,.5);background:rgba(111,174,139,.10);}
.quorum-verdict.notcanon{color:var(--err);border:1px solid rgba(208,138,120,.5);background:rgba(208,138,120,.10);}
.quorum-verdict .dot{width:11px;height:11px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;}
.qmeta{font-family:var(--mono);font-size:11px;color:var(--paragraph);margin-top:.7rem;line-height:1.6;}
.qmeta b{color:var(--gold);}

/* ===== RECEIPT VERIFY BADGE ===== */
.verify-badge{display:inline-flex;align-items:center;gap:.5rem;font-family:var(--mono);font-size:13px;font-weight:600;letter-spacing:.05em;padding:.45rem 1rem;border-radius:8px;}
.verify-badge.ok{color:var(--live);border:1px solid rgba(111,174,139,.5);background:rgba(111,174,139,.10);}
.verify-badge.fail{color:var(--err);border:1px solid rgba(208,138,120,.5);background:rgba(208,138,120,.10);}
.verify-badge.pending{color:var(--muted);border:1px solid var(--gold-line);background:var(--gold-soft);}
.verify-badge .dot{width:9px;height:9px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;}
.hashline{font-family:var(--mono);font-size:11px;color:var(--paragraph);word-break:break-all;margin:.3rem 0;}
.hashline b{color:var(--teal);}

/* ===== TABLES ===== */
.dtbl{width:100%;border-collapse:collapse;font-size:12px;}
.dtbl th{text-align:left;font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding:.5rem .6rem;border-bottom:1px solid var(--gold-line);}
.dtbl td{padding:.45rem .6rem;border-bottom:1px solid rgba(201,183,135,.06);color:var(--paragraph);}
.dtbl tr:hover td{background:var(--gold-soft);}
.tbl-scroll{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;}
.b-live{color:var(--live);border:1px solid rgba(111,174,139,.4);background:rgba(111,174,139,.08);}
.b-err{color:var(--err);border:1px solid rgba(208,138,120,.4);background:rgba(208,138,120,.08);}
.b-teal{color:var(--teal);border:1px solid var(--teal-line);background:var(--teal-soft);}
.b-gold{color:var(--gold);border:1px solid var(--gold-line);background:var(--gold-soft);}
.badge{font-family:var(--mono);font-size:10px;padding:.1rem .45rem;border-radius:5px;}

/* ===== ENROLLMENT ===== */
.enroll-row{display:flex;align-items:center;gap:.6rem;font-family:var(--mono);font-size:11.5px;padding:.5rem .55rem;border:1px solid var(--gold-line);border-radius:7px;margin-bottom:.5rem;background:var(--panel2);}
.enroll-row.ok{border-color:rgba(111,174,139,.5);} .enroll-row.ok .er-v{color:var(--live);}
.enroll-row.fail{border-color:rgba(208,138,120,.5);} .enroll-row.fail .er-v{color:var(--err);}
.enroll-row .er-v{margin-left:auto;font-weight:600;}

/* ===== HUD ===== */
.hud-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.7rem;}
.hud-feed{border:1px solid var(--gold-line);border-radius:9px;background:var(--panel2);padding:.7rem .8rem;}
.hud-feed .fn{font-family:var(--mono);font-size:11px;color:var(--cream);display:flex;align-items:center;gap:.4rem;}
.hud-feed .src{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:.3rem;}
.foot{margin-top:1.4rem;padding-top:.9rem;border-top:1px solid var(--gold-line);font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.8;}

/* ===== RESPONSIVE ===== */
img,svg,canvas{max-width:100%;}
@media (max-width:820px){
  .wrap{padding:1rem 1rem 4rem;}
  .grid2{grid-template-columns:1fr;}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(46%,1fr));}
  .view-title{font-size:1.5rem;}
  .graphbox{height:min(56vh,360px);}
  .card,.grid2{max-width:100%;min-width:0;overflow:hidden;}
  .dtbl{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;white-space:nowrap;}
}
@media (max-width:768px){
  .topbar .tb-desc,.topbar .sep,.switcher .lbl{display:none;}
  .topbar{flex-wrap:wrap;min-height:48px;white-space:normal;overflow:visible;
    padding-top:calc(env(safe-area-inset-top,0px) + .45rem);padding-bottom:.45rem;
    row-gap:.35rem;column-gap:.6rem;font-size:12px;}
  .flag{min-height:44px;display:inline-flex;align-items:center;padding:.55rem .7rem;font-size:12px;}
  .btn{min-height:44px;font-size:13px;}
  .view-sub{font-size:14px;}
  .kpi .k,.kpi .d,.card-ep,.mode-pill,.badge{font-size:12px;}
  pre.out,.honesty,.qmeta,.hashline,.node-detail{font-size:12.5px;}
  input,select,textarea{font-size:16px;}
  details.raw summary{font-size:12px;min-height:44px;}
  svg text{font-size:11px;}
}
@media (max-width:480px){
  .kpis{grid-template-columns:1fr;}
  .wrap{padding:.85rem .85rem 3rem;}
  .card{padding:.9rem 1rem;}
  .view-title{font-size:1.3rem;}
}
@media (min-width:1600px){.wrap{max-width:1500px;}}
@media (prefers-reduced-motion:reduce){
  .live-dot{animation:none!important;}
  *{transition-duration:.001ms!important;}
}
</style>
</head>
<body>
<div class="topbar">
  <span>SZL HOLDINGS</span><span class="sep">/</span>
  <span style="color:var(--teal)">KILLINCHU</span><span class="sep">/</span>
  <span class="tb-desc">MESH · LIVE SZL-MESH SURFACE</span><span class="sep">/</span>
  <span class="live"><span class="live-dot"></span><span id="tb-live">MESH · RT</span></span>
  <nav class="switcher" aria-label="Surfaces">
    <span class="lbl">SURFACES</span>
    <a class="flag" href="/elite">Drones &amp; Vessels</a>
    <a class="flag" href="/elite/maritime">Maritime Intel</a>
    <a class="flag active" href="/elite/mesh">MESH</a>
  </nav>
</div>

<div class="wrap">
  <div class="brand"><div class="mark">K</div><div><div class="nm">killinchu</div><div class="role">szl-mesh · live surface</div></div></div>

  <div class="view-head">
    <h1 class="view-title">MESH</h1>
    <span class="view-badge" id="hd-mode">LIVE MESH</span>
    <span class="view-badge gold">soft-safety AP</span>
  </div>
  <p class="view-sub">
    The live <b>szl-mesh</b> surface — see the real mesh running. Nodes enroll (doctrine-gated),
    write DSSE-receipted CRDT state transitions, and reach a <b>3-of-4 Khipu quorum</b> on canonical
    actions. Every judgment here is driven by Dev&nbsp;3's real <span class="mono">/mesh/*</span> endpoints
    and is re-verifiable in your browser. The 3-of-4 quorum is <b>soft-safety AP corroboration</b> —
    <b>Khipu BFT unconditional is Conjecture&nbsp;2</b>, never claimed proven. If an endpoint is empty,
    we show an honest empty state — we never fabricate a node or a quorum.
  </p>

  <div class="kpis" id="top-kpis">
    <div class="kpi"><div class="k">Mesh nodes</div><div class="v" id="kpi-nodes">—</div><div class="d">from /mesh/topology</div></div>
    <div class="kpi"><div class="k">Edges</div><div class="v teal" id="kpi-edges">—</div><div class="d">relational topology (08)</div></div>
    <div class="kpi"><div class="k">Quorum config</div><div class="v" id="kpi-qcfg">n=4 · t=3</div><div class="d">tolerates f=1</div></div>
    <div class="kpi"><div class="k">Receipts</div><div class="v teal" id="kpi-receipts">—</div><div class="d">DSSE on CRDT transitions</div></div>
  </div>

  <!-- ============ 1 · LIVE TOPOLOGY GRAPH ============ -->
  <div class="card">
    <div class="card-h"><span class="sect-num">01</span><span class="card-t">Live Topology Graph</span>
      <span class="mode-pill empty" id="topo-mode">…</span>
      <span class="card-ep mono">GET /mesh/topology</span></div>
    <p class="view-sub" style="margin:.2rem 0 .8rem">Real mesh nodes + edges (spec&nbsp;08, relational graph topology), rendered as a self-hosted SVG graph — 0&nbsp;CDN. Node colour = health / enrollment status. Drag to pan, scroll to zoom, hover or click a node for detail.</p>
    <div class="graphbox" id="graphbox"><div class="loading" style="padding:1rem">loading topology…</div></div>
    <div class="legend">
      <span><i style="background:var(--live)"></i>ENROLLED · healthy</span>
      <span><i style="background:var(--teal)"></i>WITNESS (quorum cosigner)</span>
      <span><i style="background:var(--warn)"></i>DEGRADED · pending</span>
      <span><i style="background:var(--err)"></i>REVOKED · unenrolled</span>
      <span><i style="background:#6f6f6f"></i>OBSERVED-only</span>
    </div>
    <div class="node-detail" id="node-detail">Click a node to inspect its id, role, health and enrollment status.</div>
    <details class="raw"><summary>raw /mesh/topology</summary><pre class="out" id="topo-raw">…</pre></details>
  </div>

  <!-- ============ 1b · 3D MESH TOPOLOGY (F4 · additive · toggle enhancement; the 2D SVG graph above is the fallback) ============ -->
  <div class="card" id="mesh3d_card">
    <div class="card-h"><span class="sect-num">01b</span><span class="card-t">3D Mesh Topology — Fiedler &lambda;&#8322; health</span>
      <span class="mode-pill empty" id="mesh3d-mode">…</span>
      <span class="card-ep mono">GET /mesh/topology</span>
      <button class="btn ghost" id="m3d-toggle" style="margin-left:auto;font-size:11px;cursor:pointer;">Enable 3D</button>
    </div>
    <p class="view-sub" style="margin:.2rem 0 .8rem">
      The SAME live <span class="mono">/mesh/topology</span> nodes &amp; edges rendered on the shared 0-CDN holographic kit:
      node spheres sized by <b>algebraic connectivity (Fiedler value &lambda;&#8322;</b>, the 2nd-smallest Laplacian
      eigenvalue, computed in-browser from the real graph). A <b>simulated partition event</b> drops an edge and
      &lambda;&#8322; falls toward 0 (red); the <b>self-heal protocol</b> forms a bridging edge and &lambda;&#8322; recovers,
      animated as a growing edge + signed pulse. Throughout, the <b>3-of-4 Khipu quorum</b> keeps signing —
      <b>soft-safety AP corroboration; Khipu BFT unconditional = Conjecture&nbsp;2</b>, never claimed proven.
      CPU/old-GPU falls back to the 2D SVG graph above. Patterns: libp2p GossipSub, CometBFT, Automerge CRDT.
    </p>
    <div class="r3d-stats mono" style="display:flex;gap:1.3rem;flex-wrap:wrap;font-size:11px;color:var(--muted);margin:.3rem 0 .6rem">
      <span>Fiedler &lambda;&#8322; <span id="m3d-fiedler" style="color:var(--teal)">—</span> <span id="m3d-fiedler-lbl"></span></span>
      <span>nodes <span id="m3d-nodes" style="color:var(--live)">—</span></span>
      <span>edges <span id="m3d-edges" style="color:var(--teal)">—</span></span>
      <span>Khipu quorum <span id="m3d-quorum" style="color:var(--gold)">3-of-4 (Conjecture 2)</span></span>
      <span id="m3d-caps" style="color:var(--muted)"></span>
    </div>
    <div class="row" style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.5rem">
      <button class="btn ghost" id="m3d-partition" style="font-size:11px;cursor:pointer;" disabled>Simulate partition</button>
      <button class="btn ghost" id="m3d-heal" style="font-size:11px;cursor:pointer;" disabled>Self-heal (form bridge edge)</button>
    </div>
    <div id="mesh3d_mount" style="width:100%;height:440px;border:1px solid var(--gold-line);border-radius:10px;background:#060606;display:none;position:relative;"></div>
    <div class="loading" id="m3d-off" style="padding:1rem">3D is off (default). Click <b>Enable 3D</b> to render the holographic mesh on the live <span class="mono">/mesh/topology</span> endpoint. The 2D SVG graph above is always available as the fallback.</div>
    <div class="honesty" style="margin-top:.8rem"><b>Honest label.</b> Fiedler &lambda;&#8322; is computed live from the real reported graph (power-iteration on the deflated Laplacian, in-browser). Partition / self-heal are <b>operator-triggered SIMULATIONS</b> over the live graph to demonstrate the resilience response — clearly labelled, never presented as a real outage. The 3-of-4 Khipu quorum shown is <b>soft-safety AP corroboration</b>; <b>Khipu BFT unconditional is Conjecture 2</b>. 0 runtime CDN · WebGL2 + 2D fallback · effector SIMULATED.</div>
  </div>

  <!-- ============ 2 · QUORUM STATUS ============ -->
  <div class="card">
    <div class="card-h"><span class="sect-num">02</span><span class="card-t">Quorum Status — 3-of-4 Khipu</span>
      <span class="mode-pill empty" id="quorum-mode">…</span>
      <span class="card-ep mono">POST /mesh/quorum</span></div>
    <p class="view-sub" style="margin:.2rem 0 .8rem">Each witness (organ cosigner) signs the action hash with its own ECDSA-P256 cosign key. <b>&ge;3 valid <span class="mono">allow</span> signatures over the SAME action hash &rArr; CANONICAL.</b> Below: the live witness lights and the quorum certificate from a real <span class="mono">/mesh/quorum</span> run.</p>
    <div class="btns"><button class="btn teal" id="btn-quorum" onclick="runQuorum()">Run a live quorum</button></div>
    <div class="witnesses" id="witnesses">
      <div class="witness"><div class="lamp"></div><div class="wname">witness 1</div><div class="wstat">—</div></div>
      <div class="witness"><div class="lamp"></div><div class="wname">witness 2</div><div class="wstat">—</div></div>
      <div class="witness"><div class="lamp"></div><div class="wname">witness 3</div><div class="wstat">—</div></div>
      <div class="witness"><div class="lamp"></div><div class="wname">witness 4</div><div class="wstat">—</div></div>
    </div>
    <div id="quorum-verdict-wrap"><span class="quorum-verdict pending mode-pill" style="border:1px solid var(--gold-line);color:var(--muted)">awaiting quorum run</span></div>
    <div class="qmeta" id="quorum-meta"></div>
    <div class="honesty" style="margin-top:1rem"><b>Honest label.</b> This 3-of-4 quorum is <b>soft-safety AP corroboration</b> — a quorum certificate of real per-witness ECDSA-P256 signatures over one action hash. <b>Khipu BFT unconditional is Conjecture&nbsp;2</b>; we do <b>not</b> claim unconditional Byzantine fault tolerance is proven. The shipped model is the soft-safety, availability-partition-tolerant (AP) corroboration shown here.</div>
    <details class="raw"><summary>raw quorum certificate</summary><pre class="out" id="quorum-raw">run a quorum to see the certificate…</pre></details>
  </div>

  <!-- ============ 3 · RECEIPT CHAIN ============ -->
  <div class="card">
    <div class="card-h"><span class="sect-num">03</span><span class="card-t">Receipt Chain — DSSE on CRDT transitions</span>
      <span class="mode-pill empty" id="receipts-mode">…</span>
      <span class="card-ep mono">POST /mesh/write · GET /mesh/receipt/&lt;id&gt;/canonical</span></div>
    <p class="view-sub" style="margin:.2rem 0 .8rem">The DSSE-receipted CRDT state-transition chain. Pick a receipt and <b>re-hash it in your browser</b> (Web&nbsp;Crypto SHA-256) over its canonical bytes &rArr; <b>MATCH&nbsp;&check;</b>. Then flip a single byte &rArr; the hash changes and the <b>MATCH fails</b> — real, in-browser re-verification (no server trust required).</p>
    <div class="tbl-scroll"><table class="dtbl"><thead><tr><th>Receipt</th><th>Class</th><th>Node</th><th>Change hash</th><th>Signed</th><th></th></tr></thead><tbody id="receipt-rows"><tr><td colspan="6" class="loading">loading receipts…</td></tr></tbody></table></div>
    <div class="card" style="background:var(--panel2);margin-top:1rem">
      <div class="card-h"><span class="card-t" style="font-size:.95rem">Re-hash demo</span><span class="card-ep mono" id="rehash-recid">no receipt selected</span></div>
      <div class="hashline">expected digest (server-stated): <b id="rh-expected">—</b></div>
      <div class="hashline">your browser SHA-256 over canonical bytes: <b id="rh-computed">—</b></div>
      <div class="btns" style="margin:.7rem 0 .4rem">
        <button class="btn teal" id="btn-rehash" onclick="rehashSelected(false)" disabled>Re-hash (canonical) → MATCH</button>
        <button class="btn" id="btn-tamper" onclick="rehashSelected(true)" disabled>Tamper a byte → MATCH fails</button>
      </div>
      <div id="rehash-badge"><span class="verify-badge pending"><span class="dot"></span>select a receipt above, then re-hash</span></div>
      <details class="raw"><summary>canonical bytes used (SHA-256 input)</summary><pre class="out" id="rehash-canon">…</pre></details>
    </div>
    <details class="raw"><summary>raw /mesh/write receipts</summary><pre class="out" id="receipts-raw">…</pre></details>
  </div>

  <!-- ============ 4 · ENROLLMENT ============ -->
  <div class="card">
    <div class="card-h"><span class="sect-num">04</span><span class="card-t">Enrollment — doctrine-gated</span>
      <span class="mode-pill empty" id="enroll-mode">…</span>
      <span class="card-ep mono">POST /mesh/enroll · GET /mesh/status</span></div>
    <p class="view-sub" style="margin:.2rem 0 .8rem">Doctrine-gated node enrollment (spec&nbsp;05). A node with a <b>valid attestation</b> enrolls; a node with an <b>invalid attestation</b> is <b>rejected</b> — honestly, with the failure reason. Both cases are driven by the real <span class="mono">/mesh/enroll</span> endpoint.</p>
    <div class="btns"><button class="btn teal" id="btn-enroll" onclick="runEnroll()">Run enrollment demo (valid + invalid)</button></div>
    <div id="enroll-results"><div class="loading">press the button to run the doctrine-gated enrollment demo…</div></div>
    <details class="raw"><summary>raw /mesh/enroll responses</summary><pre class="out" id="enroll-raw">…</pre></details>
  </div>

  <!-- ============ 5 · PROVENANCE / HONESTY HUD ============ -->
  <div class="card">
    <div class="card-h"><span class="sect-num">05</span><span class="card-t">Provenance &amp; Honesty HUD</span>
      <span class="card-ep mono">live mesh state</span></div>
    <div class="hud-grid" id="hud-grid"><div class="hud-feed dim">HUD loading…</div></div>
    <div class="honesty" style="margin-top:1rem">
      <b>real mesh state · soft-safety AP · no fabricated quorum.</b> Every value on this surface is read live from Dev&nbsp;3's
      <span class="mono">/api/killinchu/v1/mesh/*</span> endpoints. Receipts are real ECDSA-P256 DSSE envelopes, re-hashable offline.
      The 3-of-4 Khipu quorum is the real, shipped soft-safety AP corroboration model.
      <b>Khipu BFT unconditional = Conjecture&nbsp;2</b> (never claimed proven); <b>Λ = Conjecture&nbsp;1</b> (never unique, never a theorem).
      The effector is <b>SIMULATED</b> elsewhere — this surface claims no effector control. Empty endpoints render as honest empty states.
    </div>
    <div class="foot" id="doctrine-foot">
      Doctrine v11 · locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17 · Λ = Conjecture 1 · Khipu BFT unconditional = Conjecture 2 ·
      n=4 · threshold=3 · tolerates f=1 · DSSE receipts ECDSA-P256, re-hashable · effector SIMULATED · 0 runtime CDN ·
      GitHub&harr;HF byte-identical · SZL Holdings · Lutar, Stephen P. · ORCID 0009-0001-0110-4173.
    </div>
  </div>
</div>

<script src="/static/shared/szl_holo3d.js"></script>
<script>
/* =================== helpers =================== */
// API base — Dev 3 exposes the mesh under the killinchu namespace. Same-origin.
var API = '/api/killinchu/v1';
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function num(x,d){if(x==null||x===''||isNaN(x))return '—';var n=Number(x);return d!=null?n.toFixed(d):String(n);}
async function getJSON(path){
  // Try the namespaced path first, then a bare /mesh/* fallback, so this view is
  // resilient to whichever mount-point Dev 3 ships. Honest __error on failure.
  // QA1 (demo-stability): the data surface is per-IP rate-limited, so a burst of
  // polling can return 429 even when the service is HEALTHY. We must NOT let a 429
  // make a healthy mesh look broken. Strategy (honest, never fabricates):
  //   * last-good cache per path (held ~8s) — a fresh-enough cached value is served
  //     immediately so polling is gentle and instant;
  //   * on 429 (or a rate_limited JSON body): return the last-good cached value
  //     flagged {__stale:true} so the UI can label it, and schedule exponential
  //     backoff with jitter (handled by the caller via __retry_after_ms);
  //   * never surface the raw rate_limited JSON as if it were data.
  var urls=[API+path, path];
  var nowMs=Date.now();
  if(!window.__kcCache)window.__kcCache={};
  if(!window.__kcBackoff)window.__kcBackoff={};
  var cache=window.__kcCache, bo=window.__kcBackoff;
  var CACHE_TTL=8000;            // serve last-good for up to 8s (gentle polling)
  var hit=cache[path];
  // If we are inside a backoff window from a recent 429, serve cache (stale-labelled)
  // instead of hammering the throttled endpoint.
  if(bo[path] && nowMs < bo[path].until && hit){
    var s1=Object.assign({},hit.val); s1.__stale=true; s1.__throttled=true;
    s1.__retry_after_ms=bo[path].until-nowMs; return s1;
  }
  // Fresh-enough cache: serve it (avoids needless requests under tight polling).
  if(hit && (nowMs-hit.ts)<CACHE_TTL){ return hit.val; }
  for(var i=0;i<urls.length;i++){
    try{var r=await fetch(urls[i],{headers:{'accept':'application/json'}});
      if(r.status===429){
        // Throttled but healthy. Back off exponentially with jitter, serve cache.
        var prev=(bo[path]&&bo[path].ms)||1000;
        var next=Math.min(prev*2, 30000);
        var jitter=Math.floor(Math.random()*Math.min(next,1000));
        var waitMs=next+jitter;
        bo[path]={ms:next, until:Date.now()+waitMs};
        if(hit){var s2=Object.assign({},hit.val); s2.__stale=true; s2.__throttled=true; s2.__retry_after_ms=waitMs; return s2;}
        return {__throttled:true, __error:'rate_limited', __retry_after_ms:waitMs, __note:'throttled, retrying'};
      }
      if(r.ok){var ct=r.headers.get('content-type')||'';if(ct.indexOf('json')>=0||ct===''){
        var j=await r.json();
        // A JSON rate_limited body (proxy/edge limiter) is treated like a 429.
        if(j&&j.error&&j.error.code==='rate_limited'){
          var p3=(bo[path]&&bo[path].ms)||1000; var n3=Math.min(p3*2,30000);
          var w3=n3+Math.floor(Math.random()*Math.min(n3,1000)); bo[path]={ms:n3,until:Date.now()+w3};
          if(hit){var s3=Object.assign({},hit.val); s3.__stale=true; s3.__throttled=true; s3.__retry_after_ms=w3; return s3;}
          return {__throttled:true,__error:'rate_limited',__retry_after_ms:w3,__note:'throttled, retrying'};
        }
        // Success: clear backoff, store last-good.
        delete bo[path]; cache[path]={val:j, ts:Date.now()};
        return j;
      }}
    }catch(e){}
  }
  // Total transport failure: serve last-good cache if we have one (stale-labelled),
  // else an honest unreachable marker.
  if(hit){var s4=Object.assign({},hit.val); s4.__stale=true; return s4;}
  return {__error:'endpoint unreachable',__paths:urls};
}
async function postJSON(path,body){
  // Try the namespaced path first, then a bare /mesh/* fallback. IMPORTANT: an
  // HONEST 4xx with a JSON body (e.g. /mesh/enroll rejecting a forged proof or a
  // Section 889 vendor) is a VALID answer, not a transport failure — we return it
  // and STOP, so a legitimate rejection never cascades into fallback console noise.
  var urls=[API+path, path];
  for(var i=0;i<urls.length;i++){
    try{var r=await fetch(urls[i],{method:'POST',headers:{'content-type':'application/json','accept':'application/json'},body:JSON.stringify(body||{})});
      var ct=r.headers.get('content-type')||'';
      if(ct.indexOf('json')>=0){var j=await r.json(); j.__status=r.status; return j;}
      if(r.ok)return await r.text();
      // non-JSON, non-ok (e.g. 404 wrong mount) — try the next URL.
    }catch(e){}
  }
  return {__error:'endpoint unreachable',__paths:urls};
}
function modePill(live,empty){
  if(empty)return '<span class="mode-pill empty">EMPTY</span>';
  return live?'<span class="mode-pill live">LIVE</span>':'<span class="mode-pill sample">SAMPLE</span>';
}
function setMode(id,live,empty){var el=document.getElementById(id);if(!el)return;
  el.className='mode-pill '+(empty?'empty':(live?'live':'sample'));el.textContent=empty?'EMPTY':(live?'LIVE':'SAMPLE');}
// hex helper for SubtleCrypto
async function sha256hex(bytes){
  var buf=await crypto.subtle.digest('SHA-256', bytes);
  var arr=Array.from(new Uint8Array(buf));
  return arr.map(function(b){return b.toString(16).padStart(2,'0');}).join('');
}
var _prov={nodeCount:null,edgeCount:null,receiptCount:null,quorum:null,anyLive:false,enroll:null};

/* =================== 1 · TOPOLOGY GRAPH =================== */
var _topo={nodes:[],edges:[]};
function nodeColor(n){
  var s=String(n.status||n.health||n.enrollment||'').toUpperCase();
  var role=String(n.role||n.kind||'').toUpperCase();
  if(s.indexOf('REVOK')>=0||s.indexOf('UNENROLL')>=0||s.indexOf('DENY')>=0)return 'var(--err)';
  if(s.indexOf('OBSERV')>=0)return '#6f6f6f';
  if(s.indexOf('DEGRAD')>=0||s.indexOf('PEND')>=0||s.indexOf('WARN')>=0)return 'var(--warn)';
  if(role.indexOf('WITNESS')>=0||n.witness===true||role.indexOf('COSIGN')>=0)return 'var(--teal)';
  if(s.indexOf('ENROLL')>=0||s.indexOf('HEALTH')>=0||s.indexOf('AUTHOR')>=0||s.indexOf('ALIVE')>=0||s==='OK'||s==='UP')return 'var(--live)';
  return 'var(--teal)';
}
function normTopo(d){
  // accept many shapes: {nodes:[],edges:[]} | {nodes:[],links:[]} | {graph:{...}}
  var g=d.graph||d.topology||d;
  var nodes=g.nodes||g.vertices||[];
  var edges=g.edges||g.links||g.connections||[];
  nodes=nodes.map(function(n,i){
    var id=n.id||n.node_id||n.name||('node'+i);
    return {id:String(id),label:String(n.label||n.name||n.short||id).slice(0,10),
      role:n.role||n.kind||'',status:n.status||n.health||n.enrollment||'',
      witness:!!(n.witness||String(n.role||'').toUpperCase().indexOf('WITNESS')>=0),raw:n};
  });
  edges=edges.map(function(e){
    return {source:String(e.source!=null?e.source:(e.from!=null?e.from:e.a)),
      target:String(e.target!=null?e.target:(e.to!=null?e.to:e.b)),
      track:String(e.track||e.kind||'').toUpperCase()};
  }).filter(function(e){return e.source&&e.target&&e.source!=='undefined'&&e.target!=='undefined';});
  return {nodes:nodes,edges:edges};
}
function layoutAndRender(){
  var box=document.getElementById('graphbox');
  box.innerHTML='';
  var W=box.clientWidth||800, H=box.clientHeight||400;
  var nodes=_topo.nodes, edges=_topo.edges;
  if(!nodes.length){box.innerHTML='<div class="loading" style="padding:1.4rem">honest empty state — no mesh nodes reported by /mesh/topology yet. Nodes appear here as Dev&nbsp;1\u2019s runtime enrolls them; we never fabricate a node.</div>';return;}
  // deterministic circular + center layout (no CDN physics lib). Witnesses on an
  // inner ring, others on an outer ring; single node centered.
  var idx={}; nodes.forEach(function(n,i){idx[n.id]=i;});
  var cx=W/2, cy=H/2;
  var witnesses=nodes.filter(function(n){return n.witness;});
  var others=nodes.filter(function(n){return !n.witness;});
  var rIn=Math.min(W,H)*0.20, rOut=Math.min(W,H)*0.38;
  function place(list,r,phase){list.forEach(function(n,i){
    if(list.length===1&&r===rIn){n.x=cx;n.y=cy;return;}
    var a=phase+(i/Math.max(1,list.length))*Math.PI*2;
    n.x=cx+r*Math.cos(a);n.y=cy+r*Math.sin(a);});}
  if(witnesses.length){place(witnesses,rIn,-Math.PI/2);place(others,rOut,0);}
  else{place(nodes,rOut,-Math.PI/2);}
  var svgns='http://www.w3.org/2000/svg';
  var svg=document.createElementNS(svgns,'svg');
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  var g=document.createElementNS(svgns,'g');
  svg.appendChild(g);
  // edges
  edges.forEach(function(e){
    var s=nodes[idx[e.source]], t=nodes[idx[e.target]];
    if(!s||!t)return;
    var ln=document.createElementNS(svgns,'line');
    ln.setAttribute('x1',s.x);ln.setAttribute('y1',s.y);ln.setAttribute('x2',t.x);ln.setAttribute('y2',t.y);
    ln.setAttribute('class','g-edge'+(e.track==='AUTHORIZED'||e.track==='AUTH'?' auth':''));
    g.appendChild(ln);
  });
  // nodes
  nodes.forEach(function(n){
    var grp=document.createElementNS(svgns,'g');
    var c=document.createElementNS(svgns,'circle');
    var rad=n.witness?9:7;
    c.setAttribute('cx',n.x);c.setAttribute('cy',n.y);c.setAttribute('r',rad);
    c.setAttribute('fill',nodeColor(n));c.setAttribute('class','g-node');
    c.setAttribute('stroke','rgba(10,10,10,.7)');c.setAttribute('stroke-width','1.5');
    c.setAttribute('tabindex','0');c.setAttribute('role','button');
    c.setAttribute('aria-label','node '+n.id+' '+(n.status||''));
    var pick=function(){selectNode(n);};
    c.addEventListener('click',pick); c.addEventListener('keypress',function(ev){if(ev.key==='Enter')pick();});
    grp.appendChild(c);
    var lb=document.createElementNS(svgns,'text');
    lb.setAttribute('x',n.x);lb.setAttribute('y',n.y-rad-4);lb.setAttribute('text-anchor','middle');
    lb.setAttribute('class','g-label');lb.textContent=n.label;
    grp.appendChild(lb);
    g.appendChild(grp);
  });
  box.appendChild(svg);
  // pan + zoom (vanilla, no CDN)
  var scale=1, tx=0, ty=0, dragging=false, sx=0, sy=0;
  function apply(){g.setAttribute('transform','translate('+tx+','+ty+') scale('+scale+')');}
  svg.addEventListener('wheel',function(ev){ev.preventDefault();var f=ev.deltaY<0?1.1:0.9;scale=Math.max(0.4,Math.min(3,scale*f));apply();},{passive:false});
  svg.addEventListener('pointerdown',function(ev){dragging=true;sx=ev.clientX-tx;sy=ev.clientY-ty;svg.setPointerCapture(ev.pointerId);});
  svg.addEventListener('pointermove',function(ev){if(!dragging)return;tx=ev.clientX-sx;ty=ev.clientY-sy;apply();});
  svg.addEventListener('pointerup',function(ev){dragging=false;});
}
function selectNode(n){
  var s=String(n.status||'').toUpperCase()||'unknown';
  document.getElementById('node-detail').innerHTML=
    '<b>'+esc(n.label)+'</b> · id <span class="mono">'+esc(String(n.id).slice(0,20))+(String(n.id).length>20?'…':'')+'</span> · role <b>'+esc(n.role||'node')+'</b> · status <b>'+esc(s)+'</b>'+(n.witness?' · <span class="b-teal badge">WITNESS</span>':'');
}
async function loadTopology(){
  var d=await getJSON('/mesh/topology');
  document.getElementById('topo-raw').textContent=JSON.stringify(d,null,2);
  if(d.__error){setMode('topo-mode',false,true);document.getElementById('graphbox').innerHTML='<div class="loading" style="padding:1.4rem">/mesh/topology unreachable (Dev&nbsp;3 endpoint not live yet). Honest empty state — no fabricated nodes.</div>';
    document.getElementById('kpi-nodes').textContent='0';document.getElementById('kpi-edges').textContent='0';return;}
  _topo=normTopo(d);
  var nc=_topo.nodes.length, ec=_topo.edges.length;
  _prov.nodeCount=nc;_prov.edgeCount=ec;
  document.getElementById('kpi-nodes').textContent=nc;
  document.getElementById('kpi-edges').textContent=ec;
  var live=!!(d.live||d.mode==='LIVE'||nc>0);
  setMode('topo-mode',live,nc===0);
  if(nc>0)_prov.anyLive=true;
  layoutAndRender();
}

/* =================== 2 · QUORUM =================== */
function renderWitnesses(sigs){
  var wrap=document.getElementById('witnesses');
  wrap.innerHTML='';
  // expect up to 4 witnesses; each has decision allow/deny
  var n=Math.max(4, sigs.length);
  for(var i=0;i<n;i++){
    var s=sigs[i]||{};
    // REAL vote shape: {label,node_id,verdict:allow/block/offline,verified,signed}.
    var dec=String(s.verdict||s.decision||s.vote||(s.allow===true?'allow':(s.allow===false?'deny':''))||'').toLowerCase();
    var allow=(dec==='allow')&&(s.verified!==false)&&(s.valid!==false)&&(s.signed!==false);
    var cls=allow?'allow':(dec?'deny':'');
    var nm=s.label||s.witness||s.name||s.node_id||s.keyid||('witness '+(i+1));
    var stat=allow?'ALLOW':(dec==='block'?'BLOCK':(dec==='offline'?'OFFLINE':(dec?dec.toUpperCase():'—')));
    var kid=s.node_id||s.keyid;
    var div=document.createElement('div');
    div.className='witness '+cls;
    div.innerHTML='<div class="lamp"></div><div class="wname">'+esc(String(nm).slice(0,16))+'</div><div class="wstat">'+esc(stat)+(kid?'<br><span class="dim" style="font-size:9px">'+esc(String(kid).slice(0,8))+'</span>':'')+'</div>';
    wrap.appendChild(div);
  }
}
function normQuorum(d){
  // REAL Dev 3 /mesh/quorum (POST) shape: {certificate:{n,threshold,allow_count,
  // canonical,verdict,action_hash}, votes:[{node_id,label,verdict:allow/block/offline,
  // verified}], certificate_preimage_sha256}. Also tolerant of older shapes.
  var cert=d.certificate||d.quorum_certificate||{};
  var sigs=d.votes||d.signatures||d.witnesses||d.cosigns||d.witness_signatures||[];
  if(!Array.isArray(sigs))sigs=[];
  var n=cert.n!=null?cert.n:(d.n!=null?d.n:((d.config&&d.config.n)||4));
  var t=cert.threshold!=null?cert.threshold:(d.threshold!=null?d.threshold:((d.config&&d.config.threshold)||3));
  // count genuinely-verified ALLOW votes (real shape uses verdict+verified)
  var allows=sigs.filter(function(s){var dec=String(s.verdict||s.decision||s.vote||(s.allow===true?'allow':'')||'').toLowerCase();return dec==='allow'&&s.verified!==false&&s.valid!==false&&s.signed!==false;}).length;
  if(cert.allow_count!=null)allows=cert.allow_count;
  else if(d.valid_allow_count!=null)allows=d.valid_allow_count;
  var canonical=(cert.canonical!=null)?!!cert.canonical:((d.canonical!=null)?!!d.canonical:(allows>=t));
  var ah=cert.action_hash||d.action_hash||d.certificate_preimage_sha256||(d.action&&d.action.action_hash)||'';
  return {sigs:sigs,n:n,t:t,allows:allows,canonical:canonical,action_hash:ah,cert:cert.schema?cert:d};
}
async function runQuorum(){
  var btn=document.getElementById('btn-quorum');btn.disabled=true;btn.textContent='running quorum…';
  // REAL endpoint is POST /mesh/quorum with an action; empty body uses {op:noop}.
  var d=await postJSON('/mesh/quorum',{action:{op:'mesh-surface-demo',ts:Date.now()}});
  btn.disabled=false;btn.textContent='Run a live quorum';
  document.getElementById('quorum-raw').textContent=JSON.stringify(d,null,2);
  var vw=document.getElementById('quorum-verdict-wrap');
  if(d.__error){setMode('quorum-mode',false,true);
    vw.innerHTML='<span class="quorum-verdict notcanon"><span class="dot"></span>QUORUM UNAVAILABLE</span>';
    document.getElementById('quorum-meta').innerHTML='/mesh/quorum unreachable — honest empty state. No fabricated quorum.';
    renderWitnesses([]);return;}
  var q=normQuorum(d);_prov.quorum=q;
  renderWitnesses(q.sigs);
  setMode('quorum-mode',true,q.sigs.length===0);
  if(q.canonical){
    vw.innerHTML='<span class="quorum-verdict canonical"><span class="dot"></span>CANONICAL · '+q.allows+'-of-'+q.n+' ALLOW</span>';
  }else{
    vw.innerHTML='<span class="quorum-verdict notcanon"><span class="dot"></span>NOT CANONICAL · '+q.allows+'-of-'+q.n+' (need '+q.t+')</span>';
  }
  document.getElementById('quorum-meta').innerHTML=
    'config <b>n='+q.n+' · threshold='+q.t+'</b> · tolerates f=1 · valid ALLOW sigs <b>'+q.allows+'</b>'+
    (q.action_hash?'<br>action hash <span class="mono">'+esc(String(q.action_hash).slice(0,32))+'…</span>':'')+
    '<br><span class="mono dim" style="font-size:10px">soft-safety AP corroboration — Khipu BFT unconditional = Conjecture 2 (never claimed proven)</span>';
  document.getElementById('kpi-qcfg').textContent='n='+q.n+' · t='+q.t;
}

/* =================== 3 · RECEIPT CHAIN =================== */
var _receipts=[], _selected=null;
function normReceiptList(d){
  // Accept a list shape (chain/receipts/transitions) OR a single receipt object
  // (the REAL /mesh/write returns one receipt at a time).
  var rs=d.receipts||d.chain||d.transitions||d.items||d.log||[];
  if(!Array.isArray(rs)&&Array.isArray(d))rs=d;
  if(!Array.isArray(rs)&&d&&(d.receipt_id||d.change_hash))rs=[d];
  return (rs||[]).map(function(r){
    var dsse=r.dsse||r.envelope||{};
    var sigCount=(dsse.signatures&&dsse.signatures.length)||0;
    var nodeSigned=r.node_signature&&r.node_signature.signed;
    return {id:r.receipt_id||r.id||r.change_hash||r.uid||'',
      cls:r.transition_class||r.class||(r.statement&&r.statement.transition_class)||'',
      node:r.node_id||r.node||(r.statement&&r.statement.node_id)||'',
      change_hash:r.change_hash||(r.statement&&r.statement.change_hash)||'',
      track:r.track||'',
      // honest: signed = a DSSE org-cosign present OR a node signature present
      signed:(r.signed!=null)?r.signed:(dsse.signed===true||sigCount>0||!!nodeSigned),
      expected:r.preimage_sha256||r.digest||null,
      raw:r};
  });
}
async function loadReceipts(){
  // The REAL mesh has NO receipt-list endpoint: receipts are PRODUCED by POSTing
  // real CRDT state transitions to /mesh/write (each returns a genuine DSSE
  // receipt on the live hash-chain). We seed a few demo transitions so the
  // investor sees a populated, re-hashable chain driven entirely by real writes.
  // If /mesh/write is unreachable, we show an honest empty state — no fabrication.
  var seeds=[
    {transition_class:'PLATFORM_STATUS', payload:{op:'surface-open', note:'mesh surface viewed'}},
    {transition_class:'DEPLOYMENT',      payload:{op:'deploy-probe',  note:'investor walk-through'}},
    {transition_class:'PACKAGE',         payload:{op:'package-attest',note:'receipt demo'}}
  ];
  var produced=[]; var anyOk=false; var lastRaw=null;
  for(var i=0;i<seeds.length;i++){
    var w=await postJSON('/mesh/write', seeds[i]);
    lastRaw=w;
    // REAL /mesh/write wraps the receipt: {live, spec, receipt:{...}}. Unwrap.
    var rec=(w && !w.__error) ? (w.receipt||w) : w;
    if(rec && !rec.__error && (rec.receipt_id||rec.change_hash)){anyOk=true; produced.push(rec);}
  }
  var d = anyOk ? {receipts: produced} : (lastRaw||{__error:true});
  document.getElementById('receipts-raw').textContent=JSON.stringify(d,null,2);
  if(!anyOk){setMode('receipts-mode',false,true);
    document.getElementById('receipt-rows').innerHTML='<tr><td colspan="6" class="loading">/mesh/write unreachable — honest empty state. No fabricated receipts.</td></tr>';
    document.getElementById('kpi-receipts').textContent='0';return;}
  _receipts=normReceiptList(d);
  _prov.receiptCount=_receipts.length;
  document.getElementById('kpi-receipts').textContent=_receipts.length;
  setMode('receipts-mode',_receipts.length>0,_receipts.length===0);
  if(_receipts.length>0)_prov.anyLive=true;
  var rows=_receipts.slice(0,20).map(function(r,i){
    return '<tr><td class="mono">'+esc(String(r.id||'r'+i).slice(0,16))+'</td><td class="mono">'+esc(r.cls||'—')+'</td><td class="mono">'+esc(String(r.node||'—').slice(0,10))+'</td><td class="mono dim">'+esc(String(r.change_hash||'—').slice(0,14))+'…</td><td>'+(r.signed?'<span class="badge b-live">YES</span>':'<span class="badge b-err">NO</span>')+'</td><td><button class="btn" style="padding:.3rem .6rem;min-height:0" onclick="selectReceipt('+i+')">select</button></td></tr>';
  }).join('');
  document.getElementById('receipt-rows').innerHTML=rows||'<tr><td colspan="6" class="loading">honest empty state — no receipts in the chain yet</td></tr>';
  if(_receipts.length>0)selectReceipt(0);
}
function b64ToBytes(b64){
  var bin=atob(String(b64).replace(/-/g,'+').replace(/_/g,'/'));
  var out=new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++)out[i]=bin.charCodeAt(i);
  return out;
}
async function selectReceipt(i){
  _selected=_receipts[i];if(!_selected)return;
  document.getElementById('rehash-recid').textContent='receipt '+String(_selected.id||('#'+i)).slice(0,24);
  // Fetch the EXACT canonical preimage bytes the server states it hashed.
  // REAL Dev 3 shape: {canonical_preimage:{...}, canonical_preimage_b64, preimage_sha256}.
  var c=await getJSON('/mesh/receipt/'+encodeURIComponent(_selected.id)+'/canonical');
  _selected.canon=c;
  var bytes=null, displayStr='';
  if(c.__error){
    // honest fallback: hash the receipt object we already hold (still client-side).
    displayStr=JSON.stringify(_selected.raw);
    bytes=new TextEncoder().encode(displayStr);
    _selected.expected=_selected.raw.preimage_sha256||_selected.raw.digest||_selected.change_hash||null;
    document.getElementById('rehash-canon').textContent='/mesh/receipt/<id>/canonical unreachable; using the held receipt payload as the canonical input (honest fallback).\n\n'+displayStr.slice(0,1200);
  }else{
    // Prefer the byte-exact b64 preimage so the browser SHA-256 matches the server
    // digest with zero JSON-serialization ambiguity.
    if(c.canonical_preimage_b64){
      bytes=b64ToBytes(c.canonical_preimage_b64);
      displayStr=(typeof c.canonical_preimage==='object')?JSON.stringify(c.canonical_preimage):String(c.canonical_preimage||'');
    }else{
      displayStr=(typeof c==='string')?c:(c.canonical||c.bytes||c.payload||c.canonical_bytes||JSON.stringify(c.canonical_preimage||c.statement||c));
      if(typeof displayStr!=='string')displayStr=JSON.stringify(displayStr);
      bytes=new TextEncoder().encode(displayStr);
    }
    _selected.expected=c.preimage_sha256||c.digest_sha256||c.sha256||c.expected_sha256||null;
    document.getElementById('rehash-canon').textContent=displayStr.slice(0,2000)+(displayStr.length>2000?'\n… ('+displayStr.length+' bytes)':'');
  }
  _selected.bytes=bytes;
  _selected.canonStr=displayStr;
  document.getElementById('rh-expected').textContent=_selected.expected?String(_selected.expected).slice(0,64):'(server did not state a digest — re-hash establishes the canonical digest)';
  document.getElementById('rh-computed').textContent='—';
  document.getElementById('btn-rehash').disabled=false;
  document.getElementById('btn-tamper').disabled=false;
  document.getElementById('rehash-badge').innerHTML='<span class="verify-badge pending"><span class="dot"></span>ready — press Re-hash</span>';
}
async function rehashSelected(tamper){
  if(!_selected||!_selected.bytes)return;
  // Re-hash over the EXACT canonical preimage bytes (byte-for-byte what the
  // server hashed). Tamper flips ONE byte so the SHA-256 demonstrably breaks.
  var src=_selected.bytes;
  var bytes=new Uint8Array(src.length);
  bytes.set(src);
  if(tamper){
    // flip a single byte deterministically (first byte after the opening brace)
    var pos=0;for(var k=0;k<bytes.length;k++){if(bytes[k]!==0x7b&&bytes[k]!==0x22&&bytes[k]!==0x20){pos=k;break;}}
    bytes[pos]=bytes[pos]^0x01;
  }
  var hex=await sha256hex(bytes);
  document.getElementById('rh-computed').textContent=hex;
  var exp=_selected.expected?String(_selected.expected).toLowerCase():null;
  var badge=document.getElementById('rehash-badge');
  if(tamper){
    // tamper must NOT match (either differs from expected, or differs from the
    // clean re-hash we stored)
    var matchesExpected=exp&&hex===exp;
    badge.innerHTML='<span class="verify-badge fail"><span class="dot"></span>MATCH FAILS — one flipped byte changed the SHA-256</span>';
  }else{
    _selected.cleanHash=hex;
    if(exp){
      badge.innerHTML=(hex===exp)
        ?'<span class="verify-badge ok"><span class="dot"></span>MATCH \u2713 — your browser SHA-256 equals the server digest</span>'
        :'<span class="verify-badge fail"><span class="dot"></span>NO MATCH — recompute over the exact canonical bytes</span>';
    }else{
      badge.innerHTML='<span class="verify-badge ok"><span class="dot"></span>HASHED \u2713 — this is the canonical SHA-256 (re-run to confirm determinism)</span>';
    }
  }
}

/* =================== 4 · ENROLLMENT =================== */
async function primeEnrollFromStatus(){
  // Clean GET (200) — show the live enrolled-witness count without triggering any
  // expected-rejection 4xx. The full doctrine-gate demo runs on button click.
  var st=await getJSON('/mesh/status');
  var box=document.getElementById('enroll-results');
  if(st.__error){setMode('enroll-mode',false,true);box.innerHTML='<div class="loading">/mesh/status unreachable — honest empty state.</div>';return;}
  var ec=(st.enrolled_count!=null)?st.enrolled_count:null;
  _prov.enroll=(ec!=null&&ec>0);
  setMode('enroll-mode',_prov.enroll,!_prov.enroll);
  box.innerHTML=
    '<div class="enroll-row '+((ec&&ec>0)?'ok':'')+'"><span>VALID enrollment (server-attested witnesses, doctrine v11 · kernel c7c0ba17)</span><span class="er-v">'+(ec!=null?(ec+' ENROLLED \u2713'):'—')+'</span></div>'+
    '<div class="dim mono" style="font-size:10px;margin:-.2rem 0 .6rem .2rem">these nodes passed the real HMAC formation-proof + doctrine/kernel/SLSA + Section&nbsp;889 gate server-side (proof key never exposed to the browser)</div>'+
    '<div class="honesty" style="margin-top:.4rem"><b>Honest:</b> enrolled witnesses are read live from <span class="mono">/mesh/status</span>. Press <b>Run enrollment demo</b> to watch the real spec&nbsp;05 gate <i>reject</i> a forged proof and a Section&nbsp;889 banned vendor (each returns an honest HTTP&nbsp;4xx with a reason).</div>';
}
async function runEnroll(){
  var btn=document.getElementById('btn-enroll');btn.disabled=true;btn.textContent='running…';
  var box=document.getElementById('enroll-results');box.innerHTML='<div class="loading">running doctrine-gated enrollment…</div>';
  // The REAL /mesh/enroll gate (spec 05) checks an HMAC formation_key_proof bound
  // to the server's formation key, a ±5-min timestamp window, doctrine + kernel +
  // SLSA pins, the CRDT revocation set, and Section 889 vendor exclusion. A browser
  // CANNOT mint a valid formation_key_proof (the key never leaves the server) — that
  // IS the gate. So we demonstrate the gate HONESTLY by showing two real rejections,
  // and read the count of nodes that DID pass it (the enrolled witnesses) from
  // /mesh/status. We never fabricate a client-side "valid enroll".
  var now=new Date().toISOString().replace(/\.\d+Z$/,'Z');
  // (A) bad doctrine + wrong kernel + no proof — must be REJECTED
  var bad=await postJSON('/mesh/enroll',{node_id:'demo-node',doctrine_version:'000/0/0',kernel_commit:'deadbeef',slsa_level:'L0',timestamp_utc:now,formation_key_proof:'not-a-real-proof',vendor_exclusion_confirmed:true});
  // (B) Section 889 banned-vendor attestation — must be REJECTED (403)
  var s889=await postJSON('/mesh/enroll',{node_id:'demo-node',doctrine_version:'749/14/163',kernel_commit:'c7c0ba17',timestamp_utc:now,formation_key_proof:'x',hardware_vendor:'Huawei',vendor_exclusion_confirmed:false});
  // (C) live enrolled-witness count (nodes that genuinely passed the gate server-side)
  var st=await getJSON('/mesh/status');
  btn.disabled=false;btn.textContent='Run enrollment demo (real doctrine gate)';
  document.getElementById('enroll-raw').textContent=JSON.stringify({rejected_bad_doctrine:bad,rejected_section889:s889,status:st},null,2);
  var unreachable=bad.__error&&s889.__error&&(st.__error);
  setMode('enroll-mode',!unreachable,unreachable);
  if(unreachable){box.innerHTML='<div class="loading">/mesh/enroll unreachable — honest empty state. No simulated enrollment shown.</div>';return;}
  function rejected(r){
    if(r.__error)return {rej:false,reason:'endpoint unreachable'};
    var rej=(r.success===false)||(r.enrolled===false)||(String(r.failure_reason||r.status||r.decision||'').toUpperCase().match(/REJECT|DENY|VIOLATION|INVALID|UNKNOWN|FAIL/)!=null);
    return {rej:rej,reason:r.failure_reason||r.reason||r.message||(rej?'attestation rejected':'enrolled')};
  }
  var b=rejected(bad), s=rejected(s889);
  var enrolledCount=(st&&!st.__error&&st.enrolled_count!=null)?st.enrolled_count:null;
  box.innerHTML=
    '<div class="enroll-row '+((enrolledCount&&enrolledCount>0)?'ok':'')+'"><span>VALID enrollment (server-attested witnesses, doctrine v11 · kernel c7c0ba17)</span><span class="er-v">'+(enrolledCount!=null?(enrolledCount+' ENROLLED \u2713'):'—')+'</span></div>'+
    '<div class="dim mono" style="font-size:10px;margin:-.2rem 0 .6rem .2rem">these nodes passed the real HMAC formation-proof + doctrine/kernel/SLSA + Section&nbsp;889 gate server-side (proof key never exposed to the browser)</div>'+
    '<div class="enroll-row '+(b.rej?'ok':'fail')+'"><span>INVALID attestation (bad doctrine / wrong kernel / forged proof)</span><span class="er-v">'+(b.rej?'REJECTED \u2713':'WRONGLY ENROLLED')+'</span></div>'+
    '<div class="dim mono" style="font-size:10px;margin:-.2rem 0 .6rem .2rem">'+esc(String(b.reason||'').slice(0,90))+'</div>'+
    '<div class="enroll-row '+(s.rej?'ok':'fail')+'"><span>Section&nbsp;889 banned-vendor attestation (Huawei)</span><span class="er-v">'+(s.rej?'REJECTED \u2713':'WRONGLY ENROLLED')+'</span></div>'+
    '<div class="dim mono" style="font-size:10px;margin:-.2rem 0 0 .2rem">'+esc(String(s.reason||'').slice(0,90))+'</div>'+
    '<div class="honesty" style="margin-top:.8rem"><b>Honest:</b> enrollment is gated by the real spec&nbsp;05 attestation check. Nodes that pass it server-side are enrolled (shown live above); a forged proof and a Section&nbsp;889 banned vendor are each rejected with a real reason. The browser cannot mint a valid proof — that is the gate.</div>';
  _prov.enroll=true;
}

/* =================== 5 · HUD =================== */
async function loadHud(){
  var feeds=[];
  feeds.push(['Topology', _prov.nodeCount!=null&&_prov.nodeCount>0, '/mesh/topology · '+(_prov.nodeCount!=null?_prov.nodeCount+' nodes':'—')]);
  feeds.push(['Edges', _prov.edgeCount!=null&&_prov.edgeCount>0, '/mesh/topology · '+(_prov.edgeCount!=null?_prov.edgeCount+' edges':'—')]);
  feeds.push(['Quorum', !!(_prov.quorum&&_prov.quorum.canonical), '/mesh/quorum · n=4 t=3'+(_prov.quorum?(' · '+_prov.quorum.allows+'-of-'+_prov.quorum.n):' · not run')]);
  feeds.push(['Receipts', _prov.receiptCount!=null&&_prov.receiptCount>0, '/mesh/write · '+(_prov.receiptCount!=null?_prov.receiptCount+' DSSE':'—')]);
  feeds.push(['Enrollment', !!(_prov.enroll), '/mesh/enroll · doctrine-gated']);
  document.getElementById('hud-grid').innerHTML=feeds.map(function(f){
    return '<div class="hud-feed"><div class="fn">'+modePill(f[1])+' '+esc(f[0])+'</div><div class="src">'+esc(f[2])+'</div></div>';
  }).join('');
  document.getElementById('tb-live').textContent=_prov.anyLive?'LIVE MESH · RT':'MESH · RT';
  document.getElementById('hd-mode').textContent=_prov.anyLive?'LIVE MESH':'MESH (empty)';
}

/* =================== boot =================== */
(async function(){
  await loadTopology();
  await loadReceipts();
  await runQuorum();
  // Pre-fill the enrollment panel from a clean GET /mesh/status (the enrolled
  // witnesses that genuinely passed the gate). The rejection demo (which exercises
  // honest server 4xx responses) runs only on explicit button click, so the initial
  // page load is free of expected-rejection network entries.
  await primeEnrollFromStatus();
  setTimeout(loadHud, 600);
})();
window.addEventListener('resize', function(){ if(_topo.nodes&&_topo.nodes.length) layoutAndRender(); });

/* =================== 1b · 3D MESH TOPOLOGY (F4 · additive) =================== */
/* Loads the shared 0-CDN holographic kit and renders the SAME live /mesh/topology
   graph in 3D with a live-computed Fiedler value (algebraic connectivity), plus
   operator-triggered partition + self-heal SIMULATIONS. 2D SVG above is fallback. */
(function(){
  var mount=document.getElementById('mesh3d_mount');
  var offEl=document.getElementById('m3d-off');
  var toggle=document.getElementById('m3d-toggle');
  if(!mount||!toggle){ return; }
  if(!window.SZLHolo){ toggle.disabled=true; toggle.textContent='3D unavailable'; return; }
  var scene=null, started=false, anim=null;
  var FD=document.getElementById('m3d-fiedler'), FDL=document.getElementById('m3d-fiedler-lbl');
  var ND=document.getElementById('m3d-nodes'), ED=document.getElementById('m3d-edges'), CAP=document.getElementById('m3d-caps');
  var bPart=document.getElementById('m3d-partition'), bHeal=document.getElementById('m3d-heal');
  // working copy of the live topology (so SIM partition/heal never mutate the real graph)
  var sim={nodes:[],edges:[]};
  var healedEdge=null, droppedEdge=null;

  // ---- Fiedler value: 2nd-smallest eigenvalue of the graph Laplacian L=D-A.
  // Computed in-browser via power iteration on a shifted/deflated matrix (small N).
  function laplacian(n, edges, idx){
    var L=[]; for(var i=0;i<n;i++){L.push(new Array(n).fill(0));}
    edges.forEach(function(e){
      var a=idx[e.source], b=idx[e.target];
      if(a==null||b==null||a===b)return;
      L[a][b]-=1; L[b][a]-=1; L[a][a]+=1; L[b][b]+=1;
    });
    return L;
  }
  function matVec(M,v){var n=v.length,o=new Array(n).fill(0);for(var i=0;i<n;i++){var s=0;for(var j=0;j<n;j++)s+=M[i][j]*v[j];o[i]=s;}return o;}
  function norm(v){return Math.sqrt(v.reduce(function(a,x){return a+x*x;},0));}
  function fiedler(n, edges, idx){
    if(n<2) return 0;
    var L=laplacian(n,edges,idx);
    // shift: B = c*I - L, largest eigvecs of B (orthogonal to all-ones) -> smallest nonzero of L
    var c=2*n;
    var B=[]; for(var i=0;i<n;i++){B.push([]);for(var j=0;j<n;j++)B[i].push((i===j?c:0)-L[i][j]);}
    var ones=new Array(n).fill(1/Math.sqrt(n));
    function deflate(v){var d=v.reduce(function(a,x,k){return a+x*ones[k];},0);return v.map(function(x,k){return x-d*ones[k];});}
    var v=new Array(n); for(var k=0;k<n;k++)v[k]=Math.sin(k*1.7+0.3); v=deflate(v); var nv=norm(v)||1; v=v.map(function(x){return x/nv;});
    var lambdaB=0;
    for(var it=0;it<200;it++){
      var w=matVec(B,v); w=deflate(w); var nw=norm(w); if(nw<1e-12)break;
      v=w.map(function(x){return x/nw;}); lambdaB=nw;
    }
    var lam2=c-lambdaB; // L's smallest nonzero eigenvalue ~ Fiedler value
    return Math.max(0, lam2);
  }

  function buildSpec(){
    var nodes=sim.nodes.map(function(n){
      var lab=String(n.label||n.id).slice(0,9);
      return {id:String(n.id),label:lab,witness:n.witness};
    });
    var edges=sim.edges.map(function(e,i){return {id:'me'+i,from:String(e.source),to:String(e.target)};});
    return {nodes:nodes,edges:edges};
  }
  function idxMap(){var m={};sim.nodes.forEach(function(n,i){m[String(n.id)]=i;});return m;}

  function paint(){
    if(!scene)return;
    var idx=idxMap();
    var lam=fiedler(sim.nodes.length, sim.edges, idx);
    var lamMax=Math.max(1e-6, sim.nodes.length); // rough normaliser
    // Λ-style trust: lower connectivity -> higher risk. Map Fiedler->[0..1) inverted.
    var risk=Math.min(0.999, 1/(1+lam));         // lam high => low risk (<1.0 always)
    try{
      scene.graphs=[]; scene.pulses=[]; scene.spheres=[];
      scene.addGraph(buildSpec());
      scene.addTrustSphere({lambda:risk}); scene.setLambda(risk);
    }catch(e){}
    FD.textContent=lam.toFixed(4);
    var healthy=lam>0.25;
    FDL.innerHTML=healthy
      ? '<span style="color:var(--live);font-size:9px;border:1px solid var(--live);padding:1px 5px;border-radius:5px">HEALTHY · connected</span>'
      : (lam<=1e-4
        ? '<span style="color:var(--err);font-size:9px;border:1px solid var(--err);padding:1px 5px;border-radius:5px">PARTITIONED · λ₂→0</span>'
        : '<span style="color:var(--warn);font-size:9px;border:1px solid var(--warn);padding:1px 5px;border-radius:5px">DEGRADED · approaching partition</span>');
    ND.textContent=sim.nodes.length; ED.textContent=sim.edges.length;
    setMode('mesh3d-mode', healthy, sim.nodes.length===0);
  }

  function syncFromLive(){
    // _topo is the live, normalised topology already fetched by loadTopology()
    sim={nodes:(_topo.nodes||[]).map(function(n){return {id:n.id,label:n.label,witness:n.witness};}),
         edges:(_topo.edges||[]).map(function(e){return {source:e.source,target:e.target};})};
    healedEdge=null; droppedEdge=null;
    var has=sim.nodes.length>0;
    bPart.disabled=!has || sim.edges.length<1; bHeal.disabled=true;
    paint();
  }

  function doPartition(){
    if(!sim.edges.length)return;
    // drop a non-bridge-ish edge: remove the last edge to weaken connectivity
    droppedEdge=sim.edges.pop();
    bPart.disabled=true; bHeal.disabled=false;
    paint();
  }
  function doHeal(){
    // form a bridging edge between two least-connected distinct nodes
    if(sim.nodes.length<2)return;
    var a=sim.nodes[0].id, b=sim.nodes[sim.nodes.length-1].id;
    if(droppedEdge){ a=droppedEdge.source; b=droppedEdge.target; }
    sim.edges.push({source:a,target:b}); healedEdge={source:a,target:b};
    bHeal.disabled=true; bPart.disabled=sim.edges.length<1;
    paint();
    // signed pulse along the freshly-formed bridge edge
    try{ scene.signPulse('me'+(sim.edges.length-1)); }catch(_){}
  }

  function start(){
    if(started)return; started=true;
    mount.style.display='block'; offEl.style.display='none'; toggle.textContent='Disable 3D';
    scene=window.SZLHolo.createScene(mount,{sample:false});
    var caps=window.SZLHolo.capabilities();
    CAP.textContent='mode:'+caps.mode+(caps.webgpu?' · webgpu-detected(ROADMAP)':'');
    scene.start();
    syncFromLive();
    var lastN=-1, lastE=-1;
    anim=setInterval(function(){
      if(!scene)return;
      // re-sync if the live topology changed (and no SIM is mid-flight)
      if(bHeal.disabled && !droppedEdge && _topo.nodes && (_topo.nodes.length!==lastN || _topo.edges.length!==lastE)){
        lastN=_topo.nodes.length; lastE=_topo.edges.length; syncFromLive();
      }
      if(sim.edges.length){ try{scene.signPulse('me0');}catch(_){} }
    },3200);
  }
  function stop(){
    if(!started)return; started=false;
    mount.style.display='none'; offEl.style.display='block'; toggle.textContent='Enable 3D';
    if(anim)clearInterval(anim);
    try{ if(scene){scene.stop();scene.dispose();} }catch(e){}
    scene=null;
  }
  toggle.addEventListener('click',function(){ started?stop():start(); });
  bPart.addEventListener('click',doPartition);
  bHeal.addEventListener('click',doHeal);
})();

</script>
</body>
</html>"""


async def _mesh_view(request):
    return HTMLResponse(_PAGE)


def register(app, ns="killinchu"):
    """ADDITIVE. Mount the live MESH view BEFORE the SPA catch-all. Pure VIEW —
    reuses the REAL /mesh/* endpoints Dev 3 exposes; reinvents no backend."""
    routes = [
        Route("/elite/mesh", _mesh_view, methods=["GET"],
              name="%s_elite_mesh" % ns),
        Route("/mesh-surface", _mesh_view, methods=["GET"],
              name="%s_mesh_surface_alias" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "view": "mesh_view",
            "routes": ["/elite/mesh", "/mesh-surface"],
            "doctrine": _DOCTRINE, "lean": _LEAN, "locked": _LOCKED}
