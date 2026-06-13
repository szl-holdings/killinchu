# ==========================================================================
# killinchu_maritime_view.py  —  CONSOLIDATED "MARITIME INTEL" /elite view
# (renamed from a draft killinchu_maritime_intel.py to avoid colliding with the
#  EXISTING Wave-2 detection backend of that name; this is a pure VIEW page.)
# --------------------------------------------------------------------------
# ADDITIVE flagship view that UNIFIES every maritime wave killinchu shipped
# into ONE investor-facing narrative, in killinchu's EXISTING house style
# (gold + teal on near-black; Space Grotesk display + JetBrains Mono labels —
# the same tokens as killinchu_elite_console.py). It does NOT reinvent any
# backend: it is a pure VIEW that fetches the REAL endpoints the waves built.
#
#   GET  /elite/maritime          — the unified Maritime Intel surface
#   GET  /maritime-intel          — alias
#
# Sections (top -> bottom):
#   1. LIVE VESSEL BOARD   /feeds/vessels (+ /feeds/vessels/stats) — theater
#                          selector incl. China seas; LIVE/SAMPLE pill + source
#                          provenance per the FEEDS_CONTRACT.
#   2. THREAT FLAGS        /maritime/dark (going-dark) + /maritime/spoof
#                          (AIS-spoof) — evidence/signatures, advisory-labeled.
#   3. Λ RISK SCORE        /maritime/risk + /maritime/riskarc — governed
#                          compliance traffic-light + per-axis breakdown +
#                          formula trace; "advisory, governed by Λ (Conjecture
#                          1)" — NEVER "Λ is unique".
#   4. FORECAST            /maritime/forecast — track prediction / time-
#                          unaccounted / intercept, labeled FORECAST.
#   5. ASW / OSINT         /asw/osint (OSINT-LIVE), /asw/forecast (FORECAST),
#                          /asw/negative-space (INFERENCE) + honest-limits.
#   6. 3D GLOBE            embeds/links the existing maritime globe (/elite/globe)
#                          as the visual centerpiece.
#   7. PROVENANCE HUD      which feeds are LIVE now + sources + ts + the honest
#                          disclaimer; each judgment links its real DSSE receipt.
#
# Effector stays SIMULATED. We do NOT claim vessel control or live submarine
# tracking. 0 runtime CDN (fonts/libs served from /vendor/*). WCAG-AA.
# Doctrine v11 — locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17;
# Λ = Conjecture 1 (never unique); Khipu = Conjecture 2. Byte-identical GH<->HF.
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
# Mono) and the self-hosted fonts at /vendor/fonts/fonts.css.
# --------------------------------------------------------------------------
_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>killinchu · Maritime Intel</title>
<meta name="description" content="killinchu Maritime Intel — unified live AIS vessel board, dark-fleet/spoof threat flags, governed Λ risk score, vessel forecast, honest submarine/ASW OSINT, and a re-hashable signed provenance HUD. Advisory; effector SIMULATED; no vessel control or live submarine tracking."/>
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
a{color:var(--teal);text-decoration:none;}
a:hover{text-decoration:underline;}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:3px;}
::-webkit-scrollbar{width:9px;height:9px;}::-webkit-scrollbar-thumb{background:#222;border-radius:6px;}

/* ===== topbar (matches elite console breadcrumb) ===== */
.topbar{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:1rem;flex-wrap:nowrap;
  height:39px;min-height:39px;padding:0 1.1rem;background:rgba(10,10,10,.92);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--gold-line);font-family:var(--mono);font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--gold);overflow-x:auto;white-space:nowrap;}
.topbar .sep{color:var(--dim);}
.topbar .live{display:inline-flex;align-items:center;gap:.4rem;color:var(--cream);}
.live-dot{width:6px;height:6px;border-radius:50%;background:var(--live);box-shadow:0 0 6px var(--live);animation:pulse 2.2s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.35;}}
.topbar .back{margin-left:auto;color:var(--muted);}
.topbar .back:hover{color:var(--cream);}

/* ===== hero / brand ===== */
.wrap{max-width:1180px;margin:0 auto;padding:1.4rem 1.3rem 4rem;}
.brand{display:flex;align-items:center;gap:.7rem;margin-bottom:1rem;}
.brand .mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--gold),var(--teal));
  display:grid;place-items:center;color:#0a0a0a;font-weight:700;font-family:var(--mono);font-size:15px;}
.brand .nm{font-weight:600;font-size:1.1rem;line-height:1.1;}
.brand .role{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;}
.view-head{display:flex;align-items:flex-end;gap:.8rem;flex-wrap:wrap;margin:.2rem 0 .3rem;}
.view-title{font-size:2rem;font-weight:500;letter-spacing:-.02em;}
.view-badge{font-family:var(--mono);font-size:10px;color:var(--teal);border:1px solid var(--teal-line);
  border-radius:5px;padding:.18rem .55rem;background:var(--teal-soft);letter-spacing:.06em;}
.view-sub{font-size:13.5px;color:var(--paragraph);line-height:1.65;margin:.5rem 0 1.4rem;max-width:64rem;}
.view-sub b{color:var(--cream);}

/* ===== section anchor nav (in-page) ===== */
.sectnav{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.6rem;}
.sectnav a{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;
  padding:.4rem .7rem;border:1px solid var(--gold-line);border-radius:999px;color:var(--muted);
  background:var(--gold-soft);transition:.15s;}
.sectnav a:hover{color:var(--cream);border-color:var(--gold);text-decoration:none;}

/* ===== section blocks ===== */
.sect{margin:2.2rem 0;scroll-margin-top:54px;}
.sect-h{display:flex;align-items:baseline;gap:.7rem;flex-wrap:wrap;margin-bottom:.2rem;padding-bottom:.5rem;border-bottom:1px solid var(--gold-line);}
.sect-num{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.1em;}
.sect-t{font-size:1.3rem;font-weight:500;color:var(--cream);}
.sect-tag{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
  padding:.16rem .5rem;border-radius:5px;border:1px solid var(--teal-line);color:var(--teal);background:var(--teal-soft);}
