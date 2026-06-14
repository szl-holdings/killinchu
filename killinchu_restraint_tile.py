# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11/v12
"""
killinchu_restraint_tile.py — the /elite "Restraint" tile (DEV-WIRE-K R3).

A self-contained, 0-CDN /elite/restraint page that renders the a11oy Restraint
capability AS SEEN FROM killinchu:
  * the 6-rung frugality ladder + lite/full/ultra intensities,
  * the deliberate-simplification `restraint:` ceilings + never-simplify list,
  * an HONEST MEASURED/SAMPLE/ROADMAP benchmark (read live from the SAME shared
    byte-identical szl_restraint.py mounted on killinchu — never a fabricated
    number), and
  * a live "evaluate" box that routes a code task through the ladder and shows
    the stopped-at rung + the SIGNED DSSE receipt (honest UNSIGNED marker when
    the in-image key is absent).

The page is cross-linked to a11oy's canonical /restraint surface (the capability
is a11oy's; killinchu mounts the SAME governed module — szl_restraint.py is
byte-identical across both apps, like szl_dsse.py / szl_conformal.py).

This module ONLY adds an HTTP surface (a page) + injects ONE nav link into the
/elite console via its OWN idempotent middleware. It does NOT register the
restraint API itself (serve.py does that with ns="killinchu" against the shared
szl_restraint.py) and it does NOT edit the elite console source file.

PROVENANCE: the ladder + intensities are ADOPTED from the open-source Ponytail
skill (MIT, © 2026 DietrichGebert, github.com/DietrichGebert/ponytail). a11oy/
killinchu add governance (signed DSSE receipts + advisory Λ) and honest
measurement. Ponytail's published numbers are CITED as Ponytail's, never ours.

ADDITIVE, try/except-guarded, BEFORE the SPA catch-all. Pure stdlib.
Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 · Λ = Conjecture 1 (OPEN, < 1.0)
· effectors SIMULATED · trust < 100% · 0 CDN · 0 visible codenames.
"""
from __future__ import annotations

A11OY_RESTRAINT_URL = "https://szlholdings-a11oy.hf.space/restraint"
PONYTAIL_REPO = "https://github.com/DietrichGebert/ponytail"


def _page_html(ns: str) -> str:
    return _PAGE.replace("__NS__", ns).replace("__A11OY__", A11OY_RESTRAINT_URL)


