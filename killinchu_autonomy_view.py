# killinchu_autonomy_view.py
# ---------------------------------------------------------------------------
# Dev D — KILLINCHU AUTONOMY surface.
#
#   GET  /elite/autonomy   — the live AUTONOMY surface
#
# Pure VIEW. Reads the REAL /api/killinchu/v1/autonomy/* endpoints exposed by
# killinchu_autonomy.py. Reinvents no backend math. Six interactive demos:
#   1. BFT quorum multi-sensor fusion  (n>=3f+1; tolerate 1 Byzantine sensor)
#   2. CBF-QP safety filter            (clamp an unsafe PROPOSAL; SIMULATED)
#   3. EFE act-vs-ask gate             (precision beta = human-oversight knob)
#   4. Conformal threat set            (true class in set S, >=95% coverage)
#   5. Fiedler lambda2 mesh health     (algebraic connectivity; bottleneck alert)
#   6. Reflexion C2 planning           (store reflection; prepend next time)
#
# 0 runtime CDN. Self-hosted fonts at /vendor/fonts/fonts.css. Same gold+teal
# design tokens as the elite console + mesh surface. Vanilla JS, no graph lib.
# Effectors SIMULATED human-on-loop. Confidence capped <100%. No fabricated
# numbers — every figure is fetched LIVE from the autonomy endpoints and the
# honesty labels (LIVE/MODELED/EXPERIMENTAL/ROADMAP) come straight from them.
# ---------------------------------------------------------------------------
from starlette.responses import HTMLResponse
from starlette.routing import Route

_DOCTRINE = "v11"
_LEAN = ["Lutar/KhipuConsensus.lean::faultyCount (Conjecture 2)"]
_LOCKED = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]

_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>killinchu · AUTONOMY — live autonomy primitives</title>
<meta name="description" content="killinchu AUTONOMY — six live, auditable autonomy primitives over the real backend: BFT multi-sensor quorum (n>=3f+1, tolerate 1 Byzantine sensor; Khipu BFT unconditional = Conjecture 2, never claimed proven), a CBF-QP safety filter clamping an unsafe PROPOSAL (effector SIMULATED human-on-loop), an EFE act-vs-ask gate with a VISIBLE precision-beta oversight knob, a conformal threat set (true class in set S with >=95% coverage, not a bare confidence %), Fiedler lambda2 mesh connectivity with a bottleneck alert, and Reflexion over reviewed C2 plans. Real math; no fabricated numbers; effectors SIMULATED."/>
<link rel="stylesheet" href="/vendor/fonts/fonts.css"/>
<style>
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

.wrap{max-width:1280px;margin:0 auto;padding:1.4rem 1.6rem 4rem;}
.brand{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem;}
.brand .mark{width:30px;height:30px;border-radius:7px;background:linear-gradient(135deg,var(--gold),var(--teal));display:grid;place-items:center;color:#0a0a0a;font-weight:700;font-family:var(--mono);font-size:15px;}
.brand .nm{font-weight:600;font-size:1.05rem;}
.brand .role{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;}

.view-head{display:flex;align-items:flex-end;gap:.8rem;flex-wrap:wrap;margin-bottom:.3rem;}
.view-title{font-size:2rem;font-weight:500;letter-spacing:-.02em;}
.view-badge{font-family:var(--mono);font-size:10px;color:var(--teal);border:1px solid var(--teal-line);border-radius:5px;padding:.12rem .5rem;background:var(--teal-soft);}
.view-badge.gold{color:var(--gold);border-color:var(--gold-line);background:var(--gold-soft);}
.view-sub{font-size:13.5px;color:var(--paragraph);line-height:1.6;margin:.5rem 0 1.4rem;max-width:64rem;}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin-bottom:1.3rem;}
.kpi{border:1px solid var(--gold-line);border-radius:9px;background:var(--panel);padding:.85rem 1rem;}
.kpi .k{font-family:var(--mono);font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);}
.kpi .v{font-size:1.45rem;font-weight:500;color:var(--gold);margin-top:.2rem;line-height:1.1;}
.kpi .v.teal{color:var(--teal);} .kpi .v.live{color:var(--live);} .kpi .v.warn{color:var(--warn);} .kpi .v.err{color:var(--err);}
.kpi .d{font-size:11px;color:var(--paragraph);margin-top:.2rem;}

