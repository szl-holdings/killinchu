/* ============================================================================
 * JACK IN — CLASSIFY tab  (Dev 3)
 * Owns: assets/js/classify.js
 * Mount: <section id="tab-classify">
 * Wires REAL killinchu endpoints (same-origin on the Space):
 *   GET /api/killinchu/v1/cuas/plausibility   -> {demo:{chi_square,threshold,spoof_suspected,recommendation,status}}
 *   GET /api/killinchu/v1/drones/database     -> {count,total,drones:[{id,model,manufacturer,...}]}
 * Subscribes: JACKIN.on('track', fn), JACKIN.on('track-selected', fn)
 * Emits:      'classification' {trackId, class, conf, spoof, remoteId}
 * Honest labels: LIVE when from a real fetch; EXPERIMENTAL on plausibility;
 *                "endpoint unreachable" on failure — NEVER fabricate a number.
 * 0 CDN. WCAG-AA. Responsive. No edits to other devs' files.
 * ==========================================================================*/
(function () {
  'use strict';

  /* ---- scoped component styles (Dev 3 owns these; inherits Dev 1 vars) ----
   * Injected once, shared by CLASSIFY + DECIDE. Uses Dev 1's console.css
   * variables with safe fallbacks so the tabs render standalone in QA too.
   * All colors meet WCAG-AA on the navy surface.
   */
  (function injectStyles() {
    if (document.getElementById('jk-dev3-styles')) return;
    var css = [
      '#tab-classify,#tab-decide{color:var(--ink,#EAF0FB);font-family:var(--font,system-ui,sans-serif);}',
      '.jk-c-head{margin:0 0 14px;}',
      '.jk-c-title{font-size:1.15rem;letter-spacing:.08em;margin:0 0 4px;color:var(--ink,#EAF0FB);}',
      '.jk-c-sub{margin:0;color:var(--ink-mut,#A9B8D6);font-size:.85rem;line-height:1.4;}',
      '.jk-card{background:var(--glass,rgba(18,38,78,.55));border:1px solid var(--glass-border,rgba(224,122,95,.22));border-radius:var(--r-md,12px);padding:14px 16px;margin:0 0 14px;box-shadow:var(--shadow,0 10px 40px rgba(0,0,0,.45));}',
      '.jk-card--rec{border-color:var(--coral,#E07A5F);}',
      '.jk-card-h{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px;}',
      '.jk-card-t{font-weight:600;letter-spacing:.06em;font-size:.82rem;color:var(--ink,#EAF0FB);}',
      '.jk-card-b{margin-top:4px;}',
      '.jk-pill{display:inline-flex;align-items:center;font-size:.7rem;font-weight:700;letter-spacing:.05em;padding:3px 9px;border-radius:999px;border:1px solid transparent;white-space:nowrap;}',
      '.jk-pill--info{background:rgba(120,170,255,.16);color:#CFE0FF;border-color:rgba(120,170,255,.4);}',
      '.jk-pill--ok{background:rgba(84,214,160,.16);color:#8DEFC4;border-color:rgba(84,214,160,.45);}',
      '.jk-pill--err{background:rgba(224,108,117,.18);color:#F4A6AC;border-color:rgba(224,108,117,.5);}',
      '.jk-pill--warn{background:rgba(242,193,78,.16);color:#F6D384;border-color:rgba(242,193,78,.5);}',
      '.jk-pill--sim{background:rgba(242,193,78,.18);color:#F6D384;border-color:rgba(242,193,78,.55);}',
      '.jk-pill--muted{background:rgba(169,184,214,.14);color:var(--ink-mut,#A9B8D6);border-color:rgba(169,184,214,.3);}',
      '.jk-kv{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;}',
      '.jk-kv-row{display:contents;}',
      '.jk-kv-k{color:var(--ink-mut,#A9B8D6);font-size:.78rem;}',
      '.jk-kv-v{color:var(--ink,#EAF0FB);font-size:.82rem;font-family:var(--mono,monospace);text-align:right;word-break:break-word;}',
      '.jk-note{color:var(--ink-mut,#A9B8D6);font-size:.76rem;line-height:1.45;margin:8px 0 0;}',
      '.jk-note--warn{color:#F6D384;}',
      '.jk-err{color:#F4A6AC;font-size:.82rem;margin:0;}',
      '.jk-empty{background:var(--glass,rgba(18,38,78,.55));border:1px dashed var(--glass-border,rgba(224,122,95,.22));border-radius:var(--r-md,12px);padding:24px;text-align:center;color:var(--ink-mut,#A9B8D6);}',
      '.jk-tags{display:flex;gap:8px;flex-wrap:wrap;}',
      '.jk-tag{flex:1 1 90px;min-height:44px;cursor:pointer;font-weight:700;letter-spacing:.05em;font-size:.78rem;border-radius:var(--r-sm,8px);border:1.5px solid var(--hairline,rgba(190,210,255,.18));background:rgba(255,255,255,.03);color:var(--ink,#EAF0FB);transition:border-color .15s,background .15s;}',
      '.jk-tag:hover{border-color:var(--coral,#E07A5F);}',
      '.jk-tag:focus-visible{outline:3px solid var(--coral-200,#F2A48C);outline-offset:2px;}',
      '.jk-tag--friend.is-active{background:rgba(84,214,160,.22);border-color:#54D6A0;color:#BFF6DD;}',
      '.jk-tag--unknown.is-active{background:rgba(120,170,255,.2);border-color:#7EAAFF;color:#D6E4FF;}',
      '.jk-tag--threat.is-active{background:rgba(224,108,117,.24);border-color:#E06C75;color:#FBC2C6;}',
      '.jk-conf{margin:10px 0 0;font-size:.8rem;color:var(--ink,#EAF0FB);font-family:var(--mono,monospace);}',
      '.jk-table{width:100%;border-collapse:collapse;margin:0 0 8px;font-size:.8rem;}',
      '.jk-table th,.jk-table td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--hairline,rgba(190,210,255,.12));}',
      '.jk-table th{color:var(--ink-mut,#A9B8D6);font-weight:600;letter-spacing:.04em;}',
      '.jk-table td{color:var(--ink,#EAF0FB);font-family:var(--mono,monospace);}',
      '.jk-banner{display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:var(--r-sm,8px);margin:0 0 14px;font-size:.78rem;line-height:1.4;}',
      '.jk-banner--lambda{background:rgba(120,170,255,.1);border:1px solid rgba(120,170,255,.3);color:#CFE0FF;}',
      '.jk-banner--gate{background:rgba(242,193,78,.12);border:1px solid rgba(242,193,78,.45);color:#F6D384;margin:12px 0 0;}',
      '.jk-banner strong{letter-spacing:.05em;}',
      '.jk-score{display:flex;align-items:baseline;gap:10px;margin:0 0 10px;}',
      '.jk-score-n{font-size:2rem;font-weight:800;color:var(--coral,#E07A5F);font-family:var(--mono,monospace);line-height:1;}',
      '.jk-score-l{font-size:.76rem;color:var(--ink-mut,#A9B8D6);}',
      '.jk-rationale{margin:10px 0 0;color:var(--ink,#EAF0FB);font-size:.84rem;line-height:1.5;}',
      '@media (max-width:480px){.jk-kv{grid-template-columns:1fr;gap:2px 0;}.jk-kv-v{text-align:left;}.jk-tags{flex-direction:column;}}'
    ].join('');
    var s = document.createElement('style');
    s.id = 'jk-dev3-styles';
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  })();

  // ---- contract handles (defensive: tolerate load order / standalone QA) ----
  var J = (window.JACKIN = window.JACKIN || {});
  if (!J.bus) { try { J.bus = new EventTarget(); } catch (e) { J.bus = null; } }
  if (typeof J.on !== 'function') {
    // contract: J.on(type, fn) delivers fn(payload, event) and returns an off()
    J.on = function (t, fn) {
      if (!J.bus) return function () {};
      var w = function (e) { fn(e.detail, e); };
      J.bus.addEventListener(t, w);
      return function () { J.bus.removeEventListener(t, w); };
    };
  }
  if (typeof J.emit !== 'function') {
    J.emit = function (t, p) {
      if (J.bus) J.bus.dispatchEvent(new CustomEvent(t, { detail: p }));
    };
  }
  if (typeof J.label !== 'function') {
    J.label = function (isLive) { return isLive ? 'LIVE' : 'SAMPLE'; };
  }
  var BASE = typeof J.KILLINCHU_BASE === 'string' ? J.KILLINCHU_BASE : '';

  var EP_PLAUS = '/api/killinchu/v1/cuas/plausibility';
  var EP_DRONES = '/api/killinchu/v1/drones/database';

  // ---- state ----
  var state = {
    track: null,          // currently selected/active track
    tracks: {},           // id -> last seen track (for re-selection)
    droneDB: null,        // cached drone database (fetched once)
    droneDBState: 'idle', // idle|loading|ready|error
    classCache: {}        // trackId -> last emitted classification
  };

  // ---- tiny DOM helpers (no libs, no CDN) ----
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === 'on' && typeof attrs[k] === 'function')
        n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function fmt(n, d) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toFixed(d == null ? 2 : d);
  }
  function esc(s) { return String(s == null ? '' : s); }

  // ---- fetch with timeout, returns {ok,data,err} (never throws) ----
  function getJSON(path, qs) {
    var url = BASE + path + (qs ? '?' + qs : '');
    var ctrl = ('AbortController' in window) ? new AbortController() : null;
    var to = ctrl ? setTimeout(function () { ctrl.abort(); }, 12000) : null;
    return fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: ctrl ? ctrl.signal : undefined,
      credentials: 'same-origin'
    }).then(function (r) {
      if (to) clearTimeout(to);
      if (!r.ok) return { ok: false, err: 'HTTP ' + r.status, status: r.status };
      return r.json().then(function (d) { return { ok: true, data: d }; })
        .catch(function () { return { ok: false, err: 'bad JSON' }; });
    }).catch(function (e) {
      if (to) clearTimeout(to);
      return { ok: false, err: (e && e.name === 'AbortError') ? 'timeout' : 'unreachable' };
    });
  }

  /* ==========================================================================
   * Remote ID / OpenDroneID (ASTM F3411 / ASD-STAN) decode
   * Best-effort decode of telemetry.raw if Remote ID fields are present.
   * We do NOT fabricate — only surface what's actually in the payload.
   * ========================================================================*/
  var ODID_TYPES = { 0: 'None/Undeclared', 1: 'Aeroplane', 2: 'Helicopter/Multirotor',
    3: 'Gyroplane', 4: 'Hybrid Lift', 5: 'Ornithopter', 6: 'Glider', 7: 'Kite',
    8: 'Free Balloon', 9: 'Captive Balloon', 10: 'Airship', 11: 'Free Fall/Parachute',
    12: 'Rocket', 13: 'Tethered Powered Aircraft', 14: 'Ground Obstacle', 15: 'Other' };
  var ODID_IDTYPES = { 0: 'None', 1: 'Serial Number (ANSI/CTA-2063-A)',
    2: 'CAA Registration ID', 3: 'UTM (UUID)', 4: 'Specific Session ID' };

  function decodeRemoteId(raw) {
    if (!raw || typeof raw !== 'object') return null;
    // Common shapes: raw.remoteId / raw.opendroneid / raw.odid / flat fields.
    var r = raw.remoteId || raw.remote_id || raw.opendroneid || raw.openDroneID ||
            raw.odid || raw.ODID || null;
    // Also accept flat fields right on raw.
    var flat = null;
    if (!r) {
      if (raw.uas_id || raw.uasId || raw.basic_id || raw.basicId ||
          raw.operator_id || raw.operatorId || raw.serial || raw.SerialNumber) {
        flat = raw;
      }
    }
    var s = r || flat;
    if (!s) return null;

    var basic = s.basic_id || s.basicId || s.basic || {};
    var op = s.operator_id || s.operatorId || s.operator || {};
    var loc = s.location || s.loc || {};

    var uasId = basic.uas_id || basic.uasId || basic.id ||
                s.uas_id || s.uasId || s.serial || s.SerialNumber || null;
    var idType = basic.id_type != null ? basic.id_type :
                 (basic.idType != null ? basic.idType : (s.id_type != null ? s.id_type : null));
    var uaType = basic.ua_type != null ? basic.ua_type :
                 (basic.uaType != null ? basic.uaType : (s.ua_type != null ? s.ua_type : null));
    var operatorId = op.operator_id || op.operatorId || op.id ||
                     s.operator_id || s.operatorId || null;

    var out = {
      present: true,
      uasId: uasId || null,
      idType: idType != null ? idType : null,
      idTypeLabel: (idType != null && ODID_IDTYPES[idType]) ? ODID_IDTYPES[idType] : null,
      uaType: uaType != null ? uaType : null,
      uaTypeLabel: (uaType != null && ODID_TYPES[uaType]) ? ODID_TYPES[uaType] : null,
      operatorId: operatorId || null,
      operatorLat: loc.operator_lat != null ? loc.operator_lat :
                   (op.lat != null ? op.lat : (s.operator_lat != null ? s.operator_lat : null)),
      operatorLon: loc.operator_lon != null ? loc.operator_lon :
                   (op.lon != null ? op.lon : (s.operator_lon != null ? s.operator_lon : null)),
      selfId: s.self_id || s.selfId || s.description || null
    };
    // Only "present" if we actually pulled at least one real field.
    if (!out.uasId && out.uaType == null && !out.operatorId && !out.selfId) return null;
    return out;
  }

  /* ==========================================================================
   * Drone DB match — fuzzy match the track against /v1/drones/database.
   * Confidence is derived from token overlap of model/manufacturer; HONEST
   * (never claims a match it didn't compute). Returns {match, conf, candidates}.
   * ========================================================================*/
  function norm(s) { return String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
  function tokens(s) { return norm(s).split(' ').filter(Boolean); }

  function scoreCandidate(track, drone) {
    // Gather track-side hints.
    var raw = (track && track.raw) || {};
    var hints = [track && track.model, track && track.manufacturer, track && track.type,
      track && track.platform_type, raw.model, raw.manufacturer, raw.type,
      raw.callsign, raw.name].filter(Boolean).join(' ');
    var ht = tokens(hints);
    if (!ht.length) return 0;
    var dt = tokens((drone.model || '') + ' ' + (drone.manufacturer || '') +
      ' ' + (drone.id || '') + ' ' + (drone.role || ''));
    if (!dt.length) return 0;
    var set = {};
    dt.forEach(function (t) { set[t] = 1; });
    var hit = 0;
    ht.forEach(function (t) { if (set[t]) hit++; });
    // Jaccard-ish: overlap / track-token-count, clamp.
    var conf = hit / ht.length;
    return Math.max(0, Math.min(1, conf));
  }

  function matchDroneDB(track) {
    if (!state.droneDB || !state.droneDB.length) return null;
    var best = null, bestScore = 0, ranked = [];
    state.droneDB.forEach(function (d) {
      var sc = scoreCandidate(track, d);
      ranked.push({ drone: d, score: sc });
      if (sc > bestScore) { bestScore = sc; best = d; }
    });
    ranked.sort(function (a, b) { return b.score - a.score; });
    return { match: bestScore > 0 ? best : null, conf: bestScore, candidates: ranked.slice(0, 3) };
  }

  /* ==========================================================================
   * Classification logic — combine signals into class + confidence.
   * class: friend | unknown | threat   (operator can override via UI)
   * ========================================================================*/
  function autoClass(track, remoteId, dbMatch) {
    // Defaults honest: unknown unless we have a positive signal.
    var cls = 'unknown', conf = 0.25, basis = [];
    var raw = (track && track.raw) || {};

    // Track-provided classification (e.g. from FUSION) seeds us.
    if (track && track.classification && /friend|threat|unknown|hostile|neutral/i.test(track.classification)) {
      cls = /hostile|threat/i.test(track.classification) ? 'threat'
        : /friend|neutral/i.test(track.classification) ? 'friend' : 'unknown';
      conf = Math.max(conf, track.conf || 0.4);
      basis.push('track tag');
    }
    // DB match → identity confidence. side allied/friendly -> friend hint.
    if (dbMatch && dbMatch.match && dbMatch.conf > 0.3) {
      conf = Math.max(conf, dbMatch.conf);
      basis.push('DB match ' + (dbMatch.match.model || dbMatch.match.id));
      if (/allied|friend/i.test(dbMatch.match.side || '')) {
        if (cls === 'unknown') cls = 'friend';
      } else if (/hostile|adversary|enemy/i.test(dbMatch.match.side || '')) {
        cls = 'threat';
      }
    }
    // Remote ID present with registration/serial → cooperative -> friend hint.
    if (remoteId && (remoteId.uasId || remoteId.operatorId)) {
      basis.push('Remote ID present');
      if (cls === 'unknown') { cls = 'friend'; conf = Math.max(conf, 0.55); }
    }
    return { cls: cls, conf: conf, basis: basis };
  }

  /* ==========================================================================
   * RENDER
   * ========================================================================*/
  var root, ui = {};

  function pill(text, kind) {
    return el('span', { class: 'jk-pill jk-pill--' + (kind || 'info'), text: text });
  }

  function ensureMount() {
    if (root && document.body.contains(root)) return root;
    root = document.getElementById('tab-classify');
    if (!root) return null; // mount not present yet
    return root;
  }

  function render() {
    if (!ensureMount()) return;
    clear(root);

    var head = el('div', { class: 'jk-c-head' }, [
      el('h2', { class: 'jk-c-title', text: 'CLASSIFY' }),
      el('p', { class: 'jk-c-sub', text: 'Friend / Unknown / Threat tagging · Remote ID decode · GNSS-spoof plausibility · drone-DB match' })
    ]);
    root.appendChild(head);

    if (!state.track) {
      root.appendChild(el('div', { class: 'jk-empty', role: 'status' }, [
        el('p', { text: 'No track selected. Select a track in FUSION / TRACKS to classify it.' })
      ]));
      return;
    }

    var t = state.track;
    var idTxt = t.id || t.trackId || '(unidentified)';

    // --- Identity card ---
    var idCard = el('div', { class: 'jk-card', 'aria-label': 'Track identity' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'TRACK ' + idTxt }),
        pill((t.platform_type || t.type || 'unknown').toUpperCase(), 'info')
      ]),
      el('div', { class: 'jk-kv' }, [
        kv('Source', esc(t.src || (t.raw && t.raw.src) || '—')),
        kv('Position', t.pos ? (fmt(t.pos.lat, 4) + ', ' + fmt(t.pos.lon, 4))
          : (t.lat != null ? fmt(t.lat, 4) + ', ' + fmt(t.lon, 4) : '—')),
        kv('Template', esc(t.template || 'TRACK'))
      ])
    ]);
    root.appendChild(idCard);

    // --- Friend/Unknown/Threat tagging ---
    var current = (state.classCache[idTxt] && state.classCache[idTxt].class) ||
      (state._auto && state._auto.cls) || 'unknown';
    var tagWrap = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [el('span', { class: 'jk-card-t', text: 'CLASSIFICATION' })]),
      el('div', { class: 'jk-tags', role: 'radiogroup', 'aria-label': 'Threat classification' }, [
        tagBtn('friend', 'FRIEND', current),
        tagBtn('unknown', 'UNKNOWN', current),
        tagBtn('threat', 'THREAT', current)
      ]),
      ui.confLine = el('p', { class: 'jk-conf', 'aria-live': 'polite' })
    ]);
    root.appendChild(tagWrap);
    updateConfLine();

    // --- Remote ID decode ---
    var rid = decodeRemoteId(t.raw);
    var ridCard = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'REMOTE ID / OpenDroneID' }),
        rid ? pill('DECODED', 'ok') : pill('NONE IN TELEMETRY', 'muted')
      ])
    ]);
    if (rid) {
      ridCard.appendChild(el('div', { class: 'jk-kv' }, [
        kv('UAS ID', esc(rid.uasId) || '—'),
        kv('ID Type', rid.idTypeLabel || (rid.idType != null ? String(rid.idType) : '—')),
        kv('UA Type', rid.uaTypeLabel || (rid.uaType != null ? String(rid.uaType) : '—')),
        kv('Operator ID', esc(rid.operatorId) || '—'),
        kv('Operator Loc', (rid.operatorLat != null && rid.operatorLon != null)
          ? (fmt(rid.operatorLat, 4) + ', ' + fmt(rid.operatorLon, 4)) : '—'),
        kv('Self ID', esc(rid.selfId) || '—')
      ]));
    } else {
      ridCard.appendChild(el('p', { class: 'jk-note', text: 'No ASTM F3411 / OpenDroneID fields present in this track\u2019s telemetry.raw. Nothing decoded (not fabricated).' }));
    }
    root.appendChild(ridCard);

    // --- GNSS-spoof plausibility (LIVE / EXPERIMENTAL) ---
    ui.plausCard = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'GNSS-SPOOF PLAUSIBILITY' }),
        ui.plausPill = pill('LOADING\u2026', 'muted')
      ]),
      ui.plausBody = el('div', { class: 'jk-card-b', 'aria-live': 'polite' }, [
        el('p', { class: 'jk-note', text: 'Fetching chi-square plausibility\u2026' })
      ])
    ]);
    root.appendChild(ui.plausCard);

    // --- Drone DB match (LIVE / EXPERIMENTAL) ---
    ui.dbCard = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'DRONE DATABASE MATCH' }),
        ui.dbPill = pill('LOADING\u2026', 'muted')
      ]),
      ui.dbBody = el('div', { class: 'jk-card-b', 'aria-live': 'polite' }, [
        el('p', { class: 'jk-note', text: 'Matching against killinchu drone database\u2026' })
      ])
    ]);
    root.appendChild(ui.dbCard);

    // kick off live fetches for this track
    runPlausibility();
    runDroneMatch(rid);
  }

  function kv(k, v) {
    return el('div', { class: 'jk-kv-row' }, [
      el('span', { class: 'jk-kv-k', text: k }),
      el('span', { class: 'jk-kv-v', text: v })
    ]);
  }

  function tagBtn(value, labelTxt, current) {
    var sel = current === value;
    var b = el('button', {
      type: 'button',
      class: 'jk-tag jk-tag--' + value + (sel ? ' is-active' : ''),
      role: 'radio',
      'aria-checked': sel ? 'true' : 'false',
      text: labelTxt,
      onclick: function () { setClass(value, true); }
    });
    return b;
  }

  function setClass(value, operatorOverride) {
    var t = state.track; if (!t) return;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var prev = state.classCache[idTxt] || {};
    var conf = prev.conf;
    if (operatorOverride) conf = Math.max(conf || 0, 0.95); // operator decision = high confidence
    var entry = {
      trackId: idTxt,
      class: value,
      conf: conf != null ? conf : 0.25,
      spoof: prev.spoof != null ? prev.spoof : null,
      remoteId: prev.remoteId || decodeRemoteId(t.raw) || null,
      dbMatch: prev.dbMatch || null,
      operatorOverride: !!operatorOverride
    };
    state.classCache[idTxt] = entry;
    // re-render tag buttons active state + conf line
    refreshTagButtons(value);
    updateConfLine();
    emitClassification(entry);
  }

  function refreshTagButtons(value) {
    var btns = root.querySelectorAll('.jk-tag');
    Array.prototype.forEach.call(btns, function (b) {
      var on = b.className.indexOf('jk-tag--' + value) !== -1;
      if (on) { b.classList.add('is-active'); b.setAttribute('aria-checked', 'true'); }
      else { b.classList.remove('is-active'); b.setAttribute('aria-checked', 'false'); }
    });
  }

  function updateConfLine() {
    if (!ui.confLine) return;
    var t = state.track; if (!t) return;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var e = state.classCache[idTxt];
    if (!e) { ui.confLine.textContent = ''; return; }
    var bits = ['Class: ' + e.class.toUpperCase(),
      'confidence ' + Math.round((e.conf || 0) * 100) + '%'];
    if (e.operatorOverride) bits.push('(operator override)');
    if (e.spoof === true) bits.push('· GNSS spoof SUSPECTED');
    else if (e.spoof === false) bits.push('· GNSS plausible');
    ui.confLine.textContent = bits.join(' · ');
  }

  // ---- live: GNSS plausibility ----
  function runPlausibility() {
    var captured = state.track;
    getJSON(EP_PLAUS).then(function (res) {
      if (state.track !== captured || !ui.plausBody) return; // track changed
      clear(ui.plausBody);
      if (!res.ok) {
        ui.plausPill.textContent = 'ENDPOINT UNREACHABLE';
        ui.plausPill.className = 'jk-pill jk-pill--err';
        ui.plausBody.appendChild(el('p', { class: 'jk-err', role: 'alert',
          text: 'GNSS plausibility endpoint unreachable (' + res.err + '). No verdict — not fabricated.' }));
        recordSpoof(null);
        return;
      }
      // shape: {demo:{chi_square,threshold,spoof_suspected,recommendation,status}}
      var d = (res.data && res.data.demo) ? res.data.demo : res.data || {};
      var spoof = !!d.spoof_suspected;
      var status = d.status || 'EXPERIMENTAL';
      ui.plausPill.textContent = J.label(true) + ' · ' + status;
      ui.plausPill.className = 'jk-pill jk-pill--' + (spoof ? 'err' : 'ok');
      ui.plausBody.appendChild(el('div', { class: 'jk-kv' }, [
        kv('χ² statistic', fmt(d.chi_square, 2)),
        kv('Threshold', fmt(d.threshold, 2)),
        kv('Spoof suspected', spoof ? 'YES' : 'no'),
        kv('Recommendation', esc(d.recommendation) || '—')
      ]));
      ui.plausBody.appendChild(el('p', { class: 'jk-note',
        text: 'Chi-square GNSS consistency test. Status ' + status + ' — shown honestly; verdict is advisory.' }));
      recordSpoof(spoof);
    });
  }

  function recordSpoof(spoof) {
    var t = state.track; if (!t) return;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var e = state.classCache[idTxt] || { trackId: idTxt, class: 'unknown', conf: 0.25, remoteId: null };
    e.spoof = spoof;
    state.classCache[idTxt] = e;
    updateConfLine();
    emitClassification(e);
  }

  // ---- live: drone DB match ----
  function ensureDroneDB() {
    if (state.droneDBState === 'ready') return Promise.resolve(true);
    if (state.droneDBState === 'loading' && state._dbPromise) return state._dbPromise;
    state.droneDBState = 'loading';
    state._dbPromise = getJSON(EP_DRONES).then(function (res) {
      if (!res.ok) { state.droneDBState = 'error'; state._dbErr = res.err; return false; }
      var list = (res.data && (res.data.drones || res.data.list || res.data.items)) || [];
      state.droneDB = Array.isArray(list) ? list : [];
      state.droneDBState = 'ready';
      return true;
    });
    return state._dbPromise;
  }

  function runDroneMatch(remoteId) {
    var captured = state.track;
    ensureDroneDB().then(function (ok) {
      if (state.track !== captured || !ui.dbBody) return;
      clear(ui.dbBody);
      if (!ok) {
        ui.dbPill.textContent = 'ENDPOINT UNREACHABLE';
        ui.dbPill.className = 'jk-pill jk-pill--err';
        ui.dbBody.appendChild(el('p', { class: 'jk-err', role: 'alert',
          text: 'Drone database unreachable (' + (state._dbErr || 'error') + '). No match shown — not fabricated.' }));
        finalizeAuto(remoteId, null);
        return;
      }
      var m = matchDroneDB(captured);
      ui.dbPill.textContent = J.label(true) + ' · ' + (state.droneDB.length) + ' records';
      ui.dbPill.className = 'jk-pill jk-pill--info';
      if (!m || !m.match || m.conf <= 0) {
        ui.dbBody.appendChild(el('p', { class: 'jk-note',
          text: 'No confident match — track carries no model/manufacturer hint to match against the database. (Honest: nothing inferred.)' }));
        finalizeAuto(remoteId, m);
        return;
      }
      var d = m.match;
      ui.dbBody.appendChild(el('div', { class: 'jk-kv' }, [
        kv('Best match', esc(d.model) + (d.manufacturer ? ' · ' + esc(d.manufacturer) : '')),
        kv('Match confidence', Math.round(m.conf * 100) + '%'),
        kv('Side', esc(d.side) || '—'),
        kv('Role / Group', (esc(d.role) || '—') + (d.group ? ' · ' + esc(d.group) : '')),
        kv('Country', esc(d.country) || '—')
      ]));
      if (m.candidates && m.candidates.length > 1) {
        var alt = m.candidates.slice(1).filter(function (c) { return c.score > 0; })
          .map(function (c) { return (c.drone.model || c.drone.id) + ' (' + Math.round(c.score * 100) + '%)'; });
        if (alt.length) ui.dbBody.appendChild(el('p', { class: 'jk-note', text: 'Alternates: ' + alt.join(', ') }));
      }
      finalizeAuto(remoteId, m);
    });
  }

  // After signals resolve, compute auto-class (only if operator hasn't overridden).
  function finalizeAuto(remoteId, dbMatch) {
    var t = state.track; if (!t) return;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var existing = state.classCache[idTxt];
    var auto = autoClass(t, remoteId, dbMatch);
    state._auto = auto;
    if (existing && existing.operatorOverride) {
      // keep operator decision, but enrich metadata
      existing.remoteId = remoteId || existing.remoteId;
      existing.dbMatch = dbMatch ? summarizeMatch(dbMatch) : existing.dbMatch;
      state.classCache[idTxt] = existing;
      emitClassification(existing);
      return;
    }
    var entry = {
      trackId: idTxt,
      class: auto.cls,
      conf: auto.conf,
      spoof: existing ? existing.spoof : null,
      remoteId: remoteId || null,
      dbMatch: dbMatch ? summarizeMatch(dbMatch) : null,
      operatorOverride: false,
      basis: auto.basis
    };
    state.classCache[idTxt] = entry;
    refreshTagButtons(auto.cls);
    updateConfLine();
    emitClassification(entry);
  }

  function summarizeMatch(m) {
    if (!m || !m.match) return null;
    return { model: m.match.model, manufacturer: m.match.manufacturer,
      id: m.match.id, conf: m.conf, side: m.match.side };
  }

  // ---- emit on the bus for Dev 4 ----
  function emitClassification(entry) {
    var payload = {
      // task contract (Dev 4 consumes these):
      trackId: entry.trackId,
      class: entry.class,
      conf: entry.conf,
      spoof: entry.spoof,
      remoteId: entry.remoteId || null,
      dbMatch: entry.dbMatch || null,
      operatorOverride: !!entry.operatorOverride,
      // interop aliases so Dev 2 (tracks.js) updates the track view:
      id: entry.trackId,
      classification: entry.class,
      ts: Date.now()
    };
    // de-dupe identical emits to avoid bus spam
    var sig = JSON.stringify([payload.trackId, payload.class, payload.conf, payload.spoof]);
    if (state._lastSig === sig) return;
    state._lastSig = sig;
    J.emit('classification', payload);
  }

  /* ==========================================================================
   * BUS SUBSCRIPTIONS
   * ========================================================================*/
  // J.on delivers the payload directly (contract: fn(payload, event)).
  J.on('track', function (p) {
    // payload may be a single track or an array of tracks
    var t = Array.isArray(p) ? p[0] : p;
    if (!t || typeof t !== 'object') return;
    var id = t.id || t.trackId;
    if (id) state.tracks[id] = t;
    // if nothing selected yet, adopt the first/active track
    if (!state.track) { state.track = t; state._lastSig = null; state._auto = null; render(); }
    else if ((state.track.id || state.track.trackId) === id) {
      state.track = t; // refresh current track data (no full re-render to avoid fetch storm)
    }
  });

  // Dev 2 emits 'track-selected' as {id, track}. Also tolerate id-only or a bare track.
  J.on('track-selected', function (p) {
    var t = null;
    if (p && typeof p === 'object' && p.track) t = p.track;
    else if (p && typeof p === 'object' && (p.id || p.trackId)) t = p;
    else if (p != null && (typeof p === 'string' || typeof p === 'number'))
      t = state.tracks[p] || { id: String(p) };
    if (p && p.id && (!t || !(t.id || t.trackId))) t = state.tracks[p.id] || { id: String(p.id) };
    if (!t) return;
    state.track = t;
    state._lastSig = null;
    state._auto = null;
    render();
  });

  // initial paint (will show empty-state until a track arrives)
  function init() {
    if (ensureMount()) render();
    else {
      // mount may be created after tab router runs; observe once.
      var tries = 0;
      var iv = setInterval(function () {
        tries++;
        if (ensureMount()) { clearInterval(iv); render(); }
        else if (tries > 40) clearInterval(iv); // ~10s give up quietly
      }, 250);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }

  // expose a tiny hook for Dev 5 QA / debugging (read-only-ish)
  J._classify = {
    decodeRemoteId: decodeRemoteId,
    matchDroneDB: matchDroneDB,
    state: state,
    setTrack: function (t) { state.track = t; state._lastSig = null; state._auto = null; render(); }
  };
})();
