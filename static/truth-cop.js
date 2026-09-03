/* SPDX-License-Identifier: Apache-2.0 */
/* Killinchu truthful operational-picture status for Overview + Live Threats. */
(function () {
  "use strict";

  var ENDPOINT = "/api/killinchu/v1/threats/active";
  var BAND_ID = "killinchu-track-truth";
  var lastBatch = null;

  /*
   * Public Experience v3 root-shell repair.
   *
   * This controller is already loaded by both public shells. Keep the change
   * presentation-only and fail closed: it adds the audit marker, promotes the
   * exact measured brand control to 44px, and lets the status bar wrap at high
   * zoom. It does not alter a track, evidence label, endpoint, or claim class.
   */
  function installPublicExperienceV3() {
    var html = document.documentElement;
    html.setAttribute("data-szl-public-experience-v3", "true");
    html.style.maxWidth = "100%";
    html.style.overflowX = "clip";

    if (!document.body) return;
    document.body.style.maxWidth = "100%";
    document.body.style.overflowX = "clip";

    var topbar = document.querySelector(".topbar");
    if (topbar) {
      topbar.style.maxWidth = "100%";
      topbar.style.overflowX = "clip";
    }

    var shell = document.querySelector(".topbar__in");
    if (shell) {
      shell.style.width = "100%";
      shell.style.maxWidth = "100%";
      shell.style.flexWrap = "wrap";
    }

    var brand = document.querySelector(".topbar .brand");
    if (brand) {
      brand.style.display = "inline-flex";
      brand.style.minWidth = "44px";
      brand.style.minHeight = "44px";
      brand.style.maxWidth = "100%";
      brand.style.flexWrap = "wrap";
      brand.style.overflowWrap = "anywhere";
      brand.style.touchAction = "manipulation";
    }

    var meta = document.querySelector(".topbar__meta");
    if (meta) {
      meta.style.minWidth = "0";
      meta.style.maxWidth = "100%";
      meta.style.whiteSpace = "normal";
      meta.style.overflowWrap = "anywhere";
      meta.style.flex = "1 1 14rem";
    }
  }

  function text(value) {
    return value == null ? "unknown" : String(value);
  }

  function safeMode(batch) {
    var mode = text(batch && batch.mode).toUpperCase();
    return ["LIVE", "CACHED", "TRAINING", "UNAVAILABLE"].indexOf(mode) >= 0
      ? mode
      : "UNAVAILABLE";
  }

  function sentence(batch) {
    var mode = safeMode(batch);
    var count = Number(batch && batch.total_tracks) || 0;
    if (mode === "UNAVAILABLE") {
      return "UNAVAILABLE - no current or usable cached ADS-B observations; no tracks fabricated.";
    }
    if (mode === "TRAINING") {
      return "TRAINING MODE - " + count + " fixed fixtures; never a live sensor claim.";
    }
    return (
      mode +
      " - " +
      count +
      " ADS-B observation claims from " +
      text(batch.source) +
      ". Identity and position are unauthenticated; active threats remain unconfirmed."
    );
  }

  function ensureBand() {
    var band = document.getElementById(BAND_ID);
    if (band) return band;
    band = document.createElement("section");
    band.id = BAND_ID;
    band.setAttribute("role", "status");
    band.setAttribute("aria-live", "polite");
    band.style.cssText =
      "position:relative;z-index:20;margin:0;padding:10px 18px;border-bottom:1px solid #314052;" +
      "background:#0b1320;color:#d7e2ee;font:600 12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;";
    var root = document.querySelector("#root .content") || document.getElementById("root");
    if (root) root.insertBefore(band, root.firstChild);
    return band;
  }

  function replaceLegacyCopy(batch) {
    if (safeMode(batch) === "TRAINING") return;
    var paragraphs = document.querySelectorAll("#root p");
    for (var i = 0; i < paragraphs.length; i += 1) {
      if ((paragraphs[i].textContent || "").indexOf("Tracks are simulated over real drone signatures") >= 0) {
        paragraphs[i].textContent =
          "ADS-B observations from the named upstream. Broadcast identity and position are claims, " +
          "not confirmed threats. Fixtures require the explicit ?mode=training API opt-in.";
      }
    }
  }

  function render(batch) {
    lastBatch = batch;
    var mode = safeMode(batch);
    document.documentElement.setAttribute("data-killinchu-track-mode", mode);
    var band = ensureBand();
    if (band) {
      band.textContent = sentence(batch);
      band.style.borderColor =
        mode === "LIVE" ? "#2d9d78" : mode === "UNAVAILABLE" ? "#d85f5f" : "#d6aa43";
    }

    var top = document.querySelector(".live-pill");
    if (top) top.textContent = mode + " - ADS-B CLAIMS";
    var deck = document.querySelector(".kcd-ribbon .live");
    if (deck) deck.textContent = mode + " - ADS-B CLAIMS";
    var tag = document.querySelector(".kcd-ticker .tag");
    if (tag) tag.textContent = mode === "UNAVAILABLE" ? "UNAVAILABLE" : "AIR OBS";

    var proof = document.getElementById("kc-proof-state");
    if (proof) {
      proof.textContent = sentence(batch);
      proof.style.color = mode === "LIVE" ? "var(--teal)" : mode === "UNAVAILABLE" ? "var(--red)" : "var(--gold)";
    }
    replaceLegacyCopy(batch);
  }

  function refresh() {
    fetch(ENDPOINT, { cache: "no-store" })
      .then(function (response) {
        return response.json().then(function (batch) {
          if (!response.ok && (!batch || batch.mode !== "UNAVAILABLE")) throw new Error("track contract unavailable");
          return batch;
        });
      })
      .then(render)
      .catch(function () {
        render({ mode: "UNAVAILABLE", total_tracks: 0 });
      });
  }

  installPublicExperienceV3();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      installPublicExperienceV3();
      refresh();
    });
  } else {
    refresh();
  }

  var root = document.getElementById("root");
  if (root && window.MutationObserver) {
    new MutationObserver(function () {
      if (lastBatch && !document.getElementById(BAND_ID)) render(lastBatch);
      else if (lastBatch) replaceLegacyCopy(lastBatch);
    }).observe(root, { childList: true, subtree: true });
  }
  window.setInterval(refresh, 15000);
  window.KillinchuTruthCOP = {
    render: render,
    refresh: refresh,
    installPublicExperienceV3: installPublicExperienceV3
  };
})();

