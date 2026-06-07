/* ============================================================================
 * killinchu_cathedral.js — killinchu front-door sovereign 3D hero (vendored Three.js).
 * Field node (edge) tethered to the a11oy brain-sun upstream (substrate reaches the edge).
 * Honesty: locked proven = 5; Λ = Conjecture 1; Trust Gate = Conjecture;
 * conformal (never 100%) not Hoeffding; SLSA L1 honest / L2 roadmap.
 * Live /healthz + khipu ledger for a real edge-Λ constellation; honest fallback.
 * Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
 * ========================================================================== */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';

const KILLINCHU = {
  id:'killinchu', title:'killinchu — Field Node (maritime + drone C2)',
  plain:'Counter-UAS drone & vessel intelligence at the tactical edge — the deployed field node of the substrate. Live: /healthz.',
  functions:['maritime + drone C2 — vessels CONSOLIDATED into killinchu (/elite fleet group)','OpenDroneID / ASTM F3411 · ADS-B Mode-S 1090ES · MAVLink v1/v2 decoders','counter-UAS A-gate + 13-axis edge Λ verdict · tactical routing · threat ranking · adaptive sampling','/wave910: 6 wave 9/10 edge formula cards · Q2 Gershgorin spectral bound','signed Khipu receipts (ECDSA-P256 DSSE when signed)'],
  proof:['Edge verdict bound by proven formulas: C20/W7-5 router, W5-3/W7-4 conformal (never 100%)','Same doctrine lock 749/14/163 @ c7c0ba17 · Λ = Conjecture 1 · Trust Gate = Conjecture · SLSA L1 honest / L2 roadmap'],
  url:'/operator'
};
const A11OY = {
  id:'a11oy', title:'a11oy — Command Platform (the substrate)',
  plain:'The upstream governance brain. killinchu is its deployed field node at the edge.',
  functions:['one governance substrate (reasoning / policy / operator are internal)','13-axis Trust Score aggregate (geometric mean, floor 0.90)','signed Khipu receipts for every governed action'],
  proof:['Locked proven kernel = 5 {F1,F11,F12,F18,F19} @ c7c0ba17 — machine-enforced count','Λ-Aggregator uniqueness (F23) = Conjecture 1 — NOT a theorem'],
  url:'https://szlholdings-a11oy.hf.space'
};

const ENDPOINTS = { health:'/healthz', ledger:'/api/killinchu/v1/khipu/ledger', lambda:'/api/killinchu/v1/lambda' };

const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias:true, alpha:false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x070815, 0.0019);
const camera = new THREE.PerspectiveCamera(55, window.innerWidth/window.innerHeight, 0.1, 4000);
camera.position.set(60, 60, 320);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.06;
controls.minDistance = 90; controls.maxDistance = 1100;
controls.autoRotate = true; controls.autoRotateSpeed = 0.45;
controls.target.set(80, -10, -40);

scene.add(new THREE.AmbientLight(0x33304a, 0.9));
scene.add(new THREE.PointLight(0xffe6a8, 1.8, 1600, 1.4));
const rim = new THREE.DirectionalLight(0x5c8fd1, 0.7); rim.position.set(-200,120,-150); scene.add(rim);

(function backdrop(){
  const N=2600, pos=new Float32Array(N*3);
  for(let i=0;i<N;i++){ const r=1400+Math.random()*1600, t=Math.random()*Math.PI*2, p=Math.acos(2*Math.random()-1);
    pos[i*3]=r*Math.sin(p)*Math.cos(t); pos[i*3+1]=r*Math.cos(p); pos[i*3+2]=r*Math.sin(p)*Math.sin(t); }
  const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos,3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color:0x8a90c0, size:1.4, sizeAttenuation:true, transparent:true, opacity:0.55 })));
})();

const interactables=[];
function registerBody(mesh,data){ mesh.userData.inspect=data; interactables.push(mesh); }

/* upstream a11oy substrate (smaller, offset back-left) */
const subGroup=new THREE.Group(); subGroup.position.set(-220,40,-60); scene.add(subGroup);
const subCore=new THREE.Mesh(new THREE.IcosahedronGeometry(22,3),
  new THREE.MeshStandardMaterial({ color:0xffce6e, emissive:0xd79a2e, emissiveIntensity:1.3, roughness:0.35, metalness:0.1 }));
subGroup.add(subCore); registerBody(subCore, A11OY);
subGroup.add(new THREE.Mesh(new THREE.IcosahedronGeometry(27,2), new THREE.MeshBasicMaterial({ color:0xffe6a8, wireframe:true, transparent:true, opacity:0.20 })));
subGroup.add(makeLabel('a11oy', 0xffe6a8, 38));

/* killinchu field node — the focus, larger, foreground-right */
const fieldGroup=new THREE.Group(); fieldGroup.position.set(80,-10,-40); scene.add(fieldGroup);
const fieldNode=new THREE.Mesh(new THREE.OctahedronGeometry(34,0),
  new THREE.MeshStandardMaterial({ color:0x5c8fd1, emissive:0x2c5f9e, emissiveIntensity:0.7, roughness:0.45, metalness:0.3 }));
