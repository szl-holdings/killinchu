/*
 * droneid_decode.js — Remote ID / DJI-DroneID decode panel (ADDITIVE to Dev 3's CLASSIFY tab)
 *
 * OWNER: Drone-ID dev. This file does NOT rewrite classify.js. It mounts an additive
 * container `#droneid-panel` inside Dev 3's `<section id="tab-classify">`, decodes Remote ID
 * from telemetry.raw, and EXTENDS the existing 'classification' bus event with
 *   { remoteId:{...}, droneId:{...}, encrypted:bool, deviceHash } .
 * It never clobbers Dev 3's emit — it listens to Dev 3's classification events and re-emits an
 * enriched copy tagged `_droneidEnriched:true` (and ignores its own tagged emits to avoid a loop).
 *
 * DOCTRINE (hard rules honored here):
 *   - 0 runtime CDN, self-contained. Vendored nothing; pure JS.
 *   - SAMPLE is always labeled SAMPLE; we NEVER claim a LIVE decode of synthetic data.
 *   - We NEVER claim to decrypt an encrypted link (OcuSync 4+): we show a stable per-device HASH
 *     and the honest note "encrypted link — tracked, not decoded."
 *   - Remote ID only sees COOPERATIVE / compliant platforms — a blind-spot tooltip says so.
 *   - Trust is never 100%.
 *   - Honest absence: no Remote ID fields => "No Remote ID present" (nothing fabricated).
 *
 * Standalone F3411 message-pack parser below (no library). Layout per ASTM F3411 /
 * OpenDroneID core (opendroneid-core-c). 25-byte messages; message pack type 0xF.
 */