.sect-ep{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto;}
.sect-desc{font-size:12.5px;color:var(--paragraph);line-height:1.6;margin:.6rem 0 .9rem;}

/* ===== cards / kpis / pills ===== */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin:.9rem 0 1.1rem;}
.kpi{border:1px solid var(--gold-line);border-radius:9px;background:var(--panel);padding:.85rem 1rem;}
.kpi .k{font-family:var(--mono);font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);}
.kpi .v{font-size:1.5rem;font-weight:500;color:var(--gold);margin-top:.2rem;line-height:1.1;}
.kpi .v.teal{color:var(--teal);} .kpi .v.live{color:var(--live);} .kpi .v.warn{color:var(--warn);} .kpi .v.err{color:var(--err);}
.kpi .d{font-size:11px;color:var(--paragraph);margin-top:.2rem;}
.card{border:1px solid var(--gold-line);border-radius:11px;background:var(--panel);padding:1.15rem 1.25rem;margin-bottom:1rem;}
.card-h{display:flex;align-items:center;gap:.6rem;margin-bottom:.7rem;flex-wrap:wrap;}
.card-t{font-size:1.02rem;font-weight:500;color:var(--cream);}
.card-ep{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto;}
.pill{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
  padding:.16rem .5rem;border-radius:999px;display:inline-block;}
.p-live{color:var(--live);border:1px solid rgba(111,174,139,.45);background:rgba(111,174,139,.10);}
.p-sample{color:var(--gold);border:1px solid var(--gold-line);background:var(--gold-soft);}
.p-osint{color:var(--teal);border:1px solid var(--teal-line);background:var(--teal-soft);}
.p-forecast{color:var(--warn);border:1px solid rgba(214,176,106,.4);background:rgba(214,176,106,.08);}
.p-inference{color:var(--muted);border:1px solid var(--gold-line);background:var(--gold-soft);}
.p-sim{color:var(--err);border:1px solid rgba(208,138,120,.4);background:rgba(208,138,120,.08);}

/* ===== controls ===== */
label{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:.3rem;}
select,input{background:var(--panel2);border:1px solid var(--gold-line);color:var(--cream);border-radius:6px;
  padding:.45rem .7rem;font-family:var(--mono);font-size:12px;min-height:40px;}
select:focus,input:focus{outline:2px solid var(--gold);outline-offset:1px;}
.btn{display:inline-flex;align-items:center;gap:.4rem;padding:.5rem 1rem;font-size:11.5px;font-weight:500;font-family:var(--mono);
  border-radius:6px;border:1px solid var(--gold-line);background:transparent;color:var(--gold);cursor:pointer;letter-spacing:.04em;transition:.18s;min-height:40px;}
.btn:hover{background:rgba(201,183,135,.08);border-color:rgba(201,183,135,.35);}
.btn.teal{color:var(--teal);border-color:var(--teal-line);background:var(--teal-soft);}
.ctrls{display:flex;flex-wrap:wrap;gap:.8rem;align-items:flex-end;margin-bottom:1rem;}

/* ===== tables ===== */
.dtbl{width:100%;border-collapse:collapse;font-size:12.5px;}
.dtbl th{text-align:left;font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding:.5rem .6rem;border-bottom:1px solid var(--gold-line);}
.dtbl td{padding:.45rem .6rem;border-bottom:1px solid rgba(201,183,135,.06);color:var(--paragraph);}
.dtbl tr:hover td{background:var(--gold-soft);}
.tbl-scroll{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:8px;}