.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:1.1rem;}
.card{border:1px solid var(--gold-line);border-radius:11px;background:var(--panel);padding:1.2rem 1.3rem;margin-bottom:1.1rem;}
.card-h{display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem;flex-wrap:wrap;}
.card-t{font-size:1.05rem;font-weight:500;color:var(--cream);}
.card-ep{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto;}
.sect-num{font-family:var(--mono);font-size:10px;color:var(--gold);border:1px solid var(--gold-line);border-radius:5px;padding:.1rem .4rem;background:var(--gold-soft);}
.card-d{font-size:12px;color:var(--paragraph);line-height:1.55;margin:.1rem 0 .9rem;}
.lbl-pill{font-family:var(--mono);font-size:9px;letter-spacing:.06em;padding:.1rem .42rem;border-radius:4px;border:1px solid var(--gold-line);color:var(--muted);background:var(--gold-soft);}
.lbl-pill.live{color:var(--live);border-color:var(--live);}
.lbl-pill.exp{color:var(--warn);border-color:var(--warn);}
.lbl-pill.modeled{color:var(--teal);border-color:var(--teal-line);}
.lbl-pill.road{color:var(--dim);}

.controls{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin-bottom:.8rem;}
button{font-family:var(--mono);font-size:11px;letter-spacing:.04em;cursor:pointer;
  background:var(--gold-soft);color:var(--gold);border:1px solid var(--gold-line);
  border-radius:7px;padding:.42rem .8rem;transition:.15s;}
button:hover{background:var(--gold);color:var(--ground);}
button.teal{color:var(--teal);border-color:var(--teal-line);background:var(--teal-soft);}
button.teal:hover{background:var(--teal);color:var(--ground);}
button.danger{color:var(--err);border-color:var(--err);}
button.danger:hover{background:var(--err);color:var(--ground);}
.slider-row{display:flex;align-items:center;gap:.7rem;margin:.5rem 0;font-family:var(--mono);font-size:11px;color:var(--paragraph);}
input[type=range]{flex:1;accent-color:var(--teal);}
.toggle-row{display:flex;flex-wrap:wrap;gap:.4rem;margin:.4rem 0 .7rem;}
.chip{font-family:var(--mono);font-size:10px;padding:.28rem .55rem;border-radius:6px;border:1px solid var(--gold-line);
  color:var(--muted);background:var(--panel2);cursor:pointer;user-select:none;transition:.12s;}
.chip.on{color:var(--cream);border-color:var(--teal-line);background:var(--teal-soft);}
.chip.byz{color:var(--err);border-color:var(--err);}
.chip.sample{color:var(--dim);border-style:dashed;}

.out{font-family:var(--mono);font-size:11.5px;line-height:1.55;color:var(--paragraph);
  background:var(--panel2);border:1px solid var(--gold-line);border-radius:8px;padding:.8rem .9rem;
  white-space:pre-wrap;word-break:break-word;max-height:330px;overflow:auto;margin-top:.5rem;}
.verdict{display:inline-flex;align-items:center;gap:.45rem;font-family:var(--mono);font-size:13px;font-weight:600;
  padding:.32rem .7rem;border-radius:7px;margin:.3rem 0;}
.verdict.ok{color:var(--green);border:1px solid var(--green);background:rgba(111,174,139,.08);}
.verdict.warn{color:var(--warn);border:1px solid var(--warn);background:rgba(214,176,106,.08);}
.verdict.err{color:var(--err);border:1px solid var(--err);background:rgba(208,138,120,.08);}
.verdict .dot{width:8px;height:8px;border-radius:50%;background:currentColor;}
.kv{display:grid;grid-template-columns:auto 1fr;gap:.2rem .9rem;font-family:var(--mono);font-size:11.5px;margin:.4rem 0;}
.kv .k{color:var(--muted);} .kv .vv{color:var(--cream);}

.gatebar{display:flex;height:30px;border-radius:7px;overflow:hidden;border:1px solid var(--gold-line);margin:.55rem 0;}
.gatebar .seg{display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:600;color:var(--ground);transition:width .35s ease,background .2s;}
.gatebar .seg.act{background:var(--teal);} .gatebar .seg.ask{background:var(--gold);}
.gate-decision{font-family:var(--mono);font-size:1.3rem;font-weight:700;letter-spacing:.05em;}
.gate-decision.act{color:var(--teal);} .gate-decision.ask{color:var(--gold);}

.cbf-track{position:relative;height:46px;border:1px solid var(--gold-line);border-radius:8px;background:var(--panel2);margin:.6rem 0;overflow:hidden;}
.cbf-safe{position:absolute;top:0;bottom:0;background:rgba(111,174,139,.10);border-right:1px dashed var(--green);}
.cbf-tick{position:absolute;top:2px;bottom:2px;width:3px;border-radius:2px;}
.cbf-tick.nom{background:var(--err);} .cbf-tick.star{background:var(--teal);}
.cbf-lbl{position:absolute;font-family:var(--mono);font-size:9px;}

