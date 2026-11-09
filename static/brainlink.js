/* SZL killinchu brain-link ribbon — makes the a11oy tether measured, not metaphorical.
   Pulls the latest living-evolution receipts from the public chain and renders
   the brain state on the field node. No CDN; fetches public HF data only. */
(function () {
  var DS = "SZLHOLDINGS/frontier-54-runs";
  var API = "https://huggingface.co/api/datasets/" + DS + "/tree/main/receipts?recursive=true";
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function shortSha(s) { return s ? s.slice(0, 10) + "…" : "—"; }
  function mount(host) {
    var root = host || document.body;
    var ribbon = el("div", "szl-brainlink");
    ribbon.style.cssText =
      "position:fixed;z-index:40;right:12px;bottom:12px;max-width:min(46ch,88vw);" +
      "background:rgba(9,10,26,0.88);border:1px solid rgba(143,182,230,0.30);border-radius:10px;" +
      "padding:10px 12px;font:11px/1.6 ui-monospace,Menlo,Consolas,monospace;color:#f3ecdc;" +
      "backdrop-filter:blur(9px);box-shadow:0 10px 34px rgba(0,0,0,0.5)";
    var title = el("div", null, "BRAIN-LINK · a11oy living evolution");
    title.style.cssText = "color:#8fb6e6;font-weight:700;letter-spacing:.06em;margin-bottom:4px;text-transform:uppercase";
    var body = el("div", "szl-brainlink-body", "querying receipt chain…");
    body.style.cssText = "color:#aba287";
    ribbon.appendChild(title); ribbon.appendChild(body);
    root.appendChild(ribbon);
    fetch(API, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (files) {
        var living = (files || []).filter(function (f) {
          return f.path.indexOf("living-cycle-") === 0;
        });
        if (!living.length) {
          body.textContent = "no evolution receipts yet — brain cycle pending";
          return;
        }
        living.sort(function (a, b) { return a.path < b.path ? 1 : -1; });
        var latest = living[0].path;
        return fetch("https://huggingface.co/datasets/" + DS + "/resolve/main/" + latest)
          .then(function (r) { return r.json(); })
          .then(function (rec) {
            var b = rec.battery || {};
            var pass = b.pass != null ? b.pass + "/" + (b.of || 6) : "—";
            var verdict = b.verdict || "UNKNOWN";
            var vc = verdict === "PASS" ? "#4fd18b" : "#c0392b";
            body.innerHTML = "";
            var l1 = el("div");
            l1.innerHTML = "cycle <b style='color:#e6c875'>" + (rec.cycle || "?") + "</b> · battery " +
              "<b style='color:" + vc + "'>" + pass + " " + verdict + "</b> · " +
              (rec.promoted ? "promoted v" + rec.cycle : "gate held") ;
            var l2 = el("div", "szl-brainlink-sha",
              "joules " + (rec.joules_measured || "—") + " · chain " + shortSha(rec.row_sha256));
            l2.style.cssText = "color:#5cc4bf";
            var l3 = el("div");
            var a = el("a", null, "receipt →");
            a.href = "https://huggingface.co/datasets/" + DS + "/blob/main/" + latest;
            a.target = "_blank"; a.rel = "noopener"; a.style.color = "#8fb6e6";
            l3.appendChild(a);
            body.appendChild(l1); body.appendChild(l2); body.appendChild(l3);
          });
      })
      .catch(function () {
        body.textContent = "receipt chain unreachable — failing closed (no cached claim)";
      });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { mount(); });
  } else { mount(); }
})();
