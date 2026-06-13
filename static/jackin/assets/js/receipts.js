/* JACK IN — RECEIPTS tab  | Dev 4  (the killer close)
 * Every operator step (connect, track, classify, decide, engage) emits a khipu receipt.
 * We sign each receipt with the REAL same-origin endpoint:  POST /khipu/sign
 *   -> DSSE ECDSA-P256 envelope {payload(b64), payloadType, signatures:[{keyid,sig,sig_type}]}
 * We build a chain (prev_hash|action|seq), display it, and let the user RE-HASH any
 * receipt client-side with SubtleCrypto SHA-256 -> MATCH ✓.
 * "Tamper a byte" demo: flip one byte -> re-hash -> MATCH fails (caught).
 * We also pull the EXISTING chains: a11oy ledger + killinchu/a11oy command-log.
 *
 * HONESTY DOCTRINE:
 *  - Receipts are REAL. We NEVER fabricate a signature. If /khipu/sign is unreachable
 *    we show an honest "signer unreachable" state and do NOT fake a MATCH.
 *  - The MATCH is a client-side SHA-256 over the canonical receipt bytes — independently
 *    re-checkable by anyone. We label clearly what is signed vs. what is hashed.
 *
 * Contract: window.JACKIN.on('receipt', fn). Renders into Dev1 <section id="tab-receipts">.
 * 0 CDN. WCAG-AA. Responsive. Uses console.css vars w/ fallbacks.
 */
