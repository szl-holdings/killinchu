/* SPDX-License-Identifier: Apache-2.0
 * © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11/v12
 *
 * killinchu-restraint-chaski.js — Chaski (agent-transport) Restraint annotator (DEV-WIRE-K R3).
 *
 * Chaski is killinchu's agent messaging / transport layer (the floating governed-
 * operator surface mounted on every killinchu HTML page; it routes reasoning/agent
 * calls to the a11oy substrate). This tiny, self-hosted (0 CDN) script adds a
 * TRANSPORT-LEVEL "restraint" annotation: when an agent message that flows through
 * Chaski carries a CODE PROPOSAL (a fenced code block / diff / "function"/"class"),
 * it routes that proposal through the SHARED governed restraint ladder
 * (/api/killinchu/v1/restraint/evaluate — the byte-identical szl_restraint.py also
 * on a11oy) and stamps the message with the stopped-at RUNG + the SIGNED DSSE
 * receipt status as it transits.
 *
 * HONEST BY CONSTRUCTION:
 *   - It only ANNOTATES messages that actually contain code — never every message.
 *   - The rung, Λ, lines-saved (MODELED) and receipt come straight from the live
 *     endpoint; nothing is fabricated. If the endpoint is PENDING (module not yet
 *     deployed) the badge reads "restraint: PENDING" and degrades — it never invents
 *     a verdict or a signature.
 *   - "SIGNED" only renders when the receipt is genuinely signed by the in-image
 *     ECDSA-P256 key; otherwise it reads "UNSIGNED (in-image key absent)".
 *   - Transport annotation only: it does not change message content or agent
 *     behaviour. Effectors stay SIMULATED, trust < 100%, Λ = Conjecture 1 (< 1.0).
 *
 * ADDITIVE: a single MutationObserver over the Chaski/operator surface; no CDN,
 * no codenames, no new deps. Doctrine v11 LOCKED 749/14/163 @ c7c0ba17.
 */
(function () {
  "use strict";
  if (window.__KC_RESTRAINT_CHASKI__) return;
  window.__KC_RESTRAINT_CHASKI__ = true;

  var NS = "killinchu";
  var A11OY_RESTRAINT = "https://szlholdings-a11oy.hf.space/restraint";
  // A message "carries a code proposal" if it has a fenced block or codey tokens.
  var CODE_RE = /```|(^|\n)\s*(def |class |function |const |let |var |import |#include|diff --git|@@ )/;

  // Pull a compact "task" string from a code-carrying message for the ladder.
  function taskFromText(t) {
    if (!t) return "";
    var fence = t.match(/```[a-z]*\n([\s\S]*?)```/i);
    var body = fence ? fence[1] : t;
    return body.replace(/\s+/g, " ").trim().slice(0, 400);
  }

  function badge(state, text, title) {
    var b = document.createElement("span");
    b.className = "kc-restraint-badge kc-restraint-" + state;
    b.textContent = text;
    if (title) b.title = title;
    b.style.cssText =
      "display:inline-flex;align-items:center;gap:.35em;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;" +
      "font-size:10px;letter-spacing:.05em;text-transform:uppercase;padding:.12em .5em;margin:.3em .3em 0 0;border-radius:3px;" +
      "border:1px solid rgba(201,183,135,.3);color:#d6c69a;background:rgba(201,183,135,.06);cursor:default;";
    if (state === "signed") { b.style.color = "#39d98a"; b.style.borderColor = "rgba(57,217,138,.35)"; }
    else if (state === "unsigned") { b.style.color = "#f5c451"; b.style.borderColor = "rgba(245,196,81,.35)"; }
    else if (state === "pending") { b.style.color = "#5bc8ff"; b.style.borderColor = "rgba(91,200,255,.35)"; }
    return b;
  }

  function annotate(el) {
    if (!el || el.__kcRestraintDone) return;
    var text = el.textContent || "";
    if (!CODE_RE.test(text)) return;          // honest: only code-carrying messages
    el.__kcRestraintDone = true;

    var holder = document.createElement("div");
    holder.className = "kc-restraint-annot";
    holder.style.cssText = "margin-top:.4em;display:flex;flex-wrap:wrap;align-items:center;";
    holder.appendChild(badge("eval", "restraint: …", "Routing this code proposal through the governed frugality ladder (shared szl_restraint.py, byte-identical with a11oy)."));
    el.appendChild(holder);

    fetch("/api/" + NS + "/v1/restraint/evaluate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ task: taskFromText(text), intensity: "full" })
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      holder.innerHTML = "";
      var lam = (d.lambda_score && d.lambda_score.lambda);
      var saved = (d.lines_saved_estimate && d.lines_saved_estimate.lines_saved_modeled);
      var sr = d.signed_receipt;
      var isSigned = !!(sr && (sr.signed === true || (sr.signatures && sr.signatures.length && sr.signatures[0] && sr.signatures[0].sig)));
      holder.appendChild(badge("eval",
        "restraint rung " + d.stopped_at_rung + " · " + d.rung_key,
        (d.answer || "") + "\nceiling: " + (d.ceiling || "") + "\nΛ=" + lam + " (Conjecture 1, advisory <1.0) · saved≈" + saved + " LOC (MODELED, not measured)"));
      if (isSigned) {
        var kid = (sr.signatures && sr.signatures[0] && sr.signatures[0].keyid) || "in-image";
        holder.appendChild(badge("signed", "✓ signed receipt · " + kid,
          "DSSE receipt signed by the in-image ECDSA-P256 cosign key. Transport-level annotation; verify at /khipu/verify."));
      } else {
        holder.appendChild(badge("unsigned", "○ unsigned receipt",
          "In-image signing key absent in this runtime — receipt is HONEST and explicitly UNSIGNED, never fabricated."));
      }
      var rc = badge("eval", "ceiling ↗", d.restraint_comment || "");
      holder.appendChild(rc);
    }).catch(function (e) {
      holder.innerHTML = "";
      holder.appendChild(badge("pending", "restraint: PENDING",
        "Restraint module not live on this Space yet (" + e.message + "). Annotation degrades honestly — no fabricated verdict. Capability: " + A11OY_RESTRAINT));
    });
  }

  // Find the Chaski / operator-widget message surface and observe new messages.
  function surfaceRoots() {
    var sel = [
      "[data-surface=\"killinchu\"]",
      ".a11oy-operator-widget", "#a11oy-operator-widget",
      ".chaski", "#chaski", "[data-chaski]",
      ".operator-widget", "#operator-widget",
      "[data-role=\"agent-message\"]", ".agent-message", ".message"
    ];
    var set = [];
    sel.forEach(function (s) {
      document.querySelectorAll(s).forEach(function (n) { if (set.indexOf(n) < 0) set.push(n); });
    });
    return set;
  }

  function scan() {
    surfaceRoots().forEach(function (root) {
      // Annotate message-like descendants (and the root itself if it is a message).
      var msgs = root.querySelectorAll(
        "[data-role=\"agent-message\"], .agent-message, .message, .msg, .bubble, pre, code"
      );
      if (msgs.length === 0) annotate(root);
      msgs.forEach(annotate);
    });
  }

  function boot() {
    try { scan(); } catch (e) {}
    try {
      var mo = new MutationObserver(function () { try { scan(); } catch (e) {} });
      mo.observe(document.documentElement, { childList: true, subtree: true });
    } catch (e) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
