/*
 * jackin_bus.js — DEV 5 shared contract + SITL/SAMPLE source generator.
 *
 * Loads BEFORE app.js (see index.html). Establishes the canonical
 * window.JACKIN contract object per BUILD_CONTRACT.md. app.js is idempotent
 * and adopts whatever we create here, filling only what is missing — so this
 * file and Dev1's app.js cohere with NO duplication and NO clobbering.
 *
 * THE CONTRACT (authoritative — every dev codes to this):
 *   window.JACKIN = {
 *     bus: EventTarget,            // events: telemetry track classification decision engagement receipt link
 *     source: { connect(kind), disconnect(), status(), kind },  // kind: serial|ble|usb|ws|adsb|ais|sitl
 *     emit(type, payload), on(type, fn) -> off(),
 *     KILLINCHU_BASE: '',          // same-origin on the killinchu HF Space
 *     A11OY_BASE: 'https://szlholdings-a11oy.hf.space',  // cross-origin, CORS open (Dev5-confirmed)
 *     label(isLive) -> 'LIVE'|'SAMPLE',
 *     telemetry(rec),              // normalises + emits a telemetry record
 *     registerSource(impl),        // connect.js (Dev1) installs the real multi-source manager
 *     sitl: { make(opts) -> sourceImpl }   // SITL/SAMPLE generator (Dev5) — NO hardware needed
 *   }
 *   Telemetry: {lat,lon,alt,hdg,spd,batt,rssi,src,ts,raw}  (src carries 'SAMPLE'|'LIVE' provenance)
 *   Track (Lattice-style): {id,template:'TRACK',platform_type,pos,classification,conf,src}
 *
 * HARD RULE: SITL telemetry is ALWAYS labeled SAMPLE. We NEVER emit LIVE for synthetic data.
 */
