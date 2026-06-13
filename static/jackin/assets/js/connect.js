/*
 * connect.js — killinchu JACK-IN console (Dev 1)
 * The CONNECT tab + the source manager. Owns every browser-native connect
 * path and emits telemetry in the contract shape on window.JACKIN.bus.
 *
 * Source kinds: serial | ble | usb | ws | adsb | ais | sitl
 * Telemetry shape: {lat,lon,alt,hdg,spd,batt,rssi,src,ts,raw}
 *   - Real radio links emit src=<kind> and the link is LIVE.
 *   - SITL/SAMPLE emits src='sitl' (and every record is SAMPLE; we never
 *     claim LIVE without a real transport).
 *
 * Depends on: window.JACKIN (app.js), window.MAVLinkBrowser (vendor).
 */
(function () {
  'use strict';

  var J = window.JACKIN;
  var MB = window.MAVLinkBrowser;
  if (!J) { console.error('[connect] JACKIN contract missing'); return; }

  // ---------------------------------------------------------------------
  // Capability detection (honest — gray out what the browser can't do).
  // ---------------------------------------------------------------------
  var secure = window.isSecureContext === true;
  var CAP = {
    serial: ('serial' in navigator) && secure,
    ble:    ('bluetooth' in navigator) && secure,
    usb:    ('usb' in navigator) && secure,
    ws:     ('WebSocket' in window),
    adsb:   true,   // same-origin killinchu endpoint (Dev 3/5 own the data)
    ais:    true,
    sitl:   true    // always available — the demo must always work
  };
  var BROWSER_NOTE = 'Web Serial / Bluetooth / USB need Chrome or Edge over HTTPS.';

  // ---------------------------------------------------------------------
  // Connect-method catalog (drives the button grid).
  // ---------------------------------------------------------------------
  var METHODS = [
    { kind: 'serial', icon: '🔌', title: 'USB / Serial', desc: 'Flight controller over Web Serial → MAVLink v1/v2.', primary: true },
    { kind: 'ble',    icon: '📶', title: 'Bluetooth',    desc: 'BLE drone / Remote ID beacon over GATT.' },
    { kind: 'usb',    icon: '🛰️', title: 'WebUSB',       desc: 'SDR / receiver via WebUSB bridge.' },
    { kind: 'ws',     icon: '🌐', title: 'Network / WS', desc: 'Ground-agent bridge over WebSocket.' },
    { kind: 'adsb',   icon: '✈️', title: 'ADS-B / AIS',  desc: 'Aircraft + vessel feeds (same-origin killinchu).' },
    { kind: 'sitl',   icon: '🧪', title: 'SITL Sample',  desc: 'Realistic SAMPLE source — no hardware needed.', sample: true }
  ];

  // ---------------------------------------------------------------------
  // DOM helpers + handshake log.
  // ---------------------------------------------------------------------
  function $(id) { return document.getElementById(id); }
  function log(msg, level) {
    var ol = $('jk-handshake-log');
    if (!ol) return;
    var li = document.createElement('li');
    if (level) li.className = level;
    var t = new Date().toLocaleTimeString([], { hour12: false });
    li.innerHTML = '<span class="t">' + t + '</span>' + escapeHtml(msg);
    ol.appendChild(li);
    ol.scrollTop = ol.scrollHeight;
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }
  function setDetail(id, val, live) {
    var el = $(id); if (!el) return;
    el.textContent = val;
    el.classList.toggle('is-live', !!live);
  }

  // ---------------------------------------------------------------------
  // SOURCE MANAGER — the window.JACKIN.source implementation.
  // ---------------------------------------------------------------------
  var manager = {
    kind: null,
    _live: false,
    _impl: null,         // active transport handle (for disconnect)
    _frames: 0,
    _lastHb: 0,
    _hbTimer: null,

    status: function () {
      return {
        connected: !!this._impl,
        kind: this.kind,
        live: this._live,
        frames: this._frames,
        lastHeartbeat: this._lastHb
      };
    },

    connect: function (kind) {
      var self = this;
      if (self._impl) self.disconnect();
      self.kind = kind;
      self._frames = 0;
      setDetail('jk-d-state', 'Connecting…');
      setDetail('jk-d-transport', kind.toUpperCase());
      setDetail('jk-d-proto', '—');
      log('Initiating ' + kind.toUpperCase() + ' connect…');

      var fn = ({
        serial: connectSerial,
        ble:    connectBLE,
        usb:    connectUSB,
        ws:     connectWS,
        adsb:   connectADSBorAIS('adsb'),
        ais:    connectADSBorAIS('ais'),
        sitl:   connectSITL
      })[kind];

      if (!fn) return Promise.reject(new Error('unknown kind ' + kind));

      return Promise.resolve(fn(self)).then(function (impl) {
        self._impl = impl;
        self._live = (kind !== 'sitl');   // SITL is never LIVE
        setDetail('jk-d-state', self._live ? 'LINKED · LIVE' : 'LINKED · SAMPLE', self._live);
        log((self._live ? 'LIVE link up' : 'SAMPLE source running') + ' on ' + kind.toUpperCase(), 'ok');
        J.emit('link', { event: 'connected', kind: kind, live: self._live });
        markCard(kind, true);
        showDisconnect(true);
        startHbWatch(self);
        return self.status();
      }).catch(function (err) {
        self.kind = null; self._impl = null;
        setDetail('jk-d-state', 'Failed');
        log('Connect failed: ' + (err && err.message || err), 'err');
        J.emit('link', { event: 'error', kind: kind, error: String(err && err.message || err) });
        markCard(kind, false);
        throw err;
      });
    },

    disconnect: function () {
      if (this._hbTimer) { clearInterval(this._hbTimer); this._hbTimer = null; }
      if (this._impl && typeof this._impl.close === 'function') {
        try { this._impl.close(); } catch (e) { /* best-effort */ }
      }
      var k = this.kind;
      this._impl = null; this._live = false; this.kind = null;
      setDetail('jk-d-state', 'Idle');
      setDetail('jk-d-transport', '—'); setDetail('jk-d-proto', '—');
      setDetail('jk-d-hb', '—'); setDetail('jk-d-rssi', '—');
      markCard(k, false);
      showDisconnect(false);
      log('Disconnected', 'warn');
      J.emit('link', { event: 'disconnected', kind: k });
    },

    // Internal: called by transports when a telemetry record is ready.
    _emit: function (rec) {
      rec.src = rec.src || this.kind;
      rec.ts = rec.ts || Date.now();
      J.telemetry(rec);
      this._frames++;
      setDetail('jk-d-frames', String(this._frames));
      if (rec.rssi != null) setDetail('jk-d-rssi', rec.rssi + ' dBm', this._live);
    },
    _heartbeat: function (proto) {
      this._lastHb = Date.now();
      if (proto) setDetail('jk-d-proto', proto, this._live);
      setDetail('jk-d-hb', 'OK', this._live);
    }
  };

  function startHbWatch(self) {
    if (self._hbTimer) clearInterval(self._hbTimer);
    self._hbTimer = setInterval(function () {
      if (!self._impl) return;
      var age = Date.now() - self._lastHb;
      if (self._lastHb && age > 3000) setDetail('jk-d-hb', 'STALE (' + Math.round(age / 1000) + 's)', false);
    }, 1000);
  }

  // ---------------------------------------------------------------------
  // MAVLink wiring shared by transports that speak MAVLink (serial / ws / usb).
  // Translates parsed messages into the contract telemetry shape.
  // ---------------------------------------------------------------------
  function makeMavlinkSink(srcKind) {
    var parser = new MB.Parser();
    var state = { lat: null, lon: null, alt: null, hdg: null, spd: null, batt: null, rssi: null };
    parser.onMessage = function (m) {
      var f = m.fields;
      switch (m.msgid) {
        case MB.MSG.HEARTBEAT:
          manager._heartbeat('MAVLink v' + m.version);
          break;
        case MB.MSG.GLOBAL_POSITION_INT:
          state.lat = f.lat / 1e7;
          state.lon = f.lon / 1e7;
          state.alt = f.alt / 1000;              // mm → m
          if (f.hdg !== 65535) state.hdg = f.hdg / 100; // cdeg → deg
          state.spd = Math.hypot(f.vx, f.vy) / 100;     // cm/s → m/s (ground speed)
          push(m);
          break;
        case MB.MSG.ATTITUDE:
          // yaw (rad) → heading deg 0..360 if GLOBAL_POSITION_INT hasn't set it
          var yaw = (f.yaw * 180 / Math.PI); if (yaw < 0) yaw += 360;
          if (state.hdg == null) state.hdg = yaw;
          break;
        case MB.MSG.SYS_STATUS:
          state.batt = (f.battery_remaining >= 0) ? f.battery_remaining : null; // %
          push(m);
          break;
        case MB.MSG.GPS_RAW_INT:
          if (state.lat == null && f.lat) { state.lat = f.lat / 1e7; state.lon = f.lon / 1e7; }
          break;
      }
    };
    function push(m) {
      manager._emit({
        lat: state.lat, lon: state.lon, alt: state.alt, hdg: state.hdg,
        spd: state.spd, batt: state.batt, rssi: state.rssi,
        src: srcKind, ts: Date.now(),
        raw: { msg: m.name, msgid: m.msgid, fields: m.fields }
      });
    }
    return { feed: function (bytes) { parser.push(bytes); }, parser: parser };
  }

  // ---------------------------------------------------------------------
  // 1) USB / SERIAL — navigator.serial, 57600 then 115200 fallback, MAVLink.
  // ---------------------------------------------------------------------
  function connectSerial() {
    if (!CAP.serial) return Promise.reject(new Error('Web Serial unsupported — ' + BROWSER_NOTE));
    return navigator.serial.requestPort().then(function (port) {
      log('Serial port selected');
      var bauds = [57600, 115200];
      var sink = makeMavlinkSink('serial');
      var reader, keepReading = true;

      function openAt(idx) {
        if (idx >= bauds.length) return Promise.reject(new Error('no MAVLink heartbeat at 57600 or 115200'));
        var baud = bauds[idx];
        log('Opening @ ' + baud + ' baud…');
        return port.open({ baudRate: baud }).then(function () {
          // probe for a heartbeat within 2.5s; if none, fall back.
          return new Promise(function (resolve, reject) {
            var got = false;
            var origHb = manager._heartbeat.bind(manager);
            manager._heartbeat = function (p) { got = true; origHb(p); };
            reader = port.readable.getReader();
            keepReading = true;
            (function pump() {
              reader.read().then(function (r) {
                if (r.done || !keepReading) return;
                if (r.value) sink.feed(new Uint8Array(r.value));
                pump();
              }).catch(function (e) { if (keepReading) log('serial read error: ' + e.message, 'err'); });
            })();
            setTimeout(function () {
              manager._heartbeat = origHb;
              if (got) { log('Heartbeat detected @ ' + baud, 'ok'); resolve(); }
              else {
                keepReading = false;
                try { reader.releaseLock(); } catch (e) {}
                port.close().then(function () { resolve(openAt(idx + 1)); }, function () { resolve(openAt(idx + 1)); });
              }
            }, 2500);
          });
        });
      }

      return openAt(0).then(function () {
        return {
          close: function () {
            keepReading = false;
            try { if (reader) reader.cancel(); } catch (e) {}
            try { port.close(); } catch (e) {}
          }
        };
      });
    });
  }

  // ---------------------------------------------------------------------
  // 2) BLUETOOTH — navigator.bluetooth GATT → telemetry characteristics.
  //    Subscribes to notify characteristics; bytes that look like MAVLink go
  //    through the parser, otherwise we surface RSSI/heartbeat.
  // ---------------------------------------------------------------------
  function connectBLE() {
    if (!CAP.ble) return Promise.reject(new Error('Web Bluetooth unsupported — ' + BROWSER_NOTE));
    // Accept any device; request common UART/telemetry services where present.
    return navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: [
        '0000ffe0-0000-1000-8000-00805f9b34fb', // HM-10 / common BLE-UART
        '6e400001-b5a3-f393-e0a9-e50e24dcca9e'   // Nordic UART Service
      ]
    }).then(function (device) {
      log('BLE device: ' + (device.name || device.id));
      return device.gatt.connect().then(function (server) {
        log('GATT connected', 'ok');
        manager._heartbeat('BLE GATT');
        var sink = makeMavlinkSink('ble');
        // Try to find a notify characteristic on a known UART service.
        return server.getPrimaryServices().then(function (services) {
          var chain = Promise.resolve(false);
          services.forEach(function (svc) {
            chain = chain.then(function (subscribed) {
              if (subscribed) return true;
              return svc.getCharacteristics().then(function (chars) {
                var notif = chars.filter(function (c) { return c.properties.notify || c.properties.indicate; });
                if (!notif.length) return false;
                var c = notif[0];
                return c.startNotifications().then(function () {
                  c.addEventListener('characteristicvaluechanged', function (e) {
                    var dv = e.target.value;
                    var bytes = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength);
                    sink.feed(bytes); // attempt MAVLink decode
                  });
                  log('Subscribed to ' + c.uuid.slice(0, 8) + '… notifications', 'ok');
                  return true;
                });
              });
            });
          });
          return chain.then(function () {
            return { close: function () { try { device.gatt.disconnect(); } catch (e) {} } };
          });
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  // 3) WebUSB — stub bridge that emits the same telemetry shape.
  //    Opens a device + claims interface; real frame routing is wired by the
  //    ground bridge. Until a bridge protocol is finalized we keep this honest:
  //    it connects the device but drives the pipeline via the MAVLink sink so
  //    Devs 2-5 receive identical telemetry.
  // ---------------------------------------------------------------------
  function connectUSB() {
    if (!CAP.usb) return Promise.reject(new Error('WebUSB unsupported — ' + BROWSER_NOTE));
    return navigator.usb.requestDevice({ filters: [] }).then(function (device) {
      log('WebUSB device: ' + (device.productName || device.serialNumber || 'device'));
      return device.open().then(function () {
        log('WebUSB opened (bridge stub — emitting via MAVLink sink)', 'warn');
        manager._heartbeat('WebUSB bridge');
        // NOTE: vendor-specific bulk-transfer reads belong to the ground bridge.
        // This stub keeps the contract: any bytes routed here decode as MAVLink.
        var sink = makeMavlinkSink('usb');
        manager._usbSink = sink; // expose for a bridge to feed
        return { close: function () { try { device.close(); } catch (e) {} } };
      });
    });
  }

  // ---------------------------------------------------------------------
  // 4) WebSocket bridge — ground-agent SBC. Connects to a same-origin (or
  //    configured) ws endpoint and routes binary frames through the MAVLink
  //    sink; JSON frames are accepted as pre-parsed telemetry.
  // ---------------------------------------------------------------------
  function connectWS() {
    if (!CAP.ws) return Promise.reject(new Error('WebSocket unsupported'));
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = (J.KILLINCHU_BASE ? J.KILLINCHU_BASE.replace(/^http/, 'ws') : (proto + '//' + location.host)) + '/api/killinchu/v1/jackin/bridge';
    log('Connecting WebSocket bridge: ' + url);
    return new Promise(function (resolve, reject) {
      var ws;
      try { ws = new WebSocket(url); } catch (e) { return reject(e); }
      ws.binaryType = 'arraybuffer';
      var sink = makeMavlinkSink('ws');
      var settled = false;
      ws.onopen = function () { log('WS bridge open', 'ok'); manager._heartbeat('WS bridge'); settled = true; resolve({ close: function () { try { ws.close(); } catch (e) {} } }); };
      ws.onerror = function () { if (!settled) reject(new Error('WS bridge unreachable (start the ground-agent)')); };
      ws.onmessage = function (ev) {
        if (typeof ev.data === 'string') {
          try { var t = JSON.parse(ev.data); manager._heartbeat('WS JSON'); manager._emit(normalize(t, 'ws')); } catch (e) {}
        } else {
          sink.feed(new Uint8Array(ev.data));
        }
      };
      // give it 4s to open
      setTimeout(function () { if (!settled) { try { ws.close(); } catch (e) {} reject(new Error('WS bridge timeout')); } }, 4000);
    });
  }

  // ---------------------------------------------------------------------
  // 5) ADS-B / AIS — hand off to same-origin killinchu endpoints. Dev 3/5 own
  //    the data; here we just trigger the source kind + a light poller so the
  //    LIVE FEED has something, and emit telemetry-shaped records.
  // ---------------------------------------------------------------------
  // WAVE B: prefer the real Wave-A feed endpoints (/feeds/aircraft,
  // /feeds/vessels, /feeds/remoteid), falling back to the legacy
  // (/adsb, /ais/live) paths so the LIVE FEED stays real even before Wave A
  // lands. For ADS-B we also subscribe Remote-ID so the REMOTE-ID modality
  // lights LIVE when a real OpenDroneID/ASTM-F3411 broadcast is present —
  // never fabricated.
  function _feedUrls(kind, base) {
    if (kind === 'adsb') return [base + '/api/killinchu/v1/feeds/aircraft', base + '/api/killinchu/v1/adsb'];
    return [base + '/api/killinchu/v1/feeds/vessels', base + '/api/killinchu/v1/ais/live'];
  }
  function _extractArr(data) {
    if (Array.isArray(data)) return data;
    if (!data || typeof data !== 'object') return [];
    return data.tracks || data.aircraft || data.vessels ||
           (data.data && (data.data.tracks || data.data.aircraft || data.data.vessels)) || [];
  }
  // try each candidate url in order; resolve with {url, data} of first that answers JSON.
  function _firstLiveFeed(urls) {
    var i = 0;
    function attempt() {
      if (i >= urls.length) return Promise.reject(new Error('no feed endpoint answered'));
      var u = urls[i++];
      return fetch(u, { headers: { 'accept': 'application/json' } }).then(function (r) {
        var ct = r.headers.get('content-type') || '';
        if (!r.ok || ct.indexOf('text/html') >= 0) throw new Error('HTTP ' + r.status);
        return r.json().then(function (d) { return { url: u, data: d }; });
      }).catch(function () { return attempt(); });
    }
    return attempt();
  }
  function connectADSBorAIS(kind) {
    return function () {
      var base = (J.KILLINCHU_BASE || '');
      var urls = _feedUrls(kind, base);
      var ridUrl = base + '/api/killinchu/v1/feeds/remoteid';
      var feedUrl = null, timer = null, ridTimer = null, stopped = false;
      log('Subscribing ' + kind.toUpperCase() + ' feed (prefers Wave-A /feeds/*)…');
      function pumpArr(data) {
        manager._heartbeat(kind.toUpperCase() + ' feed');
        _extractArr(data).slice(0, 50).forEach(function (e) { manager._emit(normalize(e, kind)); });
      }
      function poll() {
        if (stopped || !feedUrl) return;
        fetch(feedUrl, { headers: { 'accept': 'application/json' } })
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
          .then(pumpArr)
          .catch(function (err) { log(kind.toUpperCase() + ' poll: ' + err.message, 'warn'); });
      }
      // For ADS-B, also poll Remote-ID. Each broadcast is emitted carrying a
      // RID raw key so modality_fusion lights REMOTE-ID = LIVE. If the endpoint
      // is absent we simply do nothing — never fabricate a broadcast.
      function ridPoll() {
        if (stopped) return;
        fetch(ridUrl, { headers: { 'accept': 'application/json' } })
          .then(function (r) { var ct = r.headers.get('content-type') || ''; if (!r.ok || ct.indexOf('text/html') >= 0) throw new Error('rid n/a'); return r.json(); })
          .then(function (d) {
            var bs = d.broadcasts || d.tracks || d.remoteid || (d.data && d.data.broadcasts) || [];
            (bs || []).slice(0, 50).forEach(function (b) {
              var rec = normalize(b, 'adsb');
              // tag the raw so rawHasRemoteID() detects a genuine RID broadcast
              rec.raw = rec.raw || {};
              rec.raw.OpenDroneID = b.uas_id || b.serial || b.id || true;
              rec.raw.remote_id = b.uas_id || b.serial || b.id || true;
              manager._emit(rec);
            });
            if (bs && bs.length) manager._heartbeat('Remote-ID broadcast');
          })
          .catch(function () { /* no real RID broadcast — stay DARK, never fabricate */ });
      }
      // initial probe must succeed (so connect resolves), then poll.
      return _firstLiveFeed(urls).then(function (res) {
        feedUrl = res.url;
        log(kind.toUpperCase() + ' feed live: ' + feedUrl);
        pumpArr(res.data);
        timer = setInterval(poll, 4000);
        if (kind === 'adsb') { ridPoll(); ridTimer = setInterval(ridPoll, 5000); }
        return { close: function () { stopped = true; if (timer) clearInterval(timer); if (ridTimer) clearInterval(ridTimer); } };
      }).catch(function () {
        throw new Error('feed not available — no /feeds/* or legacy endpoint answered');
      });
    };
  }

  // ---------------------------------------------------------------------
  // 6) SITL / SAMPLE — always-works source. Generates realistic-shaped
  //    telemetry by ENCODING real MAVLink v2 frames and feeding the SAME
  //    parser the radio uses, so the whole pipeline is exercised. Every emit
  //    is SAMPLE (src='sitl'); we never claim LIVE.
  // ---------------------------------------------------------------------
  function connectSITL() {
    log('Starting SITL SAMPLE source (no hardware) — clearly labeled SAMPLE', 'warn');
    var sink = makeMavlinkSink('sitl');
    // a slow circular orbit around a start point, climbing then cruising.
    var t0 = Date.now();
    var lat0 = 37.4220, lon0 = -122.0841;
    var seq = 0, batt = 96;
    manager._heartbeat('MAVLink v2 (SITL)');

    function tick() {
      var dt = (Date.now() - t0) / 1000;
      var ang = (dt * 0.18) % (2 * Math.PI);
      var R = 0.0025; // ~250m radius
      var lat = lat0 + R * Math.cos(ang);
      var lon = lon0 + R * Math.sin(ang) / Math.cos(lat0 * Math.PI / 180);
      var alt_mm = Math.round((40 + Math.min(80, dt * 2)) * 1000); // climb to ~120m
      var hdg_cdeg = Math.round((((ang * 180 / Math.PI) + 90) % 360) * 100);
      batt = Math.max(8, 96 - dt * 0.08);

      // HEARTBEAT
      sink.feed(MB.encodeV2(MB.MSG.HEARTBEAT, hbPayload(2, 3), seq++));
      // GLOBAL_POSITION_INT
      sink.feed(MB.encodeV2(MB.MSG.GLOBAL_POSITION_INT, gpiPayload(lat, lon, alt_mm, hdg_cdeg), seq++));
      // ATTITUDE (yaw matches heading)
      sink.feed(MB.encodeV2(MB.MSG.ATTITUDE, attPayload((hdg_cdeg / 100) * Math.PI / 180), seq++));
      // SYS_STATUS (battery)
      sink.feed(MB.encodeV2(MB.MSG.SYS_STATUS, sysPayload(11100, Math.round(batt)), seq++));
      // GPS_RAW_INT
      sink.feed(MB.encodeV2(MB.MSG.GPS_RAW_INT, gpsPayload(lat, lon, 3, 14), seq++));
      manager._heartbeat('MAVLink v2 (SITL)');
    }
    var timer = setInterval(tick, 500);
    tick();
    return Promise.resolve({ close: function () { clearInterval(timer); } });

    // -- sample payload builders (wire order; identical to real frames) --
    function gpiPayload(lat, lon, alt_mm, hdg_cdeg) {
      var b = new ArrayBuffer(28), dv = new DataView(b);
      dv.setUint32(0, Math.round((Date.now() - t0)), true);
      dv.setInt32(4, Math.round(lat * 1e7), true);
      dv.setInt32(8, Math.round(lon * 1e7), true);
      dv.setInt32(12, alt_mm, true); dv.setInt32(16, alt_mm - 40000, true);
      dv.setInt16(20, 600, true); dv.setInt16(22, 0, true); dv.setInt16(24, -20, true);
      dv.setUint16(26, hdg_cdeg, true);
      return new Uint8Array(b);
    }
    function attPayload(yaw) {
      var b = new ArrayBuffer(28), dv = new DataView(b);
      dv.setUint32(0, Math.round((Date.now() - t0)), true);
      dv.setFloat32(4, 0.04, true); dv.setFloat32(8, -0.03, true); dv.setFloat32(12, yaw, true);
      return new Uint8Array(b);
    }
    function sysPayload(mV, pct) {
      var b = new ArrayBuffer(31), dv = new DataView(b);
      dv.setUint16(14, mV, true); dv.setInt8(30, pct);
      return new Uint8Array(b);
    }
    function gpsPayload(lat, lon, fix, sats) {
      var b = new ArrayBuffer(30), dv = new DataView(b);
      dv.setInt32(8, Math.round(lat * 1e7), true); dv.setInt32(12, Math.round(lon * 1e7), true);
      dv.setInt32(16, 100000, true); dv.setUint8(28, fix); dv.setUint8(29, sats);
      return new Uint8Array(b);
    }
    function hbPayload(type, ap) {
      var b = new ArrayBuffer(9), dv = new DataView(b);
      dv.setUint8(4, type); dv.setUint8(5, ap); dv.setUint8(8, 3);
      return new Uint8Array(b);
    }
  }

  // ---------------------------------------------------------------------
  // Normalize an arbitrary feed entry (ADS-B/AIS/WS JSON) to contract shape.
  // ---------------------------------------------------------------------
  function normalize(e, src) {
    e = e || {};
    return {
      lat: num(e.lat != null ? e.lat : e.latitude),
      lon: num(e.lon != null ? e.lon : e.longitude),
      alt: num(e.alt != null ? e.alt : (e.altitude != null ? e.altitude : e.geom_alt)),
      hdg: num(e.hdg != null ? e.hdg : (e.heading != null ? e.heading : e.track)),
      spd: num(e.spd != null ? e.spd : (e.speed != null ? e.speed : e.gs)),
      batt: num(e.batt),
      rssi: num(e.rssi),
      src: src,
      ts: e.ts || Date.now(),
      raw: e
    };
  }
  function num(v) { var n = parseFloat(v); return isFinite(n) ? n : null; }

  // ---------------------------------------------------------------------
  // UI: build the connect-button grid + capability banner.
  // ---------------------------------------------------------------------
  function renderGrid() {
    var grid = $('jk-connect-grid');
    if (!grid) return;
    grid.innerHTML = '';
    METHODS.forEach(function (m) {
      var supported = CAP[m.kind];
      var btn = document.createElement('button');
      btn.className = 'jk-connect-card';
      btn.setAttribute('data-kind', m.kind);
      btn.type = 'button';
      if (!supported) { btn.disabled = true; }
      var capCls = m.sample ? 'sample' : (supported ? 'ok' : 'no');
      var capTxt = m.sample ? 'SAMPLE' : (supported ? 'READY' : 'N/A');
      btn.innerHTML =
        '<span class="jk-cc-cap ' + capCls + '">' + capTxt + '</span>' +
        '<span class="jk-cc-icon" aria-hidden="true">' + m.icon + '</span>' +
        '<span class="jk-cc-title">' + escapeHtml(m.title) + '</span>' +
        '<span class="jk-cc-desc">' + escapeHtml(m.desc) + '</span>' +
        (!supported && !m.sample ? '<span class="jk-cc-note">' + escapeHtml(BROWSER_NOTE) + '</span>' : '');
      btn.addEventListener('click', function () { manager.connect(m.kind).catch(function () {}); });
      grid.appendChild(btn);
    });

    // honest capability banner if hardware transports are unavailable.
    var warn = $('jk-connect-capwarn');
    if (warn) {
      if (!CAP.serial || !CAP.ble || !CAP.usb) {
        warn.hidden = false;
        warn.textContent = (!secure ? 'Not a secure (HTTPS) context — hardware connect is disabled. ' : '') + BROWSER_NOTE + ' Other paths (Network, ADS-B/AIS, SITL Sample) still work here.';
      } else { warn.hidden = true; }
    }
  }
  function markCard(kind, active) {
    document.querySelectorAll('.jk-connect-card').forEach(function (c) {
      if (c.getAttribute('data-kind') === kind) c.classList.toggle('is-active', !!active);
      else if (active) c.classList.remove('is-active');
    });
  }
  function showDisconnect(show) {
    var b = $('jk-disconnect'); if (b) b.hidden = !show;
  }

  // ---------------------------------------------------------------------
  // boot: register the source manager + wire the UI.
  // ---------------------------------------------------------------------
  function boot() {
    J.registerSource(manager);
    renderGrid();
    var dc = $('jk-disconnect');
    if (dc) dc.addEventListener('click', function () { manager.disconnect(); });
    log('Console ready. Choose a connect method above.', 'ok');
    if (!MB) log('MAVLink parser missing — serial/ble/ws decode will not work', 'err');
  }

  if (J.ready) boot();
  else J.on('ready', boot);
})();
