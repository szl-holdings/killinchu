# killinchu_organism_view.py
# ---------------------------------------------------------------------------
# Dev D — ORGANISM surface (causal anatomy + NCA self-repair, 3D).
#
#   GET /elite/organism   — the living-organism causal surface
#
# Pure VIEW. Reads the REAL /api/{ns}/v1/organism/causal + /organism/self-repair
# endpoints from killinchu_organism.py. Renders the organism as a DIRECTED
# causal-dependency graph in 3D (vendored three.js, 0 runtime CDN — same
# loadThree fallback chain as /estate-organism), with the headline DEMO:
#   kill an organ -> watch downstream organs re-route -> the tissue self-heals
#   over discrete NCA-style steps, honestly labelled EXPERIMENTAL.
#
# Vitals are LIVE where the in-process anatomy/mesh expose them, MODELED
# otherwise. Effectors SIMULATED human-on-loop. Doctrine v11.
# refs: distill.pub/2020/growing-ca ; arXiv:2511.02241 ; Fiedler arXiv:2504.06894.
# ---------------------------------------------------------------------------
from starlette.responses import HTMLResponse
from starlette.routing import Route

_DOCTRINE = "v11"
_LOCKED = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]

_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>killinchu · ORGANISM — causal anatomy + self-repair</title>
<meta name="description" content="killinchu ORGANISM — the living organism (a11oy + killinchu) as a DIRECTED causal-dependency graph: edges encode a real causal dependency (downstream organ needs upstream), each organ carries local homeostatic invariants, and an NCA-style local self-repair rule re-routes and heals when an organ goes down. Vitals are LIVE where the in-process anatomy/mesh expose them, MODELED otherwise; self-repair is EXPERIMENTAL (an explicit local rule, not a trained CA). Fiedler lambda2 shared with the mesh. 0 runtime CDN (vendored 3D). Effectors SIMULATED human-on-loop."/>
<link rel="stylesheet" href="/vendor/fonts/fonts.css"/>
<style>
:root{
  --ground:#0a0a0a; --panel:#0e0e0e; --panel2:#080808;
  --gold:#c9b787; --teal:#5fb3a3; --teal-soft:rgba(95,179,163,0.10);
  --cream:#f5f5f5; --paragraph:#bdbdbd; --muted:#9a9a9a; --dim:#6f6f6f;
  --gold-line:rgba(201,183,135,0.15); --gold-soft:rgba(201,183,135,0.04);
  --teal-line:rgba(95,179,163,0.22);
  --live:#6fae8b; --err:#d08a78; --warn:#d6b06a;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,monospace;
  --display:'Space Grotesk',Georgia,serif;
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--ground);color:var(--cream);
  font-family:var(--display);-webkit-font-smoothing:antialiased;}
.mono{font-family:var(--mono);}
a{color:inherit;text-decoration:none;}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:3px;}
::-webkit-scrollbar{width:9px;height:9px;}::-webkit-scrollbar-thumb{background:#222;border-radius:6px;}
.topbar{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:1rem;flex-wrap:nowrap;
  min-height:39px;overflow-x:auto;padding:0 1.1rem;background:rgba(10,10,10,.92);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--gold-line);font-family:var(--mono);font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--gold);scrollbar-width:none;}