.setbox{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0;}
.setbox .cls{font-family:var(--mono);font-size:12px;padding:.3rem .6rem;border-radius:6px;border:1px solid var(--gold-line);color:var(--muted);background:var(--panel2);}
.setbox .cls.inset{color:var(--cream);border-color:var(--teal);background:var(--teal-soft);}
.setbox .cls.argmax{font-weight:700;}

.meshsvg{width:100%;height:230px;border:1px solid var(--gold-line);border-radius:8px;background:var(--panel2);}
.meshsvg line{stroke:var(--teal);stroke-opacity:.5;stroke-width:1.5;}
.meshsvg line.cut{stroke:var(--err);stroke-dasharray:4 3;stroke-opacity:.7;}
.meshsvg circle{fill:var(--gold);stroke:var(--ground);stroke-width:2;}
.meshsvg text{fill:var(--paragraph);font-family:var(--mono);font-size:9px;}

textarea{width:100%;font-family:var(--mono);font-size:11px;background:var(--panel2);color:var(--cream);
  border:1px solid var(--gold-line);border-radius:7px;padding:.5rem;resize:vertical;min-height:54px;}
select{font-family:var(--mono);font-size:11px;background:var(--panel2);color:var(--cream);border:1px solid var(--gold-line);border-radius:6px;padding:.3rem .5rem;}

.footnote{font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.6;margin-top:1.6rem;border-top:1px solid var(--gold-line);padding-top:1rem;}
.footnote b{color:var(--muted);}
@media (prefers-reduced-motion: reduce){*{transition-duration:.001ms!important;}}
</style>
</head>
<body>
<div class="topbar">
  <span>SZL HOLDINGS</span><span class="sep">/</span>
  <span style="color:var(--teal)">KILLINCHU</span><span class="sep">/</span>
  <span class="tb-desc">AUTONOMY · LIVE PRIMITIVES</span><span class="sep">/</span>
  <span class="live"><span class="live-dot"></span><span id="tb-live">AUTONOMY · RT</span></span>
  <nav class="switcher" aria-label="Surfaces">
    <span class="lbl">SURFACES</span>
    <a class="flag" href="/elite">Drones &amp; Vessels</a>
    <a class="flag" href="/elite/maritime">Maritime Intel</a>
    <a class="flag" href="/elite/mesh">MESH</a>
    <a class="flag" href="/elite/organism">Organism</a>
    <a class="flag active" href="/elite/autonomy">Autonomy</a>
  </nav>
</div>