(function () {
  'use strict';

  var J = window.JACKIN = window.JACKIN || {};
  // Minimal bus shims (only if the bus contract is somehow absent — additive, idempotent).
  if (!(J.bus instanceof EventTarget)) J.bus = new EventTarget();
  if (typeof J.on !== 'function') {
    J.on = function (t, fn) {
      if (!J.bus) return function () {};
      var w = function (e) { fn(e.detail, e); };
      J.bus.addEventListener(t, w);
      return function () { J.bus.removeEventListener(t, w); };
    };
  }
  if (typeof J.emit !== 'function') {
    J.emit = function (t, p) { J.bus.dispatchEvent(new CustomEvent(t, { detail: p })); };
  }
  if (typeof J.label !== 'function') J.label = function (live) { return live ? 'LIVE' : 'SAMPLE'; };

  /* ==========================================================================
   * STYLES — Dev 1 console.css vars w/ safe fallbacks. Injected once, own id.
   * ========================================================================*/
  (function injectStyles() {
    if (document.getElementById('jk-droneid-styles')) return;
    var css = [
      '#droneid-panel{margin-top:20px;color:var(--ink,#EAF0FB);font-family:var(--font,system-ui,sans-serif);}',
      '#droneid-panel .dz-card{background:var(--glass-strong,rgba(20,42,86,.78));border:1px solid var(--glass-border,rgba(224,122,95,.22));border-radius:var(--r-lg,16px);padding:18px;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);margin-bottom:16px;}',
      '#droneid-panel .dz-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;}',
      '#droneid-panel h2.dz-h2{font-size:14px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-mut,#A9B8D6);margin:0;}',
      '#droneid-panel h3.dz-h3{font-size:12.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-mut,#A9B8D6);margin:0 0 8px;}',
      '#droneid-panel .dz-kv{margin:0;display:grid;gap:8px;}',
      '#droneid-panel .dz-kv>div{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--hairline,rgba(190,210,255,.12));padding-bottom:6px;}',
      '#droneid-panel .dz-kv>div:last-child{border-bottom:0;padding-bottom:0;}',
      '#droneid-panel .dz-kv dt{color:var(--ink-mut,#A9B8D6);font-size:12.5px;}',
      '#droneid-panel .dz-kv dd{margin:0;font-family:var(--mono,ui-monospace,monospace);font-size:12.5px;text-align:right;color:var(--ink,#EAF0FB);word-break:break-all;}',
      '#droneid-panel .dz-pill{font-size:10px;font-weight:800;letter-spacing:.1em;padding:3px 8px;border-radius:999px;text-transform:uppercase;display:inline-block;}',
      '#droneid-panel .dz-pill.live{background:rgba(84,214,160,.16);color:var(--live,#54D6A0);border:1px solid rgba(84,214,160,.5);}',
      '#droneid-panel .dz-pill.sample{background:rgba(242,193,78,.14);color:var(--sample,#F2C14E);border:1px solid rgba(242,193,78,.5);}',
      '#droneid-panel .dz-pill.enc{background:rgba(224,108,117,.16);color:var(--danger,#E06C75);border:1px solid rgba(224,108,117,.5);}',
      '#droneid-panel .dz-pill.exp{background:rgba(126,143,179,.18);color:var(--ink-mut,#A9B8D6);border:1px solid rgba(126,143,179,.4);}',
      '#droneid-panel .dz-none{font-family:var(--mono,monospace);font-size:12.5px;color:var(--ink-fnt,#7E8FB3);background:rgba(255,255,255,.03);border:1px dashed var(--glass-border,rgba(224,122,95,.22));border-radius:var(--r-sm,8px);padding:12px 14px;}',
      '#droneid-panel .dz-grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));}',
      '#droneid-panel .dz-sub{border:1px solid var(--hairline,rgba(190,210,255,.12));border-radius:var(--r-md,12px);padding:14px;background:rgba(10,27,64,.4);}',
      '#droneid-panel .dz-note{font-size:12px;color:var(--ink-mut,#A9B8D6);margin:10px 0 0;line-height:1.5;}',
      '#droneid-panel .dz-mono{font-family:var(--mono,monospace);}',
      '#droneid-panel .dz-info{position:relative;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;border:1px solid var(--glass-border,rgba(224,122,95,.5));color:var(--ink-mut,#A9B8D6);font-size:11px;font-weight:800;cursor:help;background:transparent;font-family:var(--font,system-ui);}',
      '#droneid-panel .dz-info:focus-visible{outline:2px solid var(--coral-200,#F2A48C);outline-offset:2px;}',
      '#droneid-panel .dz-tip{position:absolute;top:140%;left:50%;transform:translateX(-50%);width:min(300px,78vw);background:var(--navy-700,#0A1B40);border:1px solid var(--glass-border,rgba(224,122,95,.5));border-radius:var(--r-md,12px);padding:12px 14px;font-size:12px;line-height:1.5;color:var(--ink,#EAF0FB);box-shadow:var(--shadow,0 10px 40px rgba(0,0,0,.45));z-index:30;text-align:left;font-weight:400;letter-spacing:normal;text-transform:none;display:none;}',
      '#droneid-panel .dz-info[aria-expanded="true"] .dz-tip,#droneid-panel .dz-info:hover .dz-tip,#droneid-panel .dz-info:focus-visible .dz-tip{display:block;}',
      '#droneid-panel .dz-tip strong{color:var(--coral-200,#F2A48C);}',
      '#droneid-panel .dz-hash{font-family:var(--mono,monospace);font-size:13px;color:var(--coral-200,#F2A48C);letter-spacing:.04em;word-break:break-all;}',
      '#droneid-panel .dz-trust{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-mut,#A9B8D6);margin-top:10px;}',
      '#droneid-panel .dz-bar{flex:1;height:6px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;}',
      '#droneid-panel .dz-bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--coral-700,#B85638),var(--coral,#E07A5F));}',
      '#droneid-panel table.dz-msgs{width:100%;border-collapse:collapse;font-family:var(--mono,monospace);font-size:11.5px;margin-top:8px;}',
      '#droneid-panel table.dz-msgs th,#droneid-panel table.dz-msgs td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--hairline,rgba(190,210,255,.12));}',
      '#droneid-panel table.dz-msgs th{color:var(--ink-fnt,#7E8FB3);font-weight:700;text-transform:uppercase;letter-spacing:.06em;}',
      '@media (max-width:480px){#droneid-panel .dz-grid{grid-template-columns:1fr;}}'
    ].join('\n');
    var s = document.createElement('style');
    s.id = 'jk-droneid-styles';
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  })();

  /* ==========================================================================
   * ASTM F3411 / OpenDroneID — minimal self-contained message-pack parser.
   *
   * Accepts a 25-byte single message OR a message-pack (type 0xF) carrying N×25-byte
   * messages, supplied as: hex string, base64 string, Array<number>, Uint8Array, or
   * ArrayBuffer. Returns a structured decode {basicId, location, system, operatorId,
   * selfId, auth, messages:[...]} with only the fields actually present. Returns null
   * if the bytes do not form a valid ODID message (we never fabricate).
   *
   * Scaling factors (ASTM F3411, standard — not in the C header but normative in the spec):
   *   lat/lon  = int32 / 1e7  degrees
   *   altitude = (uint16 * 0.5) - 1000  metres   (Baro, Geo, Height, OperatorAltitudeGeo)
   *   speedH   = mult? (raw*0.75 + 255*0.25) : (raw*0.25)  m/s
   *   speedV   = int8 * 0.5  m/s
   *   direction= EW? raw+180 : raw  degrees (0..359)
   * ========================================================================*/
  var ODID = {
    TYPE: { 0: 'Basic ID', 1: 'Location/Vector', 2: 'Authentication', 3: 'Self-ID',
            4: 'System', 5: 'Operator ID', 0xF: 'Message Pack' },
    // UA type table (ASTM F3411).
    UA_TYPE: ['None/Undeclared', 'Aeroplane/Fixed-wing', 'Helicopter/Multirotor',
      'Gyroplane', 'Hybrid Lift', 'Ornithopter', 'Glider', 'Kite', 'Free Balloon',
      'Captive Balloon', 'Airship', 'Free Fall/Parachute', 'Rocket', 'Tethered Powered Aircraft',
      'Ground Obstacle', 'Other'],
    ID_TYPE: ['None', 'Serial Number (ANSI/CTA-2063-A)', 'CAA Assigned Registration ID',
      'UTM (USS) Assigned UUID', 'Specific Session ID'],
    STATUS: ['Undeclared', 'Ground', 'Airborne', 'Emergency', 'Remote ID System Failure'],
    OP_LOC_TYPE: ['Takeoff', 'Live GNSS', 'Fixed'],
    DESC_TYPE: { 0: 'Text', 1: 'Emergency', 2: 'Extended Status' }
  };

  // --- byte coercion: hex | base64 | array | typed array | buffer -> Uint8Array | null
  function toBytes(input) {
    if (input == null) return null;
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    if (Array.isArray(input)) {
      var ok = input.every(function (n) { return typeof n === 'number' && n >= 0 && n <= 255; });
      return ok ? Uint8Array.from(input) : null;
    }
    if (typeof input === 'string') {
      var s = input.trim();
      // hex (allow whitespace/colons)
      var hx = s.replace(/[\s:]+/g, '');
      if (/^[0-9a-fA-F]+$/.test(hx) && hx.length % 2 === 0 && hx.length >= 2) {
        var out = new Uint8Array(hx.length / 2);
        for (var i = 0; i < out.length; i++) out[i] = parseInt(hx.substr(i * 2, 2), 16);
        return out;
      }
      // base64
      try {
        var bin = (typeof atob === 'function')
          ? atob(s)
          : Buffer.from(s, 'base64').toString('binary');
        var b = new Uint8Array(bin.length);
        for (var j = 0; j < bin.length; j++) b[j] = bin.charCodeAt(j);
        if (b.length >= 1) return b;
      } catch (e) { /* not base64 */ }
    }
    return null;
  }

  function i32le(b, o) {
    var v = (b[o]) | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24);
    return v | 0; // force signed 32-bit
  }
  function u16le(b, o) { return (b[o]) | (b[o + 1] << 8); }
  function u32le(b, o) {
    return ((b[o]) | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
  }
  function cstr(b, o, len) {
    var s = '';
    for (var i = 0; i < len; i++) {
      var c = b[o + i];
      if (c === 0) break;
      if (c >= 32 && c < 127) s += String.fromCharCode(c);
    }
    return s.trim();
  }
  function altDecode(raw) { // uint16 -> metres; -1000 sentinel = invalid
    var m = (raw * 0.5) - 1000;
    return raw === 0 || m <= -1000 ? null : +m.toFixed(1);
  }

  // Decode ONE 25-byte message at offset `o`. Returns {type,name,...fields}.
  function decodeMessage(b, o) {
    o = o || 0;
    if (o + 25 > b.length) return null;
    var hdr = b[o];
    var proto = hdr & 0x0F;
    var mtype = (hdr >> 4) & 0x0F;
    var m = { type: mtype, name: ODID.TYPE[mtype] || ('Unknown(' + mtype + ')'), proto: proto };

    if (mtype === 0) { // Basic ID
      var b1 = b[o + 1];
      m.uaTypeCode = b1 & 0x0F;
      m.idTypeCode = (b1 >> 4) & 0x0F;
      m.uaType = ODID.UA_TYPE[m.uaTypeCode] || ('Type ' + m.uaTypeCode);
      m.idType = ODID.ID_TYPE[m.idTypeCode] || ('ID-Type ' + m.idTypeCode);
      m.uasId = cstr(b, o + 2, 20);
    } else if (mtype === 1) { // Location/Vector
      var f1 = b[o + 1];
      var speedMult = f1 & 0x01;
      var ewDir = (f1 >> 1) & 0x01;
      m.statusCode = (f1 >> 4) & 0x0F;
      m.status = ODID.STATUS[m.statusCode] || ('Status ' + m.statusCode);
      var dir = b[o + 2];
      m.direction = (dir === 361 || dir > 360) ? null : (ewDir ? dir + 180 : dir);
      if (m.direction != null) m.direction = m.direction % 360;
      var sh = b[o + 3];
      m.speed = (sh === 255) ? null
        : (speedMult ? +(sh * 0.75 + 255 * 0.25).toFixed(2) : +(sh * 0.25).toFixed(2));
      var sv = b[o + 4] << 24 >> 24; // int8
      m.vspeed = (sv === 63) ? null : +(sv * 0.5).toFixed(2);
      var latI = i32le(b, o + 5), lonI = i32le(b, o + 9);
      m.lat = latI === 0 ? null : +(latI / 1e7).toFixed(7);
      m.lon = lonI === 0 ? null : +(lonI / 1e7).toFixed(7);
      m.altBaro = altDecode(u16le(b, o + 13));
      m.altGeo = altDecode(u16le(b, o + 15));
      m.height = altDecode(u16le(b, o + 17));
      var tsRaw = u16le(b, o + 21);
      m.timeStamp = tsRaw === 0xFFFF ? null : +((tsRaw / 10)).toFixed(1); // tenths of sec after the hour
    } else if (mtype === 4) { // System (operator location)
      var s1 = b[o + 1];
      m.opLocTypeCode = s1 & 0x03;
      m.opLocType = ODID.OP_LOC_TYPE[m.opLocTypeCode] || ('Type ' + m.opLocTypeCode);
      var oLat = i32le(b, o + 2), oLon = i32le(b, o + 6);
      m.operatorLat = oLat === 0 ? null : +(oLat / 1e7).toFixed(7);
      m.operatorLon = oLon === 0 ? null : +(oLon / 1e7).toFixed(7);
      m.areaCount = u16le(b, o + 10);
      m.areaRadius = b[o + 12] * 10; // metres (10 m steps)
      m.operatorAltGeo = altDecode(u16le(b, o + 18));
      var sysTs = u32le(b, o + 20);
      m.systemTimestamp = sysTs ? sysTs : null; // sec since 2019-01-01 UTC
    } else if (mtype === 5) { // Operator ID
      m.operatorIdTypeCode = b[o + 1];
      m.operatorId = cstr(b, o + 2, 20);
    } else if (mtype === 3) { // Self-ID
      m.descTypeCode = b[o + 1];
      m.descType = ODID.DESC_TYPE[m.descTypeCode] || ('Desc ' + m.descTypeCode);
      m.selfId = cstr(b, o + 2, 23);
    } else if (mtype === 2) { // Authentication (we surface presence, not validate)
      m.authTypeCode = b[o + 1] & 0x0F;
      m.authPagePresent = true;
    } else {
      return null; // unknown / invalid message type within a valid frame -> skip
    }
    return m;
  }

  // Top-level: bytes -> structured ODID decode, or null.
  function parseF3411(input) {
    var b = toBytes(input);
    if (!b || b.length < 25) return null;
    var msgs = [];
    var hdr0 = b[0];
    var topType = (hdr0 >> 4) & 0x0F;

    if (topType === 0xF) { // Message Pack
      var single = b[1] || 25;
      var count = b[2] || 0;
      if (single !== 25) single = 25; // we only decode standard 25-byte messages
      for (var i = 0; i < count; i++) {
        var off = 3 + i * single;
        if (off + 25 > b.length) break;
        var dm = decodeMessage(b, off);
        if (dm) msgs.push(dm);
      }
    } else {
      // One or more concatenated 25-byte messages (no pack header).
      for (var p = 0; p + 25 <= b.length; p += 25) {
        var d = decodeMessage(b, p);
        if (d) msgs.push(d);
        else if (p === 0) return null; // first message invalid => not ODID
      }
    }
    if (!msgs.length) return null;

    // Roll up into a clean per-field structure (latest of each type wins).
    var out = { messages: msgs, byteLength: b.length, framing: topType === 0xF ? 'pack' : 'concat' };
    msgs.forEach(function (m) {
      if (m.type === 0) out.basicId = m;
      else if (m.type === 1) out.location = m;
      else if (m.type === 4) out.system = m;
      else if (m.type === 5) out.operatorId = m;
      else if (m.type === 3) out.selfId = m;
      else if (m.type === 2) out.auth = m;
    });
    return out;
  }

  /* ==========================================================================
   * Tolerant pre-parsed Remote ID (already-decoded JSON shapes) so we can fuse
   * with whatever a connected beacon / Dev 3 already surfaced. Returns a
   * normalized {uasId, idType, uaType, location, operatorId, operatorLoc, selfId}
   * or null. We never invent fields not present.
   * ========================================================================*/
  function adoptPreParsed(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var r = raw.remoteId || raw.remote_id || raw.opendroneid || raw.openDroneID ||
            raw.odid || raw.ODID || null;
    var flat = (raw.uasId || raw.uas_id || raw.serial || raw.operator_id || raw.operatorId);
    if (!r && !flat) return null;
    r = r || raw;
    var loc = r.location || r.Location || null;
    var sys = r.system || r.System || null;
    var out = {
      uasId: r.uasId || r.uas_id || r.serial || r.id || null,
      idType: r.idType || r.id_type || null,
      uaType: r.uaType || r.ua_type || null,
      operatorId: r.operatorId || r.operator_id || null,
      selfId: r.selfId || r.self_id || r.description || null,
      location: loc ? {
        lat: num(loc.lat != null ? loc.lat : loc.latitude),
        lon: num(loc.lon != null ? loc.lon : loc.longitude),
        altGeo: num(loc.alt != null ? loc.alt : (loc.altGeo != null ? loc.altGeo : loc.altitude)),
        speed: num(loc.speed), direction: num(loc.direction != null ? loc.direction : loc.track),
        status: loc.status || null
      } : null,
      system: sys ? {
        operatorLat: num(sys.operatorLat != null ? sys.operatorLat : sys.lat),
        operatorLon: num(sys.operatorLon != null ? sys.operatorLon : sys.lon)
      } : (r.operatorLat != null ? { operatorLat: num(r.operatorLat), operatorLon: num(r.operatorLon) } : null)
    };
    if (!out.uasId && !out.operatorId && !out.location && !out.system) return null;
    out._preParsed = true;
    return out;
  }
  function num(v) { return (v == null || v === '' || isNaN(+v)) ? null : +v; }

  /* ==========================================================================
   * DJI DroneID frame shape (serial, model, home/operator loc, UA loc).
   * If telemetry.raw carries a dji/droneid frame, adopt it. For SAMPLE, synthesize
   * a realistic DJI-DroneID-shaped record (clearly labeled SAMPLE) so the panel is
   * demonstrable with no hardware. We do NOT decode an encrypted link (see encrypted).
   * ========================================================================*/
  function adoptDjiDroneId(raw, isLive) {
    if (raw && typeof raw === 'object') {
      var d = raw.dji || raw.djiDroneId || raw.dji_droneid || raw.droneId || raw.drone_id || null;
      if (d && typeof d === 'object' && (d.serial || d.serialNumber || d.sn)) {
        return {
          live: !!isLive,
          serial: d.serial || d.serialNumber || d.sn || null,
          model: d.model || d.productType || d.product || null,
          uaLat: num(d.uaLat != null ? d.uaLat : (d.lat != null ? d.lat : (d.droneLat))),
          uaLon: num(d.uaLon != null ? d.uaLon : (d.lon != null ? d.lon : (d.droneLon))),
          uaAlt: num(d.uaAlt != null ? d.uaAlt : d.altitude),
          homeLat: num(d.homeLat != null ? d.homeLat : d.home_lat),
          homeLon: num(d.homeLon != null ? d.homeLon : d.home_lon),
          operatorLat: num(d.operatorLat != null ? d.operatorLat : (d.pilotLat != null ? d.pilotLat : d.appLat)),
          operatorLon: num(d.operatorLon != null ? d.operatorLon : (d.pilotLon != null ? d.pilotLon : d.appLon)),
          version: d.version || d.protoVersion || null,
          source: 'adopted'
        };
      }
    }
    return null;
  }

  // Deterministic SAMPLE DJI-DroneID record derived from a track id (stable per id).
  function sampleDjiDroneId(seed) {
    var h = fnv32(String(seed || 'SITL-UAV-01'));
    var models = ['Mavic 3', 'Mavic 3 Pro', 'Air 3', 'Mini 4 Pro', 'Matrice 350 RTK', 'Avata 2'];
    var model = models[h % models.length];
    // DJI serial: 16-char alnum-ish, deterministic from hash (clearly SAMPLE).
    var serial = djiSerial(h);
    // Anchor near the SITL AOR (SoCal test range, matches bus generator default).
    var baseLat = 34.9000, baseLon = -117.8800;
    var jLat = ((h % 1000) / 1e5);          // ~ up to 0.01 deg
    var jLon = (((h >> 7) % 1000) / 1e5);
    var uaLat = +(baseLat + jLat).toFixed(7);
    var uaLon = +(baseLon - jLon).toFixed(7);
    // operator/home offset a few hundred metres from the UA.
    var opLat = +(baseLat + 0.0008).toFixed(7);
    var opLon = +(baseLon - 0.0006).toFixed(7);
    return {
      live: false, // ALWAYS SAMPLE
      serial: serial,
      model: 'DJI ' + model,
      uaLat: uaLat, uaLon: uaLon, uaAlt: 118 + (h % 40),
      homeLat: opLat, homeLon: opLon,
      operatorLat: opLat, operatorLon: opLon,
      version: 'DJI DroneID v2 (frame shape)',
      source: 'SAMPLE'
    };
  }
  function djiSerial(h) {
    var chars = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ';
    var s = '';
    var x = h >>> 0;
    for (var i = 0; i < 14; i++) { s += chars[x % chars.length]; x = (x * 1103515245 + 12345) >>> 0; }
    return s;
  }

  /* ==========================================================================
   * Encrypted-link (OcuSync 4+) honest behavior: track-without-decode.
   * We derive a STABLE per-device hash from the device id (deterministic), so the
   * same physical device shows the same hash across the session — enough to TRACK
   * it as a distinct entity. We never claim to decrypt the link.
   * Uses Web Crypto SHA-256 when available; falls back to FNV-1a (still deterministic).
   * ========================================================================*/
  function fnv32(str) {
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return h >>> 0;
  }
  function deviceHashSync(deviceId) {
    // Synchronous deterministic fallback (good enough for a stable per-device tag).
    var a = fnv32('jk:' + deviceId);
    var b = fnv32('inchu:' + deviceId + ':' + a);
    var hex = ('00000000' + a.toString(16)).slice(-8) + ('00000000' + b.toString(16)).slice(-8);
    return hex;
  }
  function deviceHashAsync(deviceId, cb) {
    try {
      if (window.crypto && window.crypto.subtle && window.TextEncoder) {
        var data = new TextEncoder().encode('killinchu:droneid:' + deviceId);
        window.crypto.subtle.digest('SHA-256', data).then(function (buf) {
          var arr = Array.prototype.map.call(new Uint8Array(buf), function (x) {
            return ('00' + x.toString(16)).slice(-2);
          });
          cb(arr.join('').slice(0, 24)); // 96-bit display tag
        }).catch(function () { cb(deviceHashSync(deviceId)); });
        return;
      }
    } catch (e) { /* fall through */ }
    cb(deviceHashSync(deviceId));
  }

  // Detect an encrypted link from telemetry / link hints (honest heuristics; no decrypt).
  function detectEncrypted(raw, track) {
    if (raw && typeof raw === 'object') {
      var lk = raw.link || raw.rf || raw.ocusync || raw.protocol || '';
      if (raw.encrypted === true) return true;
      if (typeof lk === 'string' && /ocusync\s*4|encrypted|aes/i.test(lk)) return true;
      if (raw.ocusync && (raw.ocusync.version >= 4 || /4/.test(String(raw.ocusync.version || '')))) return true;
    }
    if (track && /ocusync\s*4|encrypted/i.test(String(track.link || track.proto || ''))) return true;
    return false;
  }

  /* ==========================================================================
   * STATE + RENDER
   * ========================================================================*/
  var state = {
    track: null,           // current track (id + raw)
    lastTelemetryRaw: null,// last telemetry.raw seen (may carry RID)
    decode: null,          // last computed decode bundle
    deviceHash: null
  };

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];
      else if (k === 'class') n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function kv(k, v) {
    return el('div', null, [el('dt', { text: k }), el('dd', { text: (v == null || v === '') ? '—' : String(v) })]);
  }

  function ensureMount() {
    var root = document.getElementById('tab-classify');
    if (!root) return null;
    var panel = document.getElementById('droneid-panel');
    if (!panel) {
      panel = el('div', { id: 'droneid-panel', 'aria-label': 'Remote ID and DJI DroneID decode' });
      // append after Dev 3's content (additive — never replaces it)
      root.appendChild(panel);
    }
    return panel;
  }

  function blindSpotInfo() {
    var info = el('span', { class: 'dz-info', tabindex: '0', role: 'button',
      'aria-label': 'Remote ID blind-spot note', 'aria-expanded': 'false' }, ['i']);
    var tip = el('span', { class: 'dz-tip', role: 'tooltip' });
    tip.innerHTML = '<strong>Blind-spot honesty.</strong> Remote ID / ASTM F3411 only reveals ' +
      '<strong>cooperative, compliant</strong> platforms that choose to broadcast. ' +
      'Non-compliant, modified, or RF-silent (EMCON / fiber-tether) drones <strong>will not appear here</strong>. ' +
      'Cross-reference the other modalities (RF demod, radar, EO/IR, acoustic) in FUSION/TRACKS to close the gap. ' +
      'Encrypted links (OcuSync\u00A04+) are tracked by a per-device hash, <strong>not decoded</strong>.';
    info.appendChild(tip);
    info.addEventListener('click', function () {
      var open = info.getAttribute('aria-expanded') === 'true';
      info.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
    info.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') info.setAttribute('aria-expanded', 'false');
    });
    return info;
  }

  function render() {
    var panel = ensureMount();
    if (!panel) return;
    clear(panel);

    var d = state.decode || {};
    var isLive = d.live === true;
    var labelPill = el('span', { class: 'dz-pill ' + (isLive ? 'live' : 'sample'), text: J.label(isLive) });

    // ---- header card ----
    var head = el('div', { class: 'dz-head' }, [
      el('h2', { class: 'dz-h2', text: 'Remote ID / DroneID Decode' }),
      labelPill,
      el('span', { class: 'dz-pill exp', text: 'EXPERIMENTAL' }),
      blindSpotInfo()
    ]);

    var card = el('div', { class: 'dz-card' }, [head]);

    // ---- 1) ASTM F3411 / OpenDroneID ----
    var ridCard = el('div', { class: 'dz-sub' });
    ridCard.appendChild(el('h3', { class: 'dz-h3', text: '1 · OpenDroneID / ASTM F3411' }));
    var rid = d.remoteId;
    if (rid && (rid.basicId || rid.location || rid.system || rid.operatorId || rid.selfId || rid._preParsed)) {
      var dl = el('dl', { class: 'dz-kv' });
      if (rid.basicId) {
        dl.appendChild(kv('UAS ID', rid.basicId.uasId));
        dl.appendChild(kv('ID Type', rid.basicId.idType));
        dl.appendChild(kv('UA Type', rid.basicId.uaType));
      } else if (rid.uasId) {
        dl.appendChild(kv('UAS ID', rid.uasId));
        if (rid.idType) dl.appendChild(kv('ID Type', rid.idType));
        if (rid.uaType) dl.appendChild(kv('UA Type', rid.uaType));
      }
      var L = rid.location;
      if (L) {
        dl.appendChild(kv('Status', L.status));
        dl.appendChild(kv('Lat / Lon', (L.lat != null ? L.lat : '—') + ' , ' + (L.lon != null ? L.lon : '—')));
        if (L.altGeo != null || L.altBaro != null || L.height != null)
          dl.appendChild(kv('Alt (Geo/Baro/H)', [L.altGeo, L.altBaro, L.height].map(function (x) { return x == null ? '—' : x + 'm'; }).join(' / ')));
        if (L.speed != null) dl.appendChild(kv('Speed', L.speed + ' m/s'));
        if (L.direction != null) dl.appendChild(kv('Track', L.direction + '\u00B0'));
        if (L.vspeed != null) dl.appendChild(kv('V-Speed', L.vspeed + ' m/s'));
      }
      if (rid.operatorId) dl.appendChild(kv('Operator ID', rid.operatorId.operatorId || rid.operatorId));
      var S = rid.system;
      if (S && (S.operatorLat != null || S.operatorLon != null))
        dl.appendChild(kv('Operator Loc', (S.operatorLat != null ? S.operatorLat : '—') + ' , ' + (S.operatorLon != null ? S.operatorLon : '—')));
      if (rid.selfId) dl.appendChild(kv('Self-ID', rid.selfId.selfId || rid.selfId));
      ridCard.appendChild(dl);

      // raw message-pack breakdown (only when we did a byte-level parse)
      if (rid.messages && rid.messages.length) {
        var tbl = el('table', { class: 'dz-msgs' });
        tbl.appendChild(el('tr', null, [el('th', { text: 'TYPE' }), el('th', { text: 'DECODED' })]));
        rid.messages.forEach(function (m) {
          var summary = m.uasId || m.operatorId || m.selfId ||
            (m.lat != null ? (m.lat + ',' + m.lon) : (m.operatorLat != null ? ('op ' + m.operatorLat + ',' + m.operatorLon) : '\u2713'));
          tbl.appendChild(el('tr', null, [el('td', { text: m.name }), el('td', { text: String(summary) })]));
        });
        ridCard.appendChild(tbl);
        ridCard.appendChild(el('p', { class: 'dz-note',
          text: 'Decoded ' + rid.messages.length + ' message(s) from a ' + (rid.framing === 'pack' ? 'F3411 message pack' : 'concatenated F3411 frame') + ' (' + rid.byteLength + ' bytes) by the built-in parser.' }));
      } else if (rid._preParsed) {
        ridCard.appendChild(el('p', { class: 'dz-note', text: 'Adopted from a pre-decoded Remote ID record on telemetry.raw (no raw bytes to re-parse).' }));
      }
    } else {
      ridCard.appendChild(el('p', { class: 'dz-none', text: 'No Remote ID present. No ASTM F3411 / OpenDroneID message bytes or fields found in telemetry.raw \u2014 nothing decoded (not fabricated).' }));
    }

    // ---- 2) DJI DroneID ----
    var djiCard = el('div', { class: 'dz-sub' });
    djiCard.appendChild(el('h3', { class: 'dz-h3', text: '2 · DJI DroneID' }));
    var dji = d.droneId;
    if (dji) {
      var ddl = el('dl', { class: 'dz-kv' });
      ddl.appendChild(kv('Make / Model', dji.model || 'DJI (unknown model)'));
      ddl.appendChild(kv('Serial', dji.serial));
      if (dji.uaLat != null) ddl.appendChild(kv('UA Loc', dji.uaLat + ' , ' + dji.uaLon + (dji.uaAlt != null ? '  @' + dji.uaAlt + 'm' : '')));
      if (dji.operatorLat != null) ddl.appendChild(kv('Operator Loc', dji.operatorLat + ' , ' + dji.operatorLon));
      if (dji.homeLat != null) ddl.appendChild(kv('Home Loc', dji.homeLat + ' , ' + dji.homeLon));
      if (dji.version) ddl.appendChild(kv('Frame', dji.version));
      djiCard.appendChild(ddl);
      djiCard.appendChild(el('p', { class: 'dz-note',
        text: dji.live
          ? 'Decoded from an adopted DJI-DroneID frame on telemetry.raw.'
          : 'SAMPLE DJI-DroneID-shaped record (deterministic from the track id). No DJI link was actually demodulated \u2014 labeled SAMPLE, never LIVE.' }));
    } else {
      djiCard.appendChild(el('p', { class: 'dz-none', text: 'No DJI-DroneID frame present in telemetry.raw.' }));
    }

    // ---- 3) Encrypted link (OcuSync 4+) ----
    var encCard = el('div', { class: 'dz-sub' });
    encCard.appendChild(el('h3', { class: 'dz-h3', text: '3 · Encrypted Link (OcuSync 4+)' }));
    if (d.encrypted) {
      encCard.appendChild(el('span', { class: 'dz-pill enc', text: 'ENCRYPTED \u2014 NOT DECODED' }));
      encCard.appendChild(el('div', { class: 'dz-hash', style: 'margin-top:10px;', text: d.deviceHash || state.deviceHash || '\u2026' }));
      encCard.appendChild(el('p', { class: 'dz-note',
        text: 'Encrypted link \u2014 tracked, not decoded. The link payload (make/model/serial/operator location) is not recoverable. We derive a stable per-device hash so this airframe can still be tracked as a distinct entity across the session. We do NOT claim to decrypt OcuSync 4+.' }));
    } else {
      encCard.appendChild(el('p', { class: 'dz-none', text: 'No encrypted link detected on this track. If an OcuSync\u00A04+ (encrypted) link were seen, this panel would show a per-device tracking hash \u2014 never a fabricated decode.' }));
    }

    // ---- trust line (never 100%) ----
    var trustPct = computeTrust(d);
    var trust = el('div', { class: 'dz-trust' }, [
      el('span', { text: 'Decode trust' }),
      el('span', { class: 'dz-bar' }, [el('i', { style: 'width:' + trustPct + '%;' })]),
      el('span', { class: 'dz-mono', text: trustPct + '%' })
    ]);

    var grid = el('div', { class: 'dz-grid' }, [ridCard, djiCard, encCard]);
    card.appendChild(grid);
    card.appendChild(trust);
    card.appendChild(el('p', { class: 'dz-note',
      html: 'Remote ID is one cooperative modality. <strong>Trust is never 100%.</strong> ' +
        'See the blind-spot note (\u24D8) and cross-reference FUSION/TRACKS for non-cooperative airframes.' }));
    panel.appendChild(card);
  }

  // Trust heuristic — bounded, never reaches 100%. SAMPLE caps lower than a real decode.
  function computeTrust(d) {
    var t = 0;
    if (d.remoteId) {
      if (d.remoteId.basicId || d.remoteId.uasId) t += 30;
      if (d.remoteId.location) t += 20;
      if (d.remoteId.system || d.remoteId.operatorId) t += 15;
    }
    if (d.droneId) t += d.droneId.live ? 20 : 10;
    if (d.encrypted) t = Math.max(t, 25); // we can track but not decode
    if (!d.live) t = Math.min(t, 60);     // SAMPLE never reads as a confident LIVE decode
    return Math.max(5, Math.min(92, t));  // hard ceiling < 100
  }

  /* ==========================================================================
   * DECODE PIPELINE — recompute the bundle from current track + telemetry.raw.
   * ========================================================================*/
  function recompute() {
    var t = state.track || {};
    var raw = state.lastTelemetryRaw || (t && t.raw) || null;
    var id = t.id || t.trackId || 'unidentified-device';
    var isLive = sourceIsLive();

    // 1) F3411: try byte-level parse first (raw.remoteIdBytes / raw.odidBytes / raw.rid_raw / hex/b64),
    //    then adopt a pre-parsed JSON shape.
    var remoteId = null;
    if (raw && typeof raw === 'object') {
      var bytesField = raw.remoteIdBytes || raw.odidBytes || raw.rid_raw || raw.ridRaw ||
                       raw.opendroneid_bytes || raw.f3411 || null;
      if (bytesField) remoteId = parseF3411(bytesField);
      if (!remoteId) remoteId = adoptPreParsed(raw);
    } else if (typeof raw === 'string') {
      remoteId = parseF3411(raw);
    }

    // 2) DJI DroneID: adopt a real frame if present; else SAMPLE only when source is not LIVE
    //    AND no real Remote ID is present (so a real cooperative beacon isn't masked by a fake DJI).
    var droneId = adoptDjiDroneId(raw, isLive);
    if (!droneId && !isLive && !remoteId) {
      droneId = sampleDjiDroneId(id);
    }

    // 3) Encrypted link
    var encrypted = detectEncrypted(raw, t);
    // For the SAMPLE demo, if there is neither RID nor DJI nor anything, surface the encrypted
    // track-without-decode behavior on a SAMPLE link so the honest 2026 behavior is demonstrable.
    if (!encrypted && !isLive && !remoteId && !droneId) encrypted = true;

    var bundle = {
      live: isLive,
      remoteId: remoteId,
      droneId: droneId,
      encrypted: !!encrypted,
      deviceHash: state.deviceHash || deviceHashSync(id),
      deviceId: id
    };
    state.decode = bundle;

    // async upgrade the hash to SHA-256 if available, then re-render + re-emit
    deviceHashAsync(id, function (h) {
      state.deviceHash = h;
      if (state.decode) state.decode.deviceHash = h;
      render();
      emitEnriched();
    });

    render();
    emitEnriched();
  }

  function sourceIsLive() {
    try {
      var st = (J.source && typeof J.source.status === 'function') ? J.source.status() : null;
      if (st && typeof st.live === 'boolean') return st.live;
      // SITL/sample always non-live; telemetry src carries provenance.
      var src = state.lastTelemetryRaw && state.lastTelemetryRaw.src;
      var tsrc = state.track && state.track.src;
      if (/live/i.test(String(src || tsrc || ''))) return true;
    } catch (e) {}
    return false;
  }

  /* ==========================================================================
   * EVENT EXTENSION — extend Dev 3's 'classification' WITHOUT breaking it.
   * We listen to Dev 3's emits, attach our decode fields, and re-emit a copy tagged
   * `_droneidEnriched:true`. We ignore our own tagged events to prevent a loop. Dev 3
   * de-dupes on [trackId,class,conf,spoof] so our enriched copy (same key) is dropped by
   * Dev 3's own cache — but Dev 4 / Dev 2 still receive the enriched payload from the bus.
   * If no classification has been seen yet (decode-only), we emit a standalone enriched
   * event so the contract fields are still available downstream.
   * ========================================================================*/
  var lastClassFromDev3 = null;

  function buildEnrichment() {
    var d = state.decode || {};
    var rid = d.remoteId;
    // Compact remoteId for the bus (avoid shipping the whole message array).
    var ridOut = null;
    if (rid) {
      ridOut = {
        uasId: (rid.basicId && rid.basicId.uasId) || rid.uasId || null,
        idType: (rid.basicId && rid.basicId.idType) || rid.idType || null,
        uaType: (rid.basicId && rid.basicId.uaType) || rid.uaType || null,
        operatorId: (rid.operatorId && (rid.operatorId.operatorId || rid.operatorId)) || null,
        location: rid.location ? {
          lat: rid.location.lat, lon: rid.location.lon,
          alt: rid.location.altGeo != null ? rid.location.altGeo : rid.location.alt,
          speed: rid.location.speed, track: rid.location.direction, status: rid.location.status
        } : null,
        operatorLoc: rid.system ? { lat: rid.system.operatorLat, lon: rid.system.operatorLon } : null,
        selfId: (rid.selfId && (rid.selfId.selfId || rid.selfId)) || null,
        messageCount: rid.messages ? rid.messages.length : null
      };
    }
    var djiOut = null;
    if (d.droneId) {
      djiOut = {
        live: d.droneId.live, serial: d.droneId.serial, model: d.droneId.model,
        uaLoc: (d.droneId.uaLat != null) ? { lat: d.droneId.uaLat, lon: d.droneId.uaLon, alt: d.droneId.uaAlt } : null,
        operatorLoc: (d.droneId.operatorLat != null) ? { lat: d.droneId.operatorLat, lon: d.droneId.operatorLon } : null
      };
    }
    return {
      remoteId: ridOut,
      droneId: djiOut,
      encrypted: !!d.encrypted,
      deviceHash: d.deviceHash || state.deviceHash || null
    };
  }

  function emitEnriched() {
    var d = state.decode; if (!d) return;
    var enrich = buildEnrichment();
    var base = lastClassFromDev3;
    var payload;
    if (base) {
      // clone Dev 3's last classification for THIS track + attach our fields
      payload = {};
      Object.keys(base).forEach(function (k) { payload[k] = base[k]; });
      payload.remoteId = enrich.remoteId || base.remoteId || null;
      payload.droneId = enrich.droneId;
      payload.encrypted = enrich.encrypted;
      payload.deviceHash = enrich.deviceHash;
      payload._droneidEnriched = true;
      payload.ts = Date.now();
    } else {
      // decode-only: a standalone classification carrying just the decode (honest defaults)
      payload = {
        trackId: d.deviceId, id: d.deviceId,
        class: 'unknown', classification: 'unknown',
        conf: d.encrypted ? 0.25 : (d.remoteId ? 0.55 : 0.3),
        spoof: null,
        remoteId: enrich.remoteId, droneId: enrich.droneId,
        encrypted: enrich.encrypted, deviceHash: enrich.deviceHash,
        operatorOverride: false,
        _droneidEnriched: true, _droneidStandalone: true,
        ts: Date.now()
      };
    }
    var sig = JSON.stringify([payload.trackId, payload.encrypted, payload.deviceHash,
      enrich.remoteId && enrich.remoteId.uasId, enrich.droneId && enrich.droneId.serial,
      payload.class, payload.conf]);
    if (state._lastEmitSig === sig) return;
    state._lastEmitSig = sig;
    J.emit('classification', payload);
  }

  /* ==========================================================================
   * BUS SUBSCRIPTIONS
   * ========================================================================*/
  J.on('classification', function (p) {
    if (!p || typeof p !== 'object') return;
    if (p._droneidEnriched) return; // ignore our own enriched emits (no loop)
    lastClassFromDev3 = p;
    // adopt the classified track id so our hash/decode key matches Dev 3's
    var id = p.trackId || p.id;
    if (id && (!state.track || (state.track.id || state.track.trackId) !== id)) {
      state.track = state.track && (state.track.id === id || state.track.trackId === id)
        ? state.track : { id: id, raw: state.lastTelemetryRaw };
      state.deviceHash = null; // recompute hash for the new device
    }
    recompute();
  });

  J.on('telemetry', function (t) {
    if (!t || typeof t !== 'object') return;
    state.lastTelemetryRaw = t.raw || t;
    if (state.track && !state.track.raw) state.track.raw = state.lastTelemetryRaw;
    // throttle: recompute at most ~2 Hz
    var now = Date.now();
    if (!state._lastTele || now - state._lastTele > 500) {
      state._lastTele = now;
      recompute();
    }
  });

  J.on('track', function (p) {
    var t = Array.isArray(p) ? p[0] : p;
    if (!t || typeof t !== 'object') return;
    var id = t.id || t.trackId;
    if (!state.track) {
      state.track = t;
      state.deviceHash = null;
      recompute();
    } else if (id && (state.track.id || state.track.trackId) === id) {
      // keep raw fresh
      if (t.raw) state.track.raw = t.raw;
    }
  });

  J.on('track-selected', function (p) {
    var t = p && (p.track || (p.id ? { id: p.id } : p));
    if (!t) return;
    state.track = t.raw ? t : { id: t.id || t.trackId, raw: state.lastTelemetryRaw };
    state.deviceHash = null;
    recompute();
  });

  // Initial paint (honest empty state until data arrives).
  function init() {
    if (!document.getElementById('tab-classify')) return;
    state.decode = { live: false, remoteId: null, droneId: null, encrypted: false,
      deviceHash: null, deviceId: 'awaiting-source' };
    render();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose the pure parser + helpers for QA / other devs (no side effects).
  window.JACKIN_DRONEID = {
    parseF3411: parseF3411,
    toBytes: toBytes,
    decodeMessage: decodeMessage,
    sampleDjiDroneId: sampleDjiDroneId,
    deviceHashSync: deviceHashSync,
    detectEncrypted: detectEncrypted,
    ODID: ODID,
    _state: state
  };
})();
