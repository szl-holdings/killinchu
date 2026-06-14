/* ============================================================================
 * killinchu JACK-IN console — 5-MODALITY SENSOR-FUSION PICTURE
 * NEW FILE owned by the modality-fusion dev. Additive only — does NOT modify
 * tracks.js (DEV 2). It mounts a sub-panel INSIDE the FUSION / TRACKS tab.
 *
 * THE 2026 COUNTER-UAS CREDIBILITY BAR: no single sensor sees everything.
 * Every modality has a blind spot, so serious C2 fuses five of them:
 *   [RF] [RADAR] [EO/IR] [ACOUSTIC] [REMOTE-ID]
 * Cross-verification narrative:
 *   radar blip + acoustic motor signature -> slew EO/IR -> visual confirm;
 *   RF demod -> make/model/operator-location.
 *
 * HONESTY DOCTRINE (the differentiator — we NAME the limits):
 *   - REMOTE-ID is REAL where we have a feed (a connected BLE Remote-ID beacon
 *     carrying OpenDroneID / ASTM F3411, or ADS-B / AIS cooperative broadcast).
 *   - RF / RADAR / EO-IR / ACOUSTIC are hardware we do NOT physically have at
 *     the demo. They render as SAMPLE — clearly labeled, plausibly shaped,
 *     NEVER claimed as live hardware.
 *   - Fused confidence: single-source = LOW confidence. Trust is never 100%.
 *   - Effector is SIMULATED elsewhere (ENGAGE tab), not here.
 *
 * BUS (per BUILD_CONTRACT / DEV 2 RESULT_DEV2):
 *   window.JACKIN.on('track', fn)            // a TRACK or array of TRACKs
 *   window.JACKIN.on('track-selected', fn)   // {id, track}  (DEV 2 emits)
 *   window.JACKIN.on('classification', fn)   // {id, classification, conf}
 *   window.JACKIN.on('telemetry', fn)        // {..., raw}  (for Remote-ID detect)
 *   window.JACKIN.source.status()            // {connected, kind, live}
 *   window.JACKIN.label(isLive) -> 'LIVE'|'SAMPLE'
 *
 * MOUNT HOOK: tracks.js (DEV 2) renders `.tk-wrap` into #tab-fusion but exposes
 * NO documented append hook. So — without touching tracks.js — we add our OWN
 * container element id `modality-fusion-panel` inside the fusion tab (appended
 * after `.tk-wrap`, or directly into the tab as a fallback) and render into it.
 * A MutationObserver waits for the tab/`.tk-wrap` so we never race DEV 2.
 *
 * 0 runtime CDN. WCAG-AA. responsive mobile/tablet/desktop. reduced-motion ok.
 * ==========================================================================*/