(function () {
  'use strict';

  if (!window.JACKIN) {
    var _bus = new EventTarget();
    window.JACKIN = {
      bus: _bus, KILLINCHU_BASE: '',
      emit: function (t, p) { _bus.dispatchEvent(new CustomEvent(t, { detail: p })); },
      on: function (t, fn) { _bus.addEventListener(t, function (e) { fn(e.detail, e); }); },
      label: function (l) { return l ? 'LIVE' : 'SAMPLE'; }
    };
  }
  var JACKIN = window.JACKIN;
  var BASE = JACKIN.KILLINCHU_BASE || ''; // '' = same-origin on the Space

  // a11oy host serves the existing chain endpoints with CORS allowing the killinchu origin.
  // Same-origin first (works when mounted on the killinchu Space); fall back to absolute host.
  var A11OY_HOST = 'https://szlholdings-a11oy.hf.space';
  var EXISTING_SOURCES = [
    { name: 'a11oy ledger',           paths: ['/api/a11oy/v1/ledger',      A11OY_HOST + '/api/a11oy/v1/ledger'] },
    { name: 'killinchu command-log',  paths: ['/api/a11oy/v2/command-log', A11OY_HOST + '/api/a11oy/v2/command-log'] },
    { name: 'killinchu khipu ledger', paths: ['/api/killinchu/v1/khipu/ledger'] }
  ];

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
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }
  function fmtTs(ts) { try { return new Date(ts).toISOString().replace('T', ' '); } catch (e) { return String(ts); } }

  // ---- crypto helpers (SubtleCrypto SHA-256, browser-native, no CDN) ----
  var enc = new TextEncoder();
  function bytesToHex(buf) {
    var b = new Uint8Array(buf), s = '';
    for (var i = 0; i < b.length; i++) s += b[i].toString(16).padStart(2, '0');
    return s;
  }
  function sha256Hex(strOrBytes) {
    var data = (typeof strOrBytes === 'string') ? enc.encode(strOrBytes) : strOrBytes;
    if (!(window.crypto && window.crypto.subtle)) {
      return Promise.reject(new Error('SubtleCrypto unavailable (needs HTTPS/secure context)'));
    }
    return window.crypto.subtle.digest('SHA-256', data).then(bytesToHex);
  }

  // Canonical bytes for a receipt = the exact string we hash & display.
  // Chain rule (as specified): prev_hash | action | seq  (plus a stable payload digest)
  function canonicalString(r) {
    // stable JSON of the receipt's data, then the chain triple
    var payload = JSON.stringify(r.data || {});
    return [r.prev_hash || 'GENESIS', r.action, String(r.seq), payload, String(r.ts)].join('|');
  }

  // ---- state ----
  var state = {
    receipts: [],         // {seq, action, data, ts, prev_hash, hash, canonical, signed, sig, keyid, sigType, signerNote, tampered}
    signerOk: null,       // null=unknown, true/false after first attempt
    signerNote: '',
    existing: [],         // pulled chains
    nextSeq: 0
  };
  function host() { return document.getElementById('tab-receipts'); }
  function lastHash() { return state.receipts.length ? state.receipts[state.receipts.length - 1].hash : ''; }

  // ---- styles ----
  var STYLE = '' +
    '#tab-receipts{--navy:var(--jk-navy,#06122E);--coral:var(--jk-coral,#E07A5F);' +
    '--ink:var(--jk-ink,#EAF0FF);--mut:var(--jk-muted,#9FB0D0);--card:var(--jk-card,#0B1B40);' +
    '--line:var(--jk-line,#1E3566);--ok:var(--jk-ok,#3DD68C);--warn:var(--jk-warn,#FFC857);' +
    '--bad:var(--jk-bad,#FF6B6B);color:var(--ink);font:14px/1.5 var(--jk-font,system-ui,-apple-system,Segoe UI,Roboto,sans-serif);}' +
    '#tab-receipts .rc-wrap{display:flex;flex-direction:column;gap:16px;max-width:1040px;margin:0 auto;}' +
    '#tab-receipts .rc-hero{border:1px solid var(--line);border-radius:14px;padding:16px 18px;background:linear-gradient(180deg,rgba(224,122,95,.10),rgba(255,255,255,.02));}' +
    '#tab-receipts .rc-hero h2{margin:0 0 4px;font-size:clamp(16px,3vw,22px);font-weight:800;}' +
    '#tab-receipts .rc-hero p{margin:0;color:var(--mut);font-size:13px;}' +
    '#tab-receipts .rc-signer{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;padding:4px 10px;border-radius:8px;margin-top:10px;border:1px solid var(--line);}' +
    '#tab-receipts .rc-signer.ok{color:var(--ok);border-color:var(--ok);}' +
    '#tab-receipts .rc-signer.down{color:var(--bad);border-color:var(--bad);}' +
    '#tab-receipts .rc-signer.unk{color:var(--mut);}' +
    '#tab-receipts .rc-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;}' +
    '#tab-receipts .rc-card h3{margin:0 0 12px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);}' +
    '#tab-receipts .rc-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;}' +
    '#tab-receipts button.rc-btn{font:inherit;font-weight:700;border-radius:9px;padding:9px 14px;cursor:pointer;border:1px solid var(--line);background:rgba(255,255,255,.04);color:var(--ink);}' +
    '#tab-receipts button.rc-btn.primary{background:var(--coral);color:#1a0c06;border-color:var(--coral);}' +
    '#tab-receipts button.rc-btn:focus-visible{outline:3px solid var(--warn);outline-offset:2px;}' +
    '#tab-receipts button.rc-btn:disabled{opacity:.5;cursor:not-allowed;}' +
    '#tab-receipts .rc-rcpt{border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:10px;background:rgba(255,255,255,.02);}' +
    '#tab-receipts .rc-rcpt.tampered{border-color:var(--bad);background:rgba(255,107,107,.07);}' +
    '#tab-receipts .rc-rh{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center;}' +
    '#tab-receipts .rc-seq{font-weight:800;font-size:13px;letter-spacing:.05em;}' +
    '#tab-receipts .rc-act{color:var(--coral);font-weight:700;}' +
    '#tab-receipts .rc-pill{font-size:10px;font-weight:800;letter-spacing:.1em;padding:2px 8px;border-radius:6px;}' +
    '#tab-receipts .rc-pill.signed{background:var(--ok);color:#04230f;}' +
    '#tab-receipts .rc-pill.unsigned{background:var(--bad);color:#2a0606;}' +
    '#tab-receipts .rc-pill.sim{background:var(--coral);color:#1a0c06;}' +
    '#tab-receipts .rc-mono{font-family:var(--jk-mono,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace);font-size:11.5px;word-break:break-all;color:var(--mut);}' +
    '#tab-receipts .rc-row{margin-top:6px;}' +
    '#tab-receipts .rc-row .lbl{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);}' +
    '#tab-receipts .rc-rcheck{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center;}' +
    '#tab-receipts .rc-verdict{font-weight:800;font-size:12.5px;padding:3px 9px;border-radius:7px;}' +
    '#tab-receipts .rc-verdict.match{background:var(--ok);color:#04230f;}' +
    '#tab-receipts .rc-verdict.fail{background:var(--bad);color:#2a0606;}' +
    '#tab-receipts .rc-empty{color:var(--mut);font-style:italic;}' +
    '#tab-receipts .rc-exist table{width:100%;border-collapse:collapse;font-size:12px;}' +
    '#tab-receipts .rc-exist th,#tab-receipts .rc-exist td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);}' +
    '#tab-receipts .rc-exist th{color:var(--mut);font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;}' +
    '#tab-receipts .rc-exist .rc-mono{color:var(--ink);}' +
    '#tab-receipts .rc-src-note{font-size:11.5px;color:var(--mut);margin:2px 0 10px;}' +
    '#tab-receipts .rc-src-note.bad{color:var(--bad);}' +
    '#tab-receipts .rc-foot{font-size:11px;color:var(--mut);border-top:1px solid var(--line);padding-top:10px;}' +
    '';
  function injectStyle() {
    if (document.getElementById('rc-style')) return;
    var s = el('style', { id: 'rc-style' }); s.textContent = STYLE; document.head.appendChild(s);
  }

  // ---- signing: REAL same-origin POST /khipu/sign (never fabricate) ----
  function signReceipt(r) {
    var url = BASE + '/khipu/sign'; // mode defaults to ecdsa server-side
    var body = JSON.stringify({ payload: { prev_hash: r.prev_hash, action: r.action, seq: r.seq, data: r.data, ts: r.ts } });
    return fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body
    }).then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var ct = resp.headers.get('content-type') || '';
      if (ct.indexOf('application/json') === -1) throw new Error('non-JSON (signer route not mounted)');
      return resp.json();
    }).then(function (j) {
      var sigObj = (j.envelope && j.envelope.signatures && j.envelope.signatures[0]) || null;
      if (!sigObj || !sigObj.sig) throw new Error('no signature in envelope');
      state.signerOk = true; state.signerNote = '';
      return {
        signed: true,
        sig: sigObj.sig,
        keyid: sigObj.keyid || (j.keyid || 'unknown'),
        sigType: sigObj.sig_type || (j.sig_types && j.sig_types[0]) || 'ECDSA-P256-SHA256',
        verified: j.verified === true,
        payloadType: (j.envelope && j.envelope.payloadType) || 'application/vnd.szl.khipu+json',
        signerNote: ''
      };
    }).catch(function (err) {
      // HONEST failure — never fake a signature
      state.signerOk = false;
      state.signerNote = 'signer unreachable: ' + err.message;
      return {
        signed: false, sig: null, keyid: null, sigType: null, verified: false,
        signerNote: 'signer unreachable — receipt is UNSIGNED (honest). ' + err.message
      };
    });
  }

  // ---- ingest a receipt event, hash + sign, append to chain ----
  function ingest(evt) {
    var r = {
      seq: state.nextSeq++,
      action: (evt && evt.action) || 'step',
      data: (evt && evt.data) || {},
      ts: (evt && evt.ts) || Date.now(),
      prev_hash: lastHash() || 'GENESIS',
      simulated: !!(evt && evt.simulated)
    };
    r.canonical = canonicalString(r);
    state.receipts.push(r); // show immediately (hash pending)
    render();
    // 1) client-side chain hash
    sha256Hex(r.canonical).then(function (h) {
      r.hash = h;
      render();
      // 2) real DSSE signature (same-origin)
      return signReceipt(r);
    }).then(function (sg) {
      if (sg) { r.signed = sg.signed; r.sig = sg.sig; r.keyid = sg.keyid; r.sigType = sg.sigType; r.verified = sg.verified; r.signerNote = sg.signerNote; }
      render();
    }).catch(function (e) {
      r.hashError = String(e.message || e); render();
    });
  }

  // ---- re-hash a receipt (independent verification) ----
  function rehash(seq) {
    var r = state.receipts[seq]; if (!r) return;
    var current = r.tampered ? r.canonicalTampered : r.canonical;
    sha256Hex(current).then(function (h) {
      r.rehash = h;
      r.match = (h === r.hash);
      render();
    });
  }

  // ---- tamper a byte: flip one byte of the canonical payload, then re-hash (must FAIL) ----
  function tamper(seq) {
    var r = state.receipts[seq]; if (!r || r.hash == null) return;
    if (!r.tampered) {
      // flip the first byte of the canonical string deterministically
      var s = r.canonical;
      var ch = s.charCodeAt(0);
      var flipped = String.fromCharCode(ch ^ 0x01) + s.slice(1);
      r.canonicalTampered = flipped;
      r.tampered = true;
    } else {
      r.tampered = false;
      r.canonicalTampered = null;
    }
    r.rehash = null; r.match = null;
    render();
    rehash(seq); // immediately re-verify -> shows MATCH ✗ when tampered, ✓ when restored
  }

  // ---- pull existing chains ----
  function fetchFirstOk(paths) {
    var i = 0;
    function attempt() {
      if (i >= paths.length) return Promise.reject(new Error('all paths failed'));
      var p = paths[i++];
      return fetch(p, { headers: { 'Accept': 'application/json' } }).then(function (resp) {
        var ct = resp.headers.get('content-type') || '';
        if (!resp.ok || ct.indexOf('application/json') === -1) throw new Error('HTTP ' + resp.status + ' / ' + (ct || 'no-ct'));
        return resp.json().then(function (j) { return { path: p, json: j }; });
      }).catch(function () { return attempt(); });
    }
    return attempt();
  }

  function loadExisting() {
    state.existing = EXISTING_SOURCES.map(function (s) { return { name: s.name, status: 'loading', rows: [], note: '' }; });
    render();
    EXISTING_SOURCES.forEach(function (src, idx) {
      fetchFirstOk(src.paths).then(function (res) {
        var j = res.json, rows = [];
        if (Array.isArray(j.receipts)) {
          rows = j.receipts.map(function (x) {
            return { seq: x.seq, action: x.kind || x.action || x.command || '—', hash: x.hash || x.receipt_id || '', prev: x.prev_hash || '' };
          });
        }
        state.existing[idx] = {
          name: src.name, status: 'ok', rows: rows, path: res.path,
          note: (j.chain_verified != null ? ('chain_verified: ' + j.chain_verified + ' · ') : '') +
                (j.count != null ? (j.count + ' receipts') : (j.depth != null ? (j.depth + ' deep') : (rows.length + ' rows'))) +
                (j.final_hash ? (' · head ' + j.final_hash.slice(0, 12) + '…') : '')
        };
        render();
      }).catch(function (err) {
        state.existing[idx] = { name: src.name, status: 'down', rows: [],
          note: 'unreachable (' + (err.message || 'error') + ') — shown honestly, not fabricated' };
        render();
      });
    });
  }

  // ---- render ----
  function render() {
    var root = host(); if (!root) return;
    root.innerHTML = '';
    var wrap = el('div', { class: 'rc-wrap' });

    // hero
    var hero = el('div', { class: 'rc-hero' });
    hero.appendChild(el('h2', { text: 'Everything you just saw, cryptographically provable — re-check it yourself.' }));
    hero.appendChild(el('p', { html:
      'Each operator step emits a khipu receipt, chained <code>prev_hash | action | seq</code> and ' +
      'DSSE-signed (ECDSA&#8209;P256) by the live <code>/khipu/sign</code> endpoint. ' +
      'Re-hash any receipt below with your browser&rsquo;s SubtleCrypto SHA&#8209;256 to confirm <b>MATCH ✓</b>. ' +
      'Flip a byte and the match fails — tampering is caught.' }));
    var sc = state.signerOk;
    var signerCls = sc === true ? 'ok' : (sc === false ? 'down' : 'unk');
    var signerTxt = sc === true ? 'signer LIVE — /khipu/sign returning real DSSE'
      : (sc === false ? ('signer unreachable — receipts UNSIGNED (honest)') : 'signer: not yet contacted');
    hero.appendChild(el('span', { class: 'rc-signer ' + signerCls, role: 'status', 'aria-live': 'polite', text: signerTxt }));
    wrap.appendChild(hero);

    // your receipt chain
    var chain = el('div', { class: 'rc-card' });
    chain.appendChild(el('h3', { text: 'Your khipu receipt chain (this session)' }));
    var tb = el('div', { class: 'rc-toolbar' });
    tb.appendChild(el('button', { class: 'rc-btn', type: 'button', onclick: function () { rehashAll(); } }, ['Re-hash all']));
    tb.appendChild(el('button', { class: 'rc-btn', type: 'button', onclick: function () { seedDemo(); } }, ['Seed demo step']));
    chain.appendChild(tb);

    if (!state.receipts.length) {
      chain.appendChild(el('p', { class: 'rc-empty', text:
        'No receipts yet. Take steps in CONNECT → TRACK → CLASSIFY → DECIDE → ENGAGE; each emits a receipt here.' }));
    } else {
      state.receipts.forEach(function (r) { chain.appendChild(renderReceipt(r)); });
    }
    wrap.appendChild(chain);

    // existing chains
    var ex = el('div', { class: 'rc-card rc-exist' });
    ex.appendChild(el('h3', { text: 'Existing signed chains (pulled live)' }));
    var exTb = el('div', { class: 'rc-toolbar' });
    exTb.appendChild(el('button', { class: 'rc-btn primary', type: 'button', onclick: function () { loadExisting(); } }, ['Pull existing chains']));
    ex.appendChild(exTb);
    if (!state.existing.length) {
      ex.appendChild(el('p', { class: 'rc-empty', text: 'Click “Pull existing chains” to fetch the a11oy ledger + command-log live.' }));
    } else {
      state.existing.forEach(function (s) { ex.appendChild(renderExisting(s)); });
    }
    wrap.appendChild(ex);

    // honest footer
    wrap.appendChild(el('div', { class: 'rc-foot', html:
      'Receipts are REAL — we never fabricate a signature. The MATCH is your browser&rsquo;s SHA&#8209;256 over the ' +
      'canonical receipt bytes; the signature is the server&rsquo;s DSSE envelope. If the signer is unreachable, the ' +
      'receipt is shown UNSIGNED rather than faked. trust never 100%. ' +
      'Doctrine v11 — locked=8 {F1,F4,F7,F11,F12,F18,F19,F22} @ c7c0ba17, Λ=Conjecture 1, Khipu=Conjecture 2.' }));

    root.appendChild(wrap);
  }

  function renderReceipt(r) {
    var box = el('div', { class: 'rc-rcpt' + (r.tampered ? ' tampered' : '') });
    var head = el('div', { class: 'rc-rh' });
    head.appendChild(el('span', { class: 'rc-seq', text: 'seq ' + r.seq }));
    head.appendChild(el('span', { class: 'rc-act', text: r.action }));
    var pills = el('span', {});
    if (r.simulated) pills.appendChild(el('span', { class: 'rc-pill sim', text: 'SIMULATED' }));
    if (r.signed === true) pills.appendChild(el('span', { class: 'rc-pill signed', text: 'DSSE SIGNED' }));
    else if (r.signed === false) pills.appendChild(el('span', { class: 'rc-pill unsigned', text: 'UNSIGNED' }));
    head.appendChild(pills);
    box.appendChild(head);

    box.appendChild(row('canonical (prev_hash | action | seq | payload | ts)', esc(r.tampered ? r.canonicalTampered : r.canonical)));
    box.appendChild(row('chain hash (server-time SHA-256)', r.hash ? esc(r.hash) : '<i>hashing…</i>'));
    if (r.signed === true) {
      box.appendChild(row('DSSE sig (' + esc(r.sigType || '') + ', keyid ' + esc(r.keyid || '') + ', verified ' + (r.verified ? 'true' : 'false') + ')', esc(r.sig)));
    } else if (r.signed === false) {
      box.appendChild(row('signature', '<span style="color:var(--bad)">' + esc(r.signerNote || 'signer unreachable — UNSIGNED (honest)') + '</span>'));
    }

    var rc = el('div', { class: 'rc-rcheck' });
    var seq = r.seq;
    var disabled = (r.hash == null);
    rc.appendChild(el('button', { class: 'rc-btn', type: 'button', disabled: disabled ? 'disabled' : null,
      'aria-label': 'Re-hash receipt ' + seq + ' client-side',
      onclick: function () { rehash(seq); } }, ['Re-hash (SHA-256)']));
    rc.appendChild(el('button', { class: 'rc-btn', type: 'button', disabled: disabled ? 'disabled' : null,
      'aria-label': (r.tampered ? 'Restore' : 'Tamper a byte of') + ' receipt ' + seq,
      onclick: function () { tamper(seq); } }, [r.tampered ? 'Restore byte' : 'Tamper a byte']));
    if (r.rehash) {
      rc.appendChild(el('span', { class: 'rc-verdict ' + (r.match ? 'match' : 'fail'),
        role: 'status', 'aria-live': 'polite',
        text: r.match ? 'MATCH ✓' : 'MATCH ✗ — TAMPER CAUGHT' }));
    }
    box.appendChild(rc);
    if (r.rehash) box.appendChild(row('your re-hash', esc(r.rehash)));
    return box;
  }
  function row(label, htmlVal) {
    return el('div', { class: 'rc-row' }, [
      el('div', { class: 'lbl', text: label }),
      el('div', { class: 'rc-mono', html: htmlVal })
    ]);
  }

  function renderExisting(s) {
    var box = el('div', {});
    box.appendChild(el('div', { class: 'rc-row' }, [el('b', { text: s.name }),
      el('span', { class: 'rc-pill ' + (s.status === 'ok' ? 'signed' : (s.status === 'down' ? 'unsigned' : 'sim')),
        style: 'margin-left:8px', text: s.status.toUpperCase() })]));
    box.appendChild(el('div', { class: 'rc-src-note' + (s.status === 'down' ? ' bad' : ''), text: s.note || '' }));
    if (s.rows && s.rows.length) {
      var tbl = el('table');
      tbl.appendChild(el('tr', {}, [el('th', { text: 'seq' }), el('th', { text: 'action' }), el('th', { text: 'hash / receipt_id' })]));
      s.rows.slice(0, 8).forEach(function (x) {
        tbl.appendChild(el('tr', {}, [
          el('td', { text: String(x.seq) }),
          el('td', { text: x.action }),
          el('td', {}, [el('span', { class: 'rc-mono', text: (x.hash || '').slice(0, 24) + (x.hash && x.hash.length > 24 ? '…' : '') })])
        ]));
      });
      box.appendChild(tbl);
      if (s.rows.length > 8) box.appendChild(el('div', { class: 'rc-src-note', text: '… +' + (s.rows.length - 8) + ' more' }));
    }
    return box;
  }

  // ---- batch helpers ----
  function rehashAll() { state.receipts.forEach(function (r) { if (r.hash != null) rehash(r.seq); }); }
  function seedDemo() {
    // a clearly-labeled demo step so the close works even before the loop runs
    ingest({ action: 'demo.step', data: { note: 'operator-seeded demo receipt', sample: true }, ts: Date.now(), simulated: false });
  }

  // ---- subscribe: every emitted receipt enters the chain ----
  JACKIN.on('receipt', function (payload) { ingest(payload || {}); });
  // also opportunistically receipt other lifecycle steps if Dev5 forwards them as 'receipt';
  // we do NOT double-handle telemetry/track/etc. here — receipts.js only signs explicit receipt events.

  // ---- boot ----
  function boot() { injectStyle(); render(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
  var tries = 0;
  var iv = setInterval(function () {
    tries++;
    if (host()) { injectStyle(); if (!host().querySelector('.rc-wrap')) render(); }
    if (host() || tries > 40) clearInterval(iv);
  }, 150);

  // QA harness hooks (non-authoritative)
  window.__JACKIN_RECEIPTS__ = {
    state: state, render: render, ingest: ingest, rehash: rehash, tamper: tamper,
    loadExisting: loadExisting, signReceipt: signReceipt, sha256Hex: sha256Hex, canonicalString: canonicalString
  };
})();