/* ===== traffic light ===== */
.tl{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin:.4rem 0 1rem;}
.tl-lamp{width:74px;height:74px;border-radius:50%;display:grid;place-items:center;font-family:var(--mono);
  font-size:13px;font-weight:700;letter-spacing:.04em;color:#0a0a0a;}
.tl-GREEN{background:var(--green);box-shadow:0 0 22px rgba(111,174,139,.5);}
.tl-AMBER{background:var(--amber);box-shadow:0 0 22px rgba(214,176,106,.5);}
.tl-RED{background:var(--red);box-shadow:0 0 22px rgba(208,138,120,.5);}
.tl-meta{font-size:13px;color:var(--paragraph);line-height:1.6;}
.tl-meta b{color:var(--cream);}
.axis{display:flex;align-items:center;gap:.6rem;padding:.4rem .2rem;border-bottom:1px solid rgba(201,183,135,.06);font-size:12px;}
.axis .nm{font-family:var(--mono);font-size:11px;color:var(--cream);min-width:118px;}
.bar-track{flex:1;height:8px;background:#161616;border-radius:5px;overflow:hidden;min-width:90px;}
.bar-fill{display:block;height:100%;background:linear-gradient(90deg,var(--teal),var(--gold));border-radius:5px;}
.axis .why{font-family:var(--mono);font-size:10px;color:var(--dim);flex:2;min-width:120px;}

/* ===== feed / list ===== */
.frow{padding:.5rem .2rem;border-bottom:1px solid rgba(201,183,135,.07);font-size:12.5px;line-height:1.5;}
.frow:last-child{border-bottom:none;}
.frow .ttl{color:var(--cream);font-weight:500;}
.frow .meta{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:.15rem;}
.frow .sum{color:var(--paragraph);font-size:12px;margin-top:.2rem;}

pre.out{font-family:var(--mono);font-size:11px;line-height:1.55;color:var(--paragraph);background:var(--panel2);
  border:1px solid var(--gold-line);border-radius:8px;padding:.8rem .9rem;overflow:auto;white-space:pre-wrap;word-break:break-word;max-height:360px;}
details.raw{margin-top:.8rem;} details.raw summary{cursor:pointer;font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase;}

.honesty{margin-top:1rem;padding:1rem 1.2rem;border:1px solid var(--gold-line);border-radius:9px;background:var(--gold-soft);font-size:12px;color:var(--paragraph);line-height:1.7;}
.honesty b{color:var(--gold);}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:1rem;}
.muted{color:var(--muted);} .dim{color:var(--dim);}
.loading{font-family:var(--mono);font-size:11px;color:var(--dim);padding:.6rem 0;}

/* ===== globe centerpiece ===== */
.globe-card{position:relative;border:1px solid var(--gold-line);border-radius:11px;overflow:hidden;
  background:radial-gradient(circle at 50% 40%,#0c1410,#070707);min-height:300px;display:flex;
  flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:2.2rem 1.4rem;}
.globe-card .ring{width:120px;height:120px;border-radius:50%;border:1px solid var(--teal-line);
  display:grid;place-items:center;margin-bottom:1rem;background:radial-gradient(circle,rgba(95,179,163,.12),transparent 70%);}
.globe-card .ring span{font-size:2.4rem;}

/* ===== provenance HUD ===== */
.hud{border:1px solid var(--teal-line);border-radius:11px;background:linear-gradient(180deg,rgba(95,179,163,.05),var(--panel));padding:1.15rem 1.25rem;}
.hud-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.7rem;margin:.7rem 0;}
.hud-feed{border:1px solid var(--gold-line);border-radius:8px;background:var(--panel2);padding:.6rem .7rem;font-size:11.5px;}
.hud-feed .fn{font-family:var(--mono);font-size:10px;color:var(--cream);letter-spacing:.04em;}
.hud-feed .src{color:var(--dim);font-family:var(--mono);font-size:9.5px;margin-top:.2rem;word-break:break-word;}
.disc{font-size:12px;color:var(--paragraph);line-height:1.7;margin-top:.7rem;border-top:1px solid var(--gold-line);padding-top:.7rem;}
.disc b{color:var(--err);}

/* ===== doctrine footer ===== */
.foot{margin-top:2.6rem;padding-top:1.1rem;border-top:1px solid var(--gold-line);
  font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.8;letter-spacing:.02em;}
.foot b{color:var(--muted);}

@media (max-width:820px){
  .wrap{padding:1.1rem .9rem 3rem;}
  .view-title{font-size:1.5rem;}
  .grid2{grid-template-columns:1fr;}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(46%,1fr));}
  .sect-ep,.card-ep{margin-left:0;}
}
@media (max-width:480px){ .kpis{grid-template-columns:1fr;} }
</style>
</head>
<body>
<div class="topbar">
  <span>SZL HOLDINGS</span><span class="sep">/</span>
  <span style="color:var(--teal)">KILLINCHU</span><span class="sep">/</span>
  <span>MARITIME INTEL</span><span class="sep">/</span>
  <span class="live"><span class="live-dot"></span><span id="tb-live">CONNECTING…</span></span>
  <a class="back" href="/elite">&#8592; BACK TO /ELITE</a>
</div>

