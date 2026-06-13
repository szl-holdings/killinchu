/*
 * app.js — killinchu JACK-IN console (Dev 1)
 * Owns: the window.JACKIN shared contract object, the tab router, and shell
 * wiring. All other devs (2-5) code against window.JACKIN defined here.
 *
 * SHARED CONTRACT (per BUILD_CONTRACT.md):
 *   window.JACKIN = {
 *     bus: EventTarget,                          // 'telemetry','track','classification','decision','engagement','receipt','link'
 *     source: { connect(kind), disconnect(), status(), kind },  // kind: serial|ble|usb|ws|adsb|ais|sitl
 *     emit(type, payload), on(type, fn),
 *     KILLINCHU_BASE: '',                        // same-origin on the Space
 *     label(isLive) -> 'LIVE'|'SAMPLE'
 *   }
 *   Telemetry shape: {lat,lon,alt,hdg,spd,batt,rssi,src,ts,raw}
 *
 * Idempotent: if Dev5's jackin_bus.js already created window.JACKIN, we adopt
 * it and only fill in anything missing — never clobber.
 */
(function () {
  'use strict';

  // ----------------------------------------------------------------------
  // 1) The shared contract object (created once, adopted if pre-existing).
  // ----------------------------------------------------------------------
  var J = window.JACKIN || {};

  if (!(J.bus instanceof EventTarget)) {
    J.bus = new EventTarget();
  }

  // Same-origin base on the HF Space (killinchu serves /api/killinchu/v1/*).
  if (typeof J.KILLINCHU_BASE !== 'string') {
    J.KILLINCHU_BASE = '';
  }

  // emit/on helpers over the EventTarget bus. Payload rides on evt.detail.
  if (typeof J.emit !== 'function') {
    J.emit = function (type, payload) {
      J.bus.dispatchEvent(new CustomEvent(type, { detail: payload }));
    };
  }
  if (typeof J.on !== 'function') {
    J.on = function (type, fn) {
      var wrapped = function (e) { fn(e.detail, e); };
      J.bus.addEventListener(type, wrapped);
      // return an unsubscribe handle
      return function off() { J.bus.removeEventListener(type, wrapped); };
    };
  }

  // LIVE / SAMPLE honesty label — used everywhere a pill is shown.
  if (typeof J.label !== 'function') {
    J.label = function (isLive) { return isLive ? 'LIVE' : 'SAMPLE'; };
  }

  // The active source. connect.js (Dev 1) installs the real implementation
  // via JACKIN.registerSource(impl). Until then, a safe no-op stub so other
  // devs can call status() without crashing.
  if (!J.source) {
    J.source = {
      kind: null,
      connect: function () {
        return Promise.reject(new Error('source manager not ready'));
      },
      disconnect: function () {},
      status: function () { return { connected: false, kind: null, live: false }; }
    };
  }

  // Allow connect.js to swap in the real source manager once it loads.
  J.registerSource = function (impl) {
    J.source = impl;
    J.emit('link', { event: 'source-registered', kind: impl.kind || null });
    return J.source;
  };

  // Convenience: emit a telemetry record, normalising the contract shape.
  // Sources should call JACKIN.telemetry({...}) so the shape is guaranteed.
  if (typeof J.telemetry !== 'function') {
    J.telemetry = function (rec) {
      var t = {
        lat:  (rec.lat  !== undefined) ? rec.lat  : null,
        lon:  (rec.lon  !== undefined) ? rec.lon  : null,
        alt:  (rec.alt  !== undefined) ? rec.alt  : null,
        hdg:  (rec.hdg  !== undefined) ? rec.hdg  : null,
        spd:  (rec.spd  !== undefined) ? rec.spd  : null,
        batt: (rec.batt !== undefined) ? rec.batt : null,
        rssi: (rec.rssi !== undefined) ? rec.rssi : null,
        src:  rec.src || 'unknown',
        ts:   rec.ts || Date.now(),
        raw:  rec.raw || null
      };
      J.emit('telemetry', t);
      return t;
    };
  }

  window.JACKIN = J;

  // ----------------------------------------------------------------------
  // 2) Tab router. Tabs are declared in index.html as [data-tab] buttons and
  //    matching <section id="tab-<key>"> mount points. Hash-routed so deep
  //    links (#decide) work and the back button behaves.
  // ----------------------------------------------------------------------
  var TABS = ['connect', 'livefeed', 'fusion', 'classify', 'decide', 'engage', 'receipts'];
  var DEFAULT_TAB = 'connect';

  function activate(key) {
    if (TABS.indexOf(key) === -1) key = DEFAULT_TAB;

    document.querySelectorAll('[data-tab]').forEach(function (btn) {
      var on = btn.getAttribute('data-tab') === key;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
      btn.setAttribute('tabindex', on ? '0' : '-1');
    });

    document.querySelectorAll('[data-panel]').forEach(function (sec) {
      var on = sec.getAttribute('data-panel') === key;
      sec.hidden = !on;
      sec.classList.toggle('is-active', on);
    });

    // Let panel owners (Dev 2-4) lazy-init / refresh when their tab shows.
    J.emit('tabchange', { tab: key });

    if (location.hash.slice(1) !== key) {
      history.replaceState(null, '', '#' + key);
    }
  }

  J.activateTab = activate;

  function initRouter() {
    var nav = document.querySelector('.jk-tabs');
    if (nav) {
      nav.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-tab]');
        if (btn) { e.preventDefault(); activate(btn.getAttribute('data-tab')); }
      });
      // Arrow-key navigation across the tablist (WCAG keyboard support).
      nav.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        var btns = Array.prototype.slice.call(nav.querySelectorAll('[data-tab]'));
        var cur = btns.findIndex(function (b) { return b.classList.contains('is-active'); });
        var dir = e.key === 'ArrowRight' ? 1 : -1;
        var next = (cur + dir + btns.length) % btns.length;
        var key = btns[next].getAttribute('data-tab');
        activate(key);
        btns[next].focus();
        e.preventDefault();
      });
    }

    window.addEventListener('hashchange', function () {
      activate(location.hash.slice(1) || DEFAULT_TAB);
    });

    activate(location.hash.slice(1) || DEFAULT_TAB);
  }

  // ----------------------------------------------------------------------
  // 3) Global link-status reflection in the header (everyone emits 'link').
  // ----------------------------------------------------------------------
  function initStatusReflector() {
    var dot = document.getElementById('jk-link-dot');
    var txt = document.getElementById('jk-link-text');
    var pill = document.getElementById('jk-live-pill');
    if (!dot || !txt) return;

    J.on('link', function (d) {
      d = d || {};
      var st = (J.source && J.source.status) ? J.source.status() : {};
      var connected = !!st.connected;
      dot.classList.toggle('is-up', connected);
      dot.classList.toggle('is-down', !connected);
      var kind = st.kind ? st.kind.toUpperCase() : '—';
      txt.textContent = connected ? ('JACKED IN · ' + kind) : 'NO LINK';
      if (pill) {
        var live = !!st.live;
        pill.textContent = J.label(live);
        pill.classList.toggle('is-live', live);
        pill.classList.toggle('is-sample', !live);
        pill.hidden = !connected;
      }
    });
  }

  // ----------------------------------------------------------------------
  // boot
  // ----------------------------------------------------------------------
  function boot() {
    initRouter();
    initStatusReflector();
    // Announce the contract is ready so connect.js + Dev 2-5 modules can init.
    J.ready = true;
    J.emit('ready', { ts: Date.now() });
    document.documentElement.setAttribute('data-jackin-ready', '1');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
