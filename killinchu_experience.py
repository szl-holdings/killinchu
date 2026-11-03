# SPDX-License-Identifier: Apache-2.0
"""Killinchu experience manifest and operator-facing evidence passport.

This module does not execute missions, emit receipts, mutate policies, or call
external services.  It publishes the declared contract for every discoverable
surface and supplies a small, accessible UI layer for ``/elite``.  The browser
layer probes only explicitly allow-listed GET endpoints; POST-only capabilities
stay labelled ON_DEMAND and are never auto-run.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # keep the manifest importable in lightweight audit tooling
    from fastapi import FastAPI


def _surface(
    key: str,
    label: str,
    purpose: str,
    endpoint: str,
    data_state: str,
    evidence_state: str,
    boundary: str,
    investor_value: str,
    *,
    visibility: str = "primary",
    kind: str = "view",
    method: str = "GET",
    safe_probe: bool = True,
) -> dict[str, Any]:
    route = endpoint if kind == "route" else f"/elite#{key}"
    return {
        "id": key,
        "label": label,
        "route": route,
        "kind": kind,
        "visibility": visibility,
        "purpose": purpose,
        "source": {
            "endpoint": endpoint,
            "method": method,
            "safe_probe": bool(safe_probe and method == "GET" and endpoint.startswith("/api/")),
        },
        "data_state": data_state,
        "evidence_state": evidence_state,
        "operational_boundary": boundary,
        "investor_value": investor_value,
    }


EXPERIENCE_SURFACES: tuple[dict[str, Any], ...] = (
    # Primary operator views present in the server-rendered /elite navigation.
    _surface("hero_interdiction", "Provable Interdiction", "Trace a governed recommendation from ROE policy through a receipt to its proof references.", "/api/killinchu/v1/roe/policy", "MIXED", "formal_plus_runtime", "Recommendation only; no autonomous or kinetic actuation. Receipt signing may be unavailable and must remain explicit.", "Turns autonomy assurance into inspectable evidence rather than a trust claim."),
    _surface("tracks", "Live Track Board", "Present the current air and maritime watch picture with provenance.", "/api/killinchu/v1/threats/active", "LIVE_OR_SAMPLE", "public_source", "Passive situational awareness; tracks are leads, not targeting truth.", "A legible operational wedge grounded in real public telemetry."),
    _surface("u_warhacker", "Demo Suite", "Index governed counter-UAS and maritime demonstrations with proof and tamper modes.", "/api/killinchu/v1/warhacker/index", "LIVE_COMPUTE", "runtime", "Catalog lookup only; launches are POST-only demonstrations and are never auto-run.", "A repeatable buyer-facing proof suite instead of a scripted video."),
    _surface("dataset_control", "Data Sources / Overlays", "Show which feeds and bounded reference datasets are wired and selectable.", "/api/killinchu/v1/feeds/status", "LIVE_OR_SNAPSHOT", "public_source", "Source selection is advisory and must never relabel a sample as live.", "Makes data lineage and deployment gaps visible to diligence teams.", visibility="retired_from_nav"),
    _surface("fleet_c2", "Fleet Health & Governed C2", "Combine aircraft and vessel telemetry with inferred subsystem health.", "/api/killinchu/v1/twin/platforms", "MIXED", "mixed", "Health is inferred from telemetry; command output is a simulated demonstration.", "Shows a governed common operating picture without pretending to control assets."),
    _surface("decoders", "Protocol Decoders", "Decode captured Remote ID, ADS-B, and MAVLink frames into claimed identities.", "/api/killinchu/v1/remote-id/decode", "ON_DEMAND", "runtime", "POST-only and never auto-run; broadcast identities are unauthenticated claims.", "Demonstrates protocol fluency while preserving evidence boundaries.", method="POST", safe_probe=False),
    _surface("u_assurance", "Assurance", "Expose tamper evidence, deterministic replay measurement, readiness, and UDS posture.", "/api/killinchu/uds/v1/healthz", "LIVE_RUNTIME", "mixed", "Readiness and package mappings are evidence, not certifications or authorizations.", "Packages the trust story for technical diligence and regulated buyers."),
    _surface("u_maritime", "Maritime Picture", "Fuse public AIS with sanctions, dark-vessel, and risk overlays.", "/api/killinchu/v1/ais/live", "LIVE_OR_SAMPLE", "public_source", "AIS and screening results are advisory public-source claims.", "Extends the same governed substrate from air to sea."),
    _surface("u_space", "Constellations & GEOINT", "Display screening-grade public orbital data and collection-planning estimates.", "/api/killinchu/v1/sda/propagate?group=stations", "LIVE_OR_SNAPSHOT", "public_source", "Screening-grade only; not a calibrated catalog, conjunction service, or tasking authority.", "Shows cross-domain expansion without overstating orbital precision."),
    _surface("u_swarm", "Swarm Integrity", "Render topology, intent heuristics, and resilience of grouped tracks.", "/api/killinchu/v1/swarm/topology", "MIXED", "modeled", "Intent is heuristic; topology does not authorize effects.", "Makes multi-agent integrity and graceful degradation tangible."),
    _surface("u_engage", "Engage & ROE", "Inspect the governed recommendation loop and rules of engagement.", "/api/killinchu/v1/roe/policy", "LIVE_RUNTIME", "runtime", "Human-in-the-loop; kinetic and active RF effects are outside this surface.", "Shows policy-controlled autonomy with an explicit authority boundary."),
    _surface("u_fusion", "Sensor-Fusion", "Expose multi-sensor state fusion and its uncertainty math.", "/api/killinchu/v1/sensor-fusion/status", "LIVE_OR_SAMPLE", "formal_plus_runtime", "Fusion reduces uncertainty but does not turn public telemetry into attested truth.", "Connects operational data to inspectable mathematical guarantees."),
    _surface("u_minedops", "Mined Ops", "Estimate field compute, telemetry memory, sampling, and routing tradeoffs.", "/api/killinchu/v1/mined/index", "MODELED", "modeled", "Engineering estimates only; no hardware or network settings are changed.", "Frames edge efficiency as an auditable deployment advantage.", visibility="retired_from_nav"),
    _surface("lambda", "Trust Score Monitor", "Inspect the 13-axis advisory trust score and its inputs.", "/api/killinchu/v1/honest", "CONJECTURE", "declared", "Lambda is Conjecture 1 and must never be treated as a theorem or pass/fail oracle.", "A differentiated trust vocabulary with the maturity caveat visible."),
    _surface("u_consensus", "Mesh Resilience", "Show quorum, connectivity, and conditional agreement evidence.", "/api/killinchu/uds/v1/healthz", "CONDITIONAL", "formal_plus_runtime", "Unconditional Byzantine safety remains open; no autonomous authority is conferred.", "Demonstrates resilient coordination with honest proof scope."),
    _surface("u_posture", "Posture, Topology & Zero-Trust", "Measure drift, graph health, exposure, and declared mesh policy.", "/api/killinchu/v1/topology/health", "LIVE_OR_SNAPSHOT", "mixed", "Posture findings are advisory; absent telemetry must remain unknown.", "Creates a continuous-assurance view for deployment owners."),
    _surface("u_receipts", "Receipts & Provenance", "Browse the runtime receipt ledger and verify provenance state.", "/api/killinchu/v1/receipt/ledger", "LIVE_RUNTIME", "runtime", "Unsigned or placeholder state must remain explicit; a signature attests content, not truth.", "Provides the evidence plane that links every product claim."),
    _surface("u_proofs", "Knowledge & Runtime Proofs", "Connect formulas, theorem cards, and runtime gates.", "/api/killinchu/v1/formulas/index", "PROVEN_PLUS_OPEN", "formal_plus_runtime", "Locked, experimental, conditional, and conjectural results must remain distinct.", "Makes the research moat inspectable by technical investors."),
    _surface("u_melt", "Observability (MELT)", "Expose metrics, events, logs, traces, and receipt linkage.", "/api/killinchu/v1/melt/summary", "LIVE_RUNTIME", "runtime", "Telemetry freshness and missing spans must be shown, not inferred.", "Gives operators and buyers one accountability plane.", visibility="retired_from_nav"),
    _surface("u_about", "About & Claims", "State deployment posture, research lineage, and legal boundaries.", "/api/killinchu/v1/honest", "DOCUMENTED", "declared", "Claims are not certifications; roadmap items must remain roadmap.", "A diligence-ready narrative with falsifiable claims.", visibility="retired_from_nav"),
    _surface("u_intel", "OSINT / Threat Intel", "Normalize public cyber, maritime, procurement, geopolitical, and counter-UAS reporting.", "/api/killinchu/v1/feeds/status", "LIVE_OR_CACHED", "public_source", "Third-party claims and heuristic tags are advisory, not attested intelligence.", "Turns fragmented public signals into a governed, provenance-aware watchlist."),
    _surface("u_operator", "Operator OSINT", "Rank, route, correlate, and graph the OSINT corpus.", "/api/killinchu/v1/operator/digest", "LIVE_OR_CACHED", "modeled", "Ranking and entity extraction are heuristic; operator review remains required.", "Shows the product loop from data intake to explainable decision support."),
    _surface("cuas_lab", "Counter-UAS C2 Lab", "Explore intercept, spoof, triage, fusion, and provenance experiments.", "/api/killinchu/v1/cuas/summary", "MODELED", "modeled", "Experimental and simulated; effectors never actuate.", "A controlled frontier lab without confusing prototypes for field authority.", visibility="retired_from_nav"),
    _surface("scaling", "Metabolic Scaling", "Explore cited allometric and compute-scaling analogies.", "/api/killinchu/v1/scaling/summary", "MODELED", "modeled", "Engineering analogies and proposed gates are not the formal Lambda theorem.", "Connects efficiency research to the sovereign-compute thesis.", visibility="retired_from_nav"),

    # Runtime-injected views.
    _surface("mosaic", "Nawi / Domain-Superiority", "Fuse the common operating picture with an anomaly overlay and receipt verifier.", "/api/killinchu/v1/mosaic/health", "MIXED", "mixed", "Space conjunction is roadmap; anomaly and risk outputs are advisory.", "An original cross-domain command picture with evidence built in.", visibility="runtime"),
    _surface("conjecturefactory", "Conjecture Factory", "Display signed disclosures of open conjectures and bounded-solver grades.", "/api/killinchu/v1/conjecture-factory", "OPEN", "declared", "A signature attests timestamp and content, never mathematical truth.", "Demonstrates a disciplined research pipeline that preserves uncertainty.", visibility="hidden_r_and_d"),
    _surface("sovereignty", "Sovereignty (Allodial)", "Explain operator ownership and control through cited governance models.", "/api/killinchu/v1/allodial/summary", "PROPOSED", "modeled", "A governance metaphor, not a claim to be above lawful authority.", "Clarifies the commercial sovereignty thesis for buyers and investors.", visibility="hidden_r_and_d"),
    _surface("neuro", "Neuroplasticity", "Visualize cited learning-rule and loss-of-plasticity diagnostics.", "/api/killinchu/v1/neuro/summary", "MODELED", "modeled", "Biological analogies and proposed lenses are not Lambda proofs.", "Links continual-learning research to agent reliability.", visibility="hidden_r_and_d"),
    _surface("l6chain", "Chain of Title", "Bind software, science, and math references into an inspectable artifact record.", "/api/killinchu/v1/chain/summary", "PROPOSED", "mixed", "Signing and DOI minting remain founder-gated; structural verification is not cryptographic verification.", "A compelling long-horizon provenance product thesis.", visibility="hidden_r_and_d"),
    _surface("entangle", "Entanglement", "Explore cited quantum-information bounds and engineering analogies.", "/api/killinchu/v1/entangle/summary", "MIXED", "formal_plus_runtime", "Rigorously cited pieces, structural analogies, and speculative claims stay separately tiered.", "Shows research breadth while preserving proof boundaries.", visibility="hidden_r_and_d"),
    _surface("atlas", "Formula Atlas", "Index the five engineering formula modules and their honest tiers.", "/api/killinchu/v1/unified/summary", "DOCUMENTED", "mixed", "An index does not promote experimental results into the locked set.", "Creates a single diligence entry point for the research estate.", visibility="hidden_r_and_d"),

    # Wave-K runtime surfaces; each endpoint is GET-only and safe to inspect.
    _surface("kc_trackfusion", "Track-Fusion (JPDA/MHT)", "Associate multiple targets and report swarm-intent and ROE advice.", "/api/killinchu/v1/trackfusion/associate", "SIMULATED", "modeled", "Simulated sensors; recommendation only; human-on-loop.", "Frontier multi-target reasoning with a clear simulation label.", visibility="runtime"),
    _surface("kc_onebit", "1-bit / Ternary Energy", "Estimate low-precision inference energy tradeoffs.", "/api/killinchu/v1/onebit/estimate", "MODELED", "modeled", "Measured context and modeled estimates must remain separate.", "Connects edge economics to model architecture choices.", visibility="runtime"),
    _surface("kc_ccattest", "Confidential-Compute Attest", "Compare a measurement chain against a golden reference.", "/api/killinchu/v1/cc-attest/verify", "MODELED", "modeled", "Seeded model; not a live hardware attestation unless explicitly reported.", "Shows how sovereign workloads can inherit hardware-rooted evidence.", visibility="runtime"),
    _surface("kc_sement", "Semantic-Entropy Gate", "Estimate semantic uncertainty as an advisory trust input.", "/api/killinchu/v1/sement/estimate", "MODELED", "modeled", "Advisory only; not a proof and never a green authorization.", "Adds uncertainty awareness to the governed inference story.", visibility="runtime"),
    _surface("kc_ttc", "Test-Time-Compute Allocator", "Allocate reasoning budget against expected gain and joules.", "/api/killinchu/v1/testtime/scaling", "MODELED", "modeled", "Budget recommendation only; does not change compute allocation.", "Makes reasoning cost a governed product variable.", visibility="runtime"),
    _surface("kc_specdec", "Speculative-Decode Receipt", "Model accepted-token speedup and energy receipts.", "/api/killinchu/v1/specdecode/simulate", "MODELED", "modeled", "Simulation only; losslessness is scoped to the modelled acceptance path.", "Pairs inference acceleration with auditability.", visibility="runtime"),
    _surface("kc_worldmodel", "Governed World-Model", "Run a bounded latent rollout with consistency diagnostics.", "/api/killinchu/v1/worldmodel/predict", "MODELED", "modeled", "Advisory prediction; not a physical-world authority.", "Introduces governed predictive planning as a future product layer.", visibility="runtime"),
    _surface("kc_episodic", "Episodic Memory Recall", "Score recall over a deterministic seeded memory graph.", "/api/killinchu/v1/episodic/recall", "MODELED", "modeled", "Seeded graph; not a live user-memory store.", "Makes agent memory inspectable and replayable.", visibility="runtime"),
    _surface("kc_qec", "Topological QEC / Surface-Code", "Model below-threshold suppression and receipt survival.", "/api/killinchu/v1/qec/surface-code", "MODELED", "modeled", "Classical simulation and analogy; not a live quantum processor.", "Connects resilience research to the evidence ledger." , visibility="runtime"),
    _surface("kc_energy", "Sovereign-Compute Energy", "Report local GPU energy when reachable and degrade honestly otherwise.", "/api/killinchu/v1/energy/sovereign", "LIVE_OR_ROADMAP", "mixed", "No live claim unless the sovereign metrics probe answers.", "Turns sovereign-compute economics into a measurable operating metric.", visibility="runtime"),

    # Server-injected navigation links. They are real pages, not /elite view keys.
    _surface("route_restraint", "Restraint", "Open the governed-frugality surface on the sibling application.", "https://szlholdings-a11oy.hf.space/restraint", "ROUTE", "route", "External sibling route; availability is not auto-probed by Killinchu.", "Connects mission value to governed resource use.", kind="route", safe_probe=False),
    _surface("route_mbse", "MBSE Water-Tank Co-Sim", "Open the governed water-tank co-simulation.", "/mbse", "ROUTE", "route", "Model-based engineering surface; no physical system is controlled.", "Shows requirements-to-simulation traceability.", kind="route", safe_probe=False),
    _surface("route_mbse_6dof", "MBSE 6DOF FMU Twin", "Open the modeled six-degree-of-freedom digital twin.", "/mbse-6dof", "ROUTE", "route", "Modeled twin, not live flight control.", "Demonstrates a path from software assurance to physical-system models.", kind="route", safe_probe=False),
    _surface("route_mbse_pipeline", "Requirement to Lean to FMU to Receipt", "Open the end-to-end engineering evidence pipeline.", "/mbse-pipeline", "ROUTE", "route", "Pipeline evidence does not constitute certification.", "A concise diligence path from requirement to verifiable artifact.", kind="route", safe_probe=False),
    _surface("route_waqay", "WAQAY Vector Index", "Open the governed vector-index surface.", "/waqay", "ROUTE", "route", "Retrieval remains evidence-scoped; signatures do not attest semantic truth.", "Connects governed retrieval to the broader estate.", kind="route", safe_probe=False),
    _surface("route_yupay", "YUPAY Multi-Model Audit", "Open the governed multi-model audit surface.", "/yupay", "ROUTE", "route", "Model agreement is evidence, not ground truth.", "Shows cross-model accountability and auditability.", kind="route", safe_probe=False),
    _surface("route_spaces", "Spaces", "Open the estate Space directory.", "/spaces", "ROUTE", "route", "Directory only; each linked surface retains its own evidence state.", "Provides a coherent ecosystem entry point.", kind="route", safe_probe=False),
)


def build_manifest(ns: str = "killinchu") -> dict[str, Any]:
    surfaces = []
    for item in EXPERIENCE_SURFACES:
        row = dict(item)
        row["source"] = dict(item["source"])
        row["source"]["endpoint"] = row["source"]["endpoint"].replace("{ns}", ns)
        row["route"] = row["route"].replace("{ns}", ns)
        surfaces.append(row)
    visibility = Counter(row["visibility"] for row in surfaces)
    states = Counter(row["data_state"] for row in surfaces)
    return {
        "schema": "szl.experience-manifest/v1",
        "space": ns,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "surface_count": len(surfaces),
        "summary": {
            "by_visibility": dict(sorted(visibility.items())),
            "by_data_state": dict(sorted(states.items())),
            "safe_get_probes": sum(1 for row in surfaces if row["source"]["safe_probe"]),
        },
        "operator_ui": {
            "surface_finder": "ENABLED",
            "keyboard_shortcut": "/",
            "escape_clears_filter": True,
            "minimum_touch_target_css_px": 44,
            "read_only": True,
        },
        "honesty": "Declared states are contracts, not reachability claims. The UI probes only allow-listed GET endpoints and reports HTTP/freshness separately.",
        "surfaces": surfaces,
    }


def register(app: "FastAPI", ns: str = "killinchu") -> dict[str, Any]:
    path = f"/api/{ns}/v1/experience/manifest"
    if any(getattr(route, "path", None) == path for route in app.routes):
        return {"module": __name__, "registered": [], "surface_count": len(EXPERIENCE_SURFACES)}

    @app.get(path, include_in_schema=False)
    async def experience_manifest():
        from fastapi.responses import JSONResponse

        return JSONResponse(build_manifest(ns))

    return {"module": __name__, "registered": [f"GET {path}"], "surface_count": len(EXPERIENCE_SURFACES)}


EXPERIENCE_LAYER_HTML = r"""<!-- __KILLINCHU_EXPERIENCE_LAYER_V1__ --><!-- __KILLINCHU_SURFACE_FINDER_V2__ -->
<style>
#szl-data-passport{display:grid;grid-template-columns:minmax(0,1.35fr) repeat(3,minmax(125px,1fr));gap:1px;margin:.65rem 0 .9rem;border:1px solid rgba(201,183,135,.28);border-radius:10px;overflow:hidden;background:#24282f}
.szl-passport-cell{min-width:0;background:#101318;padding:.62rem .72rem}.szl-passport-k{display:block;color:#8f9aa8;font:600 9px/1.2 var(--mono,monospace);letter-spacing:.11em;text-transform:uppercase;margin-bottom:.3rem}.szl-passport-v{display:block;color:#d9dee5;font:500 11px/1.45 var(--mono,monospace);overflow-wrap:anywhere}.szl-passport-v strong{color:#7fd6c7}.szl-passport-boundary{grid-column:1/-1;border-top:1px solid #24282f}.szl-passport-boundary .szl-passport-v{font-family:var(--sans,system-ui,sans-serif);font-size:12px;color:#b8c0ca}.szl-passport-live{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:6px;background:#c9a05f;vertical-align:1px}.szl-passport-live[data-ok="true"]{background:#5fb3a3}.szl-passport-live[data-ok="false"]{background:#b06a5a}
#szl-surface-finder{position:sticky;top:-1.1rem;z-index:4;margin:0 -.15rem .8rem;padding:.55rem .15rem .65rem;background:linear-gradient(180deg,var(--rail,#0b0b0b) 82%,rgba(11,11,11,0));}
.szl-finder-row{display:grid;grid-template-columns:minmax(0,1fr) 44px;gap:.35rem;align-items:center}.szl-finder-label{display:block;margin:0 0 .35rem;color:var(--gold,#c9b787);font:600 9px/1.2 var(--mono,monospace);letter-spacing:.13em;text-transform:uppercase}.szl-finder-input{width:100%;height:44px!important;min-width:0;padding:.55rem .65rem!important;border:1px solid var(--gold-line,rgba(201,183,135,.15))!important;border-radius:7px!important;background:#080808!important;color:var(--cream,#f5f5f5)!important;font:500 12px/1.2 var(--mono,monospace)!important}.szl-finder-input::placeholder{color:#7f8790}.szl-finder-clear{width:44px;height:44px;border:1px solid var(--gold-line,rgba(201,183,135,.15));border-radius:7px;background:var(--gold-soft,rgba(201,183,135,.04));color:var(--gold,#c9b787);font:600 16px/1 var(--mono,monospace);cursor:pointer}.szl-finder-status{display:block;min-height:1.3em;margin:.35rem .1rem 0;color:#8f9aa8;font:500 9px/1.3 var(--mono,monospace);letter-spacing:.04em}.side.szl-search-active .nav-group{display:none!important}.side.szl-search-active .nav-item:not(.szl-search-hidden){display:flex!important}.side .nav-item.szl-search-hidden{display:none!important}
@media(max-width:880px){#szl-data-passport{grid-template-columns:1fr 1fr}.szl-passport-boundary{grid-column:1/-1}}
@media(max-width:520px){#szl-data-passport{grid-template-columns:1fr}.szl-passport-boundary{grid-column:auto}}
@media(max-width:820px){#szl-surface-finder{top:-1.1rem}.szl-finder-input{font-size:16px!important}}
@media(prefers-reduced-motion:reduce){#szl-data-passport *,#szl-surface-finder *{scroll-behavior:auto!important;transition:none!important}}
</style>
<script>
(function(){
  'use strict';
  if(window.__KC_EXPERIENCE_LAYER__) return; window.__KC_EXPERIENCE_LAYER__=1;
  var NS='__NS__', manifest=null, manifestPromise=null, probeToken=0;
  function esc(s){return String(s==null?'':s).replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c];});}
  function loadManifest(){
    if(manifest) return Promise.resolve(manifest);
    if(!manifestPromise) manifestPromise=fetch('/api/'+NS+'/v1/experience/manifest',{headers:{accept:'application/json'},cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(function(d){manifest=d;return d;});
    return manifestPromise;
  }
  function rowFor(key){var xs=(manifest&&manifest.surfaces)||[];for(var i=0;i<xs.length;i++)if(xs[i].id===key)return xs[i];return null;}
  function mountFinder(){
    var side=document.querySelector('.side');if(!side||document.getElementById('szl-surface-finder'))return;
    var brand=side.querySelector('.brand'),box=document.createElement('section');box.id='szl-surface-finder';box.setAttribute('role','search');box.setAttribute('aria-label','Find a Killinchu surface');
    box.innerHTML='<label class="szl-finder-label" for="szl-surface-query">Find a surface <span aria-hidden="true">/</span></label><div class="szl-finder-row"><input id="szl-surface-query" class="szl-finder-input" type="search" inputmode="search" enterkeyhint="go" autocomplete="off" placeholder="Search capabilities or routes" aria-describedby="szl-surface-count"><button id="szl-surface-clear" class="szl-finder-clear" type="button" aria-label="Clear surface filter">&times;</button></div><span id="szl-surface-count" class="szl-finder-status" role="status" aria-live="polite"></span>';
    if(brand&&brand.nextSibling)side.insertBefore(box,brand.nextSibling);else side.insertBefore(box,side.firstChild);
    var input=box.querySelector('#szl-surface-query'),clear=box.querySelector('#szl-surface-clear'),status=box.querySelector('#szl-surface-count');
    function items(){return Array.prototype.slice.call(side.querySelectorAll('.nav-item'));}
    function apply(){
      var q=(input.value||'').trim().toLowerCase(),matches=0;
      side.classList.toggle('szl-search-active',!!q);
      items().forEach(function(node){var hay=(node.textContent+' '+(node.getAttribute('title')||'')+' '+(node.dataset.view||'')+' '+(node.getAttribute('href')||'')).toLowerCase(),hit=!q||hay.indexOf(q)>=0;node.classList.toggle('szl-search-hidden',!hit);if(hit)matches++;});
      status.textContent=q?(matches+' matching surface'+(matches===1?'':'s')+' · Enter opens the first'):(items().length+' surfaces available · press / to search');
      return matches;
    }
    input.addEventListener('input',apply);input.addEventListener('keydown',function(e){if(e.key==='Enter'&&input.value.trim()){var first=side.querySelector('.nav-item:not(.szl-search-hidden)');if(first){e.preventDefault();first.click();input.value='';apply();if(window.matchMedia&&window.matchMedia('(max-width:820px)').matches&&window.toggleSide)window.toggleSide(false);}}else if(e.key==='Escape'){input.value='';apply();input.blur();}});
    clear.addEventListener('click',function(){input.value='';apply();input.focus();});
    document.addEventListener('keydown',function(e){var tag=(e.target&&e.target.tagName||'').toLowerCase();if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&tag!=='input'&&tag!=='textarea'&&tag!=='select'){e.preventDefault();input.focus();}else if(e.key==='Escape'&&document.activeElement!==input&&input.value){input.value='';apply();}});
    try{new MutationObserver(function(records){if(records.some(function(r){return r.addedNodes&&r.addedNodes.length;}))apply();}).observe(side,{childList:true});}catch(e){}
    apply();
  }
  function stamp(d){return d&&(d.observed_at||d.fetched_at||d.as_of||d.ts||d.timestamp||d.generated_at)||null;}
  function sourceLabel(d){return d&&(d.data_label||d.status_label||d.mode||d.label||d.status)||null;}
  function cell(k,v,cls){return '<div class="szl-passport-cell '+(cls||'')+'"><span class="szl-passport-k">'+esc(k)+'</span><span class="szl-passport-v">'+v+'</span></div>';}
  function mount(key){
    var token=++probeToken;
    loadManifest().then(function(){
      if(token!==probeToken)return; var row=rowFor(key); if(!row)return;
      var old=document.getElementById('szl-data-passport'); if(old)old.remove();
      var head=document.querySelector('#content .view-head'); if(!head)return;
      var box=document.createElement('section'); box.id='szl-data-passport'; box.setAttribute('aria-label','Data and evidence passport'); box.setAttribute('role','region');
      box.innerHTML=cell('Source',esc(row.source.method+' '+row.source.endpoint))+cell('Declared data',esc(row.data_state))+cell('Evidence',esc(row.evidence_state))+cell('Reachability','<span class="szl-passport-live"></span><span id="szl-passport-reach">not probed</span>')+cell('Safety boundary',esc(row.operational_boundary)+' <strong>Why it matters:</strong> '+esc(row.investor_value),'szl-passport-boundary');
      head.insertAdjacentElement('afterend',box);
      if(!row.source.safe_probe){document.getElementById('szl-passport-reach').textContent='on demand / no automatic action';return;}
      var ctrl=new AbortController(), timer=setTimeout(function(){ctrl.abort();},4500);
      fetch(row.source.endpoint,{headers:{accept:'application/json'},cache:'no-store',signal:ctrl.signal}).then(function(r){
        var ct=r.headers.get('content-type')||''; if(!r.ok||ct.indexOf('json')<0)throw new Error('HTTP '+r.status);
        return r.json().then(function(d){return {status:r.status,data:d};});
      }).then(function(res){
        clearTimeout(timer); if(token!==probeToken)return; var target=document.getElementById('szl-passport-reach'); if(!target)return;
        var dot=target.previousElementSibling;if(dot)dot.setAttribute('data-ok','true'); var label=sourceLabel(res.data), seen=stamp(res.data);
        target.textContent='HTTP '+res.status+(label?' · '+label:'')+(seen?' · as of '+seen:' · freshness not supplied');
      }).catch(function(err){
        clearTimeout(timer); if(token!==probeToken)return; var target=document.getElementById('szl-passport-reach'); if(!target)return;
        var dot=target.previousElementSibling;if(dot)dot.setAttribute('data-ok','false');target.textContent=(err&&err.name==='AbortError')?'timeout / honest unknown':'unavailable / '+String(err&&err.message||err);
      });
    }).catch(function(){});
  }
  function activateNav(){
    document.querySelectorAll('.nav-item').forEach(function(node){
      // Preserve native anchors (including cross-surface links) as links. Only
      // div-based in-console items need the button keyboard contract.
      var nativeLink=node.tagName && node.tagName.toLowerCase()==='a';
      if(!nativeLink){
        if(!node.hasAttribute('role'))node.setAttribute('role','button');
        if(!node.hasAttribute('tabindex'))node.setAttribute('tabindex','0');
        if(!node.dataset.kcKeyboard){node.dataset.kcKeyboard='1';node.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();node.click();}});}
      }
      if(node.classList.contains('active'))node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');
    });
  }
  function wrapGo(){
    if(typeof window.go!=='function'||window.go.__kcExperience)return false;
    var original=window.go; window.go=function(view){var out=original.apply(this,arguments);activateNav();mount(view);return out;}; window.go.__kcExperience=true; return true;
  }
  function boot(){
    mountFinder(); activateNav(); wrapGo(); loadManifest().then(function(){mount((location.hash||'#tracks').slice(1));}).catch(function(){});
    var attempts=0, iv=setInterval(function(){activateNav();if(wrapGo()||++attempts>40)clearInterval(iv);},100);
    try{new MutationObserver(function(){activateNav();}).observe(document.querySelector('.side')||document.body,{childList:true,subtree:true});}catch(e){}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
</script>"""


__all__ = ["EXPERIENCE_SURFACES", "EXPERIENCE_LAYER_HTML", "build_manifest", "register"]