# 0-CDN, self-contained. Reads /api/<ns>/v1/restraint/{info,bench,evaluate} —
# the SAME shared szl_restraint.py mounted on killinchu by serve.py. All numbers
# are pulled live and rendered with their honest labels (MODELED/SAMPLE/ROADMAP/
# MEASURED); nothing is hard-coded as a savings claim.
_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Restraint — Governed Frugality Gate · killinchu</title>
<meta name="description" content="killinchu's view of a11oy Restraint: a governed, measured code-frugality ladder. Before emitting a diff the agent descends a 6-rung ladder (YAGNI, stdlib, native, installed dep, one line, then minimal code) and stops at the first rung that holds, marking deliberate simplifications with restraint: ceilings. Every decision is a signed DSSE receipt + advisory Lambda score; benchmark numbers are MEASURED only when actually run, else SAMPLE/ROADMAP. Ladder adopted from the open-source Ponytail skill (MIT); governance + measurement are SZL's. Shared byte-identical module across a11oy + killinchu."/>
<style>
:root{
  --ground:#0a0a0a; --panel:#0e0e0e; --panel2:#080808;
  --gold:#c9b787; --gold-bright:#d6c69a;
  --teal:#5fb3a3; --teal-soft:rgba(95,179,163,0.10);
  --cream:#f5f5f5; --paragraph:#9a9a9a; --muted:#888; --dim:#555;
  --gold-line:rgba(201,183,135,0.15); --gold-soft:rgba(201,183,135,0.04);
  --teal-line:rgba(95,179,163,0.22);
  --green:#39d98a; --yellow:#f5c451; --red:#ff6a5a; --blue:#5bc8ff;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --display:Georgia,'Times New Roman',serif;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--ground);color:var(--cream);font-family:var(--display);-webkit-font-smoothing:antialiased;}
.mono{font-family:var(--mono);}
a{color:var(--gold-bright);text-decoration:none;}
a:hover{text-decoration:underline;}
code{font-family:var(--mono);color:var(--gold-bright);font-size:.9em;}
.wrap{max-width:1080px;margin:0 auto;padding:1.2rem 1.1rem 4rem;}
.top{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;font-family:var(--mono);font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--gold);border-bottom:1px solid var(--gold-line);padding-bottom:.7rem;margin-bottom:1.3rem;}
.top .sep{color:var(--dim);}
h1{font-size:1.7rem;font-weight:500;margin:.2rem 0 .3rem;letter-spacing:.01em;}
h2{font-size:1.05rem;font-weight:500;color:var(--gold-bright);margin:1.8rem 0 .7rem;border-bottom:1px solid var(--gold-soft);padding-bottom:.3rem;}
.lede{color:var(--paragraph);font-size:1rem;line-height:1.55;max-width:74ch;}
.pill{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;padding:.18rem .5rem;border-radius:3px;border:1px solid var(--gold-line);color:var(--gold);background:var(--gold-soft);}
.pill.live{color:var(--green);border-color:rgba(57,217,138,.3);}
.pill.sample{color:var(--yellow);border-color:rgba(245,196,81,.3);}
.pill.roadmap{color:var(--blue);border-color:rgba(91,200,255,.3);}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.8rem;margin:.8rem 0;}
.card{background:var(--panel);border:1px solid var(--gold-line);border-radius:6px;padding:.9rem 1rem;}
.rung{display:flex;gap:.7rem;align-items:flex-start;padding:.55rem 0;border-bottom:1px solid var(--gold-soft);}
.rung:last-child{border-bottom:none;}
.rung .n{font-family:var(--mono);color:var(--gold);font-size:1.1rem;min-width:1.6rem;}
.rung .b{flex:1;}
.rung .name{color:var(--cream);font-size:.96rem;}
.rung .key{font-family:var(--mono);font-size:10px;color:var(--teal);text-transform:uppercase;letter-spacing:.08em;}
table{width:100%;border-collapse:collapse;font-size:.86rem;margin:.4rem 0;}
th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid var(--gold-soft);}
th{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:400;}
td.num{text-align:right;font-family:var(--mono);color:var(--gold-bright);}
.muted{color:var(--muted);}
.note{color:var(--paragraph);font-size:.84rem;line-height:1.5;border-left:2px solid var(--teal-line);padding:.3rem 0 .3rem .8rem;margin:.6rem 0;}
textarea,select,button{font-family:var(--mono);font-size:.85rem;background:var(--panel2);color:var(--cream);border:1px solid var(--gold-line);border-radius:4px;padding:.5rem;}
textarea{width:100%;min-height:62px;resize:vertical;}
button{cursor:pointer;background:var(--gold-soft);color:var(--gold-bright);letter-spacing:.05em;text-transform:uppercase;font-size:11px;padding:.5rem .9rem;}
button:hover{background:rgba(201,183,135,.12);}
pre{background:var(--panel2);border:1px solid var(--gold-line);border-radius:5px;padding:.8rem;overflow:auto;font-family:var(--mono);font-size:.8rem;color:var(--paragraph);max-height:340px;}
.kv{font-family:var(--mono);font-size:.8rem;color:var(--paragraph);}
.kv b{color:var(--gold-bright);font-weight:500;}
.verdict{font-family:var(--mono);font-size:.95rem;color:var(--green);}
.foot{margin-top:2.5rem;color:var(--dim);font-size:.78rem;line-height:1.6;border-top:1px solid var(--gold-soft);padding-top:1rem;}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <span>killinchu</span><span class="sep">·</span>
    <span>Restraint — Governed Frugality Gate</span><span class="sep">·</span>
    <span id="doctrineline">v11 LOCKED · &Lambda; Conjecture 1 · 0 CDN</span>
    <span class="sep">·</span><a href="/elite">&larr; /elite</a>
  </div>

  <h1>Restraint <span class="pill" id="sharedpill">shared module</span></h1>
  <p class="lede">
    <b>Restraint</b> is a <i>governed + measured</i> code-frugality gate. Before the
    code agent emits a diff it descends a <b>6-rung ladder</b> and stops at the first
    rung that holds, marking each deliberate simplification with a
    <code>restraint:</code> ceiling that names the upgrade path. Every decision becomes
    a <b>signed DSSE receipt</b> + an advisory <b>&Lambda;</b> trust score (Conjecture 1
    is OPEN; &Lambda; kept strictly &lt; 1.0). The capability lives on
    <a href="__A11OY__" target="_blank" rel="noopener">a11oy &rarr; /restraint</a>;
    killinchu mounts the <b>same byte-identical module</b> (<code>szl_restraint.py</code>,
    like <code>szl_dsse.py</code>) so the drift guard stays satisfied.
  </p>
  <p class="note">
    PROVENANCE — the ladder + lite/full/ultra intensities are <b>adopted</b> from the
    open-source <a href="https://github.com/DietrichGebert/ponytail" target="_blank" rel="noopener">Ponytail</a>
    coding-agent skill (MIT, &copy; 2026 DietrichGebert). Governance (signed receipts + &Lambda;)
    and on-our-stack measurement are SZL's. Ponytail's published numbers are CITED as
    Ponytail's, never claimed as ours.
  </p>

  <h2>The ladder <span class="pill">HEURISTIC reflex gate</span></h2>
  <div class="card"><div id="ladder">loading ladder&hellip;</div></div>
  <div class="grid">
    <div class="card">
      <div class="key mono" style="color:var(--teal);text-transform:uppercase;letter-spacing:.08em;font-size:10px">Intensities</div>
      <div id="intensities" class="kv">loading&hellip;</div>
    </div>
    <div class="card">
      <div class="key mono" style="color:var(--teal);text-transform:uppercase;letter-spacing:.08em;font-size:10px">Never simplify away</div>
      <div id="never" class="kv">loading&hellip;</div>
    </div>
  </div>

  <h2>Try it — route a code task through the ladder</h2>
  <div class="card">
    <textarea id="task" placeholder="e.g. add a cache for these API responses">add a cache for these API responses</textarea>
    <div style="display:flex;gap:.6rem;align-items:center;margin:.6rem 0;flex-wrap:wrap">
      <select id="intensity">
        <option value="lite">lite</option>
        <option value="full" selected>full</option>
        <option value="ultra">ultra</option>
      </select>
      <button id="run">evaluate</button>
      <span id="verdict" class="verdict"></span>
    </div>
    <div id="receiptline" class="kv"></div>
    <pre id="out" style="display:none"></pre>
  </div>

  <h2>Honest benchmark <span class="pill" id="benchlabel">&hellip;</span></h2>
  <p class="note" id="benchnote">
    Two arms (no-skill baseline vs Restraint) over five everyday tasks. Numbers read
    <b>MEASURED</b> only when a model run is wired on the Space; otherwise they are
    <b>SAMPLE</b> fixtures derived from our transparent ladder model and the bench is
    labelled <b>ROADMAP</b>. We never reprint Ponytail's numbers as ours.
  </p>
  <div class="card" style="overflow:auto"><table id="bench"><tbody><tr><td class="muted">loading bench&hellip;</td></tr></tbody></table></div>
  <div id="benchagg" class="kv" style="margin-top:.5rem"></div>
  <div class="card" style="margin-top:.7rem">
    <div class="key mono" style="color:var(--teal);text-transform:uppercase;letter-spacing:.08em;font-size:10px">Ponytail's published numbers — CITED, not ours</div>
    <div id="ponytail" class="kv">loading&hellip;</div>
  </div>

  <div class="foot">
    <div>Restraint capability: a11oy &middot; <a href="__A11OY__" target="_blank" rel="noopener">canonical /restraint surface &rarr;</a></div>
    <div>Shared module <code>szl_restraint.py</code> is byte-identical across a11oy + killinchu (same hf-sync lists, drift-guard enforced).</div>
    <div>Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 &middot; &Lambda; = Conjecture 1 (OPEN, advisory &lt; 1.0) &middot; effectors SIMULATED &middot; trust &lt; 100% &middot; 0 runtime CDN &middot; signed receipts.</div>
    <div>Ponytail (coding-agent skill, MIT, &copy; 2026 DietrichGebert): <a href="https://github.com/DietrichGebert/ponytail" target="_blank" rel="noopener">github.com/DietrichGebert/ponytail</a> &mdash; ladder + intensities adopted; governance + measurement are SZL's.</div>
  </div>
