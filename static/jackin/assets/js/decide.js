/* ============================================================================
 * JACK IN — DECIDE tab  (Dev 3)
 * Owns: assets/js/decide.js
 * Mount: <section id="tab-decide">
 * The governed Cannonico decision loop. Wires REAL killinchu endpoints:
 *   GET /api/killinchu/v1/cuas/wta        -> {allocation:[{threat,interceptors,V}],
 *                                             expected_destroyed_value, unassigned_interceptors,
 *                                             effector:"SIMULATED", status:"SIMULATED"}
 *   GET /api/killinchu/v1/cuas/consensus  -> {lambda2, urgency_boost, connected_quorum,
 *                                             note, status:"EXPERIMENTAL"}
 * Subscribes: JACKIN.on('track', fn), JACKIN.on('track-selected', fn),
 *             JACKIN.on('classification', fn)  (to weight the recommendation)
 * Emits:      'decision' {trackId, recommendation, wta, consensus, score}
 * Posture: Λ = Conjecture 1 (NEVER a theorem) — displayed honestly.
 *          Decision is a GOVERNED RECOMMENDATION requiring human approval.
 *          The actual APPROVE happens in Dev 4's ENGAGE tab. effector SIMULATED.
 * Honest: LIVE when from a real fetch; EXPERIMENTAL/SIMULATED labels surfaced;
 *         "endpoint unreachable" on failure — NEVER fabricate a number.
 * 0 CDN. WCAG-AA. Responsive.
 * ==========================================================================*/