.topbar::-webkit-scrollbar{display:none;}.topbar > *{flex:0 0 auto;}
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
.view-badge.warn{color:var(--warn);border-color:var(--warn);}
.view-sub{font-size:13.5px;color:var(--paragraph);line-height:1.6;margin:.5rem 0 1.4rem;max-width:64rem;}
.layout{display:grid;grid-template-columns:1.4fr 1fr;gap:1.1rem;}
@media(max-width:900px){.layout{grid-template-columns:1fr;}}
.card{border:1px solid var(--gold-line);border-radius:11px;background:var(--panel);padding:1.1rem 1.2rem;margin-bottom:1.1rem;}
.card-h{display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem;flex-wrap:wrap;}
.card-t{font-size:1.05rem;font-weight:500;color:var(--cream);}
.card-ep{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto;}
.lbl-pill{font-family:var(--mono);font-size:9px;padding:.1rem .42rem;border-radius:4px;border:1px solid var(--gold-line);color:var(--muted);background:var(--gold-soft);}
.lbl-pill.live{color:var(--live);border-color:var(--live);}
.lbl-pill.exp{color:var(--warn);border-color:var(--warn);}
#c{width:100%;height:380px;display:block;border:1px solid var(--gold-line);border-radius:10px;background:radial-gradient(circle at 50% 40%,#0e1416,#070707);}
.controls{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.7rem 0;}
button{font-family:var(--mono);font-size:11px;cursor:pointer;background:var(--gold-soft);color:var(--gold);border:1px solid var(--gold-line);border-radius:7px;padding:.42rem .8rem;transition:.15s;}
button:hover{background:var(--gold);color:var(--ground);}
button.danger{color:var(--err);border-color:var(--err);}button.danger:hover{background:var(--err);color:var(--ground);}
button.teal{color:var(--teal);border-color:var(--teal-line);}button.teal:hover{background:var(--teal);color:var(--ground);}
select{font-family:var(--mono);font-size:11px;background:var(--panel2);color:var(--cream);border:1px solid var(--gold-line);border-radius:6px;padding:.34rem .5rem;}
.organ{border:1px solid var(--gold-line);border-radius:9px;background:var(--panel2);padding:.7rem .8rem;margin-bottom:.6rem;}
.organ h3{margin:0 0 .3rem;font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:.5rem;font-family:var(--mono);}
.organ .sys{font-size:11px;color:var(--muted);margin-bottom:.35rem;}
.bar{height:7px;border-radius:4px;background:#1a1a1a;overflow:hidden;margin:.3rem 0;}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--teal),var(--gold));transition:width .3s;}
.inv{font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.5;}
.inv b{color:var(--paragraph);}
.dep{font-family:var(--mono);font-size:10px;color:var(--teal);margin-top:.25rem;}
.out{font-family:var(--mono);font-size:11px;line-height:1.5;color:var(--paragraph);background:var(--panel2);border:1px solid var(--gold-line);border-radius:8px;padding:.7rem .8rem;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;margin-top:.5rem;}
.step-readout{font-family:var(--mono);font-size:12px;color:var(--cream);margin:.4rem 0;}
.event{font-family:var(--mono);font-size:11px;color:var(--warn);margin:.15rem 0;}
.footnote{font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.6;margin-top:1.2rem;border-top:1px solid var(--gold-line);padding-top:1rem;}
.footnote b{color:var(--muted);}
@media (prefers-reduced-motion: reduce){*{transition-duration:.001ms!important;}}
</style>
</head>
<body>
<div class="topbar">
  <span>SZL HOLDINGS</span><span class="sep">/</span>
  <span style="color:var(--teal)">KILLINCHU</span><span class="sep">/</span>
  <span>ORGANISM · CAUSAL ANATOMY + SELF-REPAIR</span><span class="sep">/</span>
  <span class="live"><span class="live-dot"></span><span>ORGANISM · RT</span></span>
  <nav class="switcher" aria-label="Surfaces">
    <span class="lbl">SURFACES</span>
    <a class="flag" href="/elite">Drones &amp; Vessels</a>
    <a class="flag" href="/elite/mesh">MESH</a>
    <a class="flag active" href="/elite/organism">Organism</a>
    <a class="flag" href="/elite/autonomy">Autonomy</a>
    <a class="flag" href="/estate-organism">Estate 3D</a>
  </nav>
</div>

<div class="wrap">
  <div class="brand"><div class="mark">K</div><div><div class="nm">killinchu</div><div class="role">organism · causal anatomy + NCA self-repair</div></div></div>
  <div class="view-head">
    <h1 class="view-title">ORGANISM</h1>
    <span class="view-badge" id="hd-mode">LIVE ANATOMY</span>
    <span class="view-badge warn">self-repair EXPERIMENTAL</span>
    <span class="view-badge gold">human-on-loop</span>
  </div>
  <p class="view-sub">The living organism (a11oy + killinchu) as a <b>directed causal-dependency graph</b>: an edge source&rarr;target means the <b>target organ causally depends on</b> the source. Each organ holds <b>local homeostatic invariants</b>. <b>DEMO:</b> kill an organ and watch downstream organs <b>re-route</b> around it while the surrounding tissue <b>self-heals</b> over discrete NCA-style steps. Vitals are LIVE where the in-process anatomy/mesh expose them, MODELED otherwise; self-repair is an <b>EXPERIMENTAL explicit local rule</b> (not a trained CA). Effectors SIMULATED — this heals a <b>model</b> of the organism.</p>

  <div class="layout">
    <div>
      <div class="card">
        <div class="card-h"><span class="card-t">Causal organism · 3D</span>
          <span class="lbl-pill live" id="lbl-3d">LIVE + EXPERIMENTAL</span>
          <span class="card-ep mono">GET /organism/causal · /self-repair</span></div>
        <canvas id="c"></canvas>
        <div class="controls">
          <span class="mono" style="font-size:11px;color:var(--muted)">lesion organ</span>
          <select id="organ-sel"></select>
          <button class="danger" onclick="killOrgan()">KILL ORGAN → self-heal</button>
          <button class="teal" onclick="resetOrganism()">restore (no lesion)</button>
        </div>
        <div class="step-readout" id="step-readout">organism healthy · no lesion</div>
        <div id="events"></div>
      </div>
    </div>
    <div>
      <div class="card">
        <div class="card-h"><span class="card-t">Organs · invariants · vitals</span>
          <span class="card-ep mono" id="lam-readout">λ2 …</span></div>
        <div id="organs"><div class="organ"><h3>loading causal anatomy…</h3></div></div>
      </div>
      <div class="card">
        <div class="card-h"><span class="card-t">Self-repair trace</span><span class="lbl-pill exp">EXPERIMENTAL</span></div>
        <div class="out" id="repair-out">kill an organ to run the local homeostatic update…</div>
      </div>
    </div>
  </div>

  <div class="footnote">
    <b>HONESTY.</b> The causal graph + invariants are LIVE; per-organ vitals are LIVE where the in-process anatomy/mesh expose them, MODELED otherwise. Self-repair is an <b>EXPERIMENTAL explicit local rule</b> — s += rate·(mean(neighbour_state)−s), the lesioned organ pinned to 0, re-route on a dead required upstream — not a trained neural CA. Fiedler λ2 is the same spectral metric the MESH surface uses. 3D is the app's vendored UMD three.js (<span class="mono">/vendor/three.min.js</span>); <b>0 runtime CDN</b> — degrades to an honest 2D fallback if the vendor bundle is absent. Effectors <b>SIMULATED human-on-loop</b> — no live vessel/sub control. Doctrine v11, locked = 8 @ c7c0ba17.<br/>
    <b>Refs.</b> Growing NCA distill.pub/2020/growing-ca · homeostatic NCA arXiv:2511.02241 · Fiedler arXiv:2504.06894.
  </div>
</div>

<script>
var NS="killinchu";
var BASE="/api/"+NS+"/v1/organism";
var $=function(id){return document.getElementById(id);};
var ORGANS=[], EDGES=[], MESHES={}, LINES=[], THREEref=null, SCENE=null, CAM=null, RND=null;
var COLORS={brain:0x5fb3a3,heart:0xd08a78,nervous:0x3aa0ff,circulatory:0xc9b787,skeleton:0x9a9a9a,overwatch:0xb07cff};
var POS={brain:[0,2.2,0],heart:[0,0.7,0],nervous:[2.0,-0.1,0],circulatory:[-2.0,-0.1,0],skeleton:[0,-1.9,0],overwatch:[0,-0.5,1.6]};

function loadThree(cb){
  var srcs=['/vendor/three.min.js','/static-vendor/three.min.js','/static/vendor3d/three.min.js'];
  (function next(i){
    if(window.THREE&&window.THREE.Scene){cb(window.THREE);return;}
    if(i>=srcs.length){cb(null);return;}
    var s=document.createElement('script');s.src=srcs[i];
    s.onload=function(){(window.THREE&&window.THREE.Scene)?cb(window.THREE):next(i+1);};
    s.onerror=function(){next(i+1);};
    document.head.appendChild(s);
  })(0);
}

function organCard(o){
  var v=o.vitals||{}; var lab=(v.label||'MODELED');
  var rows='';
  for(var k in v){ if(k==='label'||v[k]==null||typeof v[k]==='object')continue; rows+='<div class="inv"><b>'+k+'</b> = '+v[k]+'</div>'; }
  var inv=(o.invariants||[]).map(function(x){return '· '+x;}).join('<br/>');
  var dep=(o.depends_on&&o.depends_on.length)?('depends on: '+o.depends_on.join(', ')):'source organ (no upstream)';
  var rr=(o.reroute&&o.reroute.length)?(' · reroute: '+o.reroute.join(', ')):'';
  return '<div class="organ" id="organ-'+o.organ+'"><h3>'+o.organ.toUpperCase()+
    ' <span class="lbl-pill '+(lab.indexOf('LIVE')===0?'live':(lab.indexOf('EXP')===0?'exp':''))+'">'+lab+'</span></h3>'+
    '<div class="sys">'+(o.system||'')+'</div>'+rows+
    '<div class="bar"><i id="bar-'+o.organ+'" style="width:100%"></i></div>'+
    '<div class="inv">'+inv+'</div><div class="dep">'+dep+rr+'</div></div>';
}

function init(){
  fetch(BASE+'/causal').then(function(r){return r.json();}).then(function(d){
    ORGANS=d.organs||[]; EDGES=d.edges||[];
    $('hd-mode').textContent=(d.label&&d.label.indexOf('LIVE')===0)?'LIVE ANATOMY':'MODELED';
    $('organs').innerHTML=ORGANS.map(organCard).join('');
    $('lam-readout').textContent='λ2 '+(d.fiedler_lambda2!=null?(+d.fiedler_lambda2).toFixed(3):'n/a')+' · '+(d.lambda2_label||'');
    var sel=$('organ-sel'); sel.innerHTML='';
    ORGANS.forEach(function(o){ var op=document.createElement('option'); op.value=o.organ; op.textContent=o.organ; sel.appendChild(op); });
    if(sel.querySelector('option[value=nervous]')) sel.value='nervous';
    draw3D();
  }).catch(function(e){ $('organs').innerHTML='<div class="organ"><h3>anatomy unreachable (honest)</h3><div class="inv">'+e.message+'</div></div>'; });
}

function draw3D(){
  var cv=$('c');
  loadThree(function(THREE){
    if(!THREE){ var ctx=cv.getContext('2d'); cv.width=cv.clientWidth;cv.height=cv.clientHeight;
      if(ctx){ctx.fillStyle='#9a9a9a';ctx.font='13px sans-serif';ctx.fillText('3D vendor unavailable — organ list + self-repair trace shown (honest fallback).',16,30);} return; }
    THREEref=THREE;
    SCENE=new THREE.Scene(); CAM=new THREE.PerspectiveCamera(55,cv.clientWidth/cv.clientHeight,0.1,100); CAM.position.z=7.2;
    RND=new THREE.WebGLRenderer({canvas:cv,antialias:true,alpha:true}); RND.setSize(cv.clientWidth,cv.clientHeight);
    MESHES={}; LINES=[];
    EDGES.forEach(function(e){ var p=POS[e.source],q=POS[e.target]; if(!p||!q)return;
      var gg=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(p[0],p[1],p[2]),new THREE.Vector3(q[0],q[1],q[2])]);
      var lm=new THREE.LineBasicMaterial({color:0x2a3a38,transparent:true,opacity:0.7});
      var ln=new THREE.Line(gg,lm); ln.userData={source:e.source,target:e.target,rerouteable:e.rerouteable}; SCENE.add(ln); LINES.push(ln); });
    ORGANS.forEach(function(o){ var p=POS[o.organ]||[0,0,0];
      var g=new THREE.SphereGeometry(0.5,24,24);
      var m=new THREE.MeshBasicMaterial({color:COLORS[o.organ]||0x5fb3a3,wireframe:true,transparent:true,opacity:0.85});
      var sp=new THREE.Mesh(g,m); sp.position.set(p[0],p[1],p[2]); sp.userData={organ:o.organ,base:0.5,health:1.0}; SCENE.add(sp); MESHES[o.organ]=sp; });
    (function anim(){ requestAnimationFrame(anim);
      for(var k in MESHES){ MESHES[k].rotation.y+=0.006; MESHES[k].rotation.x+=0.002; }
      SCENE.rotation.y+=0.0012; RND.render(SCENE,CAM); })();
    window.addEventListener('resize',function(){ if(!CAM)return; CAM.aspect=cv.clientWidth/cv.clientHeight; CAM.updateProjectionMatrix(); RND.setSize(cv.clientWidth,cv.clientHeight); });
  });
}

