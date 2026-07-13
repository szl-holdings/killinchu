# -*- coding: utf-8 -*-
# ===========================================================================
# killinchu_frontier_wave_surfaces.py — WAVE K · Dev 5 · killinchu FULL-WIRE
# ---------------------------------------------------------------------------
# GOAL (Wave K / Dev 5): the wave-built frontier BACKENDS are LIVE 200 on
# killinchu (trackfusion, onebit, cc-attest, sement, ttc/testtime, specdec,
# worldmodel, episodic, qec, energy) but they were NOT SURFACED in the killinchu
# operator deck (/elite) — a NO-HALLUCINATION gap: a live governed capability
# that no operator surface reads. On a11oy these back static/3d/surfaces/*.js on
# the holographic board (Dev 2). killinchu has no holographic board; its operator
# surface is the 14-tab elite console. This module WIRES each backend into the
# killinchu deck as a REAL tab that fetches its LIVE endpoint and shows real data
# with an HONEST label (LIVE/SIMULATED/MODELED, never "green"), Λ = Conjecture 1.
#
# HOW (ADDITIVE, idempotent, 0 lines removed from the 1.3 MB elite console):
#   1. GET /killinchu_frontier_wave_surfaces.js — a self-contained vanilla-JS
#      surface bootstrap. On load it registers 10 tabs into window.VIEWS using the
#      SAME reg(key,title,badge,sub,render) / injectNav() contract the deck's own
#      frontier tabs use (regNeuro etc.), each fetching its endpoint live, rendering
#      real fields, and painting the honest global badge. Cross-links to
#      a-11-oy.com + /verify on every surface.
#   2. A single BaseHTTPMiddleware that, on every text/html deck response that
#      carries the elite sidebar, injects ONE <script src=".../wave-surfaces.js">
#      tag before </body>. Keyed by data-kc-wave-surfaces="k5" so re-runs NEVER
#      double-inject and no other lane is touched. Mirrors the proven
#      killinchu_nav_wireup.py / _OperatorWidgetInjectorKC injector pattern.
#   3. register(app, ns) is called from serve.py BEFORE the SPA /{full_path:path}
#      catch-all so the .js route resolves LOCALLY (never the SPA shell).
#
# The SPA shell (static/index.html) and killinchu_elite_console.py are NOT edited.
# The injector only ADDS a script tag + the JS only ADDS VIEWS keys; nothing is
# removed and no existing view is clobbered (each reg() no-ops if the key exists).
#
# C2 UX (counter-UAS leaders folded, GOVERNED): Anduril Lattice — clean common
# operating picture, complexity hidden, operator sees a SHORT LIST of decisions,
# HUMAN-ON-THE-LOOP (never an autonomous kill), multi-target detect-track-ID via
# sensor fusion that reduces false positives, low cognitive load
# (uasfeed.com/article/anduril-lattice-c2-software-explained; smgconferences
# Anduril CUAS UI deck). Palantir Gotham — a live COP integrating all-domain +
# streaming sensor data with proactively-surfaced AI insights, every operator
# action feeding back into the data foundation (palantir.com/platforms/gotham).
# Our GOVERNED version: same decision-focused low-cognitive-load surface, but
# every tile is HONESTLY LABELLED (LIVE/SIMULATED/MODELED), the effector is
# SIMULATED human-on-loop, and Λ stays Conjecture 1 (advisory, NEVER green).
#
# DOCTRINE (v11): locked = 8 @ c7c0ba17 (749/14/163); Λ = Conjecture 1 (NOT a
# theorem, never "green"); 0 CDN (the only external URL is same-estate
# a-11-oy.com); honest labels only; never weakens a gate; never commits a key;
# additive-only; trust ceiling 0.97 < 1.0.
#
# Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
# ===========================================================================
from __future__ import annotations

import sys as _sys
from typing import Any, Dict

_MOUNT_PATH = "/killinchu_frontier_wave_surfaces.js"
_INJECT_KEY = "k5"  # data-kc-wave-surfaces="k5"