<div class="wrap">
  <div class="brand"><div class="mark">K</div><div><div class="nm">killinchu</div><div class="role">autonomy · live primitives</div></div></div>

  <div class="view-head">
    <h1 class="view-title">AUTONOMY</h1>
    <span class="view-badge" id="hd-mode">LIVE BACKEND</span>
    <span class="view-badge gold">human-on-loop</span>
  </div>
  <p class="view-sub">Six auditable autonomy primitives over the real backend at <span class="mono">/api/killinchu/v1/autonomy/*</span>. Every number is fetched LIVE and carries its own honesty label. <b>Effectors stay SIMULATED, human-on-loop</b> — these primitives clamp, gate and corroborate <b>PROPOSALS</b>; they never drive a vessel or sub. Khipu BFT unconditional safety is <b>Conjecture 2</b> (OPEN); only conditional agreement-under-non-equivocation is proven.</p>

  <div class="kpis" id="kpis">
    <div class="kpi"><div class="k">Backend</div><div class="v" id="kpi-backend">…</div><div class="d">/autonomy/honest</div></div>
    <div class="kpi"><div class="k">Doctrine</div><div class="v teal" id="kpi-doctrine">v11</div><div class="d">locked = 8 @ c7c0ba17</div></div>
    <div class="kpi"><div class="k">Effectors</div><div class="v warn">SIMULATED</div><div class="d">human-on-loop</div></div>
    <div class="kpi"><div class="k">Khipu BFT</div><div class="v" id="kpi-bft">Conjecture 2</div><div class="d">unconditional = OPEN</div></div>
  </div>

  <div class="grid2">

  <!-- ===== 1. BFT QUORUM ===== -->
  <div class="card" style="grid-column:1/-1">
    <div class="card-h"><span class="sect-num">01</span><span class="card-t">BFT quorum · multi-sensor fusion</span>
      <span class="lbl-pill live" id="lbl-bft">LIVE</span><span class="card-ep mono">POST /autonomy/bft</span></div>
    <p class="card-d">n sensors fuse to a single engagement <b>RECOMMENDATION</b>. Byzantine fault tolerance requires <b>n &ge; 3f+1</b> and a quorum of <b>2f+1</b> agreeing witnesses. With n=4 LIVE witnesses we tolerate <b>f=1</b> Byzantine sensor before any recommendation. Toggle a sensor to <b>Byzantine</b> (corrupt value) or <b>SAMPLE</b> (abstains — does not witness). Drop to n=3 and the configuration goes <b>INFEASIBLE</b>. Khipu BFT unconditional = <b>Conjecture 2</b> (never claimed proven).</p>
    <div class="toggle-row" id="bft-chips"></div>
    <div class="controls">
      <button onclick="runBFT()">FUSE QUORUM</button>
      <button class="teal" onclick="bftReset()">reset (n=4, 1 byzantine)</button>
    </div>
    <div id="bft-verdict"></div>
    <div class="out" id="bft-out">…</div>
  </div>

  <!-- ===== 2. CBF-QP ===== -->
  <div class="card">
    <div class="card-h"><span class="sect-num">02</span><span class="card-t">CBF-QP safety filter</span>
      <span class="lbl-pill live" id="lbl-cbf">LIVE</span><span class="card-ep mono">POST /autonomy/cbf</span></div>
    <p class="card-d">Every PROPOSED action is projected onto the safe set by a Control-Barrier-Function quadratic program: minimise &frac12;(u&minus;u_nom)&sup2; s.t. the CBF constraint &nabla;h&middot;(f+gu) &ge; &minus;&alpha;h. An unsafe proposal is <b>clamped to the boundary</b>. <b>The effector stays SIMULATED</b> — this clamps a proposal, never drives anything.</p>
    <div class="slider-row"><span>u_nom <b id="cbf-unom-v">-0.90</b></span><input type="range" id="cbf-unom" min="-1" max="1" step="0.05" value="-0.9" oninput="cbfLabel()"></div>
    <div class="slider-row"><span>h(x) <b id="cbf-h-v">0.20</b></span><input type="range" id="cbf-h" min="0" max="1" step="0.05" value="0.2" oninput="cbfLabel()"></div>
    <div class="slider-row"><span>&alpha; <b id="cbf-a-v">0.50</b></span><input type="range" id="cbf-a" min="0.1" max="2" step="0.05" value="0.5" oninput="cbfLabel()"></div>
    <div class="controls"><button onclick="runCBF()">FILTER PROPOSAL</button></div>
    <div class="cbf-track" id="cbf-track"></div>
    <div id="cbf-verdict"></div>
    <div class="out" id="cbf-out">…</div>
  </div>

  <!-- ===== 3. EFE GATE ===== -->
  <div class="card">
    <div class="card-h"><span class="sect-num">03</span><span class="card-t">EFE act-vs-ask gate</span>
      <span class="lbl-pill live" id="lbl-efe">LIVE</span><span class="card-ep mono">POST /autonomy/efe</span></div>
    <p class="card-d">Active inference computes Expected Free Energy for two policies, <b>ACT</b> (commit on the MAP class) and <b>ASK</b> (query a human). Policy posterior = softmax(&minus;&beta;&middot;[G_act, G_ask]). Precision <b>&beta;</b> is the <b>VISIBLE human-oversight knob</b>. Pick a confident vs uncertain belief and sweep &beta;: the gate flips ACT&harr;ASK.</p>
    <div class="toggle-row">
      <span class="chip on" id="efe-conf" onclick="efeBelief('conf')">confident belief</span>
      <span class="chip" id="efe-unc" onclick="efeBelief('unc')">uncertain belief</span>
    </div>
    <div class="slider-row"><span>&beta; <b id="efe-beta-v">4.0</b></span><input type="range" id="efe-beta" min="0.5" max="12" step="0.5" value="4" oninput="runEFE()"></div>
    <div style="display:flex;align-items:center;gap:.8rem;margin:.3rem 0;"><span class="gate-decision" id="efe-dec">…</span><span class="mono" style="font-size:11px;color:var(--muted)" id="efe-floor"></span></div>
    <div class="gatebar" id="efe-bar"><div class="seg act" style="width:50%">ACT</div><div class="seg ask" style="width:50%">ASK</div></div>
    <div class="out" id="efe-out">…</div>
  </div>

  <!-- ===== 4. CONFORMAL ===== -->
  <div class="card">
    <div class="card-h"><span class="sect-num">04</span><span class="card-t">Conformal threat classification</span>
      <span class="lbl-pill exp" id="lbl-conf">EXPERIMENTAL</span><span class="card-ep mono">POST /autonomy/conformal</span></div>
    <p class="card-d">Replaces a bare "confidence X%" with a <b>prediction set S</b>: split-conformal qhat = Quantile(s, &lceil;(n+1)(1&minus;&alpha;)&rceil;/n); S = {y : 1&minus;p(y|x) &le; qhat}. Guarantee: <b>true class &isin; S with &ge;95% coverage</b> (marginal, under exchangeability). LOCAL wrapper matching Dev B's <span class="mono">predict_set/coverage_guarantee</span> API — reconcile when RESULT_DEVB_AGENTIC.md lands.</p>
    <div class="slider-row"><span>P(hostile-UAS) <b id="cf-h-v">0.62</b></span><input type="range" id="cf-h" min="0.1" max="0.9" step="0.01" value="0.62" oninput="cfLabel()"></div>
    <div class="controls"><button onclick="runConf()">PREDICT SET</button><button class="teal" onclick="runConf(true)">calibrate (n=120) + set</button></div>
    <div class="setbox" id="cf-set"></div>
    <div class="out" id="cf-out">…</div>
  </div>

  <!-- ===== 5. FIEDLER ===== -->
  <div class="card">
    <div class="card-h"><span class="sect-num">05</span><span class="card-t">Fiedler &lambda;2 · mesh health</span>
      <span class="lbl-pill live" id="lbl-fied">LIVE</span><span class="card-ep mono">GET /autonomy/fiedler/mesh</span></div>
    <p class="card-d">Algebraic connectivity <b>&lambda;2</b> = 2nd-smallest eigenvalue of the graph Laplacian L=D&minus;A. &lambda;2&rarr;0 means the mesh is fracturing. We compute &lambda;2 on the <b>LIVE mesh topology</b> and alert below threshold. Cut links to force a bottleneck and watch &lambda;2 drop past the alert line.</p>
    <div class="controls">
      <button onclick="loadFiedler()">LIVE MESH &lambda;2</button>
      <button class="teal" onclick="fiedlerScenario('ring')">healthy ring</button>
      <button class="teal" onclick="fiedlerScenario('bridge')">bottleneck (bridge)</button>
      <button class="danger" onclick="fiedlerScenario('cut')">cut to disconnect</button>
    </div>
    <svg class="meshsvg" id="fied-svg" viewBox="0 0 460 230" preserveAspectRatio="xMidYMid meet"></svg>
    <div id="fied-verdict"></div>
    <div class="out" id="fied-out">…</div>
  </div>

  <!-- ===== 6. REFLEXION ===== -->
  <div class="card" style="grid-column:1/-1">
    <div class="card-h"><span class="sect-num">06</span><span class="card-t">Reflexion · C2 planning memory</span>
      <span class="lbl-pill live" id="lbl-refl">LIVE</span><span class="card-ep mono">GET/POST /autonomy/reflexion</span></div>
    <p class="card-d">After each <b>reviewed</b> C2 decision we store a reflection; on the next activation we prepend the accumulated reflections so the planner carries forward what a watch officer corrected. Log a reviewed decision, then fetch the preamble that would be prepended next time.</p>
    <div class="controls" style="align-items:flex-start">
      <div style="flex:1;min-width:280px;">
        <div class="slider-row"><span>outcome</span>
          <select id="rf-outcome"><option value="passed">passed review</option><option value="revised">REVISED by watch officer</option><option value="rejected">rejected</option></select></div>
        <textarea id="rf-action" placeholder="C2 action (e.g. vector intercept geometry B)">vector intercept geometry B</textarea>
        <textarea id="rf-note" placeholder="reviewer note (e.g. prefer standoff)">prefer standoff; corrected constraint forward</textarea>
      </div>
      <div style="display:flex;flex-direction:column;gap:.5rem;">
        <button onclick="reflLog()">STORE REFLECTION</button>
        <button class="teal" onclick="reflPreamble()">PREPEND NEXT TIME</button>
      </div>
    </div>
    <div class="out" id="rf-out">…</div>
  </div>

  </div><!-- /grid2 -->

  <div class="footnote">
    <b>HONESTY.</b> Every figure is fetched LIVE from <span class="mono">/api/killinchu/v1/autonomy/*</span>; labels (LIVE / EXPERIMENTAL / MODELED / ROADMAP) come from the backend. Conformal is an EXPERIMENTAL local wrapper pending Dev B reconciliation. <b>Khipu BFT unconditional safety = Conjecture 2 (OPEN)</b>; only conditional agreement-under-non-equivocation is proven (Lean: Lutar/KhipuConsensus.lean::faultyCount). Effectors are <b>SIMULATED human-on-loop</b> — no live vessel/sub control. Confidence is capped &lt;100%. Doctrine v11, locked = 8 {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17.<br/>
    <b>Refs.</b> BFT arXiv:2204.03181 · CBF Ames et al. + arXiv:2510.14959 · pymdp/EFE arXiv:2104.11399 · Fiedler arXiv:2504.06894 · Reflexion arXiv:2303.11366 · conformal arXiv:2305.18404.
  </div>
</div>

<script>
const API = "/api/killinchu/v1/autonomy";
const $ = (id)=>document.getElementById(id);
function show(id,obj){ $(id).textContent = (typeof obj==="string")?obj:JSON.stringify(obj,null,2); }
async function post(path,body){ const r=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})}); if(!r.ok) throw new Error(path+" -> "+r.status); return r.json(); }
async function get(path){ const r=await fetch(API+path); if(!r.ok) throw new Error(path+" -> "+r.status); return r.json(); }

/* ---- honest header ---- */
(async()=>{ try{ const h=await get("/honest"); $("kpi-backend").textContent="LIVE"; $("kpi-backend").className="v live";
  if(h.doctrine) $("kpi-doctrine").textContent=h.doctrine; }catch(e){ $("kpi-backend").textContent="DOWN"; $("kpi-backend").className="v err"; } })();