function applyState(state,down,activeReroutes){
  // scale + recolor each organ sphere by health; gray the lesion; pulse reroute lines
  for(var organ in state){ var h=state[organ];
    var bar=$('bar-'+organ); if(bar) bar.style.width=Math.round(h*100)+'%';
    var card=$('organ-'+organ); if(card) card.style.opacity=(organ===down?0.45:1);
    var sp=MESHES[organ]; if(sp){ var s=0.28+0.42*h; sp.scale.set(s/0.5,s/0.5,s/0.5);
      sp.material.opacity=(organ===down)?0.18:(0.35+0.6*h);
      sp.material.color.setHex(organ===down?0x402a26:(COLORS[organ]||0x5fb3a3)); } }
  if(THREEref&&LINES.length){ LINES.forEach(function(ln){
    var u=ln.userData; var involvesDown=(u.source===down||u.target===down);
    var isReroute=activeReroutes.some(function(rr){ return rr.organ===u.target||rr.organ===u.source; });
    ln.material.color.setHex(involvesDown?0x6f2f28:(isReroute?0x5fb3a3:0x2a3a38));
    ln.material.opacity=involvesDown?0.3:(isReroute?0.9:0.6); }); }
}

function renderTrace(d){
  var trace=d.trace||[]; var reroutes=d.reroutes||[]; var i=0;
  $('events').innerHTML=(reroutes.map(function(rr){return '<div class="event">↻ step '+rr.step+': '+rr.organ+' re-routed to '+rr.rerouted_to+'</div>';}).join(''))
    +((d.invariant_alerts||[]).map(function(a){return '<div class="event">⚠ '+a.organ+': '+a.risk+'</div>';}).join(''));
  (function tick(){
    if(i>=trace.length){ $('step-readout').textContent='healed · recovered: '+((d.recovered_organs||[]).join(', ')||'—')+' · lesion '+(d.lesion||'none')+' stays down (EXPERIMENTAL)'; return; }
    var fr=trace[i]; var activeRR=reroutes.filter(function(rr){return rr.step<=fr.step;});
    applyState(fr.state,d.lesion,activeRR);
    $('step-readout').textContent='step '+fr.step+'/'+(trace.length-1)+' · lesion '+(d.lesion||'none')+' · organism health '+(d.organism_health_excl_lesion!=null?Math.round(d.organism_health_excl_lesion*100)+'%':'…');
    i++; setTimeout(tick, 230);
  })();
}