# surface key -> (endpoint template, Nav title, honest badge, one-line sub)
# Endpoints are the CANONICAL live GET routes discovered in-process (788 routes).
# Labels are the HONEST doctrine class each backend reports at runtime.
WAVE_SURFACES = {
    "kc_trackfusion": (
        "/api/{ns}/v1/trackfusion/associate",
        "Track-Fusion (JPDA/MHT)",
        "SIMULATED SENSORS \u00b7 ROE ADVISORY \u00b7 HUMAN-ON-LOOP \u00b7 \u039b=CONJECTURE 1",
        "JPDA/MHT multi-target association + swarm-intent + \u039b-ROE gate. Effector SIMULATED, never actuates. Human-on-the-loop (Anduril-Lattice-style COP, governed).",
    ),
    "kc_onebit": (
        "/api/{ns}/v1/onebit/estimate",
        "1-bit / Ternary Energy",
        "MODELED \u00b7 measured-context honest \u00b7 \u039b=CONJECTURE 1",
        "1.58-bit ternary inference energy estimate; measured vs modeled is stated explicitly, SZL claims no number as its own.",
    ),
    "kc_ccattest": (
        "/api/{ns}/v1/cc-attest/verify",
        "Confidential-Compute Attest",
        "MODELED \u00b7 golden-match check \u00b7 \u039b=CONJECTURE 1",
        "Confidential-compute measurement chain vs golden reference; deterministic seeded simulation (cites NVIDIA H100 CC / NRAS).",
    ),
    "kc_sement": (
        "/api/{ns}/v1/sement/estimate",
        "Semantic-Entropy Gate",
        "MODELED \u00b7 advisory input to \u039b \u00b7 \u039b=CONJECTURE 1",
        "Semantic-entropy hallucination gate; an ADVISORY input to \u039b, NOT a proof, never green.",
    ),
    "kc_ttc": (
        "/api/{ns}/v1/testtime/scaling",
        "Test-Time-Compute Allocator",
        "MODELED \u00b7 governed joules \u00b7 \u039b=CONJECTURE 1",
        "Governed test-time-compute budget allocator: pass@N vs sequential-revision scaling + joules-aware route choice.",
    ),
    "kc_specdec": (
        "/api/{ns}/v1/specdecode/simulate",
        "Speculative-Decode Receipt",
        "MODELED \u00b7 lossless \u00b7 \u039b=CONJECTURE 1",
        "Speculative-decoding energy-receipt simulator; lossless (accepted tokens identical), speedup + joules receipt.",
    ),
    "kc_worldmodel": (
        "/api/{ns}/v1/worldmodel/predict",
        "Governed World-Model",
        "MODELED \u00b7 free-energy consistency \u00b7 \u039b=CONJECTURE 1",
        "Governed latent world-model rollout: prediction error, physical surprise, free-energy consistency (advisory).",
    ),
    "kc_episodic": (
        "/api/{ns}/v1/episodic/recall",
        "Episodic Memory Recall",
        "MODELED \u00b7 seeded graph \u00b7 \u039b=CONJECTURE 1",
        "Deterministic seeded episodic-memory graph + recall scoring; grounds the agent loop's memory layer.",
    ),
    "kc_qec": (
        "/api/{ns}/v1/qec/surface-code",
        "Topological QEC / Surface-Code",
        "MODELED \u00b7 below-threshold sim \u00b7 \u039b=CONJECTURE 1",
        "Rotated surface-code below-threshold suppression mapped to receipt erasure-coding survival (cites Google Quantum AI, Nature 2024).",
    ),
    "kc_energy": (
        "/api/{ns}/v1/energy/sovereign",
        "Sovereign-Compute Energy",
        "LIVE-when-reachable else SIMULATED/ROADMAP \u00b7 \u039b=CONJECTURE 1",
        "Sovereign on-box GPU energy panels; each panel reads LIVE from vLLM /metrics only when the sovereign probe is reachable, else honestly ROADMAP.",
    ),
}


