/* ============================================================================
 * killinchu JACK-IN console — FUSION / TRACKS tab  (DEV 2 owns this file)
 * Renders into  <section id="tab-tracks">  (mount point owned by DEV 1).
 *
 * Lattice-style entity model: every source (serial drone, BLE beacon, ADS-B
 * aircraft, AIS vessel, SITL) becomes a TRACK object:
 *   { id, template:'TRACK', platform_type:(drone|airplane|vessel|unknown),
 *     pos:{lat,lon,alt}, classification, conf, src, ts, fused?, mergedFrom?[] }
 *
 * Consumes the shared bus per BUILD_CONTRACT:
 *   window.JACKIN.on('track', fn)      payload = a TRACK (or array of tracks)
 *   window.JACKIN.on('telemetry', fn)  the connected source's own feed -> a TRACK
 *   window.JACKIN.on('classification', fn)  optional: updates a track's class/conf
 *   window.JACKIN.source.status()      live vs sample
 * Emits:
 *   window.JACKIN.emit('track-selected', {id, track})   for DEV 3/4
 *
 * Multi-source = one truth: de-dupe/merge tracks that are clearly the same
 * entity (simple distance + time heuristic) and label them "fused".
 * Real data labeled LIVE, sample labeled SAMPLE. Never fabricate a sourceless
 * track. 0 CDN, WCAG-AA, responsive.
 * ==========================================================================*/
