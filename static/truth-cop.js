/* SPDX-License-Identifier: Apache-2.0 */
/* Killinchu truthful operational picture + SZL Obsidian Signal family shell. */
(function () {
  "use strict";

  var ENDPOINT = "/api/killinchu/v1/threats/active";
  var BAND_ID = "killinchu-track-truth";
  var STYLE_ID = "szl-obsidian-signal-killinchu";
  var RAIL_ID = "szl-family-rail";
  var lastBatch = null;
  var refreshTimer = 0;

  function text(value) {
    return value == null || value === "" ? "unknown" : String(value);
  }

  function element(tag, className, label) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (label != null) node.textContent = label;
    return node;
  }

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var link = document.createElement("link");
    link.id = STYLE_ID;
    link.rel = "stylesheet";
    link.href = "/static/szl-obsidian-signal.css";
    link.setAttribute("data-szl-family-style", "killinchu-field");
    document.head.appendChild(link);
  }

  function familyLink(label, href, current, journey) {
    var link = element("a", "szl-family-link", label);
    link.href = href;
    if (/^https:\/\//.test(href)) link.rel = "noopener";
    if (current) link.setAttribute("aria-current", "page");
    if (journey) link.setAttribute("data-journey", journey);
    return link;
  }

  function installFamilyRail() {
    if (!document.body || document.getElementById(RAIL_ID)) return;
    var rail = element("nav", "szl-family-rail");
    rail.id = RAIL_ID;
    rail.setAttribute("aria-label", "SZL product family and pathways");

    var identity = element("a", "szl-family-identity");
    identity.href = "/";
    identity.setAttribute("aria-label", "Open Killinchu field command");
    identity.appendChild(element("span", "szl-family-mark"));
    var copy = element("span", "szl-family-copy");
    copy.appendChild(element("small", "", "SZL / Product family"));
    copy.appendChild(element("strong", "", "Killinchu Field"));
    identity.appendChild(copy);

    var track = element("div", "szl-family-track");
    track.appendChild(familyLink("A11oy", "https://a-11-oy.com/", false, ""));
    track.appendChild(familyLink("Killinchu", "/", true, ""));
    track.appendChild(familyLink("Hatun", "https://a-11-oy.com/wires", false, ""));
    track.appendChild(familyLink("Living Anatomy", "https://a-11-oy.com/living-anatomy", false, ""));
    track.appendChild(element("span", "szl-family-separator"));
    track.appendChild(familyLink("Understand", "/elite", false, "understand"));
    track.appendChild(familyLink("Build", "https://github.com/szl-holdings/killinchu", false, "build"));
    track.appendChild(familyLink("Verify", "/api/killinchu/v1/receipt/ledger/readiness", false, "verify"));

    rail.appendChild(identity);
    rail.appendChild(track);
    document.body.insertBefore(rail, document.body.firstChild);
  }

  /*
   * Public Experience v3 root-shell repair.
   * Presentation only: exact controls remain zoom-safe and the page fails closed.
   */
  function installPublicExperienceV3() {
    var html = document.documentElement;
    html.setAttribute("data-szl-public-experience-v3", "true");
    html.setAttribute("data-szl-family-shell", "obsidian-signal");
    html.setAttribute("data-szl-surface", "killinchu");
    html.setAttribute("data-szl-motif", "field-vector");
    html.style.maxWidth = "100%";
    html.style.overflowX = "clip";

    installStyle();
    if (!document.body) return;
    document.body.classList.add("szl-killinchu-field");
    document.body.style.maxWidth = "100%";
    document.body.style.overflowX = "clip";
    installFamilyRail();

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
    markViewport();
  }

  function markViewport() {
    var width = Math.max(1, window.innerWidth || document.documentElement.clientWidth || 1);
    var height = Math.max(1, window.innerHeight || document.documentElement.clientHeight || 1);
    var tier = width < 480 ? "phone" : width < 768 ? "compact" : width < 1024 ? "tablet" : width < 1440 ? "desktop" : width < 1920 ? "wide" : "theatre";
    document.documentElement.setAttribute("data-szl-viewport", tier);
    document.documentElement.setAttribute("data-szl-orientation", width >= height ? "landscape" : "portrait");
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
      return "UNAVAILABLE — no current or usable cached ADS-B observations; no tracks fabricated.";
    }
    if (mode === "TRAINING") {
      return "TRAINING MODE — " + count + " fixed fixtures; never a live sensor claim and not confirmed threats.";
    }
    return mode + " — " + count + " ADS-B observation claims from " + text(batch && batch.source) +
      ". Broadcast identity and position are unauthenticated claims, not confirmed threats.";
  }

  function ensureBand() {
    var band = document.getElementById(BAND_ID);
    if (band) return band;
    band = element("section");
    band.id = BAND_ID;
    band.setAttribute("role", "status");
    band.setAttribute("aria-live", "polite");
    var root = document.querySelector("#root .content") || document.getElementById("root") || document.querySelector("main");
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
          "not confirmed threats. Fixtures require the explicit training API opt-in.";
      }
    }
  }

  function render(batch) {
    lastBatch = batch;
    var mode = safeMode(batch);
    document.documentElement.setAttribute("data-killinchu-track-mode", mode);
    var band = ensureBand();
    if (band) band.textContent = sentence(batch);

    var top = document.querySelector(".live-pill");
    if (top) top.textContent = mode + " · ADS-B CLAIMS";
    var deck = document.querySelector(".kcd-ribbon .live");
    if (deck) deck.textContent = mode + " · ADS-B CLAIMS";
    var tag = document.querySelector(".kcd-ticker .tag");
    if (tag) tag.textContent = mode === "UNAVAILABLE" ? "UNAVAILABLE" : "AIR OBS";

    var proof = document.getElementById("kc-proof-state");
    if (proof) proof.textContent = sentence(batch);
    replaceLegacyCopy(batch);
  }

  function schedule() {
    window.clearTimeout(refreshTimer);
    if (document.hidden) return;
    refreshTimer = window.setTimeout(refresh, 15000);
  }

  function refresh() {
    var controller = new AbortController();
    var timeout = window.setTimeout(function () { controller.abort(); }, 6500);
    fetch(ENDPOINT, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal
    })
      .then(function (response) {
        return response.json().then(function (batch) {
          if (!response.ok && (!batch || batch.mode !== "UNAVAILABLE")) {
            throw new Error("track contract unavailable");
          }
          return batch;
        });
      })
      .then(render)
      .catch(function () {
        render({ mode: "UNAVAILABLE", total_tracks: 0 });
      })
      .finally(function () {
        window.clearTimeout(timeout);
        schedule();
      });
  }

  installPublicExperienceV3();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      installPublicExperienceV3();
      refresh();
    }, { once: true });
  } else {
    refresh();
  }

  var root = document.getElementById("root");
  if (root && window.MutationObserver) {
    new MutationObserver(function () {
      installFamilyRail();
      if (lastBatch && !document.getElementById(BAND_ID)) render(lastBatch);
      else if (lastBatch) replaceLegacyCopy(lastBatch);
    }).observe(root, { childList: true, subtree: true });
  }

  window.addEventListener("resize", function () {
    window.requestAnimationFrame(markViewport);
  }, { passive: true });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) window.clearTimeout(refreshTimer);
    else refresh();
  });

  window.KillinchuTruthCOP = {
    render: render,
    refresh: refresh,
    installPublicExperienceV3: installPublicExperienceV3
  };
})();