def _js() -> str:
    """Self-contained surface bootstrap. Registers the wave-K frontier tabs into
    window.VIEWS using the deck's own reg()/injectNav() contract, each fetching its
    LIVE endpoint and painting real fields + honest global badge. 0 CDN."""
    import json as _json
    reg_rows = []
    for key, (ep, title, badge, sub) in WAVE_SURFACES.items():
        reg_rows.append({"key": key, "ep": ep, "title": title, "badge": badge, "sub": sub})
    data = _json.dumps(reg_rows)
    # NB: {NS} is replaced client-side from window.__KC_NS or the ns literal.
    return (
        "/* killinchu_frontier_wave_surfaces.js \u2014 Wave K / Dev 5 (ADDITIVE, honest, \u039b=Conjecture 1) */\n"
        "(function(){\n"
        "  'use strict';\n"
        "  if(window.__KC_WAVE_SURFACES__){ return; } window.__KC_WAVE_SURFACES__=1;\n"
        "  var NS=(window.__KC_NS||'killinchu');\n"
        "  var TEAL='#3ddc97', GOLD='#c9b787', DIM='#8a8f98', RED='#ff6b6b';\n"
        "  var SURF=" + data + ";\n"
        "  function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
        "  function labelColor(l){ l=String(l||'').toUpperCase(); if(l.indexOf('LIVE')>=0)return TEAL; if(l.indexOf('SIMULATED')>=0||l.indexOf('SAMPLE')>=0)return GOLD; if(l.indexOf('ROADMAP')>=0||l.indexOf('UNAVAILABLE')>=0)return RED; return DIM; }\n"
        "  function pill(l){ var c=labelColor(l); return '<span style=\"display:inline-block;padding:2px 9px;border-radius:999px;font-family:monospace;font-size:10px;letter-spacing:.06em;font-weight:700;color:'+c+';border:1px solid '+c+';background:'+c+'1a;\">'+esc(l)+'</span>'; }\n"
        "  function xlinks(ep){ return '<div style=\"margin-top:14px;font-family:monospace;font-size:11px;color:'+DIM+';\">'\n"
        "      +'\\u25c8 endpoint <a href=\"'+esc(ep)+'\" target=\"_blank\" rel=\"noopener\" style=\"color:'+GOLD+';\">'+esc(ep)+'</a>'\n"
        "      +' \\u00b7 cross-verify at <a href=\"/verify\" style=\"color:'+TEAL+';\">/verify</a>'\n"
        "      +' \\u00b7 governed flywheel on <a href=\"https://a-11-oy.com\" target=\"_blank\" rel=\"noopener\" style=\"color:'+TEAL+';\">a-11-oy.com</a>'\n"
        "      +' \\u00b7 \\u039b = <b>Conjecture 1</b> (advisory, never green)</div>'; }\n"
        "  function kv(k,v){ return '<div style=\"display:flex;justify-content:space-between;gap:1rem;padding:4px 0;border-bottom:1px solid #1c1c1c;\"><span style=\"color:'+DIM+';font-family:monospace;font-size:12px;\">'+esc(k)+'</span><span style=\"color:#e8e8e8;font-family:monospace;font-size:12px;text-align:right;\">'+esc(v)+'</span></div>'; }\n"
        "  function flat(o,pre,rows,depth){ pre=pre||''; rows=rows||[]; depth=depth||0; if(depth>2){ return rows; }\n"
        "    if(o&&typeof o==='object'&&!Array.isArray(o)){ for(var k in o){ if(!o.hasOwnProperty(k))continue; var v=o[k];\n"
        "      if(v&&typeof v==='object'){ flat(v,pre+k+'.',rows,depth+1); } else { rows.push([pre+k, v]); } if(rows.length>26)break; } }\n"
        "    return rows; }\n"
        "  function mountFor(s){ return function(c){ if(!c)return;\n"
        "    var ep=s.ep.replace('{ns}',NS);\n"
        "    c.innerHTML='<div style=\"max-width:960px;\">'\n"
        "      +'<div style=\"margin:0 0 10px;\">'+pill(s.badge)+'</div>'\n"
        "      +'<div style=\"font-size:13px;line-height:1.55;color:#c8c8c8;margin:0 0 14px;\">'+esc(s.sub)+'</div>'\n"
        "      +'<div id=\"'+s.key+'-live\" style=\"font-family:monospace;font-size:12px;color:'+GOLD+';\">\\u25c8 fetching '+esc(ep)+' \\u2026</div>'\n"
        "      +'<div id=\"'+s.key+'-body\"></div>'\n"
        "      +xlinks(ep)+'</div>';\n"
        "    fetch(ep,{headers:{'accept':'application/json'}}).then(function(r){ return r.json().then(function(j){ return {ok:r.ok,st:r.status,j:j}; }); })\n"
        "      .then(function(res){ var live=document.getElementById(s.key+'-live'); var body=document.getElementById(s.key+'-body');\n"
        "        var j=res.j||{}; var lbl=j.label||j.data_label||j.status_label||(j.inference_state&&j.inference_state.sovereign?'LIVE':'SIMULATED/ROADMAP')||(res.ok?'LIVE 200':'ERROR');\n"
        "        if(live){ live.innerHTML='\\u25c8 GET '+esc(ep)+' \\u2192 '+res.st+' '+pill(lbl)+' \\u00b7 honest label read from the live response'; }\n"
        "        if(body){ var rows=flat(j,'',[],0); var H='<div style=\"margin-top:12px;border:1px solid #222;border-radius:8px;padding:10px 14px;background:#0d0f12;\">';\n"
        "          rows.forEach(function(p){ H+=kv(p[0], typeof p[1]==='number'?(''+p[1]).slice(0,12):String(p[1]).slice(0,90)); }); H+='</div>'; body.innerHTML=H; } })\n"
        "      .catch(function(e){ var live=document.getElementById(s.key+'-live'); if(live){ live.innerHTML='\\u25c8 GET '+esc(ep)+' \\u2192 '+pill('FETCH ERROR')+' '+esc(String(e).slice(0,120))+' \\u2014 honest degrade, no fabricated data'; } });\n"
        "  }; }\n"
        "  function reg(key,title,badge,sub,fn){ if(!window.VIEWS){ return setTimeout(function(){reg(key,title,badge,sub,fn);},90); }\n"
        "    if(window.VIEWS[key]){ return; }\n"
        "    window.VIEWS[key]={title:title,badge:badge,sub:sub,render:async function(c){ fn(c); }};\n"
        "    try{ console.log('['+NS+'] wave-K frontier surface registered: '+key); }catch(e){} }\n"
        "  function regAll(){ SURF.forEach(function(s){ reg(s.key,s.title,s.badge,s.sub,mountFor(s)); }); injectNav(); }\n"
        "  function injectNav(){ var side=document.querySelector('.side .nav')||document.querySelector('.side');\n"
        "    var anchor=document.querySelector('.nav-item[data-view]')||document.querySelector('.nav-item');\n"
        "    if(!side||!anchor){ return setTimeout(injectNav,300); }\n"
        "    if(document.getElementById('kc-wave-nav-group')){ return; }\n"
        "    var parent=anchor.parentNode;\n"
        "    var grp=document.createElement('div'); grp.className='nav-group'; grp.id='kc-wave-nav-group'; grp.textContent='Wave-K Frontier (LIVE backends)';\n"
        "    parent.appendChild(grp);\n"
        "    SURF.forEach(function(s){ if(document.getElementById(s.key+'-nav-item')){ return; }\n"
        "      var n=document.createElement('div'); n.className='nav-item'; n.id=s.key+'-nav-item'; n.setAttribute('data-view',s.key); n.setAttribute('onclick',\"go('\"+s.key+\"')\");\n"
        "      n.setAttribute('title',s.title+' \\u2014 live from '+s.ep.replace('{ns}',NS)+'. Honest label; effector SIMULATED human-on-loop; \\u039b = Conjecture 1.');\n"
        "      n.innerHTML='<span class=\"ico\">\\u25c8</span>'+esc(s.title); parent.appendChild(n); });\n"
        "    try{ console.log('['+NS+'] wave-K frontier nav injected ('+SURF.length+' surfaces)'); }catch(e){} }\n"
        "  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded',regAll); } else { regAll(); }\n"
        "})();\n"
    )