</div>

<script>
const NS = "__NS__";
const j = (s)=>{try{return JSON.stringify(s,null,2);}catch(e){return String(s);}};
async function getj(url, opts){ const r = await fetch(url, opts); if(!r.ok) throw new Error(url+" -> "+r.status); return r.json(); }

async function loadInfo(){
  try{
    const d = await getj("/api/"+NS+"/v1/restraint/info");
    const lad = document.getElementById("ladder");
    lad.innerHTML = (d.ladder||[]).map(r =>
      '<div class="rung"><div class="n mono">'+r.rung+'</div><div class="b"><div class="name">'+r.name+'</div><div class="key">rung '+r.rung+' &middot; '+r.key+'</div></div></div>'
    ).join("");
    const inten = d.intensities||{};
    document.getElementById("intensities").innerHTML =
      Object.keys(inten).map(k=>'<div><b>'+k+'</b> &mdash; '+inten[k]+'</div>').join("");
    document.getElementById("never").innerHTML =
      (d.never_simplify||[]).map(x=>'<div>&middot; '+x+'</div>').join("");
    if(d.doctrine){
      document.getElementById("doctrineline").textContent =
        d.doctrine.version+" LOCKED "+d.doctrine.locked+" @ "+d.doctrine.kernel_commit+" · Λ Conjecture 1 · "+d.doctrine.runtime_cdn+" CDN";
    }
    document.getElementById("sharedpill").classList.add("live");
    document.getElementById("sharedpill").textContent = "shared module · LIVE";
  }catch(e){
    document.getElementById("ladder").innerHTML = '<span class="muted">Restraint API PENDING on this Space ('+e.message+'). The shared module ships on next factory rebuild; numbers stay honest until then.</span>';
    const p = document.getElementById("sharedpill"); p.classList.add("sample"); p.textContent = "PENDING deploy";
  }
}