(function () {
  'use strict';

  // Shared jk-* component styles are injected by classify.js (id jk-dev3-styles).
  // Guard: if classify.js didn't run (e.g. decide loaded standalone), inject a
  // minimal fallback so DECIDE still renders legibly. Full styles live in classify.js.
  if (!document.getElementById('jk-dev3-styles')) {
    var s0 = document.createElement('style');
    s0.id = 'jk-dev3-styles';
    s0.textContent = '#tab-decide{color:var(--ink,#EAF0FB);font-family:var(--font,system-ui,sans-serif);}'
      + '.jk-card{background:var(--glass,rgba(18,38,78,.55));border:1px solid var(--glass-border,rgba(224,122,95,.22));border-radius:12px;padding:14px 16px;margin:0 0 14px;}'
      + '.jk-card-h{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px;}'
      + '.jk-pill{display:inline-flex;font-size:.7rem;font-weight:700;padding:3px 9px;border-radius:999px;background:rgba(120,170,255,.16);color:#CFE0FF;}'
      + '.jk-kv{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;}.jk-kv-row{display:contents;}'
      + '.jk-kv-k{color:var(--ink-mut,#A9B8D6);font-size:.78rem;}.jk-kv-v{font-family:var(--mono,monospace);text-align:right;}'
      + '.jk-note{color:var(--ink-mut,#A9B8D6);font-size:.76rem;}.jk-err{color:#F4A6AC;}'
      + '.jk-score-n{font-size:2rem;font-weight:800;color:var(--coral,#E07A5F);}'
      + '.jk-banner{padding:10px 12px;border-radius:8px;margin:0 0 14px;font-size:.78rem;}'
      + '.jk-table{width:100%;border-collapse:collapse;font-size:.8rem;}.jk-table th,.jk-table td{padding:6px 8px;text-align:left;border-bottom:1px solid rgba(190,210,255,.12);}';
    (document.head || document.documentElement).appendChild(s0);
  }

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
    J.emit = function (t, p) { if (J.bus) J.bus.dispatchEvent(new CustomEvent(t, { detail: p })); };
  }
  if (typeof J.label !== 'function') { J.label = function (l) { return l ? 'LIVE' : 'SAMPLE'; }; }
  var BASE = typeof J.KILLINCHU_BASE === 'string' ? J.KILLINCHU_BASE : '';

  var EP_WTA = '/api/killinchu/v1/cuas/wta';
  var EP_CONSENSUS = '/api/killinchu/v1/cuas/consensus';

  var state = {
    track: null,
    tracks: {},
    classifications: {},   // trackId -> last 'classification' payload
    wta: null, wtaState: 'idle', wtaErr: null,
    consensus: null, consState: 'idle', consErr: null,
    lastDecisionSig: null
  };

  // ---- DOM helpers ----
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === 'on' && typeof attrs[k] === 'function') n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function fmt(n, d) { if (n == null || isNaN(n)) return '—'; return Number(n).toFixed(d == null ? 2 : d); }
  function esc(s) { return String(s == null ? '' : s); }
  function pill(text, kind) { return el('span', { class: 'jk-pill jk-pill--' + (kind || 'info'), text: text }); }

  function getJSON(path, qs) {
    var url = BASE + path + (qs ? '?' + qs : '');
    var ctrl = ('AbortController' in window) ? new AbortController() : null;
    var to = ctrl ? setTimeout(function () { ctrl.abort(); }, 12000) : null;
    return fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' },
      signal: ctrl ? ctrl.signal : undefined, credentials: 'same-origin' })
      .then(function (r) {
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
   * SCORING — governed recommendation.
   * Combines: classification (threat weight), WTA value, consensus λ2 / urgency.
   * Honest: score is advisory; Λ is a Conjecture, not a theorem.
   * ========================================================================*/
  function computeScore(cls, wta, consensus) {
    // classification weight
    var w = 0.34;
    if (cls) {
      if (cls.class === 'threat') w = 0.6 + 0.3 * (cls.conf || 0);
      else if (cls.class === 'friend') w = 0.1 + 0.1 * (cls.conf || 0);
      else w = 0.34 + 0.15 * (cls.conf || 0); // unknown
      if (cls.spoof === true) w = Math.min(1, w + 0.1); // spoof raises suspicion
    }
    // WTA contribution: normalized expected destroyed value
    var wtaTerm = 0;
    if (wta && wta.expected_destroyed_value != null) {
      var edv = Number(wta.expected_destroyed_value) || 0;
      wtaTerm = Math.max(0, Math.min(1, edv / 10)); // bounded normalization
    }
    // consensus contribution: connected quorum gives confidence to act; urgency boosts.
    var consTerm = 0, urgency = 1;
    if (consensus) {
      consTerm = consensus.connected_quorum ? 0.2 : 0.0;
      urgency = Number(consensus.urgency_boost) || 1;
    }
    var raw = (0.55 * w + 0.30 * wtaTerm + 0.15 * consTerm) * urgency;
    var score = Math.max(0, Math.min(1, raw));
    return { score: score, weight: w, wtaTerm: wtaTerm, consTerm: consTerm, urgency: urgency };
  }

  function recommendFor(cls, scoreObj, wta, consensus) {
    var s = scoreObj.score;
    // governed bands — recommendation requires human approval regardless.
    if (!cls) return { action: 'MONITOR', band: 'low',
      rationale: 'No classification yet — hold and continue track custody.' };
    if (cls.class === 'friend') return { action: 'MONITOR', band: 'low',
      rationale: 'Classified FRIEND — no engagement; maintain situational awareness.' };
    var quorum = consensus && consensus.connected_quorum;
    if (s >= 0.66 && cls.class === 'threat') {
      return { action: quorum ? 'RECOMMEND ENGAGE (SIMULATED)' : 'RECOMMEND ENGAGE — QUORUM PENDING',
        band: 'high',
        rationale: 'High governed score; WTA allocates an interceptor. ' +
          (quorum ? 'Consensus quorum connected. ' : 'WARNING: consensus quorum NOT connected. ') +
          'Human approval REQUIRED in ENGAGE (effector SIMULATED).' };
    }
    if (s >= 0.45) return { action: 'TRACK & PREPARE', band: 'med',
      rationale: 'Elevated score — stage allocation, continue assessment, await stronger signal or quorum.' };
    return { action: 'MONITOR', band: 'low',
      rationale: 'Low governed score — maintain custody; no action recommended.' };
  }

  /* ==========================================================================
   * RENDER
   * ========================================================================*/
  var root, ui = {};

  function ensureMount() {
    if (root && document.body.contains(root)) return root;
    root = document.getElementById('tab-decide');
    return root || null;
  }

  function render() {
    if (!ensureMount()) return;
    clear(root);

    root.appendChild(el('div', { class: 'jk-c-head' }, [
      el('h2', { class: 'jk-c-title', text: 'DECIDE' }),
      el('p', { class: 'jk-c-sub', text: 'Governed Cannonico loop · WTA allocation · consensus / \u03BB\u2082 · recommended action (human-approved)' })
    ]));

    // Λ posture banner — honest, always shown.
    root.appendChild(el('div', { class: 'jk-banner jk-banner--lambda', role: 'note' }, [
      el('strong', { text: '\u039B = Conjecture 1' }),
      el('span', { text: '  \u00B7  \u039B is a conjecture, not a theorem. Decisioning is real; engagement is SIMULATED; a human approves.' })
    ]));

    if (!state.track) {
      root.appendChild(el('div', { class: 'jk-empty', role: 'status' }, [
        el('p', { text: 'No track selected. Select a track in FUSION / TRACKS, then classify it, to run the decision loop.' })
      ]));
      return;
    }

    var t = state.track;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var cls = state.classifications[idTxt] || null;

    // Classification summary (drives the score)
    root.appendChild(el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'TRACK ' + idTxt }),
        cls ? pill(cls.class.toUpperCase() + ' ' + Math.round((cls.conf || 0) * 100) + '%',
          cls.class === 'threat' ? 'err' : cls.class === 'friend' ? 'ok' : 'info')
          : pill('UNCLASSIFIED', 'muted')
      ]),
      cls ? el('p', { class: 'jk-note', text: 'Classification from CLASSIFY tab' +
        (cls.spoof === true ? ' · GNSS spoof SUSPECTED' : cls.spoof === false ? ' · GNSS plausible' : '') })
        : el('p', { class: 'jk-note', text: 'No classification received yet — classify the track first for a governed score.' })
    ]));

    // WTA card
    ui.wtaCard = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'WEAPON\u2013TARGET ALLOCATION (WTA)' }),
        ui.wtaPill = pill('LOADING\u2026', 'muted')
      ]),
      ui.wtaBody = el('div', { class: 'jk-card-b', 'aria-live': 'polite' }, [
        el('p', { class: 'jk-note', text: 'Fetching allocation\u2026' })
      ])
    ]);
    root.appendChild(ui.wtaCard);

    // Consensus card
    ui.consCard = el('div', { class: 'jk-card' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'CONSENSUS / QUORUM (\u03BB\u2082)' }),
        ui.consPill = pill('LOADING\u2026', 'muted')
      ]),
      ui.consBody = el('div', { class: 'jk-card-b', 'aria-live': 'polite' }, [
        el('p', { class: 'jk-note', text: 'Fetching consensus\u2026' })
      ])
    ]);
    root.appendChild(ui.consCard);

    // Recommendation card (the governed decision)
    ui.recCard = el('div', { class: 'jk-card jk-card--rec' }, [
      el('div', { class: 'jk-card-h' }, [
        el('span', { class: 'jk-card-t', text: 'GOVERNED RECOMMENDATION' }),
        ui.recPill = pill('PENDING\u2026', 'muted')
      ]),
      ui.recBody = el('div', { class: 'jk-card-b', 'aria-live': 'polite' }, [
        el('p', { class: 'jk-note', text: 'Awaiting WTA + consensus\u2026' })
      ]),
      el('div', { class: 'jk-banner jk-banner--gate', role: 'note' }, [
        el('strong', { text: 'HUMAN APPROVAL REQUIRED' }),
        el('span', { text: '  This is a recommendation only. Approval/engagement is performed by a human in the ENGAGE tab (effector SIMULATED).' })
      ])
    ]);
    root.appendChild(ui.recCard);

    // kick off live fetches
    runWTA();
    runConsensus();
  }

  function kv(k, v) {
    return el('div', { class: 'jk-kv-row' }, [
      el('span', { class: 'jk-kv-k', text: k }),
      el('span', { class: 'jk-kv-v', text: v })
    ]);
  }

  // ---- live: WTA ----
  function runWTA() {
    var captured = state.track;
    state.wtaState = 'loading';
    getJSON(EP_WTA).then(function (res) {
      if (state.track !== captured || !ui.wtaBody) return;
      clear(ui.wtaBody);
      if (!res.ok) {
        state.wtaState = 'error'; state.wtaErr = res.err; state.wta = null;
        ui.wtaPill.textContent = 'ENDPOINT UNREACHABLE';
        ui.wtaPill.className = 'jk-pill jk-pill--err';
        ui.wtaBody.appendChild(el('p', { class: 'jk-err', role: 'alert',
          text: 'WTA endpoint unreachable (' + res.err + '). No allocation shown — not fabricated.' }));
        maybeRecommend();
        return;
      }
      var d = res.data || {};
      state.wta = d; state.wtaState = 'ready';
      var status = d.status || 'SIMULATED';
      ui.wtaPill.textContent = J.label(true) + ' · ' + status;
      ui.wtaPill.className = 'jk-pill jk-pill--' + (status === 'SIMULATED' ? 'sim' : 'info');

      var alloc = Array.isArray(d.allocation) ? d.allocation : [];
      if (alloc.length) {
        var tbl = el('table', { class: 'jk-table', 'aria-label': 'WTA allocation' }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { scope: 'col', text: 'Threat' }),
            el('th', { scope: 'col', text: 'Interceptors' }),
            el('th', { scope: 'col', text: 'Value (V)' })
          ])]),
          el('tbody', {}, alloc.map(function (a) {
            return el('tr', {}, [
              el('td', { text: esc(a.threat) }),
              el('td', { text: String(a.interceptors != null ? a.interceptors : '—') }),
              el('td', { text: fmt(a.V, 2) })
            ]);
          }))
        ]);
        ui.wtaBody.appendChild(tbl);
      }
      ui.wtaBody.appendChild(el('div', { class: 'jk-kv' }, [
        kv('Expected destroyed value', fmt(d.expected_destroyed_value, 2)),
        kv('Unassigned interceptors', d.unassigned_interceptors != null ? String(d.unassigned_interceptors) : '—'),
        kv('Effector', esc(d.effector) || 'SIMULATED')
      ]));
      ui.wtaBody.appendChild(el('p', { class: 'jk-note',
        text: 'Allocation status ' + status + ' — effector SIMULATED, human-on-the-loop.' }));
      maybeRecommend();
    });
  }

  // ---- live: consensus ----
  function runConsensus() {
    var captured = state.track;
    state.consState = 'loading';
    getJSON(EP_CONSENSUS).then(function (res) {
      if (state.track !== captured || !ui.consBody) return;
      clear(ui.consBody);
      if (!res.ok) {
        state.consState = 'error'; state.consErr = res.err; state.consensus = null;
        ui.consPill.textContent = 'ENDPOINT UNREACHABLE';
        ui.consPill.className = 'jk-pill jk-pill--err';
        ui.consBody.appendChild(el('p', { class: 'jk-err', role: 'alert',
          text: 'Consensus endpoint unreachable (' + res.err + '). No quorum shown — not fabricated.' }));
        maybeRecommend();
        return;
      }
      var d = res.data || {};
      state.consensus = d; state.consState = 'ready';
      var status = d.status || 'EXPERIMENTAL';
      var quorum = !!d.connected_quorum;
      ui.consPill.textContent = J.label(true) + ' · ' + status;
      ui.consPill.className = 'jk-pill jk-pill--' + (quorum ? 'ok' : 'muted');
      ui.consBody.appendChild(el('div', { class: 'jk-kv' }, [
        kv('\u03BB\u2082 (algebraic connectivity)', fmt(d.lambda2, 2)),
        kv('Urgency boost', fmt(d.urgency_boost, 2)),
        kv('Connected quorum', quorum ? 'YES' : 'no')
      ]));
      if (d.note) ui.consBody.appendChild(el('p', { class: 'jk-note', text: esc(d.note) }));
      ui.consBody.appendChild(el('p', { class: 'jk-note',
        text: 'Status ' + status + ' — \u03BB\u2082 > 0 \u21D2 graph connected \u21D2 consensus reachable. Shown honestly.' }));
      maybeRecommend();
    });
  }

  // ---- compute + render recommendation once both fetches settle ----
  function maybeRecommend() {
    // proceed when both WTA and consensus have settled (ready or error)
    var wtaSettled = state.wtaState === 'ready' || state.wtaState === 'error';
    var consSettled = state.consState === 'ready' || state.consState === 'error';
    if (!wtaSettled || !consSettled) return;
    if (!ui.recBody) return;

    var t = state.track; if (!t) return;
    var idTxt = t.id || t.trackId || '(unidentified)';
    var cls = state.classifications[idTxt] || null;

    var scoreObj = computeScore(cls, state.wta, state.consensus);
    var rec = recommendFor(cls, scoreObj, state.wta, state.consensus);

    clear(ui.recBody);
    var bandKind = rec.band === 'high' ? 'err' : rec.band === 'med' ? 'warn' : 'ok';
    ui.recPill.textContent = rec.action;
    ui.recPill.className = 'jk-pill jk-pill--' + bandKind;

    ui.recBody.appendChild(el('div', { class: 'jk-score', 'aria-label': 'Governed score' }, [
      el('span', { class: 'jk-score-n', text: Math.round(scoreObj.score * 100) + '%' }),
      el('span', { class: 'jk-score-l', text: 'governed score (advisory)' })
    ]));
    ui.recBody.appendChild(el('div', { class: 'jk-kv' }, [
      kv('Action', rec.action),
      kv('Class weight', fmt(scoreObj.weight, 2)),
      kv('WTA term', fmt(scoreObj.wtaTerm, 2)),
      kv('Consensus term', fmt(scoreObj.consTerm, 2)),
      kv('Urgency \u00D7', fmt(scoreObj.urgency, 2))
    ]));
    ui.recBody.appendChild(el('p', { class: 'jk-rationale', text: rec.rationale }));

    // honesty footnote on degraded inputs
    var degraded = [];
    if (state.wtaState === 'error') degraded.push('WTA');
    if (state.consState === 'error') degraded.push('consensus');
    if (!cls) degraded.push('classification');
    if (degraded.length) {
      ui.recBody.appendChild(el('p', { class: 'jk-note jk-note--warn',
        text: 'Degraded inputs (' + degraded.join(', ') + ') — recommendation computed from available signals only; treat with caution.' }));
    }

    emitDecision(idTxt, rec, scoreObj);
  }

  // ---- emit 'decision' for Dev 4 (ENGAGE) ----
  function emitDecision(trackId, rec, scoreObj) {
    var payload = {
      trackId: trackId,
      recommendation: rec.action,
      band: rec.band,
      rationale: rec.rationale,
      wta: state.wta || null,        // null when unreachable (honest)
      consensus: state.consensus || null,
      score: scoreObj.score,
      scoreBreakdown: {
        classWeight: scoreObj.weight, wtaTerm: scoreObj.wtaTerm,
        consTerm: scoreObj.consTerm, urgency: scoreObj.urgency
      },
      lambda: { name: 'Lambda', status: 'Conjecture 1', note: '\u039B is a conjecture, not a theorem' },
      requiresApproval: true,
      effector: 'SIMULATED',
      ts: Date.now()
    };
    var sig = JSON.stringify([payload.trackId, payload.recommendation, payload.score,
      !!payload.wta, !!payload.consensus]);
    if (state.lastDecisionSig === sig) return;
    state.lastDecisionSig = sig;
    J.emit('decision', payload);
  }

  /* ==========================================================================
   * BUS SUBSCRIPTIONS
   * ========================================================================*/
  // J.on delivers the payload directly (contract: fn(payload, event)).
  J.on('track', function (p) {
    var t = Array.isArray(p) ? p[0] : p;
    if (!t || typeof t !== 'object') return;
    var id = t.id || t.trackId; if (id) state.tracks[id] = t;
    if (!state.track) { selectTrack(t); }
    else if ((state.track.id || state.track.trackId) === id) { state.track = t; }
  });

  // Dev 2 emits 'track-selected' as {id, track}. Tolerate id-only or bare track too.
  J.on('track-selected', function (p) {
    if (p && typeof p === 'object' && p.track) selectTrack(p.track);
    else if (p && typeof p === 'object' && (p.id || p.trackId)) selectTrack(p);
    else if (p != null && (typeof p === 'string' || typeof p === 'number'))
      selectTrack(state.tracks[p] || { id: String(p) });
    else if (p && p.id) selectTrack(state.tracks[p.id] || { id: String(p.id) });
  });

  J.on('classification', function (c) {
    if (!c) return;
    var cid = c.trackId || c.id; if (!cid) return;
    state.classifications[cid] = c;
    // if it's the active track, recompute the recommendation live
    var t = state.track;
    if (t && (t.id || t.trackId) === cid) {
      state.lastDecisionSig = null;
      maybeRecommend();
    }
  });

  function selectTrack(t) {
    state.track = t;
    state.wta = null; state.wtaState = 'idle'; state.wtaErr = null;
    state.consensus = null; state.consState = 'idle'; state.consErr = null;
    state.lastDecisionSig = null;
    render();
  }

  // ---- init ----
  function init() {
    if (ensureMount()) render();
    else {
      var tries = 0;
      var iv = setInterval(function () {
        tries++;
        if (ensureMount()) { clearInterval(iv); render(); }
        else if (tries > 40) clearInterval(iv);
      }, 250);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  J._decide = {
    computeScore: computeScore, recommendFor: recommendFor, state: state,
    setTrack: selectTrack
  };
})();