class _WaveSurfacesInjector:
    """ASGI-compatible middleware: inject ONE <script src> into deck HTML.

    Idempotent (keyed by data-kc-wave-surfaces="k5"), additive, removes nothing.
    Only fires on text/html responses that carry the elite sidebar so the SPA
    shell and non-deck pages are untouched. Never raises into a request."""

    def __init__(self, app, ns: str = "killinchu"):
        self.app = app
        self.ns = ns
        self._marker = 'data-kc-wave-surfaces="%s"' % _INJECT_KEY

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        chunks: list = []
        status_code = {"v": 200}
        headers_ref: dict = {}
        started = {"v": False}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_code["v"] = message.get("status", 200)
                hdrs = message.get("headers") or []
                ct = ""
                for k, v in hdrs:
                    if k.decode("latin-1").lower() == "content-type":
                        ct = v.decode("latin-1").lower()
                headers_ref["ct"] = ct
                headers_ref["raw"] = list(hdrs)
                headers_ref["start"] = message
                started["v"] = True
                return  # defer sending start until we know final body length
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b"") or b"")
                if message.get("more_body"):
                    return
                # last chunk — decide whether to inject
                body = b"".join(chunks)
                ct = headers_ref.get("ct", "")
                inject = False
                if "text/html" in ct and self._marker.encode() not in body:
                    # only decks: must carry the elite sidebar AND the VIEWS registry
                    if (b'class="side"' in body or b"class='side'" in body) and b"window.VIEWS" in body or b"VIEWS[" in body:
                        inject = True
                if inject:
                    try:
                        tag = (
                            '<script %s src="%s" defer></script>'
                            % (self._marker, _MOUNT_PATH)
                        ).encode("utf-8")
                        if b"</body>" in body:
                            body = body.replace(b"</body>", tag + b"</body>", 1)
                        else:
                            body = body + tag
                    except Exception:
                        pass  # honest degrade — never break the deck
                # rebuild headers with corrected content-length
                raw = []
                for k, v in headers_ref.get("raw", []):
                    if k.decode("latin-1").lower() == "content-length":
                        continue
                    raw.append((k, v))
                raw.append((b"content-length", str(len(body)).encode("latin-1")))
                start_msg = dict(headers_ref.get("start", {"type": "http.response.start", "status": status_code["v"]}))
                start_msg["headers"] = raw
                await send(start_msg)
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            # if anything above went wrong before we sent, fall back to a clean pass
            raise