/*
 * SZL Public Experience v3.1
 * Viewport-, zoom-, and audience-aware adaptation for Holographic Space Fabric v2.
 * No network, analytics, cookies, storage, or product-state mutation.
 * SPDX-License-Identifier: Apache-2.0
 */
(function () {
  "use strict";

  if (window.__SZL_PUBLIC_EXPERIENCE_V3__) return;
  window.__SZL_PUBLIC_EXPERIENCE_V3__ = true;

  var VERSION = "3.1.0";
  var ROOT = document.documentElement;
  var raf = 0;
  var observer = null;
  var rootStyleObserver = null;
  var stopObserverTimer = 0;
  var lastViewportState = "";

  function layoutViewportWidth() {
    var visual = window.visualViewport && window.visualViewport.width;
    return Math.max(
      1,
      Math.round(Number(visual) || 0),
      Math.round(Number(window.innerWidth) || 0),
      Math.round(Number(ROOT.clientWidth) || 0)
    );
  }

  function layoutViewportHeight() {
    var visual = window.visualViewport && window.visualViewport.height;
    return Math.max(
      1,
      Math.round(Number(visual) || 0),
      Math.round(Number(window.innerHeight) || 0),
      Math.round(Number(ROOT.clientHeight) || 0)
    );
  }

  function cssZoom() {
    var value = 1;
    try {
      value = Number.parseFloat(window.getComputedStyle(ROOT).zoom || ROOT.style.zoom || "1");
    } catch (_error) {
      value = Number.parseFloat(ROOT.style.zoom || "1");
    }
    return Number.isFinite(value) && value > 0 ? value : 1;
  }

  function zoomTier(value) {
    if (value >= 3) return "extreme";
    if (value >= 1.5) return "high";
    return "normal";
  }

  function tier(width) {
    if (width < 480) return "phone";
    if (width < 768) return "compact";
    if (width < 1024) return "tablet";
    if (width < 1440) return "desktop";
    if (width < 1920) return "wide";
    if (width < 2560) return "theatre";
    return "ultrawide";
  }

  function orientation(width, height) {
    return width >= height ? "landscape" : "portrait";
  }

  function audience() {
    var value = "";
    try {
      value = new URLSearchParams(window.location.search || "").get("view") || "";
    } catch (_error) {}
    value = String(value).toLowerCase();
    if (value === "developer" || value === "dev" || value === "build") return "developer";
    if (value === "investor" || value === "diligence") return "investor";
    if (value === "operator" || value === "command") return "operator";
    return "user";
  }

  function humanize(value) {
    return String(value || "")
      .replace(/^szlholdings[-/]/i, "")
      .replace(/^szl-holdings[-/]/i, "")
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, function (character) { return character.toUpperCase(); })
      .trim();
  }

  function declaredIdentity() {
    var meta = document.querySelector('meta[name="szl-space-slug"]');
    var value = ROOT.dataset.szlSpaceLabel || ROOT.dataset.szlSpaceSlug ||
      (meta && meta.getAttribute("content")) || "";
    if (!value) {
      var match = String(window.location.hostname || "").match(/^(?:szlholdings|szl-holdings)-(.+?)(?:\.static)?\.hf\.space$/i);
      value = match ? match[1] : "";
    }
    return humanize(value) || "SZL Holdings";
  }

  function ensureDocumentTitle() {
    if (String(document.title || "").trim()) return;
    document.title = declaredIdentity() + " · SZL Holdings";
  }

  function syncBars(currentZoomTier) {
    document.querySelectorAll("szl-space-ecosystem-bar").forEach(function (bar) {
      bar.dataset.szlZoomTier = currentZoomTier;
    });
  }

  function snapshot() {
    var width = layoutViewportWidth();
    var height = layoutViewportHeight();
    var zoom = cssZoom();
    return Object.freeze({
      version: VERSION,
      width: width,
      height: height,
      effectiveWidth: Math.max(280, Math.round(width / zoom)),
      zoom: zoom,
      zoomTier: zoomTier(zoom),
      viewportTier: tier(Math.max(280, Math.round(width / zoom))),
      orientation: orientation(width, height),
      audience: audience()
    });
  }

  function applyViewportState() {
    raf = 0;
    var state = snapshot();
    var key = [state.width, state.height, state.zoom.toFixed(3), state.audience].join("|");
    syncBars(state.zoomTier);
    ensureDocumentTitle();
    if (key === lastViewportState) return;
    lastViewportState = key;

    ROOT.dataset.szlSpaceHoloV2 = "true";
    ROOT.dataset.szlPublicExperienceV3 = "true";
    ROOT.dataset.szlViewportTier = state.viewportTier;
    ROOT.dataset.szlViewportOrientation = state.orientation;
    ROOT.dataset.szlZoomTier = state.zoomTier;
    ROOT.dataset.szlAudience = state.audience;
    ROOT.style.setProperty("--szl-viewport-width", state.width + "px");
    ROOT.style.setProperty("--szl-viewport-height", state.height + "px");
    ROOT.style.setProperty("--szl-effective-inline-size", state.effectiveWidth + "px");
    ROOT.style.setProperty("--szl-page-zoom", state.zoom.toFixed(3));
  }

  function scheduleViewportState() {
    if (raf) return;
    raf = window.requestAnimationFrame(applyViewportState);
  }

  function responsiveBarStyle() {
    return [
      ":host{position:sticky!important;top:0!important;inline-size:100%!important;max-inline-size:100%!important;z-index:2147483000!important}",
      ":host([data-szl-zoom-tier=high]),:host([data-szl-zoom-tier=extreme]){position:relative!important;top:auto!important}",
      ".bar{min-height:56px!important;padding-block:8px!important;padding-inline:max(clamp(12px,2.3vw,30px),env(safe-area-inset-left,0px)) max(clamp(12px,2.3vw,30px),env(safe-area-inset-right,0px))!important}",
      "nav a,button{min-width:54px!important;min-height:48px!important;border-radius:10px!important;touch-action:manipulation!important}",
      "nav{max-width:100%!important}",
      "@media(max-width:700px){.bar{position:relative!important;grid-template-columns:minmax(0,1fr) auto!important;gap:8px!important}.identity{min-width:0!important}.label{max-width:min(58vw,360px)!important}.eyebrow{font-size:8px!important}button{display:inline-flex!important}nav{position:absolute!important;top:calc(100% + 7px)!important;right:max(8px,env(safe-area-inset-right,0px))!important;left:max(8px,env(safe-area-inset-left,0px))!important;max-height:min(56dvh,420px)!important;max-width:calc(100vw - 16px)!important;overflow:auto!important;overscroll-behavior:contain!important;padding:8px!important;border-radius:14px!important}nav a{justify-content:flex-start!important;padding-inline:14px!important}}",
      "@media(max-width:420px){.bar{min-height:54px!important;padding-block:5px!important}.copy{gap:0!important}.label{font-size:12px!important}.mark{width:22px!important;height:22px!important}nav{top:calc(100% + 5px)!important}}",
      "@media(min-width:1440px){.bar{min-height:60px!important;padding-inline:max(40px,env(safe-area-inset-left,0px)) max(40px,env(safe-area-inset-right,0px))!important}nav a{padding-inline:14px!important}}",
      "@media(min-width:1920px){.bar{min-height:64px!important;padding-inline:max(64px,env(safe-area-inset-left,0px)) max(64px,env(safe-area-inset-right,0px))!important}.label{font-size:14px!important}nav{gap:8px!important}nav a{min-height:48px!important;padding-inline:18px!important;font-size:12px!important}}",
      "@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}",
      "@media(forced-colors:active){.bar,nav,nav a,button{forced-color-adjust:auto!important}}"
    ].join("");
  }

  function enhanceBar(bar) {
    if (!bar || !bar.shadowRoot || bar.dataset.szlResponsiveV3 === "true") return;
    var style = document.createElement("style");
    style.dataset.szlResponsiveV3 = "true";
    style.textContent = responsiveBarStyle();
    bar.shadowRoot.appendChild(style);
    bar.dataset.szlResponsiveV3 = "true";
    bar.dataset.szlZoomTier = ROOT.dataset.szlZoomTier || zoomTier(cssZoom());

    var nav = bar.shadowRoot.querySelector("nav");
    var button = bar.shadowRoot.querySelector("button");
    if (button) button.setAttribute("title", "Open SZL product, proof, source, and Space navigation");
    if (nav) {
      nav.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
          nav.dataset.open = "false";
          if (button) {
            button.setAttribute("aria-expanded", "false");
            button.textContent = "Menu";
          }
        });
      });
    }
  }

  function enhanceBars() {
    document.querySelectorAll("szl-space-ecosystem-bar").forEach(enhanceBar);
  }

  function startBarObserver() {
    enhanceBars();
    if (!window.MutationObserver || observer) return;
    observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (!node || node.nodeType !== 1) return;
          if (node.matches && node.matches("szl-space-ecosystem-bar")) enhanceBar(node);
          if (node.querySelectorAll) node.querySelectorAll("szl-space-ecosystem-bar").forEach(enhanceBar);
        });
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    stopObserverTimer = window.setTimeout(function () {
      if (observer) observer.disconnect();
      observer = null;
      stopObserverTimer = 0;
    }, 30000);
  }

  function startRootStyleObserver() {
    if (!window.MutationObserver || rootStyleObserver) return;
    rootStyleObserver = new MutationObserver(scheduleViewportState);
    rootStyleObserver.observe(ROOT, { attributes: true, attributeFilter: ["style"] });
  }

  function initialize() {
    applyViewportState();
    startRootStyleObserver();
    startBarObserver();
    if (window.customElements && customElements.whenDefined) {
      customElements.whenDefined("szl-space-ecosystem-bar").then(enhanceBars).catch(function () {});
    }
  }

  Object.defineProperty(window, "SZLPublicExperience", {
    configurable: false,
    enumerable: false,
    writable: false,
    value: Object.freeze({ version: VERSION, snapshot: snapshot })
  });

  window.addEventListener("resize", scheduleViewportState, { passive: true });
  window.addEventListener("orientationchange", scheduleViewportState, { passive: true });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", scheduleViewportState, { passive: true });
    window.visualViewport.addEventListener("scroll", scheduleViewportState, { passive: true });
  }
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) scheduleViewportState();
  });
  window.addEventListener("pagehide", function () {
    if (observer) observer.disconnect();
    if (rootStyleObserver) rootStyleObserver.disconnect();
    if (stopObserverTimer) window.clearTimeout(stopObserverTimer);
    if (raf) window.cancelAnimationFrame(raf);
  }, { once: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
}());