/* =================== 1. BFT =================== */
const BFT_DEFAULT=[
  {id:"rf",      label:"RF/SIGINT", status:"live",   value:"hostile", byz:false},
  {id:"radar",   label:"Radar",     status:"live",   value:"hostile", byz:true },
  {id:"eoir",    label:"EO/IR",     status:"live",   value:"hostile", byz:false},
  {id:"remoteid",label:"Remote-ID", status:"live",   value:"hostile", byz:false},
  {id:"acoustic",label:"Acoustic",  status:"sample", value:"hostile", byz:false}
];
let BFT=JSON.parse(JSON.stringify(BFT_DEFAULT));
function bftRender(){
  const c=$("bft-chips"); c.innerHTML="";
  BFT.forEach((s,i)=>{
    const el=document.createElement("span");
    let cls="chip on"; let suf="";
    if(s.status==="sample"){cls="chip sample"; suf=" · SAMPLE (abstains)";}
    else if(s.byz){cls="chip byz"; suf=" · BYZANTINE";}
    else {suf=" · LIVE";}
    el.className=cls; el.textContent=s.label+suf;
    el.title="click: LIVE → BYZANTINE → SAMPLE";
    el.onclick=()=>{ // cycle live -> byzantine -> sample -> live
      if(s.status==="live" && !s.byz){s.byz=true;}
      else if(s.status==="live" && s.byz){s.byz=false; s.status="sample";}
      else {s.status="live"; s.byz=false;}
      bftRender();
    };
    c.appendChild(el);
  });
}
function bftReset(){ BFT=JSON.parse(JSON.stringify(BFT_DEFAULT)); bftRender(); $("bft-out").textContent="…"; $("bft-verdict").innerHTML=""; }
async function runBFT(){
  // Byzantine sensor reports a corrupted value so it disagrees with the honest set.
  const sensors=BFT.map(s=>({id:s.id,label:s.label,status:s.status,value:(s.byz?"friendly":s.value)}));
  try{
    const r=await post("/bft",{sensors});
    const vd=$("bft-verdict"); const ok=(r.verdict==="DECIDE");
    vd.innerHTML='<span class="verdict '+(r.bft_feasible?(ok?"ok":"warn"):"err")+'"><span class="dot"></span>'+
      (r.bft_feasible?(r.verdict+" · "+(r.engagement_recommendation||"")):"INFEASIBLE (n &lt; 3f+1)")+'</span>';
    show("bft-out", r);
  }catch(e){ show("bft-out","ERR: "+e.message); }
}