fieldGroup.add(fieldNode); registerBody(fieldNode, KILLINCHU);
const fieldRing=new THREE.Mesh(new THREE.TorusGeometry(50,0.9,8,90), new THREE.MeshBasicMaterial({ color:0x5c8fd1, transparent:true, opacity:0.4 }));
fieldRing.rotation.x=Math.PI/2.4; fieldGroup.add(fieldRing);
const fieldRing2=new THREE.Mesh(new THREE.TorusGeometry(64,0.5,8,90), new THREE.MeshBasicMaterial({ color:0x8fb6e6, transparent:true, opacity:0.22 }));
fieldRing2.rotation.x=Math.PI/3; fieldGroup.add(fieldRing2);
fieldGroup.add(makeLabel('killinchu', 0x8fb6e6, 58));

/* traceparent tether substrate -> field node */
const tether=new THREE.Line(new THREE.BufferGeometry().setFromPoints([subGroup.position.clone(), fieldGroup.position.clone()]),
  new THREE.LineBasicMaterial({ color:0x9b8cff, transparent:true, opacity:0.45 }));
scene.add(tether);

/* edge khipu constellation around the field node */
const khipuGroup=new THREE.Group(); khipuGroup.position.copy(fieldGroup.position); scene.add(khipuGroup);
let receiptPoints=null, cordLines=null;
const VERDICT_COLOR={ green:0x4fd18b, amber:0xd7b96b, red:0xc0392b };
function verdictOf(l){ return l>=0.9?'green':(l>=0.5?'amber':'red'); }
function seededVec(seed,radius){ let h=2166136261>>>0; for(let i=0;i<seed.length;i++){ h^=seed.charCodeAt(i); h=Math.imul(h,16777619)>>>0; }
  const a=(h%10000)/10000*Math.PI*2, b=Math.acos(2*(((h>>>13)%10000)/10000)-1), r=radius*(0.55+0.45*(((h>>>7)%10000)/10000));
  return new THREE.Vector3(r*Math.sin(b)*Math.cos(a), r*Math.cos(b), r*Math.sin(b)*Math.sin(a)); }
function seedConstellation(){ const arr=[]; for(let i=0;i<48;i++){ const id='seed-'+i.toString(16).padStart(4,'0');
  const l=0.90+(((i*2654435761)>>>0)%100)/1000; arr.push({ id, prev:i>0&&(i%5!==0)?'seed-'+(i-1).toString(16).padStart(4,'0'):null, lambda:Math.min(0.999,l), source:'SEED' }); } return arr; }
function renderConstellation(nodes){
  if(receiptPoints){ khipuGroup.remove(receiptPoints); receiptPoints.geometry.dispose(); }
  if(cordLines){ khipuGroup.remove(cordLines); cordLines.geometry.dispose(); }
  const pos=new Float32Array(nodes.length*3), col=new Float32Array(nodes.length*3), byId={};
  nodes.forEach((n,i)=>{ const v=seededVec(n.id,150); n._v=v; byId[n.id]=v; pos[i*3]=v.x;pos[i*3+1]=v.y;pos[i*3+2]=v.z;
    const c=new THREE.Color(VERDICT_COLOR[verdictOf(n.lambda)]||0x888888); col[i*3]=c.r;col[i*3+1]=c.g;col[i*3+2]=c.b; });
  const g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.BufferAttribute(pos,3)); g.setAttribute('color',new THREE.BufferAttribute(col,3));
  receiptPoints=new THREE.Points(g,new THREE.PointsMaterial({ size:3.6, vertexColors:true, transparent:true, opacity:0.92, sizeAttenuation:true })); khipuGroup.add(receiptPoints);
  const lp=[]; nodes.forEach(n=>{ if(n.prev&&byId[n.prev]){ const a=byId[n.prev], b=n._v, mid=a.clone().add(b).multiplyScalar(0.5).multiplyScalar(1.18);
    const cv=new THREE.QuadraticBezierCurve3(a,mid,b).getPoints(10); for(let k=0;k<cv.length-1;k++){ lp.push(cv[k].x,cv[k].y,cv[k].z,cv[k+1].x,cv[k+1].y,cv[k+1].z); } } });
  const lg=new THREE.BufferGeometry(); lg.setAttribute('position',new THREE.Float32BufferAttribute(lp,3));
  cordLines=new THREE.LineSegments(lg,new THREE.LineBasicMaterial({ color:0xc08f2f, transparent:true, opacity:0.30 })); khipuGroup.add(cordLines);
}