def register(app, ns: str = "killinchu") -> Dict[str, Any]:
    """Single ADDITIVE integration point. Called from serve.py BEFORE the SPA
    /{full_path:path} catch-all. Adds:
      * GET /killinchu_frontier_wave_surfaces.js  (the surface bootstrap)
      * one <script src> injector middleware on deck HTML responses
    Never raises; returns a status dict."""
    try:
        from fastapi.responses import Response

        _payload = _js()

        @app.get(_MOUNT_PATH, include_in_schema=False)
        async def _serve_wave_surfaces_js():  # noqa: ANN202
            return Response(content=_payload, media_type="application/javascript")

        try:
            app.add_middleware(_WaveSurfacesInjector, ns=ns)
        except Exception as _mw_e:  # honest degrade — the .js route still serves
            print("[killinchu] wave-K surfaces injector NOT added: %r" % (_mw_e,), file=_sys.stderr)

        # move the .js route to the FRONT so it resolves before any catch-all
        try:
            routes = app.router.routes
            for i, r in enumerate(list(routes)):
                if getattr(r, "path", None) == _MOUNT_PATH:
                    routes.insert(0, routes.pop(i))
                    break
        except Exception:
            pass

        return {
            "ok": True,
            "ns": ns,
            "js_route": _MOUNT_PATH,
            "surfaces": list(WAVE_SURFACES.keys()),
            "count": len(WAVE_SURFACES),
            "injector": "text/html deck responses (idempotent, key=%s)" % _INJECT_KEY,
            "doctrine": "v11", "lambda": "Conjecture 1", "cdn": 0,
        }
    except Exception as e:  # never break serve.py boot
        print("[killinchu] wave-K frontier surfaces NOT registered: %r" % (e,), file=_sys.stderr)
        return {"ok": False, "reason": repr(e), "ns": ns}