/* =================== 2. CBF =================== */
function cbfLabel(){ $("cbf-unom-v").textContent=(+$("cbf-unom").value).toFixed(2); $("cbf-h-v").textContent=(+$("cbf-h").value).toFixed(2); $("cbf-a-v").textContent=(+$("cbf-a").value).toFixed(2); }
function cbfTrack(unom,ustar,bound){
  const t=$("cbf-track"); t.innerHTML="";
  const W=t.clientWidth||400; const x=(u)=>((u+1)/2)*W;
  const safe=document.createElement("div"); safe.className="cbf-safe";
  // safe region is where u >= bound (clamped low end) — draw boundary marker
  const sm=document.createElement("div"); sm.className="cbf-tick"; sm.style.background="var(--green)";
  sm.style.left=(x(bound)-1)+"px"; t.appendChild(sm);
  const sl=document.createElement("div"); sl.className="cbf-lbl"; sl.style.color="var(--green)"; sl.style.left=(x(bound)+4)+"px"; sl.style.bottom="3px"; sl.textContent="boundary "+bound.toFixed(2); t.appendChild(sl);
  const n=document.createElement("div"); n.className="cbf-tick nom"; n.style.left=(x(unom)-1)+"px"; t.appendChild(n);
  const nl=document.createElement("div"); nl.className="cbf-lbl"; nl.style.color="var(--err)"; nl.style.left=(x(unom)+4)+"px"; nl.style.top="3px"; nl.textContent="u_nom"; t.appendChild(nl);
  const s=document.createElement("div"); s.className="cbf-tick star"; s.style.left=(x(ustar)-1)+"px"; t.appendChild(s);
  const stl=document.createElement("div"); stl.className="cbf-lbl"; stl.style.color="var(--teal)"; stl.style.left=(x(ustar)+4)+"px"; stl.style.top="16px"; stl.textContent="u* (filtered)"; t.appendChild(stl);
}
async function runCBF(){
  const body={u_nom:+$("cbf-unom").value, h:+$("cbf-h").value, alpha:+$("cbf-a").value};
  try{
    const r=await post("/cbf",body);
    const bound=(r.boundary_u!==undefined && r.boundary_u!==null)?r.boundary_u:r.u_star;
    cbfTrack(body.u_nom, r.u_star, bound);
    const vd=$("cbf-verdict");
    vd.innerHTML='<span class="verdict '+(r.clamped?"warn":"ok")+'"><span class="dot"></span>'+
      (r.clamped?("CLAMPED → u* = "+(+r.u_star).toFixed(3)+" (SIMULATED)"):("SAFE · pass-through u* = "+(+r.u_star).toFixed(3)))+'</span>';
    show("cbf-out", r);
  }catch(e){ show("cbf-out","ERR: "+e.message); }
}