function makeLabel(text,color,size){
  const c=document.createElement('canvas'); c.width=256; c.height=64; const ctx=c.getContext('2d');
  ctx.font='700 34px ui-monospace, Menlo, Consolas, monospace'; ctx.fillStyle='#'+new THREE.Color(color).getHexString();
  ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.shadowColor='rgba(0,0,0,0.8)'; ctx.shadowBlur=8; ctx.fillText(text,128,34);
  const tex=new THREE.CanvasTexture(c); tex.anisotropy=4;
  const spr=new THREE.Sprite(new THREE.SpriteMaterial({ map:tex, transparent:true, depthWrite:false }));
  spr.scale.set(size*2,size*0.5,1); spr.position.y=size*0.9; spr.userData.isLabel=true; return spr;
}

const ray=new THREE.Raycaster(); const ptr=new THREE.Vector2();
canvas.addEventListener('click',(e)=>{ const r=canvas.getBoundingClientRect();
  ptr.x=((e.clientX-r.left)/r.width)*2-1; ptr.y=-((e.clientY-r.top)/r.height)*2+1; ray.setFromCamera(ptr,camera);
  const hits=ray.intersectObjects(interactables,false); if(hits.length) openInspector(hits[0].object.userData.inspect); });

const insp=document.getElementById('inspector');
document.getElementById('insp-close').addEventListener('click',()=>insp.classList.remove('show'));
function openInspector(d){ if(!d) return;
  document.getElementById('insp-title').textContent=d.title; document.getElementById('insp-plain').textContent=d.plain;
  let html='<div class="ih">Functions</div><ul>'+d.functions.map(f=>`<li>${esc(f)}</li>`).join('')+'</ul>';
  if(d.proof) html+='<div class="ih">Proof support (honest)</div><ul>'+d.proof.map(p=>`<li class="proof">${esc(p)}</li>`).join('')+'</ul>';
  if(d.url) html+=`<div class="ih">Open</div><ul><li><a href="${d.url}" style="color:#5cc4bf">Open ↗</a></li></ul>`;
  document.getElementById('insp-body').innerHTML=html; insp.classList.add('show'); }
function esc(s){ return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

let liveState={ killinchu:'…' }, feedSource='connecting…';
async function getJSON(url,ms){ const ctrl=new AbortController(); const t=setTimeout(()=>ctrl.abort(), ms||7000);
  try{ const r=await fetch(url,{ signal:ctrl.signal, headers:{accept:'application/json'} }); if(!r.ok) throw 0; return await r.json(); } finally{ clearTimeout(t); } }
async function poll(){
  try{ const h=await getJSON(ENDPOINTS.health,7000); liveState.killinchu=(h&&(h.status==='ok'||h.ok))?'LIVE':'DEGRADED'; }
  catch(_){ liveState.killinchu='OFFLINE'; }
  let nodes=null, src='SEED · deterministic (no live receipts yet)';
  try{ const led=await getJSON(ENDPOINTS.ledger,7000);
    if(led&&Array.isArray(led.nodes)&&led.nodes.length){ nodes=led.nodes.map((n,i)=>({ id:(n.digest||('k'+i)).slice(0,16), prev:(n.parents&&n.parents[0])?String(n.parents[0]).slice(0,16):null,
      lambda: typeof n.lambda==='number'?n.lambda:(n.signed?0.92:0.40), source:'LIVE' })); src='LIVE · killinchu khipu ledger ('+nodes.length+' receipts)'; } }catch(_){}
  if(!nodes){ try{ const lam=await getJSON(ENDPOINTS.lambda,7000); if(lam&&typeof lam.lambda==='number'){ nodes=seedConstellation().map(n=>({ ...n, lambda:lam.lambda, source:'SEED+liveΛ' }));
    src='SEED positions · LIVE edge Λ='+lam.lambda.toFixed(3); } }catch(_){} }
  if(!nodes) nodes=seedConstellation();
  feedSource=src; renderConstellation(nodes); paintHUD();
}
function paintHUD(){ const cls=liveState.killinchu==='LIVE'?'live':(liveState.killinchu==='OFFLINE'?'off':'seed');
  document.getElementById('status-rows').innerHTML=`<div class="row"><span class="dot ${cls}"></span><span>killinchu · field</span><span class="meta">${liveState.killinchu}</span></div>`;
  document.getElementById('feed-src').textContent=feedSource; }

let tms=0;
function animate(){ requestAnimationFrame(animate); tms+=0.004;
  subCore.rotation.y+=0.0014; fieldNode.rotation.y+=0.008; fieldRing.rotation.z+=0.004; fieldRing2.rotation.z-=0.0026;
  khipuGroup.rotation.y+=0.0007; controls.update(); renderer.render(scene,camera); }
window.addEventListener('resize',()=>{ camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth,window.innerHeight); });
renderConstellation(seedConstellation()); paintHUD(); animate();
(function(){ var b=document.getElementById('boot'); b.classList.add('hide');
  b.addEventListener('transitionend', function(){ b.style.display='none'; });
  setTimeout(function(){ b.style.display='none'; }, 1200); })();
poll(); setInterval(poll, 8000);
controls.addEventListener('start',()=>{ controls.autoRotate=false; });