<div class="wrap">
  <div class="brand">
    <div class="mark">K</div>
    <div><div class="nm">killinchu</div><div class="role">drones &amp; vessels &middot; maritime intel</div></div>
  </div>

  <div class="view-head">
    <h1 class="view-title">Maritime Intel</h1>
    <span class="view-badge">UNIFIED &middot; LIVE AIS &middot; GOVERNED &middot; SIGNED</span>
  </div>
  <p class="view-sub">One surface unifying every maritime layer killinchu ships, end to end:
    <b>live AIS vessel board</b> (theaters incl. China seas) &rarr; <b>dark-fleet &amp; AIS-spoof threat flags</b>
    (advisory, evidence-traced) &rarr; the governed <b>&Lambda; compliance risk score</b> (traffic-light + per-axis
    breakdown + formula trace) &rarr; <b>vessel forecast</b> (track projection) &rarr; honest
    <b>submarine / ASW</b> (OSINT-LIVE, FORECAST, INFERENCE) &rarr; the existing <b>3D globe</b> &rarr; a
    re-hashable <b>signed provenance HUD</b>. Every layer is computed over <b>REAL data</b> and labeled
    LIVE / SAMPLE / FORECAST / OSINT / INFERENCE. Advisory, human-on-the-loop; the effector is
    <b>SIMULATED</b>; we do <b>not</b> claim vessel control or live submarine tracking.</p>

  <nav class="sectnav" aria-label="Sections">
    <a href="#vessels">&#9875; 1 · Vessel Board</a>
    <a href="#threats">&#9888; 2 · Threat Flags</a>
    <a href="#risk">&#9672; 3 · Λ Risk</a>
    <a href="#forecast">&#10138; 4 · Forecast</a>
    <a href="#asw">&#9925; 5 · ASW / OSINT</a>
    <a href="#globe">&#9673; 6 · 3D Globe</a>
    <a href="#hud">&#9939; 7 · Provenance</a>
  </nav>

  <!-- 1 · LIVE VESSEL BOARD -->
  <section class="sect" id="vessels">
    <div class="sect-h"><span class="sect-num">01</span><span class="sect-t">&#9875; Live Vessel Board</span>
      <span class="sect-tag" id="vessels-mode">REAL AIS</span>
      <span class="sect-ep mono">GET /feeds/vessels</span></div>
    <p class="sect-desc">Real AIS, normalized to the FEEDS_CONTRACT TRACK shape — every record carries
      <b>source · live · provenance · ts</b>. Each theater shows an honest <b>LIVE</b> or <b>SAMPLE</b> pill
      (Asia/global theaters fall to SAMPLE when no AISStream key is in the Space secret store; FI/Norway are no-key LIVE).</p>
    <div class="ctrls">
      <div><label for="theater">Theater</label>
        <select id="theater"></select></div>
      <div><label for="vtype">Vessel type</label>
        <select id="vtype">
          <option value="all">all</option><option value="tanker">tanker</option>
          <option value="cargo">cargo</option><option value="fishing">fishing</option>
          <option value="naval">naval</option><option value="passenger">passenger</option>
          <option value="tug">tug</option><option value="unknown">unknown</option>
        </select></div>
      <button class="btn teal" onclick="loadVessels()">&#8635; Refresh</button>
    </div>
    <div id="vessels-kpis" class="kpis"></div>
    <div class="card"><div class="card-h"><span class="card-t">Vessels in theater</span>
      <span class="card-ep mono" id="vessels-prov">—</span></div>
      <div class="tbl-scroll"><table class="dtbl"><thead><tr>
        <th>Name</th><th>Type</th><th>Flag</th><th>MMSI</th><th>Lat</th><th>Lon</th><th>Spd kn</th><th>Source</th>
      </tr></thead><tbody id="vessels-rows"><tr><td colspan="8" class="loading">loading…</td></tr></tbody></table></div>
    </div>
    <details class="raw"><summary>theater stats (raw)</summary><pre class="out" id="vessels-stats">…</pre></details>
  </section>

  <!-- 2 · THREAT FLAGS -->
  <section class="sect" id="threats">
    <div class="sect-h"><span class="sect-num">02</span><span class="sect-t">&#9888; Threat Flags</span>
      <span class="sect-tag" style="color:var(--err);border-color:rgba(208,138,120,.4);background:rgba(208,138,120,.08)">ADVISORY · NOT PROVEN</span>
      <span class="sect-ep mono">GET /maritime/dark · /maritime/spoof</span></div>
    <p class="sect-desc">Dark-fleet / going-dark and AIS-spoof flags, computed by <b>correlation over REAL AIS</b>, each
      with its <b>evidence trail + signature</b>. Dark activity &ne; proof of illicit activity (Windward caveat); these
      flag RISK with honest confidence — <b>not proven</b>. Every judgment emits a re-hashable DSSE receipt.</p>
    <div class="grid2">
      <div class="card"><div class="card-h"><span class="card-t">&#9681; Going-Dark / AIS-Gap</span>
        <span class="card-ep mono" id="dark-mode">—</span></div>
        <div id="dark-kpis" class="kpis" style="margin:.3rem 0 .6rem"></div>
        <div class="tbl-scroll"><table class="dtbl"><thead><tr><th>MMSI / track</th><th>Last seen</th><th>Gap</th><th>Confidence</th></tr></thead>
          <tbody id="dark-rows"><tr><td colspan="4" class="loading">loading…</td></tr></tbody></table></div>
        <div class="meta mono dim" id="dark-method" style="font-size:10px;margin-top:.5rem"></div>
      </div>
      <div class="card"><div class="card-h"><span class="card-t">&#9888; AIS-Spoof</span>
        <span class="card-ep mono" id="spoof-mode">—</span></div>
        <div id="spoof-kpis" class="kpis" style="margin:.3rem 0 .6rem"></div>
        <div class="tbl-scroll"><table class="dtbl"><thead><tr><th>MMSI / track</th><th>Signature</th><th>Evidence</th><th>Confidence</th></tr></thead>
          <tbody id="spoof-rows"><tr><td colspan="4" class="loading">loading…</td></tr></tbody></table></div>
        <div class="meta mono dim" id="spoof-method" style="font-size:10px;margin-top:.5rem"></div>
      </div>
    </div>
  </section>

  <!-- 3 · Λ RISK SCORE -->
  <section class="sect" id="risk">
    <div class="sect-h"><span class="sect-num">03</span><span class="sect-t">&#9672; &Lambda; Risk Score</span>
      <span class="sect-tag">ADVISORY · GOVERNED BY Λ (CONJECTURE 1)</span>
      <span class="sect-ep mono">GET /maritime/risk · /maritime/riskarc</span></div>
    <p class="sect-desc">The governed compliance traffic-light (green / amber / red) with the per-axis breakdown and a
      <b>formula trace</b>. The fused score is <b>advisory, governed by &Lambda; (Conjecture 1)</b> — a 13-axis geometric-mean
      trust gate that is <b>never claimed unique and never a theorem</b>. /maritime/riskarc supplies the raw behavioral
      signals; /maritime/risk fuses them.</p>
    <div class="card">
      <div class="card-h"><span class="card-t" id="risk-vessel">scoring sample fleet vessel…</span>
        <span class="card-ep mono" id="risk-ts">—</span></div>
      <div class="tl">
        <div class="tl-lamp" id="risk-lamp">…</div>
        <div class="tl-meta" id="risk-meta">—</div>
      </div>
      <div id="risk-axes"></div>
      <details class="raw"><summary>formula trace + DSSE receipt (raw)</summary><pre class="out" id="risk-trace">…</pre></details>
    </div>
  </section>

  <!-- 4 · FORECAST -->
  <section class="sect" id="forecast">
    <div class="sect-h"><span class="sect-num">04</span><span class="sect-t">&#10138; Forecast</span>
      <span class="sect-tag p-forecast">FORECAST · PROJECTION</span>
      <span class="sect-ep mono">GET /maritime/forecast</span></div>
    <p class="sect-desc">Advisory track / destination forecast — <b>dead-reckoning + sea-lane prior</b>, deterministic,
      confidence decaying with horizon. This is a <b>FORECAST (a projection)</b>, human-on-the-loop — <b>not observed truth and
      not vessel control</b>.</p>
    <div class="card">
      <div class="card-h"><span class="card-t" id="fc-vessel">forecasting…</span>
        <span class="card-ep mono" id="fc-method">—</span></div>
      <div id="fc-kpis" class="kpis" style="margin:.2rem 0 .8rem"></div>
      <div class="tbl-scroll"><table class="dtbl"><thead><tr><th>t+h</th><th>Lat</th><th>Lon</th><th>Uncertainty (nm)</th><th>Confidence</th></tr></thead>
        <tbody id="fc-rows"><tr><td colspan="5" class="loading">loading…</td></tr></tbody></table></div>
    </div>
  </section>

  <!-- 5 · ASW / OSINT -->
  <section class="sect" id="asw">
    <div class="sect-h"><span class="sect-num">05</span><span class="sect-t">&#9925; Submarine / ASW</span>
      <span class="sect-tag">HONEST · 3 LABELED PRODUCTS</span>
      <span class="sect-ep mono">GET /asw/osint · /asw/forecast · /asw/negative-space</span></div>
    <p class="sect-desc">HONEST LIMITS — submarines do <b>not</b> broadcast AIS and there is <b>no public live submarine
      track feed</b>; we will <b>never fabricate a live submarine track</b>. Instead, three truthfully-labeled products:
      <span class="pill p-osint">OSINT-LIVE</span> public naval reporting,
      <span class="pill p-forecast">FORECAST</span> probability-field projection, and
      <span class="pill p-inference">INFERENCE</span> negative-space advisory over real surface-AIS density.</p>
    <div class="grid2">
      <div class="card"><div class="card-h"><span class="card-t">&#9875; OSINT-LIVE</span>
        <span class="pill p-osint" id="osint-mode">—</span></div>
        <div id="osint-rows"><div class="loading">loading…</div></div>
      </div>
      <div class="card"><div class="card-h"><span class="card-t">&#10138; FORECAST · probability field</span>
        <span class="pill p-forecast">FORECAST</span></div>
        <div id="aswfc-body"><div class="loading">loading…</div></div>
      </div>
    </div>
    <div class="card"><div class="card-h"><span class="card-t">&#9711; INFERENCE · negative-space</span>
      <span class="pill p-inference">INFERENCE</span></div>
      <div id="negspace-body"><div class="loading">loading…</div></div>
    </div>
    <div class="honesty" id="asw-honest">…</div>
  </section>

  <!-- 6 · 3D GLOBE -->
  <section class="sect" id="globe">
    <div class="sect-h"><span class="sect-num">06</span><span class="sect-t">&#9673; 3D Globe</span>
      <span class="sect-tag">LIVE PICTURE · CENTERPIECE</span>
      <span class="sect-ep mono">/elite/globe</span></div>
    <p class="sect-desc">The visual centerpiece — killinchu's existing holographic maritime globe: real military ADS-B + AIS
      vessels with the W2/W3 intel layers (dark/spoof/risk) rendered on a self-hosted WebGL2 scene (0 CDN).
      The governance loop is real; the effector link is <b>SIMULATED</b>.</p>
    <a class="globe-card" href="/elite/globe" aria-label="Open the live 3D maritime globe">
      <div class="ring"><span>&#127759;</span></div>
      <div style="font-size:1.05rem;font-weight:500;color:var(--cream)">Open the live 3D Maritime Globe</div>
      <div class="mono dim" style="font-size:11px;margin-top:.4rem">WebGL2 · vendored (0 CDN) · real ADS-B + AIS · intel layers · effector SIMULATED</div>
    </a>
  </section>

  <!-- 7 · PROVENANCE HUD -->
  <section class="sect" id="hud">
    <div class="sect-h"><span class="sect-num">07</span><span class="sect-t">&#9939; Provenance HUD</span>
      <span class="sect-tag">LIVE FEEDS · SIGNED · RE-HASHABLE</span>
      <span class="sect-ep mono">/feeds/realdata/status · /asw/status</span></div>
    <p class="sect-desc">Which feeds are LIVE right now, their sources and timestamps, and the honest disclaimer.
      Each governed judgment above links its <b>real DSSE receipt</b> (re-hashable: re-canonicalize the payload and
      SHA-256 it to match <code>receipt_digest_sha256</code>).</p>
    <div class="hud">
      <div class="hud-grid" id="hud-feeds"></div>
      <div id="hud-receipts" style="font-size:12px;color:var(--paragraph);line-height:1.7"></div>
      <div class="disc">
        <b>Effector SIMULATED</b> &middot; forecasts are projections &middot; we do not claim vessel control or live
        submarine tracking. All maritime intel layers are <b>advisory, human-on-the-loop</b>, computed over REAL data;
        dark / spoof / &Lambda;-risk are <b>NOT proven</b>. &Lambda; = Conjecture 1 (never unique, never a theorem).
      </div>
    </div>
  </section>

  <div class="foot" id="foot">
    Doctrine v11 &middot; 8 formulas formally proven {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17 &middot;
    &Lambda; = Conjecture 1 (advisory, not proven, never unique) &middot; Khipu BFT = Conjecture 2 &middot;
    effector SIMULATED &middot; no vessel control &middot; no live submarine tracking &middot;
    real LIVE / FORECAST / OSINT / SAMPLE labeled &middot; 0 runtime CDN &middot; signed receipts re-hashable offline.
    <br><b>SZL Holdings</b> &middot; killinchu field surface &middot; Lutar, Stephen P. &middot; ORCID 0009-0001-0110-4173
  </div>
</div>

<script>
const API = '/api/killinchu/v1';
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function num(x,d){return (x==null||isNaN(x))?'—':Number(x).toFixed(d==null?2:d);}
function modePill(live){return live?'<span class="pill p-live">LIVE</span>':'<span class="pill p-sample">SAMPLE</span>';}
async function getJSON(path,opts){
  const ctl=new AbortController();const to=setTimeout(()=>ctl.abort(),28000);
  try{const r=await fetch(API+path,Object.assign({signal:ctl.signal,headers:{'accept':'application/json'}},opts||{}));
    clearTimeout(to);if(!r.ok)throw new Error('HTTP '+r.status);return await r.json();}
  catch(e){clearTimeout(to);return {__error:String(e&&e.message||e)};}
}
function kpi(k,v,cls,d){return '<div class="kpi"><div class="k">'+esc(k)+'</div><div class="v '+(cls||'')+'">'+v+'</div>'+(d?'<div class="d">'+esc(d)+'</div>':'')+'</div>';}

let _provHud={};

/* ---------- 1 · VESSELS ---------- */
async function loadStats(){
  const s=await getJSON('/feeds/vessels/stats');
  const sel=document.getElementById('theater');
  if(s.__error||!s.by_theater){sel.innerHTML='<option value="south_china_sea">South China Sea</option>';document.getElementById('vessels-stats').textContent=JSON.stringify(s,null,2);return;}
  const order=s.theaters||Object.keys(s.by_theater);
  sel.innerHTML=order.map(k=>{const t=s.by_theater[k];const lab=(t&&t.label)||k;const m=(t&&t.live>0)?' · LIVE':' · SAMPLE';return '<option value="'+esc(k)+'">'+esc(lab)+m+'</option>';}).join('');
  document.getElementById('vessels-stats').textContent=JSON.stringify(s,null,2);
  _provHud.vessels_stats=s;
}
async function loadVessels(){
  const th=document.getElementById('theater').value||'south_china_sea';
  const ty=document.getElementById('vtype').value||'all';
  document.getElementById('vessels-rows').innerHTML='<tr><td colspan="8" class="loading">loading…</td></tr>';
  const d=await getJSON('/feeds/vessels?theater='+encodeURIComponent(th)+'&type='+encodeURIComponent(ty)+'&limit=40');
  if(d.__error){document.getElementById('vessels-rows').innerHTML='<tr><td colspan="8" class="loading">feed error: '+esc(d.__error)+'</td></tr>';return;}
  const live=!!d.live;
  document.getElementById('vessels-mode').textContent=live?'LIVE AIS':'SAMPLE (no key for this theater)';
  document.getElementById('vessels-kpis').innerHTML=
    kpi('Theater',esc((d.theater_box&&d.theater_box.label)||d.theater),'teal')+
    kpi('Vessels',d.count!=null?d.count:'—','')+
    kpi('Mode',modePill(live),'')+
    kpi('Type filter',esc(d.type||ty),'');
  const tried=(d.sources_tried||[]).filter(x=>x&&x.ok);const top=tried.length?tried[0].source:((d.sources_tried||[])[0]||{}).source;
  document.getElementById('vessels-prov').textContent='source: '+(top||'—')+' · ts '+((d.fetched_at||'').slice(11,19)||'—');
  const vs=d.vessels||d.tracks||d.items||[];
  document.getElementById('vessels-rows').innerHTML=(vs.length?vs.slice(0,40).map(v=>{
    const p=v.position||v;const src=v.source||(d.sources_tried&&d.sources_tried.find(x=>x.ok)||{}).source||'—';
    return '<tr><td>'+esc(v.name||v.shipname||v.mmsi||'—')+'</td><td>'+esc(v.vessel_type||v.type||'unknown')+'</td><td>'+esc(v.flag||'—')+'</td><td class="mono">'+esc(v.mmsi||'—')+'</td><td class="mono">'+num(p.lat,3)+'</td><td class="mono">'+num(p.lon,3)+'</td><td class="mono">'+num(p.speed_kn!=null?p.speed_kn:p.sog,1)+'</td><td class="dim">'+esc(String(src).slice(0,28))+'</td></tr>';
  }).join(''):'<tr><td colspan="8" class="loading">no vessels in window</td></tr>');
  _provHud.vessels=d;
  setLiveBanner();
}

/* ---------- 2 · THREAT FLAGS ---------- */
async function loadDark(){
  const d=await getJSON('/maritime/dark');
  if(d.__error){document.getElementById('dark-rows').innerHTML='<tr><td colspan="4" class="loading">error: '+esc(d.__error)+'</td></tr>';return;}
  const live=(d.ingest||[]).some(i=>i&&i.feed_live);
  document.getElementById('dark-mode').textContent=(live?'LIVE AIS':'SAMPLE')+' · '+(d.theaters||[]).join(',');
  document.getElementById('dark-kpis').innerHTML=
    kpi('Tracked',d.tracked_vessels!=null?d.tracked_vessels:'—','')+kpi('Flagged',d.count!=null?d.count:'—','warn')+kpi('Proven',(d.proven?'YES':'NO'),'err');
  const fl=d.flagged||[];
  document.getElementById('dark-rows').innerHTML=(fl.length?fl.slice(0,12).map(f=>
    '<tr><td class="mono">'+esc(f.mmsi||f.track_id||'—')+'</td><td class="mono">'+esc((f.last_seen||'').slice(11,19)||'—')+'</td><td class="mono">'+esc(f.gap_human||(f.gap_s?Math.round(f.gap_s/60)+'m':'—'))+'</td><td class="mono">'+num(f.confidence,2)+'</td></tr>'
  ).join(''):'<tr><td colspan="4" class="loading">no going-dark flags in window</td></tr>');
  document.getElementById('dark-method').textContent=d.method||'';
  _provHud.dark=d;
}
async function loadSpoof(){
  const d=await getJSON('/maritime/spoof');
  if(d.__error){document.getElementById('spoof-rows').innerHTML='<tr><td colspan="4" class="loading">error: '+esc(d.__error)+'</td></tr>';return;}
  const live=(d.ingest||[]).some(i=>i&&i.feed_live);
  document.getElementById('spoof-mode').textContent=(live?'LIVE AIS':'SAMPLE')+' · '+(d.theaters||[]).join(',');
  document.getElementById('spoof-kpis').innerHTML=
    kpi('Tracked',d.tracked_vessels!=null?d.tracked_vessels:'—','')+kpi('Flagged',d.count!=null?d.count:'—','warn')+kpi('Proven',(d.proven?'YES':'NO'),'err');
  const fl=d.flagged||[];
  document.getElementById('spoof-rows').innerHTML=(fl.length?fl.slice(0,12).map(f=>
    '<tr><td class="mono">'+esc(f.mmsi||f.track_id||'—')+'</td><td class="mono">'+esc(f.signature||(f.signatures||[]).join(',')||'—')+'</td><td class="dim">'+esc(String(f.evidence||f.why||'—').slice(0,46))+'</td><td class="mono">'+num(f.confidence,2)+'</td></tr>'
  ).join(''):'<tr><td colspan="4" class="loading">no spoof flags in window</td></tr>');
  document.getElementById('spoof-method').textContent=d.method||'';
  _provHud.spoof=d;
}

/* ---------- 3 · Λ RISK ---------- */
async function loadRisk(){
  const d=await getJSON('/maritime/risk');
  if(d.__error){document.getElementById('risk-meta').textContent='error: '+d.__error;return;}
  const v=d.vessel||{};const tl=d.traffic_light||{};
  document.getElementById('risk-vessel').textContent='Sample: '+(v.name||v.mmsi||'vessel')+' · '+(v.flag||'')+' · '+(v.type||'');
  document.getElementById('risk-ts').textContent='ts '+((d.ts_utc||'').slice(11,19)||'—');
  const light=(tl.light||'GREEN').toUpperCase();
  const lamp=document.getElementById('risk-lamp');lamp.className='tl-lamp tl-'+light;lamp.textContent=light;
  document.getElementById('risk-meta').innerHTML=
    '<b>'+esc(tl.action||'advisory only')+'</b><br>risk score <b>'+num(d.risk_score,3)+'</b> · Λ trust <b>'+num(d.lambda_trust,3)+'</b> · band '+esc(tl.band||'')+
    '<br><span class="mono dim" style="font-size:10px">advisory, governed by Λ (Conjecture 1) — never unique, never a theorem</span>';
  const ax=d.axes||{};
  document.getElementById('risk-axes').innerHTML=Object.keys(ax).map(k=>{
    const a=ax[k];const risk=(a.raw_risk!=null?a.raw_risk:0);const pct=Math.max(2,Math.round(risk*100));
    return '<div class="axis"><span class="nm">'+esc(k)+'</span><span class="bar-track"><span class="bar-fill" style="width:'+pct+'%"></span></span><span class="mono" style="min-width:46px;color:var(--gold)">'+num(risk,2)+'</span><span class="why">'+esc(String(a.why||a.source||'').slice(0,72))+'</span></div>';
  }).join('');
  const trace={formula_trace:d.formula_trace,receipt:d.receipt,doctrine:d.doctrine};
  document.getElementById('risk-trace').textContent=JSON.stringify(trace,null,2);
  _provHud.risk=d;
}

/* ---------- 4 · FORECAST ---------- */
async function loadForecast(){
  const d=await getJSON('/maritime/forecast');
  if(d.__error){document.getElementById('fc-vessel').textContent='error: '+d.__error;return;}
  const v=d.vessel||{};const lk=d.last_known||{};
  document.getElementById('fc-vessel').textContent='Sample: '+(v.name||v.mmsi||'vessel')+' · '+(v.status||'');
  document.getElementById('fc-method').textContent=(d.method||'').slice(0,52);
  const track=d.projected_track||[];const lastpt=track[track.length-1]||{};
  document.getElementById('fc-kpis').innerHTML=
    kpi('Horizon',num(d.horizon_h,0)+' h','teal')+
    kpi('Last known','('+num(lk.lat,2)+', '+num(lk.lon,2)+')','','spd '+num(lk.speed_kn,1)+' kn')+
    kpi('End uncertainty',num(lastpt.uncertainty_radius_nm,0)+' nm','warn','radius @ horizon')+
    kpi('Label','<span class="pill p-forecast">FORECAST</span>','');
  document.getElementById('fc-rows').innerHTML=(track.length?track.map(p=>
    '<tr><td class="mono">+'+num(p.t_plus_h,0)+'h</td><td class="mono">'+num(p.lat,3)+'</td><td class="mono">'+num(p.lon,3)+'</td><td class="mono">'+num(p.uncertainty_radius_nm,1)+'</td><td class="mono">'+num(p.confidence,2)+'</td></tr>'
  ).join(''):'<tr><td colspan="5" class="loading">no track</td></tr>');
  _provHud.forecast=d;
}

/* ---------- 5 · ASW ---------- */
async function loadASW(){
  const o=await getJSON('/asw/osint');
  const ob=document.getElementById('osint-rows');
  if(o.__error){ob.innerHTML='<div class="loading">error: '+esc(o.__error)+'</div>';}
  else{
    document.getElementById('osint-mode').textContent=(o.live?'OSINT-LIVE':'CACHED');
    const items=o.items||[];
    ob.innerHTML=items.length?items.slice(0,6).map(it=>
      '<div class="frow"><div class="ttl"><a href="'+esc(it.url||'#')+'" target="_blank" rel="noopener">'+esc(it.title||'—')+'</a></div><div class="meta">'+esc((it.published||'').slice(0,16))+' · '+esc(it.source||'public naval reporting')+'</div><div class="sum">'+esc(String(it.summary||'').slice(0,150))+'…</div></div>'
    ).join(''):'<div class="loading">no current OSINT items</div>';
    _provHud.osint=o;
  }
  const f=await getJSON('/asw/forecast');
  const fb=document.getElementById('aswfc-body');
  if(f.__error){fb.innerHTML='<div class="loading">error: '+esc(f.__error)+'</div>';}
  else{
    const areas=f.probability_field||f.areas||f.fields||f.items||[];
    fb.innerHTML='<div class="mono dim" style="font-size:10px;margin-bottom:.5rem">'+esc(String(f.label||f.product||'FORECAST — probability field').slice(0,90))+'</div>'+
      (Array.isArray(areas)&&areas.length?'<table class="dtbl"><thead><tr><th>Area / corridor</th><th>Class</th><th>Prob</th></tr></thead><tbody>'+
      areas.slice(0,8).map(a=>'<tr><td>'+esc(a.area||a.name||a.corridor||a.label||'—')+'</td><td class="mono">'+esc(a.vessel_class||a.class||'—')+'</td><td class="mono">'+num(a.probability!=null?a.probability:a.prob,2)+'</td></tr>').join('')+'</tbody></table>'
      :'<div class="loading">model projection (probability field) — see raw status</div>');
    _provHud.aswforecast=f;
  }
  const n=await getJSON('/asw/negative-space');
  const nb=document.getElementById('negspace-body');
  if(n.__error){nb.innerHTML='<div class="loading">error: '+esc(n.__error)+'</div>';}
  else{
    const cells=n.cells||n.areas||n.items||n.gaps||[];
    nb.innerHTML='<div class="mono dim" style="font-size:10px;margin-bottom:.5rem">'+esc(String(n.label||'INFERENCE — absence-of-AIS advisory over REAL surface density').slice(0,110))+'</div>'+
      (Array.isArray(cells)&&cells.length?'<div class="tbl-scroll"><table class="dtbl"><thead><tr><th>Region</th><th>AIS density</th><th>Inference</th></tr></thead><tbody>'+
      cells.slice(0,8).map(c=>'<tr><td>'+esc(c.region||c.area||c.cell||'—')+'</td><td class="mono">'+num(c.density!=null?c.density:c.ais_density,2)+'</td><td class="dim">'+esc(String(c.inference||c.note||c.why||'—').slice(0,60))+'</td></tr>').join('')+'</tbody></table></div>'
      :'<div class="loading">negative-space inference — see raw status</div>');
    _provHud.negspace=n;
  }
  const st=await getJSON('/asw/status');
  document.getElementById('asw-honest').innerHTML='<b>HONEST LIMITS</b> — '+esc(st.honest_limits||'Submarines do not broadcast AIS; no public live submarine track feed; we never fabricate a live submarine track. OSINT-LIVE / FORECAST / INFERENCE are advisory, human-on-the-loop.');
  _provHud.aswstatus=st;
}

/* ---------- live banner ---------- */
function setLiveBanner(){
  const anyLive=(_provHud.vessels&&_provHud.vessels.live)||(_provHud.osint&&_provHud.osint.live);
  document.getElementById('tb-live').textContent=anyLive?'LIVE FEEDS · RT':'SAMPLE · RT';
}

/* ---------- 7 · PROVENANCE HUD ---------- */
async function loadHud(){
  const fs=await getJSON('/feeds/realdata/status');
  const grid=document.getElementById('hud-feeds');
  const feeds=[];
  if(_provHud.vessels){feeds.push(['AIS vessels',_provHud.vessels.live,(((_provHud.vessels.sources_tried||[]).find(x=>x.ok)||{}).source)||'AIS chain',(_provHud.vessels.fetched_at||'').slice(11,19)]);}
  if(_provHud.dark){feeds.push(['Dark-fleet',(_provHud.dark.ingest||[]).some(i=>i.feed_live),'correlation over REAL AIS',(_provHud.dark.fetched_at||'').slice(11,19)]);}
  if(_provHud.spoof){feeds.push(['AIS-spoof',(_provHud.spoof.ingest||[]).some(i=>i.feed_live),'correlation over REAL AIS',(_provHud.spoof.fetched_at||'').slice(11,19)]);}
  if(_provHud.risk){feeds.push(['Λ risk',true,'13-axis Λ (Conjecture 1)',(_provHud.risk.ts_utc||'').slice(11,19)]);}
  if(_provHud.osint){feeds.push(['ASW OSINT',_provHud.osint.live,((_provHud.osint.sources_tried||[]).find(x=>x.ok)||{}).source||'USNI/Naval News',''])}
  grid.innerHTML=feeds.map(f=>'<div class="hud-feed"><div class="fn">'+modePill(f[1])+' '+esc(f[0])+'</div><div class="src">'+esc(String(f[2]).slice(0,40))+(f[3]?' · ts '+esc(f[3]):'')+'</div></div>').join('')||'<div class="hud-feed dim">feeds loading…</div>';
  // DSSE receipts (re-hashable)
  const recs=[];
  if(_provHud.risk&&_provHud.risk.receipt){const r=_provHud.risk.receipt;recs.push(['Λ risk verdict',r]);}
  document.getElementById('hud-receipts').innerHTML=recs.length?recs.map(rr=>{
    const r=rr[1];const sha=r.receipt_digest_sha256||'—';
    return '<div style="margin:.4rem 0"><span class="mono dim">⛯ '+esc(rr[0])+'</span> — receipt <span class="mono" style="color:var(--teal)">'+esc(r.receipt_id||'—')+'</span> · digest <span class="mono dim">'+esc(String(sha).slice(0,18))+'…</span> · signed '+(r.signed?'<span class="pill p-live">YES</span>':'<span class="pill p-sample">NO</span>')+' · keyid '+esc(r.keyid||'—')+' <span class="mono dim">(re-hashable: re-canonicalize payload, SHA-256 to match)</span></div>';
  }).join(''):'<div class="dim mono" style="font-size:11px">Each governed judgment above carries a DSSE receipt in its raw panel (re-hashable offline).</div>';
  _provHud.feeds_status=fs;
}

/* ---------- boot ---------- */
(async function(){
  await loadStats();
  await loadVessels();
  loadDark();loadSpoof();loadRisk();loadForecast();loadASW();
  setTimeout(loadHud,2600);
})();
</script>
</body>
</html>"""


async def _maritime_intel(request):
    return HTMLResponse(_PAGE)


def register(app, ns="killinchu"):
    """ADDITIVE. Mount the unified Maritime Intel view BEFORE the SPA catch-all.
    Pure VIEW — reuses the REAL maritime endpoints; reinvents no backend."""
    routes = [
        Route("/elite/maritime", _maritime_intel, methods=["GET"],
              name="%s_elite_maritime" % ns),
        Route("/maritime-intel", _maritime_intel, methods=["GET"],
              name="%s_maritime_intel_alias" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "view": "maritime_view",
            "routes": ["/elite/maritime", "/maritime-intel"],
            "doctrine": _DOCTRINE, "lean": _LEAN, "locked": _LOCKED}
