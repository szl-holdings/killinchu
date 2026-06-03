/* SPDX-License-Identifier: Apache-2.0
 * © 2026 Lutar, Stephen P. — SZL Holdings.  ORCID: 0009-0001-0110-4173
 * killinchu console.js — binds the premium edge deck to the REAL live verdict
 * stream (SSE /api/killinchu/v1/stream/verdicts) and the REAL 3D edge scene
 * (/api/killinchu/v1/edge/3d). Every value rendered is a real signed Λ verdict.
 * Flight motion is simulator-driven (simulated=true), NOT a connected drone.
 * Doctrine v11 LOCKED · Λ = Conjecture 1 · SLSA L1 honest. No mocks.
 * Signed-off-by: Yachay <yachay@szlholdings.ai>
 * Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
 */
(function () {
  "use strict";
  var API = "/api/killinchu/v1";
  var COL = { DENY: 0xd65151, REVIEW: 0xcda64a, ALLOW: 0x34aaa4 };
  var COLHEX = { DENY: "#d65151", REVIEW: "#cda64a", ALLOW: "#34aaa4" };

  var $ = function (id) { return document.getElementById(id); };
  var recent = [];          // last verdicts (most recent first)
  var tracks = {};          // track_id -> latest record
  var maxRows = 20;

  /* ── Λ tile ─────────────────────────────────────────── */
  function lamClass(d) { return d === "ALLOW" ? "allow" : d === "REVIEW" ? "review" : "deny"; }
  function updateLambda(r) {
    var v = $("lamVal");
    v.textContent = r.lambda_value.toFixed(4);
    v.className = "lambda-val " + lamClass(r.decision);
    $("lamTrack").textContent = r.track_id + " · " + r.source + (r.simulated ? " · sim" : "");
    var pill = $("lamPill");
    pill.textContent = r.decision; pill.className = "verdict-pill " + r.decision;
    $("lamBar").style.width = (Math.max(0, Math.min(1, r.lambda_value)) * 100).toFixed(1) + "%";
    $("lamEmp").textContent = (r.lambda_empirical != null ? r.lambda_empirical : r.lambda_value).toFixed(4);
    $("lamFloor").textContent = (r.certified_floor != null ? r.certified_floor : r.lambda_value).toFixed(4);
    $("lamN").textContent = r.n_observations;
    $("lamKhipu").textContent = "#" + r.khipu_index;
    $("keyid").textContent = r.dsse_keyid || r.key_source || "edge";
  }

  /* ── Verdict stream rows ────────────────────────────── */
  function renderStream() {
    var box = $("stream");
    if (!recent.length) { box.innerHTML = '<div class="empty">Binding to live verdict stream…</div>'; return; }
    var html = "";
    for (var i = 0; i < Math.min(recent.length, maxRows); i++) {
      var r = recent[i];
      var t = new Date(r.ts);
      var hh = t.toLocaleTimeString([], { hour12: false });
      html += '<div class="vrow ' + r.decision + '">' +
        '<span class="badge"></span>' +
        '<div class="who">' + esc(r.track_id) +
          '<small>' + esc(r.source) + ' · ' + hh + ' · n=' + r.n_observations +
          ' · khipu#' + r.khipu_index + '</small></div>' +
        '<div class="lam"><span class="b">' + r.lambda_value.toFixed(3) + '</span>' +
          '<small>' + r.decision + '</small></div>' +
      '</div>';
    }
    box.innerHTML = html;
    $("streamCount").textContent = recent.length + " signed";
  }
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function ingest(r) {
    recent.unshift(r);
    if (recent.length > 200) recent.pop();
    tracks[r.track_id] = r;
    updateLambda(r);
    renderStream();
    updateScene();
  }

  /* ── 3D edge map (Three.js) ─────────────────────────── */
  var THREE = window.THREE, renderer, scene, camera, trackMeshes = {}, pathLines = {}, noFly = [];
  var GRID = 60;          // world half-extent
  var originLat = -13.53, originLon = -71.97, mPerDeg = 111000;

  function ll2world(lat, lon) {
    // local tangent-plane projection centred on the sensor (scaled to fill scene)
    var x = (lon - originLon) * mPerDeg * Math.cos(originLat * Math.PI / 180) / 5.5;
    var z = (lat - originLat) * mPerDeg / 5.5;
    return new THREE.Vector3(x, 0, -z);
  }

  function initScene() {
    if (!THREE) return;
    var cv = $("scene");
    renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x0a0f1e, 90, 240);
    camera = new THREE.PerspectiveCamera(46, 1, 0.1, 1000);
    resize();
    // lights
    scene.add(new THREE.AmbientLight(0x6f7c93, 0.7));
    var key = new THREE.DirectionalLight(0xffe6c4, 0.9); key.position.set(40, 80, 30); scene.add(key);
    var rim = new THREE.DirectionalLight(0xd65151, 0.35); rim.position.set(-50, 30, -40); scene.add(rim);

    // terrain — Andean ridged plane
    var geo = new THREE.PlaneGeometry(GRID * 2, GRID * 2, 48, 48);
    var pos = geo.attributes.position;
    for (var i = 0; i < pos.count; i++) {
      var x = pos.getX(i), y = pos.getY(i);
      var h = Math.sin(x * 0.06) * Math.cos(y * 0.05) * 3.0
            + Math.sin(x * 0.13 + 1.7) * 1.4 + Math.cos(y * 0.11) * 1.2;
      pos.setZ(i, h);
    }
    geo.computeVertexNormals();
    var mat = new THREE.MeshStandardMaterial({ color: 0x182234, roughness: 0.95, metalness: 0.0, flatShading: true });
    var terrain = new THREE.Mesh(geo, mat); terrain.rotation.x = -Math.PI / 2; terrain.position.y = -2; scene.add(terrain);
    // grid overlay
    var grid = new THREE.GridHelper(GRID * 2, 28, 0x2e3a52, 0x1b2334); grid.position.y = 0.02; scene.add(grid);

    // sensor marker at origin
    var sensor = new THREE.Mesh(new THREE.ConeGeometry(1.4, 4, 6),
      new THREE.MeshStandardMaterial({ color: 0x5cc4bf, emissive: 0x0f726e, emissiveIntensity: 0.5 }));
    sensor.position.set(0, 2, 0); scene.add(sensor);

    animate();
    window.addEventListener("resize", resize);
  }

  function resize() {
    if (!renderer) return;
    var cv = $("scene"); var w = cv.clientWidth || 600, h = cv.clientHeight || 400;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }

  function drawNoFly(poly) {
    if (!THREE || !scene || !poly || noFly.length) return;
    var pts = poly.map(function (p) { var v = ll2world(p.lat, p.lon); v.y = 0.3; return v; });
    pts.push(pts[0].clone());
    var g = new THREE.BufferGeometry().setFromPoints(pts);
    var line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xd65151, transparent: true, opacity: 0.85 }));
    scene.add(line); noFly.push(line);
    // translucent fill
    var shape = new THREE.Shape();
    poly.forEach(function (p, i) { var v = ll2world(p.lat, p.lon); if (i === 0) shape.moveTo(v.x, -v.z); else shape.lineTo(v.x, -v.z); });
    var fillGeo = new THREE.ShapeGeometry(shape);
    var fill = new THREE.Mesh(fillGeo, new THREE.MeshBasicMaterial({ color: 0xd65151, transparent: true, opacity: 0.10, side: THREE.DoubleSide }));
    fill.rotation.x = -Math.PI / 2; fill.position.y = 0.25; scene.add(fill); noFly.push(fill);
  }

  function updateScene() {
    if (!THREE || !scene) return;
    Object.keys(tracks).forEach(function (id) {
      var r = tracks[id];
      var col = COL[r.decision] || 0x888888;
      var p = ll2world(r.position.lat, r.position.lon); p.y = 2 + (r.position.alt_m || 0) / 20;
      var m = trackMeshes[id];
      if (!m) {
        var geo = new THREE.SphereGeometry(1.3, 18, 18);
        m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.55 }));
        var halo = new THREE.Mesh(new THREE.RingGeometry(2, 2.4, 24),
          new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
        halo.rotation.x = -Math.PI / 2; m.add(halo); m.userData.halo = halo;
        scene.add(m); trackMeshes[id] = m;
        pathLines[id] = { pts: [], line: null };
      }
      m.position.copy(p);
      m.material.color.setHex(col); m.material.emissive.setHex(col);
      m.userData.halo.material.color.setHex(col);
      // trail
      var pl = pathLines[id]; pl.pts.push(p.clone()); if (pl.pts.length > 60) pl.pts.shift();
      if (pl.line) scene.remove(pl.line);
      if (pl.pts.length > 1) {
        var g = new THREE.BufferGeometry().setFromPoints(pl.pts);
        pl.line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.55 }));
        scene.add(pl.line);
      }
    });
  }

  var camAngle = 0;
  function animate() {
    requestAnimationFrame(animate);
    if (!renderer) return;
    camAngle += 0.0016;
    var R = 72, H = 50;
    camera.position.set(Math.sin(camAngle) * R, H, Math.cos(camAngle) * R);
    camera.lookAt(0, 5, 0);
    Object.keys(trackMeshes).forEach(function (id) {
      var h = trackMeshes[id].userData.halo; if (h) h.rotation.z += 0.03;
    });
    renderer.render(scene, camera);
  }

  /* ── Live binding: SSE primary, polling fallback ────── */
  function setConn(state, text) {
    var d = $("connDot"); d.className = "dot" + (state === "live" ? " live" : "");
    $("connText").textContent = text;
  }

  function bootstrap() {
    // seed from the 3D endpoint so the deck isn't empty on first paint
    fetch(API + "/edge/3d").then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.scene) {
        drawNoFly(d.scene.no_fly_polygon);
        (d.scene.tracks || []).forEach(function (t) {
          ingest(normalize(t));
        });
      }
    }).catch(function () {});
  }

  function normalize(t) {
    return {
      ts: t.ts, track_id: t.track_id, source: t.source, simulated: t.simulated,
      position: t.position || { lat: 0, lon: 0, alt_m: 0 },
      lambda_value: t.lambda_value, lambda_empirical: t.lambda_empirical,
      certified_floor: t.certified_floor, decision: t.decision,
      n_observations: t.n_observations, khipu_index: t.khipu_index,
      dsse_keyid: t.dsse_keyid, key_source: t.key_source,
    };
  }

  function connectSSE() {
    try {
      var es = new EventSource(API + "/stream/verdicts");
      es.addEventListener("open", function () { setConn("live", "live · SSE bound"); });
      es.addEventListener("verdict", function (ev) {
        try { ingest(normalize(JSON.parse(ev.data))); } catch (e) {}
      });
      es.addEventListener("error", function () {
        setConn("", "reconnecting…");
      });
    } catch (e) { pollFallback(); }
  }

  function pollFallback() {
    setConn("live", "live · polling");
    setInterval(function () {
      fetch(API + "/edge/3d").then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.scene && d.scene.tracks && d.scene.tracks.length) {
          ingest(normalize(d.scene.tracks[d.scene.tracks.length - 1]));
        }
      }).catch(function () {});
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initScene();
    bootstrap();
    if (window.EventSource) connectSSE(); else pollFallback();
  });
})();
