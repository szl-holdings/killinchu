(function () {
  "use strict";

  var ENDPOINTS = Object.freeze({
    observations: "/api/killinchu/v1/threats/active",
    feeds: "/api/killinchu/v1/feeds/status",
    honesty: "/api/killinchu/v1/honest",
    receipt: "/api/killinchu/v1/receipt/export"
  });

  var state = {
    tracks: [],
    selectedTrackId: null,
    requestController: null
  };

  var elements = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") {
      return fallback || "—";
    }
    return String(value);
  }

  function finiteNumber(value) {
    if (value === null || value === undefined || value === "" || typeof value === "boolean") {
      return null;
    }
    var numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function setText(element, value, fallback) {
    element.textContent = text(value, fallback);
  }

  function setStatus(element, label, tone) {
    setText(element, label, "UNAVAILABLE");
    element.dataset.tone = tone || "neutral";
  }

  function toneForMode(mode) {
    if (mode === "LIVE") return "good";
    if (mode === "CACHED" || mode === "STALE") return "warn";
    return "bad";
  }

  function formatAge(value) {
    var seconds = finiteNumber(value);
    if (seconds === null) return "Age not reported";
    if (seconds < 60) return Math.round(seconds) + " s old";
    if (seconds < 3600) return Math.round(seconds / 60) + " min old";
    return (seconds / 3600).toFixed(1) + " h old";
  }

  function formatNumber(value, digits) {
    var number = finiteNumber(value);
    return number === null ? "—" : number.toFixed(digits);
  }

  function safeHttpUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      var url = new URL(value, window.location.origin);
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
    } catch (error) {
      return null;
    }
  }

  function validObject(value) {
    return value && typeof value === "object" && !Array.isArray(value);
  }

  function normalizedObjects(value) {
    return Array.isArray(value) ? value.filter(validObject) : [];
  }

  function humanizeKey(value) {
    return text(value, "label").replace(/_/g, " ").replace(/^./, function (letter) {
      return letter.toUpperCase();
    });
  }

  function normalizeObservationResult(result) {
    var status = result && finiteNumber(result.status);
    if (!result || result.ok !== true) {
      return {
        healthy: false,
        httpStatus: status,
        mode: "UNAVAILABLE",
        tracks: [],
        sourceField: null,
        sourceLabel: status === null ? "Observation endpoint unavailable" : "HTTP " + status + " · response rejected as observation evidence",
        authentication: "UNAVAILABLE",
        age: null,
        honesty: "No observation claims are inferred from a non-2xx or unreachable response."
      };
    }

    var body = validObject(result.body) ? result.body : {};
    var sourceField = null;
    var tracks = [];
    if (Array.isArray(body.threats)) {
      sourceField = "threats";
      tracks = normalizedObjects(body.threats);
    } else if (body.schema === "killinchu.track-batch.v1" && Array.isArray(body.tracks)) {
      // Explicit compatibility path for the typed canonical contract. Untyped
      // `tracks` arrays are rejected so a shape coincidence cannot become evidence.
      sourceField = "tracks:killinchu.track-batch.v1";
      tracks = normalizedObjects(body.tracks);
    }

    var mode = text(body.mode, sourceField ? "UNLABELLED" : "UNAVAILABLE").toUpperCase();
    var fieldLabel = sourceField === "threats" ? "threats array" : sourceField ? "typed tracks compatibility" : "unsupported response shape";
    return {
      healthy: true,
      httpStatus: status,
      mode: mode,
      tracks: tracks,
      sourceField: sourceField,
      sourceLabel: text(body.source, "Source not reported") + " · " + fieldLabel,
      authentication: text(body.authentication, "UNAVAILABLE"),
      age: body.age_s,
      honesty: text(body.honesty, "The observation response did not include an honesty label.")
    };
  }

  function formatDoctrineLock(lock) {
    if (!validObject(lock)) return null;
    var identity = [lock.doctrine, lock.state].filter(Boolean).join(" ");
    var counts = [lock.declarations, lock.axioms, lock.sorries].every(function (value) {
      return finiteNumber(value) !== null;
    }) ? [lock.declarations, lock.axioms, lock.sorries].join("/") : null;
    return [identity, counts, lock.commit ? "commit " + lock.commit : null].filter(Boolean).join(" · ") || null;
  }

  function normalizeHonestyResult(result) {
    var status = result && finiteNumber(result.status);
    if (!result || result.ok !== true) {
      return {
        healthy: false,
        httpStatus: status,
        summary: status === null ? "Honest-disclosure endpoint unavailable. No runtime claims are inferred." : "HTTP " + status + " · disclosure response rejected.",
        disclosures: []
      };
    }

    var body = validObject(result.body) ? result.body : {};
    var labels = validObject(body.honest_labels) ? body.honest_labels : null;
    var disclosures = [];
    if (labels) {
      Object.keys(labels).sort().forEach(function (key) {
        var value = labels[key];
        if (typeof value === "string" && value.trim()) {
          disclosures.push(humanizeKey(key) + ": " + value);
        }
      });
    } else if (Array.isArray(body.honest_disclosures)) {
      // Compatibility with the newer detailed disclosure contract.
      disclosures = body.honest_disclosures.filter(function (item) {
        return typeof item === "string" && item.trim();
      });
    }

    var doctrine = formatDoctrineLock(body.doctrine_lock);
    if (doctrine) disclosures.push("Doctrine lock: " + doctrine);
    if (body.git_sha !== null && body.git_sha !== undefined && body.git_sha !== "") {
      disclosures.push("Deployed git SHA: " + String(body.git_sha));
    }
    var principle = labels && typeof labels.principle === "string" ? labels.principle : null;
    return {
      healthy: true,
      httpStatus: status,
      summary: text(principle || body.telemetry_trust, "Runtime disclosure returned without a summary label."),
      disclosures: disclosures
    };
  }

  async function fetchJson(path, signal) {
    var response = await fetch(path, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
      signal: signal
    });
    var body;
    try {
      body = await response.json();
    } catch (error) {
      throw new Error("HTTP " + response.status + " returned non-JSON evidence");
    }
    return { ok: response.ok, status: response.status, body: body };
  }

  function appendCell(row, label, primary, secondary, className) {
    var cell = document.createElement("td");
    cell.dataset.label = label;
    if (className) cell.className = className;
    var main = document.createElement("span");
    main.className = "cell-primary";
    setText(main, primary);
    cell.appendChild(main);
    if (secondary) {
      var detail = document.createElement("span");
      detail.className = "cell-secondary";
      setText(detail, secondary);
      cell.appendChild(detail);
    }
    row.appendChild(cell);
  }

  function trackIdentity(track, index) {
    return text(track.track_id, "observation-" + (index + 1));
  }

  function renderTracks() {
    var query = elements.search.value.trim().toLowerCase();
    var requestedMode = elements.mode.value;
    var visible = state.tracks.filter(function (track, index) {
      var mode = text(track.mode, "UNAVAILABLE").toUpperCase();
      var haystack = [
        trackIdentity(track, index), track.model, track.source, track.sensor_id,
        track.status, track.trust, track.authentication
      ].map(function (value) { return text(value, "").toLowerCase(); }).join(" ");
      return (requestedMode === "ALL" || mode === requestedMode) && (!query || haystack.includes(query));
    });

    var fragment = document.createDocumentFragment();
    visible.forEach(function (track) {
      var row = document.createElement("tr");
      var identity = text(track.track_id, "Unnamed observation");
      var identityCell = document.createElement("td");
      identityCell.dataset.label = "Observation";
      var inspect = document.createElement("button");
      inspect.type = "button";
      inspect.className = "inspect-button";
      inspect.dataset.trackId = identity;
      inspect.setAttribute("aria-pressed", String(state.selectedTrackId === identity));
      inspect.textContent = identity;
      inspect.addEventListener("click", function () { selectTrack(identity); });
      identityCell.appendChild(inspect);
      var model = document.createElement("span");
      model.className = "cell-secondary";
      setText(model, track.model, "Model not reported");
      identityCell.appendChild(model);
      row.appendChild(identityCell);

      appendCell(row, "Status", track.status, track.mode);
      appendCell(row, "Age", formatAge(track.age_s), text(track.observed_at, "Timestamp unavailable"), "mono");
      appendCell(
        row,
        "Position",
        formatNumber(track.latitude, 4) + ", " + formatNumber(track.longitude, 4),
        track.altitude_m === null || track.altitude_m === undefined ? "Altitude unavailable" : formatNumber(track.altitude_m, 0) + " m",
        "mono"
      );
      appendCell(row, "Trust", track.trust, track.authentication);
      fragment.appendChild(row);
    });

    elements.rows.replaceChildren(fragment);
    elements.empty.hidden = visible.length !== 0;
    elements.tableWrap.hidden = visible.length === 0;
    elements.caption.textContent = visible.length + " of " + state.tracks.length + " observations shown. Select an ID for provenance.";
  }

  function selectTrack(trackId) {
    var track = state.tracks.find(function (candidate) {
      return text(candidate.track_id, "") === trackId;
    });
    if (!track) return;

    state.selectedTrackId = trackId;
    setText(elements.inspectorTitle, trackId);
    elements.inspectorEmpty.hidden = true;
    elements.inspectorFields.hidden = false;
    elements.rawEvidence.hidden = false;
    setText(byId("detail-track-id"), track.track_id);
    setText(byId("detail-model"), track.model, "Not reported");
    setText(byId("detail-mode"), track.mode, "UNAVAILABLE");
    setText(byId("detail-authentication"), track.authentication, "UNAVAILABLE");
    setText(byId("detail-trust"), track.trust, "UNAVAILABLE");
    setText(byId("detail-observed-at"), track.observed_at, "Not reported");
    setText(byId("detail-received-at"), track.received_at, "Not reported");
    setText(byId("detail-sensor"), track.sensor_id, "Not reported");
    setText(byId("detail-digest"), track.payload_sha256, "Not reported");

    var sourceUrl = safeHttpUrl(track.source_url);
    elements.sourceLink.hidden = !sourceUrl;
    elements.sourceText.hidden = Boolean(sourceUrl);
    if (sourceUrl) {
      elements.sourceLink.href = sourceUrl;
      elements.sourceLink.textContent = text(track.source, "Open named source");
      elements.sourceLink.target = "_blank";
      elements.sourceLink.rel = "noopener noreferrer";
    } else {
      elements.sourceLink.removeAttribute("href");
      setText(elements.sourceText, track.source, "Not reported");
    }
    elements.raw.textContent = JSON.stringify(track, null, 2);
    renderTracks();
  }

  function renderObservationBatch(result) {
    var batch = normalizeObservationResult(result);
    var mode = batch.mode;
    state.tracks = batch.tracks;
    state.selectedTrackId = null;

    setStatus(elements.feedMode, mode, toneForMode(mode));
    setText(elements.feedAge, batch.healthy ? formatAge(batch.age) : "Response not accepted");
    setText(elements.observationCount, batch.healthy && batch.sourceField ? state.tracks.length : "—");
    setText(elements.observationSource, batch.sourceLabel);
    setStatus(
      elements.authentication,
      batch.authentication,
      batch.authentication === "UNAUTHENTICATED_BROADCAST" ? "warn" : "bad"
    );
    setText(elements.batchHonesty, batch.honesty);
    elements.inspectorTitle.textContent = "Select an observation";
    elements.inspectorEmpty.hidden = false;
    elements.inspectorFields.hidden = true;
    elements.rawEvidence.hidden = true;
    renderTracks();
  }

  function renderObservationFailure() {
    renderObservationBatch(null);
  }

  function renderFeedStatus(result) {
    if (!result || result.ok !== true) {
      renderFeedFailure(result);
      return;
    }
    var body = result && result.body && typeof result.body === "object" ? result.body : {};
    var feeds = body.feeds && typeof body.feeds === "object" ? Object.values(body.feeds) : [];
    setText(elements.feedCount, feeds.length || "—");
    if (!feeds.length) {
      setText(elements.feedInventory, "No feed inventory reported");
      return;
    }
    var modes = feeds.reduce(function (counts, feed) {
      var mode = text(feed && feed.last_mode, "not sampled").toLowerCase();
      counts[mode] = (counts[mode] || 0) + 1;
      return counts;
    }, {});
    var summary = Object.keys(modes).sort().map(function (mode) {
      return modes[mode] + " " + mode;
    }).join(" · ");
    setText(elements.feedInventory, summary);
  }

  function renderFeedFailure(result) {
    var status = result && finiteNumber(result.status);
    setText(elements.feedCount, "—");
    setText(elements.feedInventory, status === null ? "Feed-status endpoint unavailable" : "HTTP " + status + " · feed status unavailable");
  }

  function renderReceipt(result) {
    if (!result || result.ok !== true) {
      renderReceiptFailure(result);
      return;
    }
    var body = result && result.body && typeof result.body === "object" ? result.body : {};
    var verification = body.verification && typeof body.verification === "object" ? body.verification : {};
    var verified = body.signed === true && verification.verified === true;
    var label = verified ? "VERIFIED" : text(body.export_state, "UNAVAILABLE").toUpperCase();
    var tone = verified ? "good" : label === "EMPTY" || label === "UNSIGNED" ? "warn" : "bad";
    setStatus(elements.receiptState, label, tone);
    if (verified) {
      setText(elements.receiptNote, verification.reason, "Signature verified against the published key");
    } else if (body.receipt_available === false) {
      setText(elements.receiptNote, body.honesty, "No receipt is available");
    } else {
      setText(elements.receiptNote, verification.reason, "No verified-signature claim is available");
    }
  }

  function renderReceiptFailure(result) {
    var status = result && finiteNumber(result.status);
    setStatus(elements.receiptState, status === null ? "UNAVAILABLE" : "HTTP " + status, "bad");
    setText(elements.receiptNote, status === null ? "Receipt-export endpoint unavailable" : "Non-2xx receipt response; no verification claim accepted");
  }

  function renderHonesty(result) {
    var disclosure = normalizeHonestyResult(result);
    setText(elements.honestySummary, disclosure.summary);
    var fragment = document.createDocumentFragment();
    disclosure.disclosures.forEach(function (item) {
      var row = document.createElement("li");
      row.textContent = item;
      fragment.appendChild(row);
    });
    elements.honestyList.replaceChildren(fragment);
  }

  function renderHonestyFailure() {
    renderHonesty(null);
  }

  function outcomeValue(settled) {
    return settled.status === "fulfilled" ? settled.value : null;
  }

  async function refreshEvidence() {
    if (state.requestController) state.requestController.abort();
    state.requestController = new AbortController();
    var controller = state.requestController;
    var timeout = window.setTimeout(function () { controller.abort(); }, 12000);
    elements.refresh.disabled = true;
    elements.workspace.setAttribute("aria-busy", "true");
    setText(elements.refreshStatus, "Reading four same-origin evidence endpoints…");

    var outcomes;
    try {
      outcomes = await Promise.allSettled([
        fetchJson(ENDPOINTS.observations, controller.signal),
        fetchJson(ENDPOINTS.feeds, controller.signal),
        fetchJson(ENDPOINTS.honesty, controller.signal),
        fetchJson(ENDPOINTS.receipt, controller.signal)
      ]);
    } finally {
      window.clearTimeout(timeout);
    }

    if (controller !== state.requestController) return;
    var observationResult = outcomeValue(outcomes[0]);
    var feedResult = outcomeValue(outcomes[1]);
    var honestyResult = outcomeValue(outcomes[2]);
    var receiptResult = outcomeValue(outcomes[3]);
    observationResult ? renderObservationBatch(observationResult) : renderObservationFailure();
    feedResult ? renderFeedStatus(feedResult) : renderFeedFailure();
    honestyResult ? renderHonesty(honestyResult) : renderHonestyFailure();
    receiptResult ? renderReceipt(receiptResult) : renderReceiptFailure();

    var endpointResults = [observationResult, feedResult, honestyResult, receiptResult];
    var parsedCount = endpointResults.filter(Boolean).length;
    var healthyCount = endpointResults.filter(function (result) { return result && result.ok === true; }).length;
    var timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    setText(elements.refreshStatus, healthyCount + "/4 endpoints returned 2xx JSON · " + parsedCount + "/4 parsed · refreshed " + timestamp);
    elements.refresh.disabled = false;
    elements.workspace.setAttribute("aria-busy", "false");
  }

  function cacheElements() {
    elements.workspace = byId("workspace");
    elements.refresh = byId("refresh-evidence");
    elements.refreshStatus = byId("refresh-status");
    elements.feedMode = byId("feed-mode");
    elements.feedAge = byId("feed-age");
    elements.observationCount = byId("observation-count");
    elements.observationSource = byId("observation-source");
    elements.feedCount = byId("feed-count");
    elements.feedInventory = byId("feed-inventory");
    elements.receiptState = byId("receipt-state");
    elements.receiptNote = byId("receipt-note");
    elements.authentication = byId("batch-authentication");
    elements.batchHonesty = byId("batch-honesty");
    elements.search = byId("observation-search");
    elements.mode = byId("mode-filter");
    elements.caption = byId("observation-caption");
    elements.rows = byId("observation-rows");
    elements.empty = byId("observation-empty");
    elements.tableWrap = document.querySelector(".table-wrap");
    elements.inspectorTitle = byId("inspector-title");
    elements.inspectorEmpty = byId("inspector-empty");
    elements.inspectorFields = byId("inspector-fields");
    elements.rawEvidence = byId("raw-evidence");
    elements.raw = byId("detail-raw");
    elements.sourceLink = byId("detail-source");
    elements.sourceText = byId("detail-source-text");
    elements.honestySummary = byId("honesty-summary");
    elements.honestyList = byId("honesty-list");
  }

  function initialize() {
    cacheElements();
    elements.refresh.addEventListener("click", refreshEvidence);
    elements.search.addEventListener("input", renderTracks);
    elements.mode.addEventListener("change", renderTracks);
    refreshEvidence().catch(function () {
      renderObservationFailure();
      renderFeedFailure();
      renderHonestyFailure();
      renderReceiptFailure();
      setText(elements.refreshStatus, "Evidence refresh failed before endpoint results were available.");
      elements.refresh.disabled = false;
      elements.workspace.setAttribute("aria-busy", "false");
    });
  }

  var analystContract = Object.freeze({
    normalizeObservationResult: normalizeObservationResult,
    normalizeHonestyResult: normalizeHonestyResult
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = analystContract;
  }
  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", initialize);
  }
}());
