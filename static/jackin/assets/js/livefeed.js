/* ============================================================================
 * killinchu JACK-IN console — LIVE FEED tab  (DEV 2 owns this file)
 * Renders into  <section id="tab-livefeed">  (mount point owned by DEV 1).
 * Consumes the shared bus per BUILD_CONTRACT:
 *     window.JACKIN.on('telemetry', fn)   payload {lat,lon,alt,hdg,spd,batt,rssi,src,ts,raw}
 *     window.JACKIN.on('link', fn)        link/heartbeat state changes
 *     window.JACKIN.source.status()       -> { live:bool, kind, connected, ... }
 *     window.JACKIN.label(isLive)         -> 'LIVE' | 'SAMPLE'
 * 0 CDN. Self-hosted canvas tactical map (NO map tiles). WCAG-AA. Responsive.
 * Premium glassmorphic styling — uses DEV 1's console.css CSS variables, with
 * safe fallbacks so this file renders standalone during dev.
 * ==========================================================================*/
(function () {
  'use strict';

  // --- defensive bus access -------------------------------------------------
  // BUILD_CONTRACT guarantees window.JACKIN once DEV 1 + DEV 5 land. We never
  // assume it exists; we degrade gracefully and (for dev only) spin a mock.
  function bus() { return (window.JACKIN && window.JACKIN.bus) || null; }
  function on(type, fn) {
    if (window.JACKIN && typeof window.JACKIN.on === 'function') {
      window.JACKIN.on(type, fn); return true;
    }
    var b = bus();
    if (b && typeof b.addEventListener === 'function') {
      b.addEventListener(type, function (e) { fn(e.detail); }); return true;
    }
    return false;
  }
  function sourceStatus() {
    try {
      if (window.JACKIN && window.JACKIN.source && typeof window.JACKIN.source.status === 'function') {
        return window.JACKIN.source.status() || {};
      }
    } catch (_) {}
    return {};
  }
  function labelFor(isLive) {
    if (window.JACKIN && typeof window.JACKIN.label === 'function') {
      try { return window.JACKIN.label(isLive); } catch (_) {}
    }
    return isLive ? 'LIVE' : 'SAMPLE';
  }

  var prefersReduced = false;
  try { prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) {}

  // --- module state ---------------------------------------------------------
  var state = {
    last: null,            // latest telemetry frame
    trail: [],             // [{lat,lon,ts}] history for the map trail
    maxTrail: 240,
    haveFix: false,
    linkUp: false,
    sats: 0,
    fixType: 0,            // 0/1 no fix, 2 2D, 3 3D
    mounted: false,
    raf: 0,
    lastDrawTs: 0,
    dpr: 1
  };

  var el = {}; // cached DOM refs

  // ==========================================================================
  // STYLES — scoped, glassmorphic, consistent with DEV 1 console.css variables.
  // We reference --jk-* vars but provide fallbacks (navy #06122E / coral #E07A5F)
  // so the tab is legible even before the shell stylesheet loads.
  // ==========================================================================
  function injectStyles() {
    if (document.getElementById('jk-livefeed-style')) return;
    var css = `
    #tab-livefeed{--lf-navy:var(--jk-navy,#06122E);--lf-coral:var(--jk-coral,#E07A5F);
      --lf-ink:var(--jk-ink,#EAF0FF);--lf-muted:var(--jk-muted,#9FB0D0);
      --lf-glass:var(--jk-glass,rgba(255,255,255,.05));--lf-stroke:var(--jk-stroke,rgba(159,176,208,.22));
      --lf-good:var(--jk-good,#5AD19A);--lf-warn:var(--jk-warn,#F2C14E);--lf-bad:var(--jk-bad,#E0625F);
      --lf-grid:var(--jk-grid,rgba(120,180,255,.16));--lf-radius:var(--jk-radius,16px);
      color:var(--lf-ink);font-family:var(--jk-font,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif);}
    #tab-livefeed *{box-sizing:border-box;}
    .lf-wrap{display:flex;flex-direction:column;gap:14px;padding:4px;}
    .lf-topbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
    .lf-title{font-weight:700;font-size:1.05rem;letter-spacing:.04em;margin:0;}
    .lf-sub{color:var(--lf-muted);font-size:.78rem;margin:0;}
    .lf-pill{display:inline-flex;align-items:center;gap:7px;padding:6px 13px;border-radius:999px;
      font-weight:800;font-size:.78rem;letter-spacing:.09em;border:1px solid var(--lf-stroke);}
    .lf-pill .lf-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto;}
    .lf-pill.is-live{background:rgba(90,209,154,.14);color:var(--lf-good);border-color:rgba(90,209,154,.5);}
    .lf-pill.is-live .lf-dot{background:var(--lf-good);box-shadow:0 0 0 0 rgba(90,209,154,.6);animation:lf-beacon 1.6s infinite;}
    .lf-pill.is-sample{background:rgba(242,193,78,.14);color:var(--lf-warn);border-color:rgba(242,193,78,.5);}
    .lf-pill.is-sample .lf-dot{background:var(--lf-warn);}
    .lf-pill.is-off{background:rgba(224,98,95,.12);color:var(--lf-bad);border-color:rgba(224,98,95,.45);}
    .lf-pill.is-off .lf-dot{background:var(--lf-bad);}
    @keyframes lf-beacon{0%{box-shadow:0 0 0 0 rgba(90,209,154,.55);}70%{box-shadow:0 0 0 7px rgba(90,209,154,0);}100%{box-shadow:0 0 0 0 rgba(90,209,154,0);}}
    .lf-srcbadge{margin-left:auto;display:inline-flex;gap:8px;align-items:center;color:var(--lf-muted);font-size:.74rem;}
    .lf-kind{padding:3px 9px;border-radius:8px;border:1px solid var(--lf-stroke);background:var(--lf-glass);
      font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--lf-ink);}
    .lf-grid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:14px;align-items:stretch;}
    .lf-card{background:var(--lf-glass);border:1px solid var(--lf-stroke);border-radius:var(--lf-radius);
      backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);padding:14px;position:relative;overflow:hidden;}
    .lf-card h3{margin:0 0 10px;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--lf-muted);font-weight:700;}
    .lf-mapcard{padding:0;display:flex;flex-direction:column;min-height:340px;}
    .lf-maphead{display:flex;justify-content:space-between;align-items:center;padding:12px 14px 6px;}
    .lf-maphead h3{margin:0;}
    .lf-mapwrap{position:relative;flex:1;min-height:280px;}
    .lf-mapwrap canvas{display:block;width:100%;height:100%;}
    .lf-mapmeta{position:absolute;left:12px;bottom:10px;font-size:.7rem;color:var(--lf-muted);
      background:rgba(6,18,46,.55);padding:4px 8px;border-radius:8px;border:1px solid var(--lf-stroke);}
    .lf-rcol{display:flex;flex-direction:column;gap:14px;}
    .lf-att{display:flex;flex-direction:column;align-items:center;gap:8px;}
    .lf-att canvas{width:160px;height:160px;max-width:60vw;}
    .lf-att .lf-attvals{display:flex;gap:14px;font-size:.78rem;color:var(--lf-muted);}
    .lf-att .lf-attvals b{color:var(--lf-ink);font-variant-numeric:tabular-nums;}
    .lf-readouts{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
    .lf-stat{background:rgba(255,255,255,.03);border:1px solid var(--lf-stroke);border-radius:12px;padding:10px 12px;}
    .lf-stat .lf-lbl{font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--lf-muted);}
    .lf-stat .lf-val{font-size:1.35rem;font-weight:700;font-variant-numeric:tabular-nums lining-nums;line-height:1.15;margin-top:2px;}
    .lf-stat .lf-unit{font-size:.7rem;color:var(--lf-muted);font-weight:600;margin-left:3px;}
    .lf-batt{margin-top:2px;}
    .lf-batt .lf-bartrack{height:12px;border-radius:7px;background:rgba(255,255,255,.07);border:1px solid var(--lf-stroke);overflow:hidden;position:relative;}
    .lf-batt .lf-barfill{height:100%;border-radius:6px;transition:width .35s ease,background .35s ease;}
    .lf-batt .lf-battnums{display:flex;justify-content:space-between;font-size:.72rem;color:var(--lf-muted);margin-top:4px;}
    .lf-batt .lf-battnums b{color:var(--lf-ink);font-variant-numeric:tabular-nums;}
    .lf-link{display:flex;align-items:center;gap:10px;}
    .lf-bars{display:flex;align-items:flex-end;gap:3px;height:22px;}
    .lf-bars i{width:5px;background:var(--lf-muted);border-radius:2px;opacity:.3;}
    .lf-bars i.on{opacity:1;}
    .lf-meta-line{display:flex;justify-content:space-between;font-size:.74rem;color:var(--lf-muted);margin-top:6px;}
    .lf-meta-line b{color:var(--lf-ink);font-variant-numeric:tabular-nums;}
    .lf-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;
      padding:34px 16px;text-align:center;color:var(--lf-muted);}
    .lf-empty .lf-big{font-size:.95rem;color:var(--lf-ink);font-weight:600;}
    .lf-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
    @media (max-width:880px){.lf-grid{grid-template-columns:1fr;}}
    @media (prefers-reduced-motion: reduce){.lf-pill.is-live .lf-dot{animation:none;}.lf-batt .lf-barfill{transition:none;}}
    `;
    var s = document.createElement('style');
    s.id = 'jk-livefeed-style';
    s.textContent = css;
    document.head.appendChild(s);
  }

  // ==========================================================================
  // MARKUP
  // ==========================================================================
  function buildMarkup(host) {
    host.innerHTML = `
    <div class="lf-wrap" role="region" aria-label="Live telemetry feed">
      <div class="lf-topbar">
        <div>
          <p class="lf-title">LIVE FEED</p>
          <p class="lf-sub">Real-time telemetry from the connected source</p>
        </div>
        <span class="lf-pill is-off" id="lf-pill" role="status" aria-live="polite">
          <span class="lf-dot" aria-hidden="true"></span><span id="lf-pill-text">NO SOURCE</span>
        </span>
        <span class="lf-srcbadge">source <span class="lf-kind" id="lf-kind">—</span></span>
      </div>

      <div class="lf-grid">
        <div class="lf-card lf-mapcard">
          <div class="lf-maphead">
            <h3>Position — tactical grid</h3>
            <span class="lf-sub" id="lf-mapscale">±0 m</span>
          </div>
          <div class="lf-mapwrap">
            <canvas id="lf-map" aria-label="Tactical position map showing track marker and trail"></canvas>
            <div class="lf-mapmeta" id="lf-mapmeta">awaiting fix</div>
          </div>
        </div>

        <div class="lf-rcol">
          <div class="lf-card">
            <h3>Attitude</h3>
            <div class="lf-att">
              <canvas id="lf-att" aria-label="Attitude indicator showing roll pitch and heading"></canvas>
              <div class="lf-attvals">
                <span>ROLL <b id="lf-roll">0°</b></span>
                <span>PITCH <b id="lf-pitch">0°</b></span>
                <span>HDG <b id="lf-yaw">0°</b></span>
              </div>
            </div>
          </div>

          <div class="lf-card">
            <h3>Battery / SYS_STATUS</h3>
            <div class="lf-batt">
              <div class="lf-bartrack"><div class="lf-barfill" id="lf-battfill" style="width:0%"></div></div>
              <div class="lf-battnums"><span>charge <b id="lf-battpct">—</b></span><span id="lf-battnote">—</span></div>
            </div>
          </div>
        </div>
      </div>

      <div class="lf-grid">
        <div class="lf-card">
          <h3>Readouts</h3>
          <div class="lf-readouts">
            <div class="lf-stat"><div class="lf-lbl">Altitude</div><div class="lf-val"><span id="lf-alt">—</span><span class="lf-unit">m AGL</span></div></div>
            <div class="lf-stat"><div class="lf-lbl">Ground speed</div><div class="lf-val"><span id="lf-spd">—</span><span class="lf-unit">m/s</span></div></div>
            <div class="lf-stat"><div class="lf-lbl">Latitude</div><div class="lf-val" style="font-size:1rem"><span id="lf-lat">—</span></div></div>
            <div class="lf-stat"><div class="lf-lbl">Longitude</div><div class="lf-val" style="font-size:1rem"><span id="lf-lon">—</span></div></div>
          </div>
        </div>

        <div class="lf-rcol">
          <div class="lf-card">
            <h3>GPS fix</h3>
            <div class="lf-link">
              <span class="lf-pill is-off" id="lf-fixpill" style="font-size:.72rem"><span class="lf-dot" aria-hidden="true"></span><span id="lf-fixtext">NO FIX</span></span>
            </div>
            <div class="lf-meta-line"><span>satellites</span><b id="lf-sats">0</b></div>
          </div>

          <div class="lf-card">
            <h3>Link / RSSI</h3>
            <div class="lf-link">
              <div class="lf-bars" id="lf-bars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
              <span id="lf-rssitext" class="lf-sub">no link</span>
            </div>
            <div class="lf-meta-line"><span>last frame</span><b id="lf-age">—</b></div>
          </div>
        </div>
      </div>
    </div>`;

    el.pill = host.querySelector('#lf-pill');
    el.pillText = host.querySelector('#lf-pill-text');
    el.kind = host.querySelector('#lf-kind');
    el.map = host.querySelector('#lf-map');
    el.mapmeta = host.querySelector('#lf-mapmeta');
    el.mapscale = host.querySelector('#lf-mapscale');
    el.att = host.querySelector('#lf-att');
    el.roll = host.querySelector('#lf-roll');
    el.pitch = host.querySelector('#lf-pitch');
    el.yaw = host.querySelector('#lf-yaw');
    el.battfill = host.querySelector('#lf-battfill');
    el.battpct = host.querySelector('#lf-battpct');
    el.battnote = host.querySelector('#lf-battnote');
    el.alt = host.querySelector('#lf-alt');
    el.spd = host.querySelector('#lf-spd');
    el.lat = host.querySelector('#lf-lat');
    el.lon = host.querySelector('#lf-lon');
    el.fixpill = host.querySelector('#lf-fixpill');
    el.fixtext = host.querySelector('#lf-fixtext');
    el.sats = host.querySelector('#lf-sats');
    el.bars = host.querySelector('#lf-bars');
    el.rssitext = host.querySelector('#lf-rssitext');
    el.age = host.querySelector('#lf-age');
  }

  // ==========================================================================
  // CANVAS HELPERS
  // ==========================================================================
  function fitCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    state.dpr = dpr;
    var rect = canvas.getBoundingClientRect();
    var w = Math.max(1, Math.round(rect.width));
    var h = Math.max(1, Math.round(rect.height));
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr; canvas.height = h * dpr;
    }
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }
  function cssVar(name, fallback) {
    try {
      var v = getComputedStyle(document.getElementById('tab-livefeed') || document.body).getPropertyValue(name);
      return (v && v.trim()) || fallback;
    } catch (_) { return fallback; }
  }

  // Tactical grid map: self-hosted vector canvas, NO tiles. We project the
  // recent trail into a local ENU frame centred on the latest position, scaling
  // so the trail spread fills ~70% of the view (min span guard for stillness).
  function drawMap() {
    if (!el.map) return;
    var f = fitCanvas(el.map);
    var ctx = f.ctx, W = f.w, H = f.h;
    var cx = W / 2, cy = H / 2;
    var grid = cssVar('--lf-grid', 'rgba(120,180,255,.16)');
    var coral = cssVar('--lf-coral', '#E07A5F');
    var muted = cssVar('--lf-muted', '#9FB0D0');

    ctx.clearRect(0, 0, W, H);
    // backdrop wash
    var g = ctx.createRadialGradient(cx, cy, 10, cx, cy, Math.max(W, H) * 0.7);
    g.addColorStop(0, 'rgba(120,180,255,0.06)');
    g.addColorStop(1, 'rgba(6,18,46,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    // grid
    ctx.strokeStyle = grid; ctx.lineWidth = 1;
    var step = Math.max(28, Math.min(W, H) / 8);
    ctx.beginPath();
    for (var x = cx % step; x < W; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
    for (var y = cy % step; y < H; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
    ctx.stroke();
    // crosshair + range rings
    ctx.strokeStyle = 'rgba(159,176,208,0.30)';
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.moveTo(0, cy); ctx.lineTo(W, cy); ctx.stroke();
    ctx.strokeStyle = 'rgba(159,176,208,0.18)';
    var maxR = Math.min(W, H) / 2 - 6;
    for (var r = maxR / 3; r <= maxR + 1; r += maxR / 3) {
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    }

    var trail = state.trail;
    if (!trail.length || !state.haveFix) {
      ctx.fillStyle = muted; ctx.font = '12px system-ui,sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(state.last ? 'no GPS fix yet' : 'awaiting telemetry', cx, cy + maxR + 0 - 4 > H ? H - 8 : cy);
      ctx.textAlign = 'start';
      return;
    }

    // local ENU projection around latest point
    var c = trail[trail.length - 1];
    var latRad = c.lat * Math.PI / 180;
    var mPerLat = 111320;
    var mPerLon = 111320 * Math.cos(latRad);
    function toM(p) {
      return { e: (p.lon - c.lon) * mPerLon, n: (p.lat - c.lat) * mPerLat };
    }
    // determine span
    var maxSpan = 8; // metres min
    for (var i = 0; i < trail.length; i++) {
      var m = toM(trail[i]);
      maxSpan = Math.max(maxSpan, Math.abs(m.e), Math.abs(m.n));
    }
    var scale = (maxR * 0.82) / maxSpan; // px per metre
    function toPx(p) { var m = toM(p); return { x: cx + m.e * scale, y: cy - m.n * scale }; }
    if (el.mapscale) el.mapscale.textContent = '±' + Math.round(maxSpan) + ' m';

    // trail
    ctx.lineWidth = 2; ctx.lineJoin = 'round';
    for (var j = 1; j < trail.length; j++) {
      var a = toPx(trail[j - 1]), b = toPx(trail[j]);
      var alpha = 0.12 + 0.65 * (j / trail.length);
      ctx.strokeStyle = 'rgba(224,122,95,' + alpha.toFixed(3) + ')';
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    // marker (heading-aware chevron)
    var p = toPx(c);
    var hdg = (state.last && isFinite(state.last.hdg)) ? state.last.hdg : 0;
    var rad = hdg * Math.PI / 180;
    ctx.save();
    ctx.translate(p.x, p.y); ctx.rotate(rad);
    ctx.fillStyle = coral; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, -11); ctx.lineTo(7, 9); ctx.lineTo(0, 4); ctx.lineTo(-7, 9); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.restore();
    // glow
    ctx.beginPath(); ctx.arc(p.x, p.y, 16, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(224,122,95,0.4)'; ctx.lineWidth = 1; ctx.stroke();
  }

  // Attitude indicator: artificial horizon rolled+pitched, plus heading tick.
  function drawAttitude() {
    if (!el.att) return;
    var f = fitCanvas(el.att);
    var ctx = f.ctx, W = f.w, H = f.h;
    var cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 4;
    var t = state.last || {};
    // derive roll/pitch — most MAVLink sample buses give hdg; some give raw ATTITUDE.
    var roll = num(t.roll, num(t.raw && t.raw.roll, 0));   // deg
    var pitch = num(t.pitch, num(t.raw && t.raw.pitch, 0)); // deg
    var yaw = num(t.hdg, num(t.yaw, 0));                     // deg

    ctx.clearRect(0, 0, W, H);
    ctx.save();
    // clip to circle
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    ctx.translate(cx, cy);
    ctx.rotate(-roll * Math.PI / 180);
    var pitchPx = (pitch / 45) * R; // 45° maps to full radius
    ctx.translate(0, pitchPx);
    // sky
    ctx.fillStyle = 'rgba(80,140,220,0.55)';
    ctx.fillRect(-R * 2, -R * 3, R * 4, R * 3);
    // ground
    ctx.fillStyle = 'rgba(150,110,70,0.55)';
    ctx.fillRect(-R * 2, 0, R * 4, R * 3);
    // horizon line
    ctx.strokeStyle = '#EAF0FF'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(-R * 2, 0); ctx.lineTo(R * 2, 0); ctx.stroke();
    // pitch ladder
    ctx.strokeStyle = 'rgba(234,240,255,0.7)'; ctx.lineWidth = 1;
    ctx.fillStyle = 'rgba(234,240,255,0.8)'; ctx.font = '9px system-ui,sans-serif'; ctx.textAlign = 'center';
    for (var d = -30; d <= 30; d += 10) {
      if (d === 0) continue;
      var yy = -(d / 45) * R;
      var len = (d % 20 === 0) ? 22 : 12;
      ctx.beginPath(); ctx.moveTo(-len, yy); ctx.lineTo(len, yy); ctx.stroke();
      if (d % 20 === 0) ctx.fillText(Math.abs(d) + '', 0, yy - 2);
    }
    ctx.restore();

    // fixed aircraft reticle
    ctx.strokeStyle = cssVar('--lf-coral', '#E07A5F'); ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx - 26, cy); ctx.lineTo(cx - 8, cy);
    ctx.moveTo(cx + 8, cy); ctx.lineTo(cx + 26, cy);
    ctx.moveTo(cx, cy - 6); ctx.lineTo(cx, cy + 2);
    ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI * 2); ctx.fillStyle = cssVar('--lf-coral', '#E07A5F'); ctx.fill();

    // bezel + heading tick
    ctx.strokeStyle = 'rgba(159,176,208,0.5)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    // top heading marker
    ctx.fillStyle = cssVar('--lf-coral', '#E07A5F');
    ctx.beginPath(); ctx.moveTo(cx, cy - R); ctx.lineTo(cx - 5, cy - R + 9); ctx.lineTo(cx + 5, cy - R + 9); ctx.closePath(); ctx.fill();

    if (el.roll) el.roll.textContent = fmt(roll, 0) + '°';
    if (el.pitch) el.pitch.textContent = fmt(pitch, 0) + '°';
    if (el.yaw) el.yaw.textContent = fmt(((yaw % 360) + 360) % 360, 0) + '°';
  }

  // ==========================================================================
  // DOM UPDATES (cheap; called on each frame from RAF)
  // ==========================================================================
  function updatePills() {
    var st = sourceStatus();
    var connected = !!(st.connected || st.kind || state.last);
    var isLive = (st.live === true) || (st.mode === 'live');
    var kind = st.kind || (state.last && state.last.src) || '—';
    if (el.kind) el.kind.textContent = String(kind).toUpperCase();

    if (!connected && !state.last) {
      setPill(el.pill, el.pillText, 'is-off', 'NO SOURCE'); return;
    }
    if (isLive) setPill(el.pill, el.pillText, 'is-live', labelFor(true));
    else setPill(el.pill, el.pillText, 'is-sample', labelFor(false));
  }
  function setPill(pill, txt, cls, text) {
    if (!pill) return;
    pill.className = 'lf-pill ' + cls;
    if (txt) txt.textContent = text;
  }

  function updateReadouts() {
    var t = state.last;
    if (!t) return;
    setText(el.alt, isFinite(t.alt) ? fmt(t.alt, 1) : '—');
    setText(el.spd, isFinite(t.spd) ? fmt(t.spd, 1) : '—');
    setText(el.lat, isFinite(t.lat) ? t.lat.toFixed(6) : '—');
    setText(el.lon, isFinite(t.lon) ? t.lon.toFixed(6) : '—');

    // battery
    var batt = num(t.batt, NaN);
    if (isFinite(batt)) {
      batt = Math.max(0, Math.min(100, batt));
      if (el.battfill) {
        el.battfill.style.width = batt + '%';
        el.battfill.style.background = batt > 50 ? cssVar('--lf-good', '#5AD19A')
          : batt > 20 ? cssVar('--lf-warn', '#F2C14E') : cssVar('--lf-bad', '#E0625F');
      }
      setText(el.battpct, fmt(batt, 0) + '%');
      setText(el.battnote, batt > 20 ? 'nominal' : 'LOW');
    } else { setText(el.battpct, '—'); setText(el.battnote, 'n/a'); }

    // GPS fix
    var fix = state.fixType;
    var fixOk = fix >= 2 && state.haveFix;
    if (el.fixpill) {
      el.fixpill.className = 'lf-pill ' + (fixOk ? 'is-live' : 'is-off');
      el.fixpill.style.fontSize = '.72rem';
    }
    setText(el.fixtext, fix >= 3 ? '3D FIX' : fix === 2 ? '2D FIX' : 'NO FIX');
    setText(el.sats, String(state.sats || 0));

    // RSSI / link bars
    var rssi = num(t.rssi, NaN);
    var qualBars = 0, qualText = 'no link';
    if (isFinite(rssi)) {
      // accept either 0-100 quality or dBm (-120..-30)
      var q = rssi > 0 ? Math.min(100, rssi) : Math.max(0, Math.min(100, (rssi + 110) / 80 * 100));
      qualBars = Math.round(q / 20);
      qualText = (rssi <= 0 ? Math.round(rssi) + ' dBm' : Math.round(rssi) + '%') + ' · ' +
        (q > 66 ? 'strong' : q > 33 ? 'fair' : 'weak');
    }
    if (el.bars) {
      var bs = el.bars.children;
      for (var i = 0; i < bs.length; i++) {
        bs[i].className = (i < qualBars) ? 'on' : '';
        bs[i].style.height = (8 + i * 3) + 'px';
        if (i < qualBars) bs[i].style.background = q > 33 ? cssVar('--lf-good', '#5AD19A') : cssVar('--lf-warn', '#F2C14E');
        else bs[i].style.background = '';
      }
    }
    setText(el.rssitext, qualText);

    // frame age
    var age = (Date.now() - (t.ts || Date.now())) / 1000;
    setText(el.age, age < 1 ? 'now' : fmt(age, 1) + 's ago');
    if (el.mapmeta) el.mapmeta.textContent = fixOk
      ? (t.lat.toFixed(5) + ', ' + t.lon.toFixed(5))
      : 'no GPS fix';
  }

  // ==========================================================================
  // TELEMETRY INGEST
  // ==========================================================================
  function onTelemetry(t) {
    if (!t || typeof t !== 'object') return;
    state.last = t;
    // GPS fix bookkeeping (raw may carry fix_type/satellites_visible from GPS_RAW)
    var raw = t.raw || {};
    state.fixType = num(raw.fix_type, num(t.fix_type, (isFinite(t.lat) && isFinite(t.lon) && (t.lat || t.lon)) ? 3 : 0));
    state.sats = num(raw.satellites_visible, num(t.sats, state.sats));
    state.haveFix = isFinite(t.lat) && isFinite(t.lon) && state.fixType >= 2;
    if (state.haveFix) {
      var prev = state.trail[state.trail.length - 1];
      // only push if moved enough or first point (avoid trail spam when static)
      if (!prev || Math.abs(prev.lat - t.lat) > 1e-7 || Math.abs(prev.lon - t.lon) > 1e-7) {
        state.trail.push({ lat: t.lat, lon: t.lon, ts: t.ts || Date.now() });
        if (state.trail.length > state.maxTrail) state.trail.shift();
      }
    }
  }
  function onLink(s) {
    if (!s) return;
    state.linkUp = !!(s.up || s.connected || s.heartbeat);
  }

  // ==========================================================================
  // RENDER LOOP — throttled to ~20fps (50ms). Pauses when tab hidden.
  // ==========================================================================
  function loop(ts) {
    state.raf = window.requestAnimationFrame(loop);
    var host = document.getElementById('tab-livefeed');
    if (!host) return;
    // pause work when this tab isn't visible (DEV 1 shell hides inactive tabs)
    var visible = host.offsetParent !== null || host.getClientRects().length > 0;
    if (!visible) return;
    if (ts - state.lastDrawTs < (prefersReduced ? 200 : 50)) return; // ~20fps (5fps reduced)
    state.lastDrawTs = ts;
    updatePills();
    updateReadouts();
    drawMap();
    drawAttitude();
  }

  // ==========================================================================
  // HELPERS
  // ==========================================================================
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function fmt(v, p) { return isFinite(v) ? Number(v).toFixed(p) : '—'; }
  function setText(node, v) { if (node && node.textContent !== v) node.textContent = v; }

  // ==========================================================================
  // MOUNT
  // ==========================================================================
  function mount() {
    var host = document.getElementById('tab-livefeed');
    if (!host || state.mounted) return false;
    injectStyles();
    buildMarkup(host);
    state.mounted = true;

    // subscribe to bus (defensive — retries if bus arrives later)
    var sub = on('telemetry', onTelemetry) && true;
    on('link', onLink);
    if (!sub) {
      // bus not ready — poll briefly until DEV 1/5 attach it, then subscribe
      var tries = 0;
      var iv = setInterval(function () {
        tries++;
        if (on('telemetry', onTelemetry)) { on('link', onLink); clearInterval(iv); }
        else if (tries > 40) { clearInterval(iv); maybeMock(); } // ~10s
      }, 250);
    }

    // start loop
    if (!state.raf) state.raf = window.requestAnimationFrame(loop);

    // resize redraw (canvas dpr)
    window.addEventListener('resize', function () { state.lastDrawTs = 0; });

    // DEV-ONLY local mock (NOT shipped logic): only fires if no real bus exists
    // AND an explicit ?lf_mock=1 flag is present, so production never sees it.
    maybeMock();
    return true;
  }

  // ---- DEV-ONLY MOCK --------------------------------------------------------
  // Synthesises a SAMPLE-labelled flight so this tab can be developed before
  // DEV 1's bus lands. Guarded by ?lf_mock=1 (or absence of any JACKIN bus during
  // local file:// dev). This is test scaffolding, NOT product behaviour.
  function maybeMock() {
    var hasRealBus = !!(window.JACKIN && (window.JACKIN.bus || window.JACKIN.on));
    var flag = /[?&]lf_mock=1/.test(location.search);
    if (hasRealBus && !flag) return;       // real bus present → never mock
    if (!flag && location.protocol !== 'file:') return; // only auto-mock in file:// dev
    if (state._mockOn) return; state._mockOn = true;

    var lat = 35.0, lon = -78.0, alt = 0, hdg = 0, t0 = Date.now();
    setInterval(function () {
      var dt = (Date.now() - t0) / 1000;
      hdg = (dt * 18) % 360;
      var rr = hdg * Math.PI / 180;
      lat += Math.cos(rr) * 0.00002;
      lon += Math.sin(rr) * 0.00002;
      alt = 40 + 15 * Math.sin(dt / 5);
      onTelemetry({
        lat: lat, lon: lon, alt: alt, hdg: hdg,
        spd: 8 + 2 * Math.sin(dt / 3),
        batt: Math.max(5, 100 - dt * 0.6),
        rssi: -55 - 10 * Math.abs(Math.sin(dt / 7)),
        src: 'sitl', ts: Date.now(),
        raw: { roll: 12 * Math.sin(dt / 2), pitch: 6 * Math.cos(dt / 2.3), fix_type: 3, satellites_visible: 14 }
      });
    }, 60);
  }

  // boot — DEV 1 may mount tabs lazily; observe until our mount point exists.
  function boot() {
    if (mount()) return;
    var mo = new MutationObserver(function () { if (mount()) mo.disconnect(); });
    mo.observe(document.documentElement, { childList: true, subtree: true });
    // also expose for explicit init by the shell if it prefers manual wiring
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  // public hook for DEV 1's router (optional): JACKIN_LIVEFEED.mount()
  window.JACKIN_LIVEFEED = { mount: mount, _state: state };
})();