function killOrgan(){
  var organ=$('organ-sel').value;
  fetch(BASE+'/self-repair?down='+encodeURIComponent(organ)+'&steps=14&rate=0.5').then(function(r){return r.json();}).then(function(d){
    $('repair-out').textContent=JSON.stringify({lesion:d.lesion,rule:d.rule,reroutes:d.reroutes,invariant_alerts:d.invariant_alerts,recovered_organs:d.recovered_organs,final_state:d.final_state,label:d.label},null,2);
    renderTrace(d);
  }).catch(function(e){ $('repair-out').textContent='ERR: '+e.message; });
}
function resetOrganism(){
  fetch(BASE+'/self-repair?steps=2&rate=0.5').then(function(r){return r.json();}).then(function(d){
    applyState(d.final_state,null,[]); $('events').innerHTML=''; $('step-readout').textContent='organism healthy · no lesion';
    $('repair-out').textContent='restored — all organs holding homeostatic set-points.';
  }).catch(function(e){ $('repair-out').textContent='ERR: '+e.message; });
}

init();
</script>
</body>
</html>"""


async def _organism_view(request):
    return HTMLResponse(_PAGE)


def register(app, ns="killinchu"):
    """ADDITIVE. Mount the ORGANISM causal/self-repair view BEFORE the SPA
    catch-all. Pure VIEW — reads the REAL /organism/causal + /organism/self-repair
    endpoints; reinvents no backend. 0 runtime CDN. Effectors SIMULATED."""
    routes = [
        Route("/elite/organism", _organism_view, methods=["GET"],
              name="%s_elite_organism" % ns),
        Route("/organism-surface", _organism_view, methods=["GET"],
              name="%s_organism_surface_alias" % ns),
    ]
    for r in reversed(routes):
        app.router.routes.insert(0, r)
    return {"status": "ok", "view": "organism_view",
            "routes": ["/elite/organism", "/organism-surface"],
            "doctrine": _DOCTRINE, "locked": _LOCKED}
