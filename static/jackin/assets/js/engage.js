/* JACK IN — ENGAGE (SIMULATED) tab  | Dev 4
 * Human-on-the-loop approval gate. The effector is SIMULATED. NEVER sends a real
 * command anywhere. NEVER claims takeover / jam / spoof. Decisioning is real;
 * the effect is simulated; a human approves every action.
 *
 * Contract (BUILD_CONTRACT.md):
 *   window.JACKIN.on('decision', fn)         -> consumes Dev 3's decisions
 *   window.JACKIN.emit('engagement', {...})  -> {trackId, action, approvedBy, ts, simulated:true}
 *   window.JACKIN.emit('receipt', {...})     -> Dev 4 receipts.js signs the khipu chain
 * Renders into Dev 1's <section id="tab-engage">. Uses console.css vars w/ fallbacks.
 * 0 CDN. WCAG-AA. Responsive.
 */
(function () {
  'use strict';

  // ---- minimal JACKIN shim (only if Dev1/Dev5 haven't loaded yet; never overwrite) ----
  if (!window.JACKIN) {
    var _bus = new EventTarget();
    window.JACKIN = {
      bus: _bus,
      KILLINCHU_BASE: '',
      emit: function (type, payload) {
        _bus.dispatchEvent(new CustomEvent(type, { detail: payload }));
      },
      on: function (type, fn) {
        _bus.addEventListener(type, function (e) { fn(e.detail, e); });
      },
      label: function (isLive) { return isLive ? 'LIVE' : 'SAMPLE'; }
    };
  }
  var JACKIN = window.JACKIN;

  // ---- DOM helpers ----
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === 'on' && typeof attrs[k] === 'function') n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function fmtTs(ts) { try { return new Date(ts).toISOString().replace('T', ' ').replace('Z', 'Z'); } catch (e) { return String(ts); } }
  function shortId() { return 'ENG-' + Math.random().toString(16).slice(2, 8).toUpperCase(); }

  // ---- styles (scoped to #tab-engage; uses Dev1 vars w/ honest fallbacks) ----
  var STYLE = '' +
    '#tab-engage{--navy:var(--jk-navy,#06122E);--coral:var(--jk-coral,#E07A5F);' +
    '--ink:var(--jk-ink,#EAF0FF);--mut:var(--jk-muted,#9FB0D0);--card:var(--jk-card,#0B1B40);' +
    '--line:var(--jk-line,#1E3566);--ok:var(--jk-ok,#3DD68C);--warn:var(--jk-warn,#FFC857);' +
    '--bad:var(--jk-bad,#FF6B6B);color:var(--ink);font:14px/1.5 var(--jk-font,system-ui,-apple-system,Segoe UI,Roboto,sans-serif);}' +
    '#tab-engage .eg-wrap{display:flex;flex-direction:column;gap:16px;max-width:980px;margin:0 auto;}' +
    '#tab-engage .eg-sim-banner{position:relative;border:2px solid var(--coral);border-radius:14px;' +
    'background:repeating-linear-gradient(135deg,rgba(224,122,95,.16) 0 18px,rgba(224,122,95,.05) 18px 36px);' +
    'padding:14px 18px;display:flex;align-items:center;gap:14px;}' +
    '#tab-engage .eg-sim-dot{flex:0 0 auto;width:14px;height:14px;border-radius:50%;background:var(--coral);' +
    'box-shadow:0 0 0 0 rgba(224,122,95,.7);animation:egPulse 1.6s infinite;}' +
    '@keyframes egPulse{0%{box-shadow:0 0 0 0 rgba(224,122,95,.55)}70%{box-shadow:0 0 0 12px rgba(224,122,95,0)}100%{box-shadow:0 0 0 0 rgba(224,122,95,0)}}' +
    '@media (prefers-reduced-motion:reduce){#tab-engage .eg-sim-dot{animation:none}}' +
    '#tab-engage .eg-sim-banner h2{margin:0;font-size:clamp(15px,2.6vw,20px);letter-spacing:.04em;font-weight:800;color:var(--ink);}' +
    '#tab-engage .eg-sim-banner .eg-sub{font-size:12px;color:var(--mut);margin-top:2px;}' +
    '#tab-engage .eg-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;}' +
    '#tab-engage .eg-card h3{margin:0 0 10px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);}' +
    '#tab-engage .eg-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;}' +
    '#tab-engage .eg-kv{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:10px;padding:10px 12px;}' +
    '#tab-engage .eg-kv .k{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);}' +
    '#tab-engage .eg-kv .v{font-size:16px;font-weight:700;margin-top:3px;word-break:break-word;}' +
    '#tab-engage .eg-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:4px;}' +
    '#tab-engage button.eg-btn{font:inherit;font-weight:700;border-radius:10px;padding:12px 20px;cursor:pointer;border:1px solid var(--line);min-width:140px;}' +
    '#tab-engage button.eg-approve{background:var(--coral);color:#1a0c06;border-color:var(--coral);}' +
    '#tab-engage button.eg-deny{background:transparent;color:var(--ink);border-color:var(--mut);}' +
    '#tab-engage button.eg-btn:disabled{opacity:.45;cursor:not-allowed;}' +
    '#tab-engage button.eg-btn:focus-visible{outline:3px solid var(--warn);outline-offset:2px;}' +
    '#tab-engage .eg-caption{font-size:12.5px;color:var(--mut);border-left:3px solid var(--coral);padding-left:10px;}' +
    '#tab-engage .eg-trust{font-variant-numeric:tabular-nums;}' +
    '#tab-engage .eg-trust b{color:var(--warn);}' +
    '#tab-engage .eg-sim-stage{margin-top:12px;border:1px dashed var(--coral);border-radius:12px;padding:14px;background:rgba(224,122,95,.06);}' +
    '#tab-engage .eg-sim-stage .eg-sim-tag{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.14em;color:#1a0c06;background:var(--coral);padding:2px 8px;border-radius:6px;}' +
    '#tab-engage .eg-bar{height:12px;border-radius:7px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:10px;border:1px solid var(--line);}' +
    '#tab-engage .eg-bar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--coral),var(--warn));transition:width .12s linear;}' +
    '#tab-engage .eg-cd{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;text-align:center;margin:6px 0;}' +
    '#tab-engage .eg-timeline{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px;}' +
    '#tab-engage .eg-timeline li{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line);border-radius:10px;padding:9px 12px;background:rgba(255,255,255,.02);}' +
    '#tab-engage .eg-timeline .badge{flex:0 0 auto;font-size:10px;font-weight:800;letter-spacing:.1em;padding:2px 7px;border-radius:6px;margin-top:2px;}' +
    '#tab-engage .eg-timeline .badge.ap{background:var(--ok);color:#04230f;}' +
    '#tab-engage .eg-timeline .badge.dn{background:var(--bad);color:#2a0606;}' +
    '#tab-engage .eg-timeline .badge.sim{background:var(--coral);color:#1a0c06;}' +
    '#tab-engage .eg-timeline .meta{font-size:11.5px;color:var(--mut);margin-top:2px;}' +
    '#tab-engage .eg-empty{color:var(--mut);font-style:italic;}' +
    '#tab-engage .eg-never{font-size:11.5px;color:var(--mut);margin-top:8px;}' +
    '#tab-engage .eg-never code{color:var(--coral);}' +
    '';

  function injectStyle() {
    if (document.getElementById('eg-style')) return;
    var s = el('style', { id: 'eg-style' }); s.textContent = STYLE;
    document.head.appendChild(s);
  }

  // ---- state ----
  var state = {
    decision: null,   // latest decision from Dev 3
    engagements: [],  // simulated engagement records
    busy: false,
    operator: 'operator@console' // honest default actor label
  };

  function host() { return document.getElementById('tab-engage'); }

  // ---- render ----
  function render() {
    var root = host();
    if (!root) return;
    root.innerHTML = '';
    var wrap = el('div', { class: 'eg-wrap' });

    // SIMULATED banner — big, unmissable, present always
    wrap.appendChild(el('div', { class: 'eg-sim-banner', role: 'status', 'aria-live': 'polite' }, [
      el('span', { class: 'eg-sim-dot', 'aria-hidden': 'true' }),
      el('div', {}, [
        el('h2', { text: 'SIMULATED — EFFECTOR NOT LIVE — HUMAN ON THE LOOP' }),
        el('div', { class: 'eg-sub', text: 'No command leaves this console. This gate records a simulated engagement only.' })
      ])
    ]));

    // honest one-line caption
    wrap.appendChild(el('div', { class: 'eg-caption', text:
      'Decisioning is real; the effector is simulated; a human approves every action.' }));

    // Recommended action card
    var card = el('div', { class: 'eg-card' });
    card.appendChild(el('h3', { text: 'Recommended action (from DECIDE)' }));
    if (!state.decision) {
      card.appendChild(el('p', { class: 'eg-empty', text:
        'Awaiting a governed decision from the DECIDE tab… Run the loop to produce a recommendation.' }));
    } else {
      var d = state.decision;
      var grid = el('div', { class: 'eg-grid' });
      function kv(k, v) { return el('div', { class: 'eg-kv' }, [el('div', { class: 'k', text: k }), el('div', { class: 'v', text: v })]); }
      grid.appendChild(kv('Track', d.trackId || d.track_id || '—'));
      grid.appendChild(kv('Action', d.action || d.recommendation || '—'));
      grid.appendChild(kv('Verdict', d.verdict || d.decision || '—'));
      // trust / lambda — never claim 100%
      var lam = (d.lambda != null) ? d.lambda : (d.score != null ? d.score : null);
      var trustEl = el('div', { class: 'eg-kv' }, [
        el('div', { class: 'k', text: 'Trust (Λ)' }),
        el('div', { class: 'v eg-trust', html: lam != null ? trustStr(lam) : '—' })
      ]);
      grid.appendChild(trustEl);
      card.appendChild(grid);

      // approval actions
      var approve = el('button', {
        class: 'eg-btn eg-approve', type: 'button', id: 'eg-approve',
        'aria-label': 'Approve simulated engagement',
        onclick: function () { onApprove(); }
      }, ['APPROVE (simulate)']);
      var deny = el('button', {
        class: 'eg-btn eg-deny', type: 'button', id: 'eg-deny',
        'aria-label': 'Deny engagement',
        onclick: function () { onDeny(); }
      }, ['DENY']);
      if (state.busy) { approve.disabled = true; deny.disabled = true; }
      card.appendChild(el('div', { class: 'eg-actions' }, [approve, deny]));

      // simulation stage (filled during the simulated intercept)
      card.appendChild(el('div', { id: 'eg-stage' }));

      card.appendChild(el('p', { class: 'eg-never', html:
        'This control will <b>never</b> transmit to any aircraft, radio, or effector. ' +
        'No takeover / jam / spoof is performed or claimed. Outcome is recorded as ' +
        '<code>simulated:true</code> and chained into a khipu receipt.' }));
    }
    wrap.appendChild(card);

    // Engagement timeline
    var tl = el('div', { class: 'eg-card' });
    tl.appendChild(el('h3', { text: 'Engagement timeline (simulated)' }));
    if (!state.engagements.length) {
      tl.appendChild(el('p', { class: 'eg-empty', text: 'No engagements yet.' }));
    } else {
      var ul = el('ul', { class: 'eg-timeline' });
      state.engagements.slice().reverse().forEach(function (e) {
        var badgeCls = e.outcome === 'APPROVED' ? 'ap' : 'dn';
        ul.appendChild(el('li', {}, [
          el('span', { class: 'badge ' + badgeCls, text: e.outcome === 'APPROVED' ? 'SIM ✓' : 'DENIED' }),
          el('div', {}, [
            el('div', { html: '<b>' + esc(e.action) + '</b> — track ' + esc(e.trackId) }),
            el('div', { class: 'meta', text:
              'id ' + e.id + ' · by ' + e.approvedBy + ' · ' + fmtTs(e.ts) + ' · simulated:true' })
          ]),
          el('span', { class: 'badge sim', text: 'SIMULATED' })
        ]));
      });
      tl.appendChild(ul);
    }
    wrap.appendChild(tl);

    root.appendChild(wrap);
  }

  function trustStr(lam) {
    var n = Number(lam);
    if (!isFinite(n)) {
      // No numeric trust value yet — honest placeholder (never fabricate a number).
      return '<b>—</b> <span style="color:var(--mut);font-size:11px">(never 100%)</span>';
    }
    var pct = (n <= 1 ? n * 100 : n);
    if (pct >= 100) pct = 99.9; // doctrine: trust never 100%
    return '<b>' + pct.toFixed(1) + '%</b> <span style="color:var(--mut);font-size:11px">(never 100%)</span>';
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }

  // ---- approval flow ----
  function onDeny() {
    if (!state.decision || state.busy) return;
    var d = state.decision;
    var rec = {
      id: shortId(), trackId: d.trackId || d.track_id || 'unknown',
      action: d.action || d.recommendation || 'engage',
      outcome: 'DENIED', approvedBy: state.operator, ts: Date.now(), simulated: true
    };
    state.engagements.push(rec);
    // receipt for the denial (every operator step gets a receipt)
    emitReceipt('engage.deny', { trackId: rec.trackId, action: rec.action, outcome: 'DENIED', approvedBy: rec.approvedBy, simulated: true });
    render();
  }

  function onApprove() {
    if (!state.decision || state.busy) return;
    state.busy = true;
    render();
    runSimIntercept(function () {
      var d = state.decision;
      var rec = {
        id: shortId(), trackId: d.trackId || d.track_id || 'unknown',
        action: d.action || d.recommendation || 'engage',
        outcome: 'APPROVED', approvedBy: state.operator, ts: Date.now(), simulated: true
      };
      state.engagements.push(rec);
      // 1) emit engagement event (contract shape) — SIMULATED, never a real command
      JACKIN.emit('engagement', {
        trackId: rec.trackId, action: rec.action, approvedBy: rec.approvedBy,
        ts: rec.ts, simulated: true
      });
      // 2) emit a khipu receipt for the approved (simulated) engagement
      emitReceipt('engage.approve', {
        trackId: rec.trackId, action: rec.action, outcome: 'APPROVED',
        approvedBy: rec.approvedBy, simulated: true
      });
      state.busy = false;
      render();
    });
  }

  // emit a receipt the way receipts.js expects (it signs via /khipu/sign)
  function emitReceipt(action, data) {
    JACKIN.emit('receipt', { action: action, data: data, simulated: true, ts: Date.now() });
  }

  // ---- simulated intercept animation + countdown (clearly labeled SIMULATED) ----
  function runSimIntercept(done) {
    var stage = document.getElementById('eg-stage');
    if (!stage) { done(); return; }
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    stage.innerHTML = '';
    var box = el('div', { class: 'eg-sim-stage', role: 'status', 'aria-live': 'assertive' });
    box.appendChild(el('span', { class: 'eg-sim-tag', text: 'SIMULATED INTERCEPT' }));
    var cd = el('div', { class: 'eg-cd', id: 'eg-cd', text: '3' });
    var bar = el('div', { class: 'eg-bar' }, [el('i', { id: 'eg-bar-i' })]);
    var note = el('div', { class: 'eg-sub', style: 'margin-top:8px;color:var(--mut)',
      text: 'Rehearsing the governed action — no signal transmitted. Effector remains OFFLINE.' });
    box.appendChild(cd); box.appendChild(bar); box.appendChild(note);
    stage.appendChild(box);

    if (reduce) { // accessibility: skip the animation, still honest
      document.getElementById('eg-bar-i').style.width = '100%';
      cd.textContent = 'SIMULATED ✓';
      setTimeout(done, 250);
      return;
    }
    var dur = 1800, t0 = performance.now();
    function step(now) {
      var p = Math.min(1, (now - t0) / dur);
      var bi = document.getElementById('eg-bar-i'); if (bi) bi.style.width = (p * 100).toFixed(1) + '%';
      var remain = Math.ceil((1 - p) * 3);
      var cdn = document.getElementById('eg-cd');
      if (cdn) cdn.textContent = p < 1 ? String(Math.max(0, remain)) : 'SIMULATED ✓';
      if (p < 1) requestAnimationFrame(step); else setTimeout(done, 220);
    }
    requestAnimationFrame(step);
  }

  // ---- subscribe to decisions ----
  JACKIN.on('decision', function (payload) {
    state.decision = payload || null;
    state.busy = false;
    render();
  });

  // ---- boot ----
  function boot() { injectStyle(); render(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
  // re-render if the section appears later (Dev1 shell loads after us)
  var tries = 0;
  var iv = setInterval(function () {
    tries++;
    if (host()) { injectStyle(); if (!host().querySelector('.eg-wrap')) render(); }
    if (host() || tries > 40) clearInterval(iv);
  }, 150);

  // expose for QA harness (non-authoritative)
  window.__JACKIN_ENGAGE__ = { state: state, render: render, _onApprove: onApprove, _onDeny: onDeny };
})();
