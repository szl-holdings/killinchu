/* SZL killinchu field supply-chain view — the estate graph, visible from the edge.
   Renders the nodes that feed this field node (repos, artifacts, GPU containers)
   from the public estate-graph dataset. Fail-closed; no cached claims. */
(function () {
  var DS = "SZLHOLDINGS/estate-graph";
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function mount() {
    var host = document.querySelector("[data-szl-fieldsupply]") || document.body;
    var panel = el("div", "szl-fieldsupply");
    panel.style.cssText =
      "position:fixed;z-index:39;left:12px;bottom:12px;max-width:min(42ch,86vw);" +
      "background:rgba(9,10,26,0.88);border:1px solid rgba(143,182,230,0.30);border-radius:10px;" +
      "padding:10px 12px;font:11px/1.6 ui-monospace,Menlo,Consolas,monospace;color:#f3ecdc;" +
      "backdrop-filter:blur(9px);box-shadow:0 10px 34px rgba(0,0,0,0.5)";
    var title = el("div", null, "FIELD SUPPLY CHAIN · estate graph");
    title.style.cssText = "color:#8fb6e6;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px";
    var body = el("div", null, "querying estate graph…");
    body.style.cssText = "color:#aba287";
    panel.appendChild(title); panel.appendChild(body);
    host.appendChild(panel);
    fetch("https://huggingface.co/datasets/" + DS + "/resolve/main/estate-graph.json")
      .then(function (r) { return r.json(); })
      .then(function (g) {
        var c = g.counts || {};
        body.innerHTML = "";
        var l1 = el("div");
        l1.innerHTML = "upstream: <b style='color:#e6c875'>" + (c.nodes || "?") + "</b> nodes · " +
          "<b style='color:#e6c875'>" + (c.edges || "?") + "</b> edges";
        var bk = c.by_kind || {};
        var l2 = el("div",
          null,
          "repos " + (bk.repo || 0) + " · models " + (bk.model || 0) + " · datasets " +
          (bk.dataset || 0) + " · spaces " + (bk.space || 0) + " · gpu " + (bk.gpu_container || 0));
        l2.style.cssText = "color:#5cc4bf";
        var l3 = el("div");
        var a = el("a", null, "graph receipt →");
        a.href = "https://huggingface.co/datasets/" + DS;
        a.target = "_blank"; a.rel = "noopener"; a.style.color = "#8fb6e6";
        l3.appendChild(a);
        body.appendChild(l1); body.appendChild(l2); body.appendChild(l3);
      })
      .catch(function () {
        body.textContent = "estate graph unreachable — failing closed";
      });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { mount(); });
  } else { mount(); }
})();