(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // SHARED COSIGN/DSSE RECEIPT MODULE (window.SZLReceipts)
  // The jack-in shell (index.html) does NOT load the shared receipt module, so
  // we load it ourselves — ADDITIVELY, same-origin, 0 CDN — for the headline
  // "fuse → cosign DSSE receipt" drop. We NEVER edit the shared index.html or
  // the shared module bytes. If it fails to load, the receipt drop renders an
  // honest UNSIGNED fallback (never a faked signature).
  // -------------------------------------------------------------------------
  function ensureReceipts() {
    if (window.SZLReceipts) return;
    if (document.getElementById('jk-szl-receipts')) return;
    try {
      var s = document.createElement('script');
      s.id = 'jk-szl-receipts';
      s.src = '/shared/szl_receipt_cosign.js';   // same-origin, served 200 (verified)
      s.async = true;
      s.onerror = function () { /* honest: receipt drop shows UNSIGNED fallback */ };
      (document.head || document.documentElement).appendChild(s);
    } catch (_) {}
  }
  ensureReceipts();

  // -------------------------------------------------------------------------
  // defensive bus access (mirrors DEV 2's posture; never throws)
  // -------------------------------------------------------------------------
  function on(type, fn) {
    if (window.JACKIN && typeof window.JACKIN.on === 'function') { window.JACKIN.on(type, fn); return true; }
    var b = window.JACKIN && window.JACKIN.bus;
    if (b && typeof b.addEventListener === 'function') { b.addEventListener(type, function (e) { fn(e.detail); }); return true; }
    return false;
  }
  function sourceStatus() {
    try { if (window.JACKIN && window.JACKIN.source && window.JACKIN.source.status) return window.JACKIN.source.status() || {}; } catch (_) {}
    return {};
  }
  function labelFor(isLive) {
    if (window.JACKIN && typeof window.JACKIN.label === 'function') { try { return window.JACKIN.label(isLive); } catch (_) {} }
    return isLive ? 'LIVE' : 'SAMPLE';
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }

  var prefersReduced = false;
  try { prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) {}

  // -------------------------------------------------------------------------
  // MODALITY MODEL
  // status per modality, per track:
  //   'live'        -> we actually have this feed for this track   (Remote ID family only)
  //   'sample'      -> hardware we don't have at the demo; plausibly shaped, labeled SAMPLE
  //   'blind'       -> this modality structurally CANNOT see this track (its blind spot)
  // -------------------------------------------------------------------------
  var MODALITIES = [
    { key: 'rf',     label: 'RF',        full: 'RF Analysis',
      desc: 'Control-link / telemetry demod → make·model·serial, TDOA/AoA → operator location.',
      blind: 'Blind to autonomous / EMCON drones with the datalink severed, and to fiber-tether drones (zero RF).' },
    { key: 'radar',  label: 'RADAR',     full: 'Radar (AESA)',
      desc: 'Wide-area early warning; range & velocity from skin return.',
      blind: 'Cannot classify what it sees; struggles in ground / sea clutter and against small/slow targets.' },
    { key: 'eoir',   label: 'EO/IR',     full: 'EO / IR',
      desc: 'The eyes — electro-optical & thermal visual confirmation.',
      blind: 'Range-limited and line-of-sight; night / smoke needs the IR channel.' },
    { key: 'acoustic', label: 'ACOUSTIC', full: 'Acoustic',
      desc: 'Motor / prop signature; near-field — catches RF-silent platforms.',
      blind: 'Short range and easily masked by ambient / wind noise.' },
    { key: 'remoteid', label: 'REMOTE-ID', full: 'Remote ID',
      desc: 'ASTM F3411 / OpenDroneID broadcast + ADS-B / AIS cooperative reporting.',
      blind: 'Sees only COOPERATIVE / compliant platforms — non-broadcasting threats are invisible to it.' },
  ];

  // Which modalities are REAL (a feed we can actually have) vs SAMPLE-only hardware.
  // Per doctrine: only the Remote-ID family is feed-backed at the demo.
  var REAL_CAPABLE = { remoteid: true };

  // -------------------------------------------------------------------------
  // Remote-ID DETECTION — honest: only lights LIVE when a real cooperative
  // signal exists for this track.
  //  - source kind 'ble'  → a connected BLE Remote ID beacon
  //  - source kind 'adsb' → ADS-B cooperative broadcast (aircraft)
  //  - source kind 'ais'  → AIS cooperative broadcast (vessel)
  //  - telemetry .raw carrying OpenDroneID / ASTM F3411 frame fields
  // -------------------------------------------------------------------------
  var RID_RAW_KEYS = [
    'OpenDroneID', 'open_drone_id', 'opendroneid',
    'F3411', 'astm_f3411', 'ASTM_F3411',
    'OPEN_DRONE_ID_LOCATION', 'OPEN_DRONE_ID_BASIC_ID',
    'remote_id', 'remoteId', 'RemoteID', 'rid',
    'DroneID', 'drone_id', 'dji_droneid'
  ];
  function rawHasRemoteID(raw) {
    if (!raw || typeof raw !== 'object') return false;
    for (var i = 0; i < RID_RAW_KEYS.length; i++) {
      if (raw[RID_RAW_KEYS[i]] != null) return true;
    }
    return false;
  }
  // last-seen Remote-ID evidence per track id (from telemetry raw, time-boxed)
  var ridEvidence = Object.create(null);  // id -> ts

  // -------------------------------------------------------------------------
  // store of the tracks we know about (mirrors what DEV 2 ingests, independently)
  // -------------------------------------------------------------------------
  var tracks = Object.create(null);     // id -> {id, platform_type, src, mergedFrom[], classification, conf, live, ts}
  var selectedId = null;
  var el = {};
  var state = { mounted: false, dirty: true, timer: 0 };

  function platformFromSrc(src) {
    if (src === 'adsb') return 'airplane';
    if (src === 'ais') return 'vessel';
    if (src === 'serial' || src === 'ble' || src === 'usb' || src === 'sitl') return 'drone';
    return 'unknown';
  }

  function ingestTrack(input) {
    if (!input || typeof input !== 'object') return;
    var src = input.src || 'unknown';
    var id = input.id || (src + ':self');
    var prev = tracks[id] || {};
    tracks[String(id)] = {
      id: String(id),
      platform_type: input.platform_type || prev.platform_type || platformFromSrc(src),
      src: src,
      mergedFrom: input.mergedFrom || prev.mergedFrom || null,
      callsign: input.callsign || input.name || prev.callsign || null,
      classification: input.classification || prev.classification || 'unevaluated',
      conf: isFinite(input.conf) ? input.conf : (prev.conf != null ? prev.conf : null),
      live: input.live === true || sourceStatus().live === true || prev.live === true,
      ts: input.ts || Date.now()
    };
    state.dirty = true;
  }

  // -------------------------------------------------------------------------
  // PER-TRACK MODALITY EVALUATION (honest + plausibly shaped)
  // Returns { rf:{status,sample}, radar:{...}, ... } where status ∈ live|sample|blind.
  // SAMPLE values are deterministic from the track id so they're stable, not random.
  // -------------------------------------------------------------------------
  function hash01(str) {
    var h = 2166136261;
    str = String(str);
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    // map to 0..1
    return ((h >>> 0) % 100000) / 100000;
  }

  function evalModalities(t) {
    var sources = [t.src].concat(t.mergedFrom || []);  // every contributing sensor kind
    function has(kind) { return sources.indexOf(kind) >= 0; }
    var r = hash01(t.id);
    var r2 = hash01(t.id + ':2');
    var r3 = hash01(t.id + ':3');

    var out = {};

    // ----- REMOTE-ID (REAL where we have a feed) -----
    var ridLive =
      has('ble') ||                                  // BLE Remote-ID beacon
      has('adsb') ||                                 // ADS-B cooperative
      has('ais') ||                                  // AIS cooperative
      (ridEvidence[t.id] && (Date.now() - ridEvidence[t.id]) < 20000);
    if (ridLive) {
      var ridKind = has('adsb') ? 'ADS-B squitter' :
                    has('ais') ? 'AIS position report' :
                    'OpenDroneID / ASTM F3411 broadcast';
      out.remoteid = {
        status: 'live',
        sample: false,
        value: ridKind,
        detail: has('ble') ? 'serial + operator-loc + UA type decoded from beacon' :
                has('adsb') ? 'ICAO 24-bit + callsign + alt/velocity' :
                has('ais') ? 'MMSI + nav-status + COG/SOG' : 'cooperative broadcast received'
      };
    } else {
      // honest: a non-cooperative platform is INVISIBLE to Remote ID
      out.remoteid = {
        status: 'blind', sample: false,
        value: 'no cooperative broadcast',
        detail: 'platform is not transmitting Remote ID — structurally invisible to this modality'
      };
    }

    // ----- RF analysis (SAMPLE hardware) -----
    // Blind to fiber-tether (zero RF) and to severed-datalink EMCON. We mark a
    // minority of tracks RF-blind to demonstrate the limitation honestly.
    var rfBlind = (r < 0.18);  // ~ a fiber-tether / EMCON case, deterministic
    if (rfBlind) {
      out.rf = { status: 'blind', sample: true,
        value: 'no RF emission', detail: 'fiber-tether or datalink-severed (EMCON) — RF cannot see it' };
    } else {
      out.rf = { status: 'sample', sample: true,
        value: pickRF(r, t), detail: 'demod → make/model + TDOA/AoA operator fix (SAMPLE — no SDR at demo)' };
    }

    // ----- RADAR (SAMPLE hardware) -----
    // Detects skin return but CANNOT classify. Small/slow targets in clutter
    // may be missed — mark a few as blind.
    var radarBlind = (r2 < 0.12 && t.platform_type === 'drone');
    if (radarBlind) {
      out.radar = { status: 'blind', sample: true,
        value: 'lost in clutter', detail: 'small/slow target below clutter threshold — radar drops it' };
    } else {
      out.radar = { status: 'sample', sample: true,
        value: 'blip · ' + (20 + Math.round(r2 * 40)) + ' m/s · ' + (1 + Math.round(r2 * 8)) + ' km',
        detail: 'range + velocity only — cannot classify (SAMPLE — no AESA at demo)' };
    }

    // ----- EO/IR (SAMPLE hardware) -----
    // Range-limited; needs a cue to slew. We say "slewed/confirmed" once radar
    // or acoustic has cued it; otherwise it is not yet on target.
    var eoirBlind = (r3 > 0.78);  // beyond optical range / no LOS
    if (eoirBlind) {
      out.eoir = { status: 'blind', sample: true,
        value: 'beyond optical range', detail: 'out of EO/IR range or no line-of-sight (night needs IR)' };
    } else {
      out.eoir = { status: 'sample', sample: true,
        value: r3 < 0.45 ? 'visual confirm' : 'IR signature',
        detail: 'slewed on radar/acoustic cue → visual/thermal confirm (SAMPLE — no gimbal at demo)' };
    }

    // ----- ACOUSTIC (SAMPLE hardware) -----
    // Near-field motor signature; catches RF-silent platforms but short range.
    var acBlind = (r > 0.62) || t.platform_type === 'airplane' || t.platform_type === 'vessel';
    if (acBlind) {
      out.acoustic = { status: 'blind', sample: true,
        value: 'out of acoustic range', detail: 'beyond near-field or masked by ambient noise' };
    } else {
      out.acoustic = { status: 'sample', sample: true,
        value: 'multirotor motor signature', detail: 'prop/motor harmonics — catches RF-silent UAS (SAMPLE — no array at demo)' };
    }

    return out;
  }

  function pickRF(r, t) {
    // plausibly-shaped SAMPLE make/model (clearly SAMPLE; never real serials)
    var models = ['DJI Mavic 3 (OcuSync 4)', 'DJI Air 3 (OcuSync 4)', 'Autel EVO II', 'DIY OcuSync 2', 'Generic 2.4 GHz FHSS'];
    var m = models[Math.floor(r * models.length) % models.length];
    var enc = r > 0.6;
    return m + (enc ? ' · encrypted → per-device hash' : ' · serial decoded');
  }

  // Fused confidence model (HONEST):
  //   - REAL corroboration is driven by LIVE modalities only — a SAMPLE modality
  //     is a demonstration of what the hardware WOULD add, NOT real corroboration.
  //     We never let SAMPLE inflate real confidence.
  //   - We also surface how many modalities would contribute with full hardware
  //     (live + sample) as a separate, clearly-labeled "potential" figure.
  function corroboration(modes) {
    var live = 0, sample = 0, blind = 0;
    MODALITIES.forEach(function (m) {
      var s = modes[m.key];
      if (!s) return;
      if (s.status === 'live') live++;
      else if (s.status === 'sample') sample++;
      else blind++;
    });
    return { live: live, sample: sample, blind: blind, potential: live + sample };
  }

  // -------------------------------------------------------------------------
  // BFT QUORUM OVER 5 SENSORS (honest, Conjecture 2 OPEN).
  // Treat each modality as an independent witness voting on "this track is real".
  //   - a LIVE modality is a TRUSTED witness (real feed) — it votes
  //   - a SAMPLE modality is a DEMO witness — it abstains from the REAL quorum
  //     (shown separately; never inflates the real tally)
  //   - a BLIND modality cannot witness this track — it abstains
  // Classic BFT safety needs n > 3t (tolerate t Byzantine). With n=5 trusted
  // witnesses the byzantine-tolerant quorum threshold is ceil((n+ (n>3?1:0))/?)
  // — we use the standard 2f+1 majority over the witnessing set and report the
  // Byzantine fault tolerance f = floor((w-1)/3) HONESTLY. The unconditional
  // Khipu BFT safety theorem is Conjecture 2 (OPEN); what is proved is the
  // CONDITIONAL agreement-under-non-equivocation result. We NEVER claim BFT-safe.
  // -------------------------------------------------------------------------
  function quorum(modes) {
    var witnesses = [];   // LIVE = trusted voters
    var demo = [];        // SAMPLE = demo voters (separate)
    var abstain = [];     // BLIND = cannot witness
    MODALITIES.forEach(function (m) {
      var s = modes[m.key]; if (!s) { abstain.push(m); return; }
      if (s.status === 'live') witnesses.push(m);
      else if (s.status === 'sample') demo.push(m);
      else abstain.push(m);
    });
    var w = witnesses.length;                 // trusted witnessing set size
    // 2f+1 majority over the witnessing set; quorum needs > 2/3 to be BFT-shaped
    var need = w > 0 ? Math.floor(2 * w / 3) + 1 : 0;   // 2f+1
    var ftol = w > 0 ? Math.floor((w - 1) / 3) : 0;      // Byzantine f tolerated
    var have = w;                              // every trusted witness present votes "real"
    var reached = w > 0 && have >= need;
    // demo witnesses, if hardware were present, would lift the set toward 5
    var potentialW = w + demo.length;
    var potentialNeed = potentialW > 0 ? Math.floor(2 * potentialW / 3) + 1 : 0;
    var potentialFtol = potentialW > 0 ? Math.floor((potentialW - 1) / 3) : 0;
    return {
      witnesses: witnesses, demo: demo, abstain: abstain,
      w: w, have: have, need: need, ftol: ftol, reached: reached,
      potentialW: potentialW, potentialNeed: potentialNeed, potentialFtol: potentialFtol
    };
  }

  // -------------------------------------------------------------------------
  // STYLES (consumes console.css vars with safe fallbacks)
  // -------------------------------------------------------------------------
  function injectStyles() {
    if (document.getElementById('jk-modality-style')) return;
    var css = `
    #modality-fusion-panel{
      --mf-navy:var(--navy-800,#06122E);--mf-coral:var(--coral,#E07A5F);
      --mf-ink:var(--ink,#EAF0FB);--mf-mut:var(--ink-mut,#A9B8D6);--mf-fnt:var(--ink-fnt,#7E8FB3);
      --mf-glass:var(--glass,rgba(18,38,78,.55));--mf-glass2:var(--glass-strong,rgba(20,42,86,.78));
      --mf-stroke:var(--hairline,rgba(190,210,255,.12));--mf-edge:var(--glass-border,rgba(224,122,95,.22));
      --mf-live:var(--live,#54D6A0);--mf-sample:var(--sample,#F2C14E);--mf-bad:var(--danger,#E06C75);
      --mf-r:var(--r-lg,16px);--mf-rm:var(--r-md,12px);--mf-rs:var(--r-sm,8px);
      --mf-mono:var(--mono,ui-monospace,Menlo,Consolas,monospace);
      display:block;margin-top:18px;color:var(--mf-ink);
      font-family:var(--font,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif);}
    #modality-fusion-panel *{box-sizing:border-box;}
    .mf-card{background:var(--mf-glass);border:1px solid var(--mf-stroke);border-radius:var(--mf-r);
      backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:16px 18px;margin-bottom:16px;}
    .mf-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px;}
    .mf-h{margin:0;font-size:.82rem;letter-spacing:.1em;text-transform:uppercase;color:var(--mf-mut);font-weight:800;}
    .mf-sub{color:var(--mf-mut);font-size:.78rem;margin:0;}
    .mf-tip{color:var(--mf-fnt);font-size:.74rem;}

    /* selected-track header */
    .mf-trackline{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:6px 0 12px;}
    .mf-trackid{font-weight:800;font-size:1rem;font-variant-numeric:tabular-nums;}
    .mf-chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;
      font-size:.7rem;font-weight:800;letter-spacing:.06em;border:1px solid var(--mf-stroke);background:rgba(255,255,255,.04);}
    .mf-chip.threat{color:var(--mf-bad);border-color:rgba(224,108,117,.5);}
    .mf-chip.friend,.mf-chip.self{color:var(--mf-live);border-color:rgba(84,214,160,.5);}
    .mf-chip.unknown,.mf-chip.unevaluated{color:var(--mf-mut);}

    /* modality row */
    .mf-modgrid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;}
    .mf-mod{border:1px solid var(--mf-stroke);border-radius:var(--mf-rm);padding:11px 11px 12px;
      background:var(--mf-glass2);display:flex;flex-direction:column;gap:6px;min-height:128px;position:relative;}
    .mf-mod-top{display:flex;align-items:center;justify-content:space-between;gap:6px;}
    .mf-mod-name{font-weight:800;font-size:.72rem;letter-spacing:.06em;}
    .mf-state{font-size:.7rem;font-weight:800;letter-spacing:.07em;padding:2px 7px;border-radius:6px;
      border:1px solid var(--mf-stroke);white-space:nowrap;text-transform:uppercase;}
    .mf-state.live{color:var(--mf-live);background:rgba(84,214,160,.14);border-color:rgba(84,214,160,.5);}
    .mf-state.sample{color:var(--mf-sample);background:rgba(242,193,78,.14);border-color:rgba(242,193,78,.5);}
    .mf-state.blind{color:var(--mf-fnt);background:rgba(126,143,179,.12);border-color:rgba(126,143,179,.4);}
    .mf-mod-val{font-size:.74rem;font-weight:700;color:var(--mf-ink);line-height:1.25;}
    .mf-mod-val.dim{color:var(--mf-fnt);font-weight:600;font-style:italic;}
    .mf-mod-detail{font-size:.72rem;color:var(--mf-mut);line-height:1.4;margin-top:auto;}
    .mf-mod[data-st="blind"]{opacity:.78;}
    .mf-mod .mf-dot{position:absolute;top:11px;right:11px;}

    /* fused confidence readout */
    .mf-fuse{display:grid;grid-template-columns:auto 1fr;gap:14px 16px;align-items:center;}
    .mf-bignum{font-size:2.1rem;font-weight:800;font-variant-numeric:tabular-nums;line-height:1;}
    .mf-bignum small{font-size:.85rem;color:var(--mf-mut);font-weight:700;}
    .mf-meter{height:10px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden;border:1px solid var(--mf-stroke);}
    .mf-meter > i{display:block;height:100%;border-radius:999px;transition:width .4s ease;}
    @media (prefers-reduced-motion: reduce){.mf-meter > i{transition:none;}}
    .mf-conf-low{color:var(--mf-bad);} .mf-conf-med{color:var(--mf-sample);} .mf-conf-high{color:var(--mf-live);}
    .mf-meter > i.low{background:var(--mf-bad);} .mf-meter > i.med{background:var(--mf-sample);} .mf-meter > i.high{background:var(--mf-live);}
    .mf-posture{font-size:.74rem;color:var(--mf-mut);margin:10px 0 0;}
    .mf-posture b{color:var(--mf-ink);}

    /* cross-verification narrative */
    .mf-narr{font-size:.8rem;color:var(--mf-ink);line-height:1.5;margin:6px 0 0;}
    .mf-narr .step{color:var(--mf-coral);font-weight:700;}
    .mf-narr .arrow{color:var(--mf-fnt);padding:0 4px;}

    /* blind-spot reference table */
    .mf-table{width:100%;border-collapse:collapse;font-size:.78rem;}
    .mf-table th{text-align:left;color:var(--mf-mut);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;
      font-weight:800;padding:8px 10px;border-bottom:1px solid var(--mf-edge);}
    .mf-table td{padding:10px 10px;border-bottom:1px solid var(--mf-stroke);vertical-align:top;line-height:1.4;}
    .mf-table tr:last-child td{border-bottom:0;}
    .mf-table .mf-mname{font-weight:800;white-space:nowrap;}
    .mf-table .mf-can{color:var(--mf-ink);} .mf-table .mf-cant{color:var(--mf-sample);}
    .mf-tag-real{color:var(--mf-live);font-weight:800;font-size:.72rem;letter-spacing:.04em;}
    .mf-tag-samp{color:var(--mf-sample);font-weight:800;font-size:.72rem;letter-spacing:.04em;}

    .mf-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.72rem;color:var(--mf-mut);margin-top:8px;}
    .mf-legend span{display:inline-flex;align-items:center;gap:5px;}
    .mf-legend i{width:9px;height:9px;border-radius:3px;display:inline-block;border:1px solid var(--mf-stroke);}
    .mf-empty{color:var(--mf-mut);font-size:.82rem;padding:8px 2px;}
    .mf-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);}

    /* BFT quorum-over-5 */
    .mf-quorum{display:grid;grid-template-columns:auto 1fr;gap:14px 18px;align-items:center;}
    .mf-qcol{display:flex;flex-direction:column;gap:3px;} .mf-qcol-grow{align-items:flex-start;}
    .mf-qvote{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0;}
    .mf-qnote{color:var(--mf-mut);font-size:.78rem;margin:10px 0 0;line-height:1.5;}
    .mf-rct-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:2px 0 10px;}
    .mf-qbig{font-size:1.9rem;font-weight:800;font-variant-numeric:tabular-nums;line-height:1;}
    .mf-qbig small{font-size:.8rem;color:var(--mf-mut);font-weight:700;}
    .mf-qbig.ok{color:var(--mf-live);} .mf-qbig.no{color:var(--mf-sample);}
    .mf-qverdict{font-size:.78rem;font-weight:800;letter-spacing:.06em;padding:3px 10px;border-radius:999px;
      border:1px solid var(--mf-stroke);display:inline-block;}
    .mf-qverdict.ok{color:var(--mf-live);border-color:rgba(84,214,160,.5);background:rgba(84,214,160,.12);}
    .mf-qverdict.no{color:var(--mf-sample);border-color:rgba(242,193,78,.5);background:rgba(242,193,78,.12);}
    .mf-vote{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0;}
    .mf-voter{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:8px;font-size:.72rem;
      font-weight:800;letter-spacing:.04em;border:1px solid var(--mf-stroke);}
    .mf-voter.live{color:var(--mf-live);border-color:rgba(84,214,160,.5);background:rgba(84,214,160,.10);}
    .mf-voter.sample{color:var(--mf-sample);border-color:rgba(242,193,78,.4);background:rgba(242,193,78,.08);}
    .mf-voter.blind{color:var(--mf-fnt);border-color:rgba(126,143,179,.35);opacity:.8;}
    .mf-voter b{font-size:.66rem;font-weight:900;opacity:.85;}

    /* cosign DSSE receipt drop */
    .mf-rct-btns{display:flex;gap:10px;flex-wrap:wrap;margin:4px 0 12px;}
    .mf-btn{appearance:none;cursor:pointer;border:1px solid var(--mf-stroke);border-radius:10px;
      background:rgba(224,122,95,.14);color:var(--mf-ink);font-weight:800;font-size:.8rem;letter-spacing:.03em;
      padding:9px 16px;transition:filter .15s ease;}
    .mf-btn:hover{filter:brightness(1.12);} .mf-btn:disabled{opacity:.5;cursor:default;}
    .mf-btn.ghost{background:rgba(255,255,255,.04);}
    .mf-rct-state{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:2px 0 10px;}
    .mf-rct-badge{font-size:.72rem;font-weight:800;letter-spacing:.06em;padding:3px 10px;border-radius:999px;border:1px solid var(--mf-stroke);}
    .mf-rct-badge.ok{color:var(--mf-live);border-color:rgba(84,214,160,.5);background:rgba(84,214,160,.12);}
    .mf-rct-badge.pend{color:var(--mf-sample);border-color:rgba(242,193,78,.5);background:rgba(242,193,78,.12);}
    .mf-rct-badge.err{color:var(--mf-bad);border-color:rgba(224,108,117,.5);background:rgba(224,108,117,.12);}
    .mf-kv{display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:.74rem;margin:6px 0 0;}
    .mf-kv dt{color:var(--mf-mut);font-weight:700;} .mf-kv dd{margin:0;color:var(--mf-ink);word-break:break-all;font-variant-numeric:tabular-nums;}
    .mf-pre{background:var(--mf-glass2);border:1px solid var(--mf-stroke);border-radius:8px;padding:10px 12px;
      font-size:.7rem;line-height:1.45;color:var(--mf-mut);overflow:auto;max-height:220px;white-space:pre;margin:8px 0 0;}

    @media (max-width:880px){.mf-modgrid{grid-template-columns:repeat(2,minmax(0,1fr));}}
    @media (max-width:520px){.mf-modgrid{grid-template-columns:1fr;}.mf-fuse{grid-template-columns:1fr;}.mf-quorum{grid-template-columns:1fr;}.mf-kv{grid-template-columns:1fr;}}
    `;
    var s = document.createElement('style');
    s.id = 'jk-modality-style';
    s.textContent = css;
    document.head.appendChild(s);
  }

  // -------------------------------------------------------------------------
  // MARKUP
  // -------------------------------------------------------------------------
  function buildPanel(container) {
    container.innerHTML = `
      <div class="mf-card" aria-labelledby="mf-modtitle">
        <div class="mf-head">
          <h3 class="mf-h" id="mf-modtitle">5-Modality sensor fusion</h3>
          <p class="mf-sub">no single sensor sees everything — five modalities, cross-verified</p>
        </div>
        <div class="mf-trackline" id="mf-trackline">
          <span class="mf-empty">Select a track above to see its per-modality picture.</span>
        </div>
        <div class="mf-modgrid" id="mf-modgrid" role="list" aria-label="Per-modality contribution for the selected track"></div>
        <div class="mf-legend" aria-hidden="false">
          <span><i style="background:rgba(84,214,160,.6)"></i>LIVE — real feed we have</span>
          <span><i style="background:rgba(242,193,78,.6)"></i>SAMPLE — modality not present at demo</span>
          <span><i style="background:rgba(126,143,179,.5)"></i>BLIND — modality structurally cannot see it</span>
        </div>
      </div>

      <div class="mf-card">
        <div class="mf-head"><h3 class="mf-h">Cross-verification</h3>
          <p class="mf-sub">how the modalities chain into one confident track</p></div>
        <p class="mf-narr" id="mf-narrative"></p>
      </div>

      <div class="mf-card">
        <div class="mf-head"><h3 class="mf-h">Fused confidence</h3>
          <p class="mf-sub">corroboration across modalities — trust is never 100%</p></div>
        <div class="mf-fuse">
          <div>
            <div class="mf-bignum" id="mf-corrnum" aria-live="polite">0<small>/5</small></div>
            <div class="mf-sub" id="mf-corrlabel">modalities corroborating</div>
          </div>
          <div>
            <div class="mf-meter"><i id="mf-meter" style="width:0%"></i></div>
            <p class="mf-posture" id="mf-posture"></p>
          </div>
        </div>
      </div>

      <div class="mf-card">
        <div class="mf-head">
          <h3 class="mf-h">BFT quorum over witnessing sensors</h3>
          <p class="mf-sub">a track is &ldquo;agreed&rdquo; only when &gt;2/3 of trusted live witnesses vote it real</p>
        </div>
        <div class="mf-quorum">
          <div class="mf-qcol">
            <div class="mf-qbig" id="mf-qbig" aria-live="polite">0<small>&nbsp;votes</small></div>
            <div class="mf-sub">live witnesses voting &ldquo;real&rdquo;</div>
          </div>
          <div class="mf-qcol mf-qcol-grow">
            <div class="mf-qverdict no" id="mf-qverdict">NO QUORUM</div>
            <div class="mf-qvote" id="mf-qvote"></div>
          </div>
        </div>
        <p class="mf-qnote" id="mf-qnote"></p>
        <p class="mf-tip" style="margin-top:8px;">
          Quorum shape is <b>BFT-style 2f+1 over the witnessing set</b>. Unconditional Byzantine
          safety of the Khipu mesh is <b>Conjecture&nbsp;2 (OPEN)</b> &mdash; only conditional
          <b>agreement under non-equivocation</b> is proven. SAMPLE sensors <b>abstain</b> from the
          real quorum and never inflate it.
        </p>
      </div>

      <div class="mf-card">
        <div class="mf-head">
          <h3 class="mf-h">Cosign DSSE receipt</h3>
          <p class="mf-sub">fuse the picture into one signed, chain-hashed envelope</p>
        </div>
        <div class="mf-rct-row">
          <button type="button" class="mf-btn" id="mf-fuse-btn">Fuse + sign track</button>
          <span class="mf-rct-badge" id="mf-rct-badge">NOT SIGNED</span>
        </div>
        <div class="mf-kv" id="mf-rct-kv"></div>
        <pre class="mf-pre" id="mf-rct-pre" aria-label="signed DSSE envelope">&mdash; press &ldquo;Fuse + sign track&rdquo; to mint a receipt &mdash;</pre>
        <p class="mf-tip" style="margin-top:8px;">
          Receipt is signed by killinchu&rsquo;s in-process cosign signer
          (<code>ECDSA-P256-SHA256</code>). Until an operator provisions the canonical
          <code>SZL_COSIGN_PRIVATE_PEM</code> secret the key is <b>ephemeral</b>, so cross-app
          verification shows <b>PENDING</b>. We never fake a signature.
        </p>
      </div>

      <div class="mf-card">
        <div class="mf-head"><h3 class="mf-h">Blind-spot reference</h3>
          <p class="mf-sub">we name the limits — the honesty that earns trust</p></div>
        <div style="overflow:auto;">
        <table class="mf-table">
          <thead><tr>
            <th scope="col">Modality</th><th scope="col">Status</th>
            <th scope="col">What it CAN see</th><th scope="col">What it CANNOT see (blind spot)</th>
          </tr></thead>
          <tbody id="mf-blindbody"></tbody>
        </table>
        </div>
        <p class="mf-tip" style="margin-top:10px;">Effector action is <b>SIMULATED</b> on the ENGAGE tab, human-on-the-loop — never automated from this picture.</p>
      </div>
    `;
    el.trackline = container.querySelector('#mf-trackline');
    el.modgrid = container.querySelector('#mf-modgrid');
    el.narrative = container.querySelector('#mf-narrative');
    el.corrnum = container.querySelector('#mf-corrnum');
    el.corrlabel = container.querySelector('#mf-corrlabel');
    el.meter = container.querySelector('#mf-meter');
    el.posture = container.querySelector('#mf-posture');
    el.blindbody = container.querySelector('#mf-blindbody');
    el.qbig = container.querySelector('#mf-qbig');
    el.qverdict = container.querySelector('#mf-qverdict');
    el.qvote = container.querySelector('#mf-qvote');
    el.qnote = container.querySelector('#mf-qnote');
    el.fuseBtn = container.querySelector('#mf-fuse-btn');
    el.rctBadge = container.querySelector('#mf-rct-badge');
    el.rctKv = container.querySelector('#mf-rct-kv');
    el.rctPre = container.querySelector('#mf-rct-pre');
    if (el.fuseBtn) el.fuseBtn.addEventListener('click', fuseAndSign);

    renderBlindTable();
  }

  // The blind-spot reference is STATIC content — render once.
  function renderBlindTable() {
    if (!el.blindbody) return;
    el.blindbody.innerHTML = MODALITIES.map(function (m) {
      var real = REAL_CAPABLE[m.key];
      var statusTag = real
        ? '<span class="mf-tag-real">REAL where fed</span>'
        : '<span class="mf-tag-samp">SAMPLE at demo</span>';
      return '<tr>'
        + '<td class="mf-mname">' + esc(m.label) + '<div class="mf-tip">' + esc(m.full) + '</div></td>'
        + '<td>' + statusTag + '</td>'
        + '<td class="mf-can">' + esc(m.desc) + '</td>'
        + '<td class="mf-cant">' + esc(m.blind) + '</td>'
        + '</tr>';
    }).join('');
  }

  // -------------------------------------------------------------------------
  // RENDER the per-track modality picture
  // -------------------------------------------------------------------------
  function classChip(c) {
    c = (c || 'unevaluated').toLowerCase();
    var label = c;
    var cls = (c === 'threat' || c === 'hostile') ? 'threat'
            : (c === 'friend' || c === 'self') ? c
            : 'unknown';
    return '<span class="mf-chip ' + cls + '">' + esc(label) + '</span>';
  }

  function renderSelected() {
    if (!el.modgrid) return;
    var t = selectedId && tracks[selectedId];
    if (!t) {
      el.trackline.innerHTML = '<span class="mf-empty">Select a track above to see its per-modality picture.</span>';
      el.modgrid.innerHTML = '';
      if (el.narrative) el.narrative.innerHTML = '<span class="mf-empty">No track selected.</span>';
      if (el.corrnum) el.corrnum.innerHTML = '0<small>/5</small>';
      if (el.corrlabel) el.corrlabel.textContent = 'modalities corroborating';
      if (el.meter) { el.meter.style.width = '0%'; el.meter.className = ''; }
      if (el.posture) el.posture.textContent = '';
      if (el.qbig) el.qbig.innerHTML = '0<small>&nbsp;votes</small>';
      if (el.qbig) el.qbig.className = 'mf-qbig';
      if (el.qverdict) { el.qverdict.textContent = 'NO QUORUM'; el.qverdict.className = 'mf-qverdict no'; }
      if (el.qvote) el.qvote.innerHTML = '';
      if (el.qnote) el.qnote.textContent = '';
      resetReceiptDrop();
      return;
    }

    var modes = evalModalities(t);
    var srcs = [t.src].concat(t.mergedFrom || []);

    // header line
    el.trackline.innerHTML =
      '<span class="mf-trackid">' + esc(t.callsign || t.id) + '</span>'
      + classChip(t.classification)
      + '<span class="mf-chip">' + esc((t.platform_type || 'unknown').toUpperCase()) + '</span>'
      + '<span class="mf-chip">SRC ' + esc(srcs.map(function (s) { return String(s).toUpperCase(); }).join('+')) + '</span>'
      + '<span class="mf-chip ' + (t.live ? 'friend' : 'unevaluated') + '">' + labelFor(t.live) + '</span>';

    // modality cards
    el.modgrid.innerHTML = MODALITIES.map(function (m) {
      var s = modes[m.key];
      var stateLbl = s.status === 'live' ? labelFor(true)
                    : s.status === 'sample' ? labelFor(false)
                    : 'BLIND';
      var valCls = s.status === 'blind' ? 'mf-mod-val dim' : 'mf-mod-val';
      return '<div class="mf-mod" data-st="' + s.status + '" role="listitem" '
        + 'aria-label="' + esc(m.label + ': ' + stateLbl + ' — ' + s.value) + '">'
        + '<div class="mf-mod-top"><span class="mf-mod-name">' + esc(m.label) + '</span>'
        + '<span class="mf-state ' + s.status + '">' + esc(stateLbl) + '</span></div>'
        + '<div class="' + valCls + '">' + esc(s.value) + '</div>'
        + '<div class="mf-mod-detail">' + esc(s.detail) + '</div>'
        + '</div>';
    }).join('');

    renderNarrative(t, modes);
    renderConfidence(t, modes);
    renderQuorum(t, modes);
    // a new selection invalidates any previously-minted receipt
    resetReceiptDrop();
  }

  // -------------------------------------------------------------------------
  // BFT QUORUM over the witnessing (LIVE) set — honest 2f+1, SAMPLE abstains.
  // -------------------------------------------------------------------------
  function renderQuorum(t, modes) {
    if (!el.qbig) return;
    var q = quorum(modes);
    el.qbig.innerHTML = q.have + '<small>&nbsp;/&nbsp;' + q.need + ' needed</small>';
    el.qbig.className = 'mf-qbig ' + (q.reached ? 'ok' : 'no');
    if (q.w === 0) {
      el.qverdict.textContent = 'NO LIVE WITNESS';
      el.qverdict.className = 'mf-qverdict no';
    } else if (q.reached) {
      el.qverdict.textContent = 'QUORUM ✓ (2f+1, f≤' + q.ftol + ')';
      el.qverdict.className = 'mf-qverdict ok';
    } else {
      el.qverdict.textContent = 'NO QUORUM';
      el.qverdict.className = 'mf-qverdict no';
    }
    // voter chips: LIVE = real vote, SAMPLE = abstain (demo), BLIND = cannot witness
    var chips = MODALITIES.map(function (m) {
      var s = modes[m.key]; var st = s ? s.status : 'blind';
      var role = st === 'live' ? 'votes REAL' : st === 'sample' ? 'abstains (demo)' : 'cannot witness';
      return '<span class="mf-voter ' + st + '">' + esc(m.label) + ' <b>' + role + '</b></span>';
    }).join('');
    el.qvote.innerHTML = chips;
    var noteParts = [];
    if (q.w === 0) {
      noteParts.push('No LIVE sensor is witnessing this track — BFT quorum is undefined over an empty witnessing set.');
    } else {
      noteParts.push('Witnessing set = <b>' + q.w + '</b> LIVE sensor' + (q.w === 1 ? '' : 's')
        + '; quorum threshold <b>2f+1 = ' + q.need + '</b>, tolerating up to <b>f = ' + q.ftol
        + '</b> Byzantine fault' + (q.ftol === 1 ? '' : 's') + '.');
    }
    if (q.demo.length) {
      noteParts.push('With demo hardware live, the witnessing set would grow to <b>' + q.potentialW
        + '</b> (threshold ' + q.potentialNeed + ', f≤' + q.potentialFtol + ').');
    }
    el.qnote.innerHTML = noteParts.join(' ');
  }

  // -------------------------------------------------------------------------
  // COSIGN DSSE RECEIPT — fuse the selected picture, sign via shared module.
  // NEVER fakes: honest UNSIGNED / cross-app-PENDING when signer non-canonical.
  // -------------------------------------------------------------------------
  function resetReceiptDrop() {
    if (!el.rctBadge) return;
    el.rctBadge.textContent = 'NOT SIGNED';
    el.rctBadge.className = 'mf-rct-badge';
    if (el.rctKv) el.rctKv.innerHTML = '';
    if (el.rctPre) el.rctPre.textContent = '— press “Fuse + sign track” to mint a receipt —';
    if (el.fuseBtn) el.fuseBtn.disabled = false;
  }

  function kvRow(k, v) {
    return '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>';
  }

  async function fuseAndSign() {
    if (!el.rctBadge) return;
    var t = selectedId && tracks[selectedId];
    if (!t) { resetReceiptDrop(); return; }
    var modes = evalModalities(t);
    var c = corroboration(modes);
    var q = quorum(modes);

    // confidence band -> percent (mirrors renderConfidence; capped <100)
    var pct = c.live <= 0 ? 14 : c.live === 1 ? 26 : c.live === 2 ? 54 : c.live === 3 ? 74 : 90;

    var SZL = window.SZLReceipts;
    if (!SZL || typeof SZL.signReceipt !== 'function') {
      el.rctBadge.textContent = 'SIGNER UNAVAILABLE';
      el.rctBadge.className = 'mf-rct-badge err';
      if (el.rctPre) el.rctPre.textContent = 'window.SZLReceipts not loaded — cannot mint a receipt. (We do not fake signatures.)';
      return;
    }

    el.fuseBtn.disabled = true;
    el.rctBadge.textContent = 'SIGNING…';
    el.rctBadge.className = 'mf-rct-badge pend';

    var receipt = {
      type: 'killinchu.jackin.fused_track',
      track_id: String(t.callsign || t.id),
      classification: String(t.classification || 'unevaluated').toLowerCase(),
      modalities: { live: c.live, sample: c.sample, blind: c.blind },
      quorum: { w: q.w, need: q.need, reached: !!q.reached, ftol: q.ftol },
      confidence_pct: pct,
      scheme: SZL.SCHEME || 'ECDSA-P256-SHA256',
      ts: new Date().toISOString()
    };

    var canonical = '';
    var chainHash = '';
    try {
      canonical = SZL.canonicalJSON(receipt);
      if (typeof SZL.sha256Hex === 'function') chainHash = await SZL.sha256Hex(canonical);
    } catch (e) { /* hash is best-effort display only */ }

    var res;
    try {
      res = await SZL.signReceipt(receipt, { base: '' });
    } catch (e) {
      el.rctBadge.textContent = 'UNSIGNED (signer unreachable)';
      el.rctBadge.className = 'mf-rct-badge err';
      if (el.rctKv) el.rctKv.innerHTML =
        kvRow('track', receipt.track_id)
        + kvRow('quorum', q.reached ? ('reached (' + q.have + '/' + q.need + ')') : ('NOT reached (' + q.have + '/' + q.need + ')'))
        + kvRow('confidence', pct + '%')
        + (chainHash ? kvRow('sha256', chainHash) : '');
      if (el.rctPre) el.rctPre.textContent = 'Signer unreachable — receipt left UNSIGNED. We never fabricate a signature.\n\ncanonical payload:\n' + canonical;
      el.fuseBtn.disabled = false;
      return;
    }

    // res: {signed, canonicalKey, crossAppVerifiable, keyid, sigType, sig, envelope, signerNote}
    var signed = res && res.signed;
    var canonicalKey = res && res.canonicalKey;
    var crossApp = res && res.crossAppVerifiable;

    if (!signed) {
      el.rctBadge.textContent = 'UNSIGNED';
      el.rctBadge.className = 'mf-rct-badge err';
    } else if (canonicalKey && crossApp) {
      el.rctBadge.textContent = 'SIGNED ✓ cross-app verifiable';
      el.rctBadge.className = 'mf-rct-badge ok';
    } else {
      el.rctBadge.textContent = 'SIGNED · cross-app PENDING';
      el.rctBadge.className = 'mf-rct-badge pend';
    }

    if (el.rctKv) {
      el.rctKv.innerHTML =
        kvRow('track', receipt.track_id + ' · ' + receipt.classification.toUpperCase())
        + kvRow('quorum', q.reached ? ('✓ reached (' + q.have + '/' + q.need + ', f≤' + q.ftol + ')') : ('✗ not reached (' + q.have + '/' + q.need + ')'))
        + kvRow('modalities', c.live + ' live / ' + c.sample + ' sample / ' + c.blind + ' blind')
        + kvRow('confidence', pct + '%')
        + kvRow('scheme', (res && res.sigType) || receipt.scheme)
        + kvRow('keyid', (res && res.keyid) || '—')
        + kvRow('canonical key', canonicalKey ? 'yes' : 'no (ephemeral signer)')
        + (chainHash ? kvRow('payload sha256', chainHash) : '')
        + ((res && res.signerNote) ? kvRow('signer note', res.signerNote) : '');
    }
    if (el.rctPre) {
      var envOut = (res && res.envelope) ? res.envelope : { unsigned: true, payload: receipt };
      try { el.rctPre.textContent = JSON.stringify(envOut, null, 2); }
      catch (e) { el.rctPre.textContent = String(envOut); }
    }
    el.fuseBtn.disabled = false;
  }

  function renderNarrative(t, modes) {
    if (!el.narrative) return;
    // Build an honest chain from whatever modalities are contributing.
    var parts = [];
    var radarOk = modes.radar.status === 'sample';
    var acOk = modes.acoustic.status === 'sample';
    var eoirOk = modes.eoir.status === 'sample';
    var rfOk = modes.rf.status === 'sample';
    var ridOk = modes.remoteid.status === 'live';

    if (radarOk) parts.push('<span class="step">radar blip</span>');
    if (acOk) parts.push('<span class="step">acoustic motor signature</span>');
    if ((radarOk || acOk) && eoirOk) parts.push('<span class="step">slew EO/IR</span><span class="arrow">→</span><span class="step">visual confirm</span>');
    else if (eoirOk) parts.push('<span class="step">EO/IR visual confirm</span>');
    if (rfOk) parts.push('<span class="step">RF demod</span><span class="arrow">→</span><span class="step">make/model + operator-loc</span>');
    if (ridOk) parts.push('<span class="step">Remote ID</span><span class="arrow">→</span><span class="step">' + esc(modes.remoteid.detail) + '</span>');

    var chain = parts.join('<span class="arrow"> · </span>');
    var blinds = MODALITIES.filter(function (m) { return modes[m.key].status === 'blind'; })
      .map(function (m) { return m.label; });

    var html = '';
    if (chain) {
      html += chain + '.';
    } else {
      html += 'No modality is contributing to this track yet.';
    }
    if (blinds.length) {
      html += '<br><span class="arrow">⚠</span> Blind here: <b>' + esc(blinds.join(', ')) + '</b> '
        + '— this is exactly why fusion matters: a gap in one modality is covered by another, and named openly.';
    }
    el.narrative.innerHTML = html;
  }

  function renderConfidence(t, modes) {
    var c = corroboration(modes);
    // The BIG number is REAL corroboration (LIVE feeds only). SAMPLE never inflates it.
    if (el.corrnum) el.corrnum.innerHTML = c.live + '<small>/5 real</small>';
    if (el.corrlabel) {
      el.corrlabel.textContent = c.live + ' LIVE feed' + (c.live === 1 ? '' : 's') + ' corroborating'
        + (c.sample ? ' · +' + c.sample + ' SAMPLE (demo hardware)' : '')
        + (c.blind ? ' · ' + c.blind + ' blind' : '');
    }
    // Confidence posture is driven by REAL (LIVE) corroboration. Single-source = LOW.
    var pct, band, word, postureTxt;
    if (c.live <= 0) {
      pct = 14; band = 'low'; word = 'UNCONFIRMED';
      postureTxt = 'No LIVE modality corroborates this track yet. SAMPLE modalities below demonstrate what real hardware would add — they are NOT counted as confirmation.';
    } else if (c.live === 1) {
      pct = 26; band = 'low'; word = 'LOW';
      postureTxt = 'Single LIVE source is not a confirmed track — independent corroboration required before any decision.';
    } else if (c.live === 2) {
      pct = 54; band = 'med'; word = 'MODERATE';
      postureTxt = 'Two LIVE modalities corroborate; still seek a third independent confirm.';
    } else if (c.live === 3) {
      pct = 74; band = 'med'; word = 'GOOD';
      postureTxt = 'Three LIVE modalities corroborate — cross-verified across independent physics.';
    } else {
      pct = 90; band = 'high'; word = 'HIGH';
      postureTxt = c.live + ' LIVE modalities corroborate. Trust is still capped below 100% — sensors lie, fusion mitigates.';
    }
    if (el.meter) { el.meter.style.width = pct + '%'; el.meter.className = band; }
    if (el.corrnum) {
      el.corrnum.className = 'mf-bignum ' + (band === 'low' ? 'mf-conf-low' : band === 'med' ? 'mf-conf-med' : 'mf-conf-high');
    }
    if (el.posture) {
      var potentialNote = c.sample
        ? ' <span class="mf-tip">With full hardware, up to <b>' + c.potential + '/5</b> modalities would corroborate.</span>'
        : '';
      el.posture.innerHTML = '<b>' + word + ' confidence.</b> ' + esc(postureTxt) + potentialNote;
    }
  }

  // -------------------------------------------------------------------------
  // CONTAINER PLACEMENT — additive, never touches tracks.js DOM ownership.
  // We append `#modality-fusion-panel` to the fusion tab, ideally AFTER DEV 2's
  // `.tk-wrap` so it reads as a continuation of the same tab.
  // -------------------------------------------------------------------------
  function fusionTab() {
    return document.getElementById('tab-fusion') || document.getElementById('tab-tracks');
  }

  function ensureContainer() {
    var tab = fusionTab();
    if (!tab) return null;
    var c = document.getElementById('modality-fusion-panel');
    if (c) {
      // keep it inside the fusion tab; if DEV 2 re-rendered the wrap, re-place it
      if (c.parentNode !== tab && !tab.contains(c)) tab.appendChild(c);
      return c;
    }
    c = document.createElement('section');
    c.id = 'modality-fusion-panel';
    c.setAttribute('aria-label', '5-modality sensor fusion');
    // place after DEV 2's .tk-wrap if present, else at end of the tab
    var wrap = tab.querySelector('.tk-wrap');
    if (wrap && wrap.parentNode) wrap.parentNode.insertBefore(c, wrap.nextSibling);
    else tab.appendChild(c);
    return c;
  }

  // -------------------------------------------------------------------------
  // MOUNT
  // -------------------------------------------------------------------------
  function mount() {
    var tab = fusionTab();
    if (!tab) return false;
    if (state.mounted && document.getElementById('modality-fusion-panel')) {
      return true;
    }
    injectStyles();
    var container = ensureContainer();
    if (!container) return false;
    if (!state.mounted) buildPanel(container);
    else if (!container.firstChild) buildPanel(container);
    state.mounted = true;

    // subscribe to the bus (idempotent guard so we don't double-subscribe)
    if (!state._subscribed) {
      var ok = on('track', function (p) {
        if (Array.isArray(p)) p.forEach(ingestTrack);
        else ingestTrack(p);
        // if nothing selected yet, auto-select the first real track so the
        // panel is populated even before the user clicks.
        if (!selectedId) {
          var firstNonAircraft = Object.keys(tracks)[0];
          if (firstNonAircraft) { selectedId = firstNonAircraft; state.dirty = true; }
        }
        state.dirty = true;
      });
      on('telemetry', function (te) {
        // detect Remote-ID evidence carried on raw telemetry frames (honest LIVE)
        if (te && rawHasRemoteID(te.raw)) {
          var id = (te.src || 'link') + ':self';
          ridEvidence[id] = Date.now();
          state.dirty = true;
        }
      });
      on('track-selected', function (sel) {
        if (sel && sel.id) {
          selectedId = sel.id;
          if (sel.track) ingestTrack(sel.track);
          state.dirty = true;
        }
      });
      on('classification', function (c) {
        if (c && c.id && tracks[c.id]) {
          if (c.classification) tracks[c.id].classification = c.classification;
          if (c.conf != null) tracks[c.id].conf = c.conf;
          state.dirty = true;
        }
      });
      if (ok) state._subscribed = true;
      else {
        // bus not ready — retry briefly (graceful with DEV 1/5 lazy attach)
        var tries = 0, iv = setInterval(function () {
          tries++;
          if (on('track', function (p) { if (Array.isArray(p)) p.forEach(ingestTrack); else ingestTrack(p); state.dirty = true; })) {
            on('track-selected', function (sel) { if (sel && sel.id) { selectedId = sel.id; if (sel.track) ingestTrack(sel.track); state.dirty = true; } });
            on('classification', function (c) { if (c && c.id && tracks[c.id]) { if (c.classification) tracks[c.id].classification = c.classification; if (c.conf != null) tracks[c.id].conf = c.conf; state.dirty = true; } });
            on('telemetry', function (te) { if (te && rawHasRemoteID(te.raw)) { ridEvidence[(te.src || 'link') + ':self'] = Date.now(); state.dirty = true; } });
            state._subscribed = true; clearInterval(iv);
          } else if (tries > 40) { clearInterval(iv); }
        }, 250);
      }
    }

    // light refresh loop (1 Hz) — re-render only when dirty and tab is visible
    if (!state.timer) {
      state.timer = setInterval(function () {
        var tabNow = fusionTab();
        if (!tabNow) return;
        ensureContainer();
        var visible = tabNow.offsetParent !== null || tabNow.getClientRects().length > 0;
        if (!visible) return;
        if (state.dirty) { renderSelected(); state.dirty = false; }
        else { renderSelected(); }  // keep Remote-ID time-box + ages fresh
      }, 1000);
    }

    renderSelected();
    return true;
  }

  function boot() {
    if (mount()) return;
    var mo = new MutationObserver(function () { if (mount()) { /* keep observer: DEV2 may re-render */ } });
    mo.observe(document.documentElement, { childList: true, subtree: true });
    // also try once the DOM settles
    setTimeout(mount, 400);
    setTimeout(mount, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  // public hook (lets the router or QA force a mount / inspect state)
  window.JACKIN_MODALITY = {
    mount: mount,
    _eval: evalModalities,
    _tracks: tracks,
    _select: function (id) { selectedId = id; state.dirty = true; renderSelected(); },
    _modalities: MODALITIES
  };
})();