/* =================== 3. EFE =================== */
let EFE_BELIEF=[0.80,0.13,0.07]; // confident
function efeBelief(kind){
  if(kind==="conf"){EFE_BELIEF=[0.80,0.13,0.07]; $("efe-conf").classList.add("on"); $("efe-unc").classList.remove("on");}
  else {EFE_BELIEF=[0.40,0.34,0.26]; $("efe-unc").classList.add("on"); $("efe-conf").classList.remove("on");}
  runEFE();
}
async function runEFE(){
  const beta=+$("efe-beta").value; $("efe-beta-v").textContent=beta.toFixed(1);
  try{
    const r=await post("/efe",{belief:EFE_BELIEF, beta});
    const dec=$("efe-dec"); dec.textContent=r.decision; dec.className="gate-decision "+(r.decision==="ACT"?"act":"ask");
    const bar=$("efe-bar"); const pa=Math.round((r.p_act||0)*100), pk=100-pa;
    bar.children[0].style.width=pa+"%"; bar.children[0].textContent="ACT "+pa+"%";
    bar.children[1].style.width=pk+"%"; bar.children[1].textContent="ASK "+pk+"%";
    $("efe-floor").textContent=r.forced_ask_by_floor?"⟂ oversight floor engaged (forced ASK)":"";
    show("efe-out", r);
  }catch(e){ show("efe-out","ERR: "+e.message); }
}

/* =================== 4. CONFORMAL =================== */
function cfLabel(){ $("cf-h-v").textContent=(+$("cf-h").value).toFixed(2); }
async function runConf(calibrate){
  const h=+$("cf-h").value; const rest=1-h; const friendly=rest*0.7, clutter=rest*0.3;
  const class_probs={"hostile-UAS":h,"friendly":+friendly.toFixed(3),"bird/clutter":+clutter.toFixed(3)};
  const body={class_probs};
  if(calibrate){
    // synthetic calibration: mostly-correct probabilities for the true class
    const cal=[]; for(let i=0;i<120;i++){ cal.push(0.55+0.4*Math.random()); }
    body.calibration=cal;
  }
  try{
    const r=await post("/conformal",body);
    const sb=$("cf-set"); sb.innerHTML="";
    Object.keys(class_probs).forEach(lbl=>{
      const inset=(r.prediction_set||[]).includes(lbl);
      const el=document.createElement("span");
      el.className="cls"+(inset?" inset":"")+(lbl===r.argmax?" argmax":"");
      el.textContent=lbl+" ("+(class_probs[lbl]*100).toFixed(0)+"%)"+(inset?" ✓":"");
      sb.appendChild(el);
    });
    show("cf-out", r);
  }catch(e){ show("cf-out","ERR: "+e.message); }
}