(function () {
  'use strict';

  var J = window.JACKIN || {};

  // ---- 1) core contract (idempotent; app.js will not re-create these) ----
  if (!(J.bus instanceof EventTarget)) J.bus = new EventTarget();
  if (typeof J.KILLINCHU_BASE !== 'string') J.KILLINCHU_BASE = '';     // same-origin
  if (typeof J.A11OY_BASE !== 'string') J.A11OY_BASE = 'https://szlholdings-a11oy.hf.space';

  if (typeof J.emit !== 'function') {
    J.emit = function (type, payload) {
      J.bus.dispatchEvent(new CustomEvent(type, { detail: payload }));
    };
  }
  if (typeof J.on !== 'function') {
    J.on = function (type, fn) {
      var wrapped = function (e) { fn(e.detail, e); };
      J.bus.addEventListener(type, wrapped);
      return function off() { J.bus.removeEventListener(type, wrapped); };
    };
  }
  if (typeof J.label !== 'function') {
    J.label = function (isLive) { return isLive ? 'LIVE' : 'SAMPLE'; };
  }
  if (typeof J.telemetry !== 'function') {
    J.telemetry = function (rec) {
      rec = rec || {};
      var t = {
        lat:  rec.lat  !== undefined ? rec.lat  : null,
        lon:  rec.lon  !== undefined ? rec.lon  : null,
        alt:  rec.alt  !== undefined ? rec.alt  : null,
        hdg:  rec.hdg  !== undefined ? rec.hdg  : null,
        spd:  rec.spd  !== undefined ? rec.spd  : null,
        batt: rec.batt !== undefined ? rec.batt : null,
        rssi: rec.rssi !== undefined ? rec.rssi : null,
        src:  rec.src || 'unknown',
        ts:   rec.ts || Date.now(),
        raw:  rec.raw || null
      };
      J.emit('telemetry', t);
      return t;
    };
  }
  if (!J.source) {
    // safe no-op until connect.js (Dev1) registers the real manager
    J.source = {
      kind: null,
      connect: function () { return Promise.reject(new Error('source manager not ready')); },
      disconnect: function () {},
      status: function () { return { connected: false, kind: null, live: false }; }
    };
  }
  if (typeof J.registerSource !== 'function') {
    J.registerSource = function (impl) {
      J.source = impl;
      J.emit('link', { event: 'source-registered', kind: (impl && impl.kind) || null });
      return J.source;
    };
  }

  // ----------------------------------------------------------------------
  // 2) SITL / SAMPLE generator (Dev5). Emits realistic-shaped telemetry for a
  //    short orbit flight: GPS path, battery drain, attitude, heading, speed,
  //    RSSI. EVERY record is labeled SAMPLE. Drives the SAME pipeline as a real
  //    source so CONNECT->LIVE FEED->FUSION->CLASSIFY->DECIDE->ENGAGE->RECEIPTS
  //    works end-to-end with NO hardware (the demo always works; CI relies on it).
  //
  //    A track is also emitted so FUSION has a Lattice-style entity immediately.
  // ----------------------------------------------------------------------
  function makeSITL(opts) {
    opts = opts || {};
    // Start over a credible AOR (default: SoCal test range, matches ADS-B sample area).
    var lat0 = opts.lat != null ? opts.lat : 34.9000;
    var lon0 = opts.lon != null ? opts.lon : -117.8800;
    var alt0 = opts.alt != null ? opts.alt : 120;     // metres AGL
    var radiusDeg = opts.radiusDeg != null ? opts.radiusDeg : 0.0050; // ~ a few hundred m orbit
    var hz = opts.hz || 4;                              // 4 Hz telemetry
    var trackId = opts.trackId || 'SITL-UAV-01';

    var timer = null;
    var t0 = 0;          // ms since connect
    var connected = false;
    var batt = 100.0;    // %
    var heading = 0;

    function tick() {
      t0 += 1000 / hz;
      var secs = t0 / 1000;
      // Circular orbit path (deterministic, smooth) — realistic for a loiter.
      var theta = (secs * 0.10) % (2 * Math.PI);          // ~63 s per orbit
      var lat = lat0 + radiusDeg * Math.cos(theta);
      var lon = lon0 + radiusDeg * Math.sin(theta) /
                Math.cos(lat0 * Math.PI / 180);            // lon scaling by latitude
      // Altitude gently oscillates around alt0 (climb/descend), clamp >= 0.
      var alt = Math.max(0, alt0 + 25 * Math.sin(secs * 0.05));
      // Heading is tangent to the orbit (deg, 0..360).
      heading = (theta * 180 / Math.PI + 90) % 360;
      // Ground speed ~ orbit circumference / period, with a little jitter.
      var spd = 14 + 1.5 * Math.sin(secs * 0.3);           // m/s
      // Battery drains ~ 0.08%/s (a ~20 min endurance), never below 0.
      batt = Math.max(0, batt - (0.08 / hz));
      // RSSI wanders around -62 dBm (a healthy link) with mild fade.
      var rssi = -62 + Math.round(6 * Math.sin(secs * 0.7));

      var rec = {
        lat: +lat.toFixed(6), lon: +lon.toFixed(6), alt: +alt.toFixed(1),
        hdg: +heading.toFixed(1), spd: +spd.toFixed(2),
        batt: +batt.toFixed(1), rssi: rssi,
        src: 'SAMPLE',                       // <- provenance: NEVER 'LIVE' for SITL
        ts: Date.now(),
        raw: {
          // MAVLink-shaped raw fields so LIVE FEED/decoders see familiar keys.
          GLOBAL_POSITION_INT: {
            lat: Math.round(lat * 1e7), lon: Math.round(lon * 1e7),
            alt: Math.round(alt * 1000), relative_alt: Math.round(alt * 1000),
            hdg: Math.round(heading * 100)
          },
          ATTITUDE: {
            roll: +(0.15 * Math.sin(secs * 0.9)).toFixed(3),
            pitch: +(0.05 * Math.cos(secs * 0.6)).toFixed(3),
            yaw: +(heading * Math.PI / 180).toFixed(3)
          },
          SYS_STATUS: {
            battery_remaining: Math.round(batt),
            voltage_battery: Math.round(11000 + 1200 * (batt / 100)) // mV, ~3S
          },
          GPS_RAW_INT: { fix_type: 3, satellites_visible: 12, eph: 80 },
          HEARTBEAT: { type: 2, autopilot: 12, system_status: 4 } // MAV_TYPE_QUADROTOR-ish
        }
      };

      // Drive the shared pipeline.
      J.telemetry(rec);

      // Emit a Lattice-style TRACK so FUSION has an entity (labeled SAMPLE).
      J.emit('track', {
        id: trackId, template: 'TRACK', platform_type: 'drone',
        pos: { lat: rec.lat, lon: rec.lon, alt: rec.alt },
        classification: 'unknown', conf: 0.62, src: 'SAMPLE'
      });

      // Periodic heartbeat on the link channel.
      if (Math.round(secs * hz) % hz === 0) {
        J.emit('link', { event: 'heartbeat', kind: 'sitl', live: false,
                         rssi: rssi, batt: rec.batt, proto: 'MAVLink v2 (SITL)' });
      }
    }

    var impl = {
      kind: 'sitl',
      connect: function () {
        if (connected) return Promise.resolve(impl.status());
        connected = true; t0 = 0; batt = 100.0;
        J.emit('link', {
          event: 'connected', kind: 'sitl', live: false,
          proto: 'MAVLink v2 (SITL)', detail: 'SITL/SAMPLE source — no hardware',
          heartbeat: true
        });
        timer = setInterval(tick, 1000 / hz);
        return Promise.resolve(impl.status());
      },
      disconnect: function () {
        if (timer) { clearInterval(timer); timer = null; }
        connected = false;
        J.emit('link', { event: 'disconnected', kind: 'sitl', live: false });
      },
      status: function () {
        return { connected: connected, kind: 'sitl', live: false,
                 proto: 'MAVLink v2 (SITL)', batt: +batt.toFixed(1) };
      }
    };
    return impl;
  }

  if (!J.sitl) J.sitl = { make: makeSITL };

  window.JACKIN = J;

  // Expose a tiny diagnostic marker so QA can assert the bus contract loaded.
  window.JACKIN_BUS_READY = true;
})();