(function () {
  'use strict';

  // --- defensive bus access -------------------------------------------------
  function on(type, fn) {
    if (window.JACKIN && typeof window.JACKIN.on === 'function') { window.JACKIN.on(type, fn); return true; }
    var b = window.JACKIN && window.JACKIN.bus;
    if (b && typeof b.addEventListener === 'function') { b.addEventListener(type, function (e) { fn(e.detail); }); return true; }
    return false;
  }
  function emit(type, payload) {
    if (window.JACKIN && typeof window.JACKIN.emit === 'function') { try { window.JACKIN.emit(type, payload); return; } catch (_) {} }
    var b = window.JACKIN && window.JACKIN.bus;
    if (b && typeof b.dispatchEvent === 'function') { b.dispatchEvent(new CustomEvent(type, { detail: payload })); }
  }
  function sourceStatus() {
    try { if (window.JACKIN && window.JACKIN.source && window.JACKIN.source.status) return window.JACKIN.source.status() || {}; } catch (_) {}
    return {};
  }
  function labelFor(isLive) {
    if (window.JACKIN && typeof window.JACKIN.label === 'function') { try { return window.JACKIN.label(isLive); } catch (_) {} }
    return isLive ? 'LIVE' : 'SAMPLE';
  }
  // --- host resolver --------------------------------------------------------
  // The shell (DEV 1 / BUILD_CONTRACT) names this panel "fusion" (#tab-fusion,
  // labelled "FUSION / TRACKS"). This module was authored against #tab-tracks.
  // Prefer the real panel id, fall back to #tab-tracks for dev/standalone.
  // (Integration fix by DEV 5 — preserves DEV 2's intent; tab-tracks still works.)
  function trackHost() {
    return document.getElementById('tab-fusion') || document.getElementById('tab-tracks');
  }

  var prefersReduced = false;
  try { prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) {}

  // --- config / heuristics --------------------------------------------------
  var MERGE_DIST_M = 120;      // tracks within this distance...
  var MERGE_TIME_MS = 4000;    // ...and this recency, of compatible type -> fused
  var STALE_MS = 15000;        // a track older than this is "stale"
  var DROP_MS = 120000;        // ...older than this is removed entirely (2 min)

  // platform-type → glyph/colour (encoded, not decorative — distinguishes class)
  var PLATFORM = {
    drone:    { glyph: '✈', label: 'DRONE',   color: '#E07A5F' },
    airplane: { glyph: '✈', label: 'AIRCRAFT',color: '#5591C7' },
    vessel:   { glyph: '⬢', label: 'VESSEL',  color: '#5AD19A' },
    unknown:  { glyph: '◆', label: 'UNKNOWN', color: '#9FB0D0' }
  };
  // source-kind → short badge
  var SRC_BADGE = {
    serial: 'SERIAL', ble: 'BLE', usb: 'USB', ws: 'NET',
    adsb: 'ADS-B', ais: 'AIS', sitl: 'SITL', telemetry: 'LINK'
  };

  // --- store ----------------------------------------------------------------
  var tracks = Object.create(null);   // id -> track
  var selectedId = null;
  var el = {};
  var state = { mounted: false, raf: 0, lastDraw: 0, dirty: true };

  // ==========================================================================
  // TRACK NORMALISATION — accept the contract's loose shapes and canonicalise.
  // ==========================================================================
  function platformFromSrc(src) {
    if (src === 'adsb') return 'airplane';
    if (src === 'ais') return 'vessel';
    if (src === 'serial' || src === 'ble' || src === 'usb' || src === 'sitl') return 'drone';
    return 'unknown';
  }
  function normTrack(input, srcHint) {
    if (!input || typeof input !== 'object') return null;
    var src = input.src || srcHint || (input.pos && input.pos.src) || 'unknown';
    var pos = input.pos || { lat: input.lat, lon: input.lon, alt: input.alt };
    if (!pos || !isFinite(pos.lat) || !isFinite(pos.lon)) {
      // a track with no position can't be placed; only keep if it has an id (table-only)
      pos = pos || {};
    }
    var pt = input.platform_type || platformFromSrc(src);
    if (!PLATFORM[pt]) pt = 'unknown';
    var id = input.id || (src + ':' + (input.icao || input.mmsi || input.serial || 'self'));
    return {
      id: String(id),
      template: 'TRACK',
      platform_type: pt,
      pos: { lat: num(pos.lat, NaN), lon: num(pos.lon, NaN), alt: num(pos.alt, NaN) },
      classification: input.classification || 'unevaluated',
      conf: isFinite(input.conf) ? input.conf : (input.confidence != null ? num(input.confidence, null) : null),
      src: src,
      hdg: num(input.hdg, num(input.heading, NaN)),
      spd: num(input.spd, num(input.speed, NaN)),
      ts: input.ts || Date.now(),
      live: input.live === true || sourceStatus().live === true,
      callsign: input.callsign || input.name || null,
      fused: false,
      mergedFrom: null,
      _seen: Date.now()
    };
  }

  // Telemetry from the connected source is itself a TRACK ("self" entity).
  function trackFromTelemetry(t) {
    if (!t || !isFinite(t.lat) || !isFinite(t.lon)) return null;
    return normTrack({
      id: (t.src || 'link') + ':self',
      platform_type: platformFromSrc(t.src || 'serial'),
      pos: { lat: t.lat, lon: t.lon, alt: t.alt },
      hdg: t.hdg, spd: t.spd, src: t.src || 'telemetry',
      classification: 'self', conf: 1, ts: t.ts || Date.now(),
      live: sourceStatus().live === true
    });
  }

  function ingest(track) {
    if (!track) return;
    var prev = tracks[track.id];
    if (prev) {
      // update in place, preserve fusion lineage + selection
      track.fused = prev.fused; track.mergedFrom = prev.mergedFrom;
      if (track.classification === 'unevaluated' && prev.classification !== 'unevaluated') {
        track.classification = prev.classification; track.conf = prev.conf;
      }
    }
    tracks[track.id] = track;
    state.dirty = true;
  }

  // ==========================================================================
  // FUSION — distance + time heuristic. Same platform family + close in space
  // + recent in time → mark the newer as fused into a canonical track.
  // We do NOT delete sources; we flag the duplicate so the table shows "fused"
  // and the map draws one merged marker. One truth from multiple sources.
  // ==========================================================================
  function haversine(a, b) {
    if (!isFinite(a.lat) || !isFinite(b.lat)) return Infinity;
    var R = 6371000, dLat = (b.lat - a.lat) * Math.PI / 180, dLon = (b.lon - a.lon) * Math.PI / 180;
    var la1 = a.lat * Math.PI / 180, la2 = b.lat * Math.PI / 180;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function typeCompatible(a, b) {
    if (a === b) return true;
    // unknown can fuse with anything; otherwise must match family
    return a === 'unknown' || b === 'unknown';
  }
  function runFusion() {
    var list = Object.keys(tracks).map(function (k) { return tracks[k]; })
      .filter(function (t) { return isFinite(t.pos.lat) && isFinite(t.pos.lon); });
    // reset transient fusion flags
    list.forEach(function (t) { t.fused = false; t.mergedFrom = null; });
    var now = Date.now();
    for (var i = 0; i < list.length; i++) {
      for (var j = i + 1; j < list.length; j++) {
        var a = list[i], b = list[j];
        if (a.src === b.src) continue;                  // same sensor ≠ a fusion event
        if (!typeCompatible(a.platform_type, b.platform_type)) continue;
        if (Math.abs(a.ts - b.ts) > MERGE_TIME_MS) continue;
        if (haversine(a.pos, b.pos) > MERGE_DIST_M) continue;
        // canonical = higher confidence, else LIVE over SAMPLE, else earlier id
        var primary, secondary;
        var ca = a.conf == null ? -1 : a.conf, cb = b.conf == null ? -1 : b.conf;
        if (ca !== cb) { primary = ca > cb ? a : b; secondary = ca > cb ? b : a; }
        else if (a.live !== b.live) { primary = a.live ? a : b; secondary = a.live ? b : a; }
        else { primary = a; secondary = b; }
        secondary.fused = true;
        primary.fused = true;
        primary.mergedFrom = (primary.mergedFrom || []);
        if (primary.mergedFrom.indexOf(secondary.src) < 0) primary.mergedFrom.push(secondary.src);
        secondary.mergedInto = primary.id;
      }
    }
  }

  function pruneStale() {
    var now = Date.now();
    Object.keys(tracks).forEach(function (k) {
      if (now - tracks[k].ts > DROP_MS) { delete tracks[k]; state.dirty = true; }
    });
  }

  function visibleTracks() {
    // tracks merged INTO another are hidden from the map (shown as part of canonical)
    return Object.keys(tracks).map(function (k) { return tracks[k]; });
  }
  function canonicalTracks() {
    return visibleTracks().filter(function (t) { return !t.mergedInto; });
  }

  // ==========================================================================
  // STYLES
  // ==========================================================================
  function injectStyles() {
    if (document.getElementById('jk-tracks-style')) return;
    var css = `
    #tab-fusion,#tab-tracks{--tk-navy:var(--jk-navy,#06122E);--tk-coral:var(--jk-coral,#E07A5F);
      --tk-ink:var(--jk-ink,#EAF0FF);--tk-muted:var(--jk-muted,#9FB0D0);
      --tk-glass:var(--jk-glass,rgba(255,255,255,.05));--tk-stroke:var(--jk-stroke,rgba(159,176,208,.22));
      --tk-good:var(--jk-good,#5AD19A);--tk-warn:var(--jk-warn,#F2C14E);--tk-bad:var(--jk-bad,#E0625F);
      --tk-grid:var(--jk-grid,rgba(120,180,255,.16));--tk-radius:var(--jk-radius,16px);
      color:var(--tk-ink);font-family:var(--jk-font,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif);}
    #tab-fusion *,#tab-tracks *{box-sizing:border-box;}
    .tk-wrap{display:flex;flex-direction:column;gap:14px;padding:4px;}
    .tk-topbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
    .tk-title{font-weight:700;font-size:1.05rem;letter-spacing:.04em;margin:0;}
    .tk-sub{color:var(--tk-muted);font-size:.78rem;margin:0;}
    .tk-count{margin-left:auto;display:inline-flex;align-items:center;gap:8px;}
    .tk-countnum{font-size:1.5rem;font-weight:800;font-variant-numeric:tabular-nums;}
    .tk-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
      font-weight:800;font-size:.66rem;letter-spacing:.08em;border:1px solid var(--tk-stroke);}
    .tk-pill.is-live{background:rgba(90,209,154,.14);color:var(--tk-good);border-color:rgba(90,209,154,.5);}
    .tk-pill.is-sample{background:rgba(242,193,78,.14);color:var(--tk-warn);border-color:rgba(242,193,78,.5);}
    .tk-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:14px;align-items:stretch;}
    .tk-card{background:var(--tk-glass);border:1px solid var(--tk-stroke);border-radius:var(--tk-radius);
      backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);padding:0;position:relative;overflow:hidden;display:flex;flex-direction:column;}
    .tk-cardhead{display:flex;justify-content:space-between;align-items:center;padding:12px 14px 8px;}
    .tk-cardhead h3{margin:0;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--tk-muted);font-weight:700;}
    .tk-mapwrap{position:relative;flex:1;min-height:320px;}
    .tk-mapwrap canvas{display:block;width:100%;height:100%;}
    .tk-legend{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:4px;
      background:rgba(6,18,46,.55);border:1px solid var(--tk-stroke);border-radius:10px;padding:7px 9px;font-size:.66rem;color:var(--tk-muted);}
    .tk-legend span{display:flex;align-items:center;gap:6px;}
    .tk-legend i{width:9px;height:9px;border-radius:2px;display:inline-block;}
    .tk-tablewrap{max-height:430px;overflow:auto;}
    table.tk-table{width:100%;border-collapse:collapse;font-size:.78rem;}
    .tk-table th{position:sticky;top:0;background:var(--tk-navy);color:var(--tk-muted);text-align:left;
      font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--tk-stroke);z-index:1;}
    .tk-table td{padding:9px 10px;border-bottom:1px solid var(--tk-stroke);vertical-align:middle;}
    .tk-row{cursor:pointer;transition:background .12s;}
    .tk-row:hover{background:rgba(255,255,255,.04);}
    .tk-row:focus-visible{outline:2px solid var(--tk-coral);outline-offset:-2px;}
    .tk-row.sel{background:rgba(224,122,95,.16);box-shadow:inset 3px 0 0 var(--tk-coral);}
    .tk-glyph{font-size:1rem;margin-right:6px;}
    .tk-id{font-weight:700;font-variant-numeric:tabular-nums;}
    .tk-badge{display:inline-block;padding:2px 7px;border-radius:7px;font-size:.6rem;font-weight:800;letter-spacing:.06em;
      border:1px solid var(--tk-stroke);background:rgba(255,255,255,.04);color:var(--tk-ink);}
    .tk-fused{background:rgba(85,145,199,.18);border-color:rgba(85,145,199,.6);color:#9CC4EA;}
    .tk-srclist{display:flex;gap:4px;flex-wrap:wrap;}
    .tk-classtag{font-size:.64rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;}
    .tk-c-self{color:var(--tk-coral);} .tk-c-friend{color:var(--tk-good);}
    .tk-c-threat{color:var(--tk-bad);} .tk-c-unknown,.tk-c-unevaluated{color:var(--tk-muted);}
    .tk-age{font-variant-numeric:tabular-nums;color:var(--tk-muted);}
    .tk-age.stale{color:var(--tk-warn);}
    .tk-livecell{font-weight:800;font-size:.6rem;letter-spacing:.06em;}
    .tk-livecell.l{color:var(--tk-good);} .tk-livecell.s{color:var(--tk-warn);}
    .tk-empty{padding:30px 16px;text-align:center;color:var(--tk-muted);}
    .tk-empty b{color:var(--tk-ink);display:block;margin-bottom:4px;}
    .tk-detail{padding:12px 14px;border-top:1px solid var(--tk-stroke);font-size:.76rem;color:var(--tk-muted);}
    .tk-detail b{color:var(--tk-ink);}
    .tk-detail .tk-kv{display:flex;justify-content:space-between;padding:3px 0;}
    .tk-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);}
    @media (max-width:880px){.tk-grid{grid-template-columns:1fr;}.tk-mapwrap{min-height:260px;}}
    @media (prefers-reduced-motion: reduce){.tk-row{transition:none;}}
    `;
    var s = document.createElement('style'); s.id = 'jk-tracks-style'; s.textContent = css;
    document.head.appendChild(s);
  }

  // ==========================================================================
  // MARKUP
  // ==========================================================================
  function buildMarkup(host) {
    host.innerHTML = `
    <div class="tk-wrap" role="region" aria-label="Fusion and tracks">
      <div class="tk-topbar">
        <div>
          <p class="tk-title">FUSION / TRACKS</p>
          <p class="tk-sub">Lattice-style entity model — multiple sources, one truth</p>
        </div>
        <div class="tk-count">
          <span class="tk-sub">tracks</span>
          <span class="tk-countnum" id="tk-count" aria-live="polite">0</span>
          <span class="tk-pill is-sample" id="tk-mode"><span id="tk-mode-text">SAMPLE</span></span>
        </div>
      </div>

      <div class="tk-grid">
        <div class="tk-card">
          <div class="tk-cardhead"><h3>Fused situational picture</h3><span class="tk-sub" id="tk-mapscale">±0 m</span></div>
          <div class="tk-mapwrap">
            <canvas id="tk-map" aria-label="Fused map of all tracks"></canvas>
            <div class="tk-legend" aria-hidden="true">
              <span><i style="background:#E07A5F"></i>drone</span>
              <span><i style="background:#5591C7"></i>aircraft</span>
              <span><i style="background:#5AD19A"></i>vessel</span>
              <span><i style="background:#9FB0D0"></i>unknown</span>
            </div>
          </div>
        </div>

        <div class="tk-card">
          <div class="tk-cardhead"><h3>Live track table</h3><span class="tk-sub">select to inspect</span></div>
          <div class="tk-tablewrap">
            <table class="tk-table" role="grid" aria-label="Track list">
              <thead><tr>
                <th scope="col">Track</th><th scope="col">Type</th><th scope="col">Source</th>
                <th scope="col">Class</th><th scope="col">Seen</th><th scope="col">Feed</th>
              </tr></thead>
              <tbody id="tk-tbody"></tbody>
            </table>
          </div>
          <div class="tk-detail" id="tk-detail" hidden></div>
        </div>
      </div>
    </div>`;

    el.count = host.querySelector('#tk-count');
    el.mode = host.querySelector('#tk-mode');
    el.modeText = host.querySelector('#tk-mode-text');
    el.map = host.querySelector('#tk-map');
    el.mapscale = host.querySelector('#tk-mapscale');
    el.tbody = host.querySelector('#tk-tbody');
    el.detail = host.querySelector('#tk-detail');
  }

  // ==========================================================================
  // TABLE RENDER
  // ==========================================================================
  function ageStr(ts) {
    var s = (Date.now() - ts) / 1000;
    if (s < 1) return 'now';
    if (s < 60) return Math.round(s) + 's';
    return Math.round(s / 60) + 'm';
  }
  function classClass(c) {
    c = (c || 'unevaluated').toLowerCase();
    if (c === 'self') return 'tk-c-self';
    if (c === 'friend') return 'tk-c-friend';
    if (c === 'threat' || c === 'hostile') return 'tk-c-threat';
    return 'tk-c-unknown';
  }
  function renderTable() {
    if (!el.tbody) return;
    var list = canonicalTracks().sort(function (a, b) { return b.ts - a.ts; });
    if (el.count) el.count.textContent = String(list.length);

    // mode pill (any LIVE track → LIVE; else SAMPLE)
    var anyLive = list.some(function (t) { return t.live; }) || sourceStatus().live === true;
    if (el.mode) {
      el.mode.className = 'tk-pill ' + (anyLive ? 'is-live' : 'is-sample');
      el.modeText.textContent = anyLive ? labelFor(true) : labelFor(false);
    }

    if (!list.length) {
      el.tbody.innerHTML = '<tr><td colspan="6"><div class="tk-empty"><b>No tracks yet</b>'
        + 'Connect a source on the CONNECT tab — every source becomes a track here.</div></td></tr>';
      return;
    }

    var rows = list.map(function (t) {
      var p = PLATFORM[t.platform_type] || PLATFORM.unknown;
      var srcs = [t.src].concat(t.mergedFrom || []);
      var srcBadges = srcs.map(function (s) {
        return '<span class="tk-badge">' + (SRC_BADGE[s] || String(s).toUpperCase()) + '</span>';
      }).join(' ');
      var fusedBadge = t.fused ? ' <span class="tk-badge tk-fused" title="fused from ' + srcs.length + ' sources">FUSED</span>' : '';
      var stale = (Date.now() - t.ts) > STALE_MS;
      return '<tr class="tk-row' + (t.id === selectedId ? ' sel' : '') + '" tabindex="0" role="row" data-id="' + esc(t.id) + '" '
        + 'aria-selected="' + (t.id === selectedId) + '">'
        + '<td role="gridcell"><span class="tk-glyph" style="color:' + p.color + '" aria-hidden="true">' + p.glyph + '</span>'
        + '<span class="tk-id">' + esc(t.callsign || shortId(t.id)) + '</span></td>'
        + '<td role="gridcell">' + p.label + '</td>'
        + '<td role="gridcell"><span class="tk-srclist">' + srcBadges + fusedBadge + '</span></td>'
        + '<td role="gridcell"><span class="tk-classtag ' + classClass(t.classification) + '">' + esc(t.classification) + '</span></td>'
        + '<td role="gridcell"><span class="tk-age' + (stale ? ' stale' : '') + '">' + ageStr(t.ts) + '</span></td>'
        + '<td role="gridcell"><span class="tk-livecell ' + (t.live ? 'l' : 's') + '">' + (t.live ? labelFor(true) : labelFor(false)) + '</span></td>'
        + '</tr>';
    }).join('');
    el.tbody.innerHTML = rows;

    // wire row interaction
    Array.prototype.forEach.call(el.tbody.querySelectorAll('.tk-row'), function (row) {
      row.addEventListener('click', function () { selectTrack(row.getAttribute('data-id')); });
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectTrack(row.getAttribute('data-id')); }
      });
    });

    renderDetail();
  }

  function renderDetail() {
    if (!el.detail) return;
    var t = selectedId && tracks[selectedId];
    if (!t) { el.detail.hidden = true; el.detail.innerHTML = ''; return; }
    var p = PLATFORM[t.platform_type] || PLATFORM.unknown;
    var srcs = [t.src].concat(t.mergedFrom || []);
    el.detail.hidden = false;
    el.detail.innerHTML =
      '<div class="tk-kv"><span>selected</span><b>' + esc(t.callsign || t.id) + '</b></div>'
      + '<div class="tk-kv"><span>template</span><b>' + esc(t.template) + ' · ' + p.label + '</b></div>'
      + '<div class="tk-kv"><span>position</span><b>' + (isFinite(t.pos.lat) ? t.pos.lat.toFixed(5) + ', ' + t.pos.lon.toFixed(5) : 'no fix') + '</b></div>'
      + '<div class="tk-kv"><span>altitude</span><b>' + (isFinite(t.pos.alt) ? Math.round(t.pos.alt) + ' m' : '—') + '</b></div>'
      + '<div class="tk-kv"><span>classification</span><b class="' + classClass(t.classification) + '">' + esc(t.classification)
      + (t.conf != null ? ' (' + Math.round(t.conf * 100) + '%)' : '') + '</b></div>'
      + '<div class="tk-kv"><span>sources</span><b>' + srcs.map(function (s) { return SRC_BADGE[s] || s; }).join(' + ') + (t.fused ? ' · FUSED' : '') + '</b></div>'
      + '<div class="tk-kv"><span>feed</span><b>' + (t.live ? labelFor(true) : labelFor(false)) + '</b></div>';
  }

  function selectTrack(id) {
    if (!id || !tracks[id]) return;
    selectedId = id;
    state.dirty = true;
    renderTable();
    // emit for DEV 3 (classify) / DEV 4 (engage)
    emit('track-selected', { id: id, track: tracks[id] });
  }

  // ==========================================================================
  // FUSED MAP — same self-hosted canvas projection idea as LIVE FEED, but plots
  // ALL canonical tracks in a shared local ENU frame centred on their centroid.
  // ==========================================================================
  function fitCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    var w = Math.max(1, Math.round(rect.width)), h = Math.max(1, Math.round(rect.height));
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
    var ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }
  function cssVar(name, fb) {
    try { var v = getComputedStyle(trackHost() || document.body).getPropertyValue(name); return (v && v.trim()) || fb; } catch (_) { return fb; }
  }
  function drawMap() {
    if (!el.map) return;
    var f = fitCanvas(el.map), ctx = f.ctx, W = f.w, H = f.h, cx = W / 2, cy = H / 2;
    var grid = cssVar('--tk-grid', 'rgba(120,180,255,.16)');
    ctx.clearRect(0, 0, W, H);
    var g = ctx.createRadialGradient(cx, cy, 10, cx, cy, Math.max(W, H) * 0.7);
    g.addColorStop(0, 'rgba(120,180,255,0.06)'); g.addColorStop(1, 'rgba(6,18,46,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // grid
    ctx.strokeStyle = grid; ctx.lineWidth = 1;
    var step = Math.max(28, Math.min(W, H) / 8);
    ctx.beginPath();
    for (var x = cx % step; x < W; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
    for (var y = cy % step; y < H; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
    ctx.stroke();
    ctx.strokeStyle = 'rgba(159,176,208,0.18)';
    var maxR = Math.min(W, H) / 2 - 6;
    for (var r = maxR / 3; r <= maxR + 1; r += maxR / 3) { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke(); }

    var plotted = canonicalTracks().filter(function (t) { return isFinite(t.pos.lat) && isFinite(t.pos.lon); });
    if (!plotted.length) {
      ctx.fillStyle = cssVar('--tk-muted', '#9FB0D0'); ctx.font = '12px system-ui,sans-serif';
      ctx.textAlign = 'center'; ctx.fillText('no positioned tracks', cx, cy); ctx.textAlign = 'start';
      return;
    }
    // centroid
    var clat = 0, clon = 0;
    plotted.forEach(function (t) { clat += t.pos.lat; clon += t.pos.lon; });
    clat /= plotted.length; clon /= plotted.length;
    var latRad = clat * Math.PI / 180, mPerLat = 111320, mPerLon = 111320 * Math.cos(latRad);
    function toM(t) { return { e: (t.pos.lon - clon) * mPerLon, n: (t.pos.lat - clat) * mPerLat }; }
    var maxSpan = 30;
    plotted.forEach(function (t) { var m = toM(t); maxSpan = Math.max(maxSpan, Math.abs(m.e), Math.abs(m.n)); });
    var scale = (maxR * 0.82) / maxSpan;
    function toPx(t) { var m = toM(t); return { x: cx + m.e * scale, y: cy - m.n * scale }; }
    if (el.mapscale) el.mapscale.textContent = '±' + Math.round(maxSpan) + ' m';

    plotted.forEach(function (t) {
      var p = PLATFORM[t.platform_type] || PLATFORM.unknown;
      var pt = toPx(t);
      var isSel = t.id === selectedId;
      // fused ring
      if (t.fused) {
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 14, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(156,196,234,0.9)'; ctx.lineWidth = 2; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);
      }
      // selection halo
      if (isSel) {
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 19, 0, Math.PI * 2);
        ctx.strokeStyle = cssVar('--tk-coral', '#E07A5F'); ctx.lineWidth = 2; ctx.stroke();
      }
      // marker
      ctx.beginPath(); ctx.arc(pt.x, pt.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = p.color; ctx.fill();
      ctx.strokeStyle = t.live ? '#fff' : 'rgba(255,255,255,0.5)'; ctx.lineWidth = 1.5; ctx.stroke();
      // heading vector
      if (isFinite(t.hdg)) {
        var rr = t.hdg * Math.PI / 180;
        ctx.beginPath(); ctx.moveTo(pt.x, pt.y);
        ctx.lineTo(pt.x + Math.sin(rr) * 14, pt.y - Math.cos(rr) * 14);
        ctx.strokeStyle = p.color; ctx.lineWidth = 2; ctx.stroke();
      }
      // label
      ctx.fillStyle = cssVar('--tk-ink', '#EAF0FF'); ctx.font = '10px system-ui,sans-serif';
      ctx.fillText(shortId(t.callsign || t.id), pt.x + 9, pt.y - 8);
    });
  }

  // hit-testing for clicks on the fused map → select a track
  function mapClick(ev) {
    var plotted = canonicalTracks().filter(function (t) { return isFinite(t.pos.lat) && isFinite(t.pos.lon); });
    if (!plotted.length) return;
    var rect = el.map.getBoundingClientRect();
    var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    var W = rect.width, H = rect.height, cx = W / 2, cy = H / 2;
    var clat = 0, clon = 0; plotted.forEach(function (t) { clat += t.pos.lat; clon += t.pos.lon; });
    clat /= plotted.length; clon /= plotted.length;
    var latRad = clat * Math.PI / 180, mPerLat = 111320, mPerLon = 111320 * Math.cos(latRad);
    var maxR = Math.min(W, H) / 2 - 6, maxSpan = 30;
    plotted.forEach(function (t) { maxSpan = Math.max(maxSpan, Math.abs((t.pos.lon - clon) * mPerLon), Math.abs((t.pos.lat - clat) * mPerLat)); });
    var scale = (maxR * 0.82) / maxSpan;
    var best = null, bestD = 18;
    plotted.forEach(function (t) {
      var px = cx + (t.pos.lon - clon) * mPerLon * scale, py = cy - (t.pos.lat - clat) * mPerLat * scale;
      var d = Math.hypot(px - mx, py - my);
      if (d < bestD) { bestD = d; best = t; }
    });
    if (best) selectTrack(best.id);
  }

  // ==========================================================================
  // LOOP — light: fuse + prune + redraw at ~10fps (table only on change).
  // ==========================================================================
  function loop(ts) {
    state.raf = window.requestAnimationFrame(loop);
    var host = trackHost();
    if (!host) return;
    var visible = host.offsetParent !== null || host.getClientRects().length > 0;
    if (!visible) return;
    if (ts - state.lastDraw < (prefersReduced ? 250 : 100)) return; // ~10fps
    state.lastDraw = ts;
    pruneStale();
    runFusion();
    if (state.dirty) { renderTable(); state.dirty = false; }
    else { // light refresh of ages without full rebuild every second
      if (Math.floor(ts / 1000) !== state._lastAgeSec) { state._lastAgeSec = Math.floor(ts / 1000); renderTable(); }
    }
    drawMap();
  }

  // ==========================================================================
  // HELPERS
  // ==========================================================================
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function shortId(id) { var s = String(id); return s.length > 16 ? s.slice(0, 15) + '…' : s; }

  // ==========================================================================
  // MOUNT
  // ==========================================================================
  function mount() {
    var host = trackHost();
    if (!host || state.mounted) return false;
    injectStyles();
    buildMarkup(host);
    state.mounted = true;

    var ok = on('track', function (p) {
      if (Array.isArray(p)) p.forEach(function (x) { ingest(normTrack(x)); });
      else ingest(normTrack(p));
    });
    on('telemetry', function (t) { ingest(trackFromTelemetry(t)); });
    on('classification', function (c) {
      if (!c || !c.id || !tracks[c.id]) return;
      if (c.classification) tracks[c.id].classification = c.classification;
      if (c.conf != null) tracks[c.id].conf = c.conf;
      state.dirty = true;
    });

    if (!ok) {
      var tries = 0, iv = setInterval(function () {
        tries++;
        if (on('track', function (p) { if (Array.isArray(p)) p.forEach(function (x) { ingest(normTrack(x)); }); else ingest(normTrack(p)); })) {
          on('telemetry', function (t) { ingest(trackFromTelemetry(t)); });
          clearInterval(iv);
        } else if (tries > 40) { clearInterval(iv); maybeMock(); }
      }, 250);
    }

    if (el.map) el.map.addEventListener('click', mapClick);
    window.addEventListener('resize', function () { state.lastDraw = 0; });

    if (!state.raf) state.raf = window.requestAnimationFrame(loop);
    renderTable();
    maybeMock();
    return true;
  }

  // ---- DEV-ONLY MOCK --------------------------------------------------------
  // Synthesises SAMPLE tracks from 3 distinct sources (incl. two that overlap so
  // fusion is demonstrable) to develop this tab before DEV 1/5's bus lands.
  // Guarded by ?tk_mock=1 or file:// dev only. NOT shipped product logic.
  function maybeMock() {
    var hasRealBus = !!(window.JACKIN && (window.JACKIN.bus || window.JACKIN.on));
    var flag = /[?&]tk_mock=1/.test(location.search);
    if (hasRealBus && !flag) return;
    if (!flag && location.protocol !== 'file:') return;
    if (state._mockOn) return; state._mockOn = true;

    var base = { lat: 35.0, lon: -78.0 };
    var t0 = Date.now();
    setInterval(function () {
      var dt = (Date.now() - t0) / 1000;
      // our own drone (LINK self)
      ingest(trackFromTelemetry({ src: 'serial', lat: base.lat + 0.0006 * Math.sin(dt / 6), lon: base.lon + 0.0006 * Math.cos(dt / 6), alt: 60, hdg: (dt * 20) % 360, spd: 9, ts: Date.now() }));
      // an ADS-B aircraft far off
      ingest(normTrack({ id: 'adsb:AAL123', src: 'adsb', platform_type: 'airplane', callsign: 'AAL123', lat: base.lat + 0.004, lon: base.lon - 0.003, alt: 2400, hdg: 210, classification: 'friend', conf: 0.9, ts: Date.now() }));
      // an AIS vessel
      ingest(normTrack({ id: 'ais:367001230', src: 'ais', platform_type: 'vessel', callsign: 'M/V SAMPLE', lat: base.lat - 0.002, lon: base.lon + 0.001, hdg: 80, classification: 'unknown', conf: 0.4, ts: Date.now() }));
      // a BLE Remote-ID beacon that COINCIDES with our drone → should fuse
      ingest(normTrack({ id: 'ble:RID-77', src: 'ble', platform_type: 'drone', callsign: 'RID-77', lat: base.lat + 0.0006 * Math.sin(dt / 6) + 0.00001, lon: base.lon + 0.0006 * Math.cos(dt / 6), alt: 60, hdg: (dt * 20) % 360, classification: 'unevaluated', conf: 0.6, ts: Date.now() }));
    }, 500);
  }

  function boot() {
    if (mount()) return;
    var mo = new MutationObserver(function () { if (mount()) mo.disconnect(); });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.JACKIN_TRACKS = { mount: mount, _tracks: tracks, _runFusion: runFusion, _normTrack: normTrack };
})();