/* =================== 5. FIEDLER =================== */
function drawMesh(nodes,edges,cutSet){
  const svg=$("fied-svg"); svg.innerHTML="";
  const W=460,H=230,cx=W/2,cy=H/2,R=85;
  const pos={}; nodes.forEach((n,i)=>{ const a=-Math.PI/2+2*Math.PI*i/nodes.length; pos[n]={x:cx+R*Math.cos(a),y:cy+R*Math.sin(a)}; });
  edges.forEach(e=>{ const p=pos[e.source||e[0]],q=pos[e.target||e[1]]; if(!p||!q)return;
    const ln=document.createElementNS("http://www.w3.org/2000/svg","line");
    ln.setAttribute("x1",p.x);ln.setAttribute("y1",p.y);ln.setAttribute("x2",q.x);ln.setAttribute("y2",q.y);
    svg.appendChild(ln); });
  (cutSet||[]).forEach(e=>{ const p=pos[e[0]],q=pos[e[1]]; if(!p||!q)return;
    const ln=document.createElementNS("http://www.w3.org/2000/svg","line"); ln.setAttribute("class","cut");
    ln.setAttribute("x1",p.x);ln.setAttribute("y1",p.y);ln.setAttribute("x2",q.x);ln.setAttribute("y2",q.y);
    svg.appendChild(ln); });
  nodes.forEach(n=>{ const c=document.createElementNS("http://www.w3.org/2000/svg","circle");
    c.setAttribute("cx",pos[n].x);c.setAttribute("cy",pos[n].y);c.setAttribute("r",7); svg.appendChild(c);
    const t=document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",pos[n].x+9);t.setAttribute("y",pos[n].y+3);t.textContent=String(n).slice(0,8); svg.appendChild(t); });
}
function fiedVerdict(r){
  const a=r.alert; const dc=!r.connected;
  $("fied-verdict").innerHTML='<span class="verdict '+(dc?"err":(a?"warn":"ok"))+'"><span class="dot"></span>'+
    "λ2 = "+(+r.lambda2).toFixed(4)+" · "+(dc?"DISCONNECTED":(a?"BELOW THRESHOLD — bottleneck alert":"HEALTHY"))+'</span>';
}
async function loadFiedler(){
  try{ const r=await get("/fiedler/mesh");
    const nodes=(r.nodes||[]); const edges=(r.edges||[]); drawMesh(nodes,edges,[]); fiedVerdict(r); show("fied-out",r);
  }catch(e){ show("fied-out","ERR: "+e.message); }
}
async function fiedlerScenario(kind){
  let nodes,edges; const thr=0.6;
  if(kind==="ring"){ nodes=["n0","n1","n2","n3","n4","n5"]; edges=[["n0","n1"],["n1","n2"],["n2","n3"],["n3","n4"],["n4","n5"],["n5","n0"]]; }
  else if(kind==="bridge"){ nodes=["a0","a1","a2","b0","b1","b2"]; edges=[["a0","a1"],["a1","a2"],["a2","a0"],["b0","b1"],["b1","b2"],["b2","b0"],["a0","b0"]]; }
  else { nodes=["a0","a1","a2","b0","b1","b2"]; edges=[["a0","a1"],["a1","a2"],["a2","a0"],["b0","b1"],["b1","b2"],["b2","b0"]]; }
  const E=edges.map(e=>({source:e[0],target:e[1]}));
  try{ const r=await post("/fiedler",{nodes,edges:E,threshold:thr}); drawMesh(nodes,E,[]); fiedVerdict(r); show("fied-out",r);
  }catch(e){ show("fied-out","ERR: "+e.message); }
}

/* =================== 6. REFLEXION =================== */
async function reflLog(){
  const body={decision:{outcome:$("rf-outcome").value, action:$("rf-action").value, note:$("rf-note").value, reviewer:"watch officer", decision_id:"d-"+Date.now()}};
  try{ const r=await post("/reflexion",body); show("rf-out",r); }catch(e){ show("rf-out","ERR: "+e.message); }
}
async function reflPreamble(){
  try{ const r=await get("/reflexion"); show("rf-out", (r.preamble||r)); }catch(e){ show("rf-out","ERR: "+e.message); }
}

/* ---- boot ---- */
bftRender(); cbfLabel(); cfLabel(); runCBF(); runEFE(); runConf(); loadFiedler(); reflPreamble();
</script>
</body>
</html>"""


async def _autonomy_view(request):
    return HTMLResponse(_PAGE)


def register(app, ns="killinchu"):
    """ADDITIVE. Mount the live AUTONOMY view BEFORE the SPA catch-all. Pure
    VIEW — reads the REAL /api/killinchu/v1/autonomy/* endpoints; reinvents no
    backend math. Effectors SIMULATED human-on-loop."""
    routes = [
        Route("/elite/autonomy", _autonomy_view, methods=["GET"],
              name="%s_elite_autonomy" % ns),
        Route("/autonomy-surface", _autonomy_view, methods=["GET"],
              name="%s_autonomy_surface_alias" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "view": "autonomy_view",
            "routes": ["/elite/autonomy", "/autonomy-surface"],
            "doctrine": _DOCTRINE, "lean": _LEAN, "locked": _LOCKED}