async function loadBench(){
  try{
    const d = await getj("/api/"+NS+"/v1/restraint/bench");
    const lbl = document.getElementById("benchlabel");
    lbl.textContent = d.overall_label || "ROADMAP";
    lbl.className = "pill " + (d.overall_label==="MEASURED" ? "live" : (d.overall_label==="ROADMAP"?"roadmap":"sample"));
    const tb = document.querySelector("#bench tbody");
    tb.innerHTML = '<tr><th>task</th><th>rung</th><th>baseline LOC</th><th>restraint LOC</th><th>LOC&minus;%</th><th>label</th></tr>' +
      (d.rows||[]).map(r =>
        '<tr><td>'+r.task.slice(0,46)+(r.task.length>46?"…":"")+'</td><td class="num">'+r.stopped_at_rung+'</td><td class="num">'+r.baseline.loc+'</td><td class="num">'+r.a11oy_restraint.loc+'</td><td class="num">'+r.loc_reduction_pct+'%</td><td><span class="pill '+(r.label==="MEASURED"?"live":"sample")+'">'+r.label+'</span></td></tr>'
      ).join("");
    const a = d.aggregate||{};
    document.getElementById("benchagg").innerHTML =
      '<b>median LOC reduction</b> '+a.median_loc_reduction_pct+'% &middot; <b>cost-proxy</b> '+a.median_cost_proxy_reduction_pct+'% &middot; <b>latency</b> '+a.median_latency_reduction_pct+'% &middot; <span class="muted">'+(d.overall_label==="MEASURED"?"measured on our stack":"SAMPLE/ROADMAP — derived from our ladder model, not a measured claim")+'</span>';
    const pn = d.ponytail_published||{};
    document.getElementById("ponytail").innerHTML =
      '<div><b>code</b> '+pn.code_reduction+' &middot; <b>cost</b> '+pn.cost_reduction+' &middot; <b>speed</b> '+pn.speed+'</div>'+
      '<div class="muted">'+(pn.basis||"")+' &mdash; '+(pn.label||"CITED")+'</div>';
  }catch(e){
    document.querySelector("#bench tbody").innerHTML = '<tr><td class="muted">Bench PENDING on this Space ('+e.message+'). Honest by construction: nothing is shown until the shared module is live.</td></tr>';
    const lbl = document.getElementById("benchlabel"); lbl.className="pill roadmap"; lbl.textContent="PENDING";
  }
}

document.getElementById("run").addEventListener("click", async ()=>{
  const task = document.getElementById("task").value || "";
  const intensity = document.getElementById("intensity").value;
  const v = document.getElementById("verdict"); v.textContent = "evaluating…";
  document.getElementById("receiptline").textContent = "";
  try{
    const d = await getj("/api/"+NS+"/v1/restraint/evaluate", {
      method:"POST", headers:{"content-type":"application/json"},
      body: JSON.stringify({task, intensity})
    });
    v.textContent = "rung "+d.stopped_at_rung+" ("+d.rung_key+") · Λ="+(d.lambda_score&&d.lambda_score.lambda)+" · saved≈"+(d.lines_saved_estimate&&d.lines_saved_estimate.lines_saved_modeled)+" LOC (MODELED)";
    const sr = d.signed_receipt;
    let rl;
    if(sr && (sr.signed===true || (sr.signatures&&sr.signatures.length&&sr.signatures[0].sig))){
      rl = '✓ SIGNED DSSE receipt &middot; keyid '+((sr.signatures&&sr.signatures[0]&&sr.signatures[0].keyid)||"in-image")+' &middot; '+(d.restraint_comment||"");
    } else {
      rl = '○ UNSIGNED (in-image key absent — receipt is honest, never fabricated) &middot; '+(d.restraint_comment||"");
    }
    document.getElementById("receiptline").innerHTML = rl;
    const out = document.getElementById("out"); out.style.display="block"; out.textContent = j(d);
  }catch(e){
    v.textContent = "PENDING: "+e.message;
  }
});

