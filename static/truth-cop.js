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