loadInfo(); loadBench();
</script>
</body>
</html>
"""


def register(app, ns: str = "killinchu"):
    from starlette.responses import HTMLResponse
    from starlette.middleware.base import BaseHTTPMiddleware as _Base
    from starlette.responses import Response as _SResp

    registered = []
    html = _page_html(ns)

    async def _page(request):
        return HTMLResponse(html)

    app.router.routes.insert(0, __import__("starlette.routing", fromlist=["Route"]).Route(
        "/elite/restraint", _page, methods=["GET"], name="%s_elite_restraint" % ns))
    app.router.routes.insert(0, __import__("starlette.routing", fromlist=["Route"]).Route(
        "/%s/elite/restraint" % ns, _page, methods=["GET"], name="%s_elite_restraint_ns" % ns))
    registered.append("GET /elite/restraint")

    # --- nav-link injector (OWNED by this module; does NOT edit the console file) ---
    # Mirrors the active-flux / operator-widget injector pattern: append ONE <a>
    # nav-item to the /elite console HTML right after a stable anchor. Idempotent.
    try:
        _NAV_MARK = b'data-view-restraint="restraint_gate"'
        _ANCHOR = b"MESH (live surface)</a>"
        _NAV_LINK = (
            b'<a class="nav-item" data-view-restraint="restraint_gate" href="/elite/restraint" '
            b'style="color:var(--gold-bright)" title="Restraint: a governed + measured code-frugality '
            b'ladder (6 rungs - YAGNI, stdlib, native, installed dep, one line, then minimal code). '
            b'Every decision is a signed DSSE receipt + advisory Lambda (Conjecture 1, < 1.0). Shared '
            b'byte-identical module with a11oy. Ladder adopted from Ponytail (MIT); governance + '
            b'measurement are ours. Bench is MEASURED only when run, else SAMPLE/ROADMAP.">'
            b'<span class="ico">&#9776;</span>Restraint (Frugality Gate)</a>'
        )

        class _RestraintNavInjector(_Base):
            async def dispatch(self, request, call_next):
                resp = await call_next(request)
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    p = request.url.path
                    if "text/html" not in ct or p.startswith(("/api/", "/assets/", "/vendor/", "/shared/")):
                        return resp
                    if p == "/elite/restraint" or p.endswith("/elite/restraint"):
                        return resp  # never inject into my own page
                    body = b""
                    async for chunk in resp.body_iterator:
                        body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()
                    if _NAV_MARK in body or _ANCHOR not in body:
                        new_body = body
                    else:
                        new_body = body.replace(_ANCHOR, _ANCHOR + _NAV_LINK, 1)
                    headers = dict(resp.headers)
                    headers.pop("content-length", None)
                    return _SResp(content=new_body, status_code=resp.status_code,
                                  headers=headers, media_type="text/html")
                except Exception:
                    return resp

        app.add_middleware(_RestraintNavInjector)
        registered.append("MIDDLEWARE restraint nav-link injector")
    except Exception:  # never crash the app — additive only
        pass

    return {"registered": registered, "count": len(registered),
            "capability": "Restraint · Governed Frugality Gate",
            "shared_module": "szl_restraint.py (byte-identical with a11oy)",
            "a11oy_canonical": A11OY_RESTRAINT_URL}


if __name__ == "__main__":
    # offline smoke: the page renders + namespace substitution worked.
    h = _page_html("killinchu")
    assert "/api/killinchu/v1/restraint/info" not in h  # built at runtime in JS via NS var
    assert 'const NS = "killinchu";' in h
    assert "szlholdings-a11oy.hf.space/restraint" in h
    assert "Ponytail" in h
    print("killinchu_restraint_tile: page OK (%d bytes)" % len(h))
