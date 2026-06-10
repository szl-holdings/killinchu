"""killinchu_research_sources.py — per-tab "Research & Sources" grounding.

Task #662. Every /elite console tab gains a panel of *vetted, real* upstream
sources (UDS/Zarf/Pepr repos, supply-chain standards, threat feeds, domain data
feeds, Lean/proof references, and per-subject arXiv literature) drawn from the
2026-06-10 source-registry brief.

Honesty doctrine (matches szl_readiness / szl_evidence_research):
  * The static `/research/{tab}` endpoint NEVER asserts a source is reachable. It
    only returns the curated source records (title/url/kind/note).
  * The `/research/{tab}/live` endpoint performs a REAL reachability probe
    (HEAD -> ranged GET, short timeout, cached) and returns honest
    live / unreachable per source with the HTTP status and checked_at.
  * No fabricated data. Feeds that were UNREACHABLE-from-this-environment in the
    brief and are "fix-before-cite" (SEC EDGAR full-text, Treasury Fiscal Data)
    are intentionally NOT cited as live anywhere here.

Pure stdlib (urllib). serve.py imports this try/except-guarded and calls
register(app, ns="killinchu").
"""
from __future__ import annotations

import datetime as _dt
import threading as _threading
import urllib.request as _urlreq
import urllib.error as _urlerr

_HONEST = (
    "Curated real upstream sources per tab. Static list never claims reachability; "
    "the /live probe reports honest live/unreachable with HTTP status + checked_at. "
    "No fabricated sources; fix-before-cite feeds (SEC EDGAR FTS, Treasury Fiscal "
    "Data) are deliberately omitted until corrected."
)

_UA = "killinchu-research/1.0 (+https://github.com/szl-holdings/killinchu)"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Canonical source pool (vetted real URLs, brief §1 + §1.6) ──────────────────
# kind: repo | docs | standard | feed | knowledge | arxiv
_SRC = {
    # §1.1 UDS / Defense Unicorns / Zarf / Pepr (GitHub, all LIVE in brief)
    "uds_core":    ("UDS Core (defenseunicorns/uds-core)", "https://github.com/defenseunicorns/uds-core", "repo", "Secure runtime platform · AGPL-3.0 · v1.6.0 (2026-06-09)."),
    "uds_cli":     ("UDS CLI (defenseunicorns/uds-cli)", "https://github.com/defenseunicorns/uds-cli", "repo", "Bundle/deploy CLI · AGPL-3.0 · v0.32.0."),
    "uds_common":  ("UDS Common (defenseunicorns/uds-common)", "https://github.com/defenseunicorns/uds-common", "repo", "Shared UDS tasks/actions · AGPL-3.0 · v1.24.13."),
    "pepr":        ("Pepr (defenseunicorns/pepr)", "https://github.com/defenseunicorns/pepr", "repo", "K8s admission/policy engine · Apache-2.0 · v1.2.1."),
    "zarf":        ("Zarf (zarf-dev/zarf)", "https://github.com/zarf-dev/zarf", "repo", "Airgap package/delivery · Apache-2.0 · v0.77.0."),
    "uds_docs":    ("UDS Core documentation", "https://docs.defenseunicorns.com/core", "docs", "Runtime/platform docs."),
    "du_home":     ("Defense Unicorns", "https://www.defenseunicorns.com", "docs", "Mission-software platform vendor / fleet-trust context."),
    "pepr_docs":   ("Pepr docs", "https://pepr.dev", "docs", "Policy-as-code docs."),
    "zarf_docs":   ("Zarf docs", "https://docs.zarf.dev/", "docs", "Airgap delivery docs."),
    # §1.2 supply-chain / signing standards
    "cosign":      ("Sigstore Cosign (sigstore/cosign)", "https://github.com/sigstore/cosign", "repo", "Keyless signing/attestation · Apache-2.0 · v3.1.1."),
    "in_toto":     ("in-toto Attestation framework", "https://github.com/in-toto/attestation", "repo", "Attestation predicates · v1.2.0."),
    "in_toto_io":  ("in-toto project", "https://in-toto.io", "docs", "Supply-chain integrity framework."),
    "slsa_fw":     ("SLSA framework (slsa-framework/slsa)", "https://github.com/slsa-framework/slsa", "repo", "Supply-chain levels."),
    "slsa_dev":    ("SLSA spec", "https://slsa.dev", "standard", "killinchu provenance = L1/L2 (honest)."),
    # §1.3 threat / vulnerability feeds (server-side KEV = cisagov GitHub mirror)
    "kev_mirror":  ("CISA KEV (cisagov GitHub mirror)", "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json", "feed", "Server-side KEV source (box 403s cisa.gov). Identical catalog/schema."),
    "nvd":         ("NVD CVE API 2.0", "https://services.nvd.nist.gov/rest/json/cves/2.0", "feed", "Rate-limited; treat as CACHED at volume."),
    "epss":        ("FIRST EPSS API", "https://api.first.org/data/v1/epss", "feed", "Exploit Prediction Scoring System; pairs with KEV."),
    # §1.4 domain data feeds (LIVE ones only)
    "adsb_mil":    ("adsb.lol military ADS-B", "https://api.adsb.lol/v2/mil", "feed", "killinchu's real maritime/air feed (wired in killinchu_backend.py)."),
    "fed_reg":     ("US Federal Register API", "https://www.federalregister.gov/api/v1/documents.json", "feed", "Rules/notices/EOs for legal-regulatory framing."),
    "usgs_quake":  ("USGS Earthquake feed", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson", "feed", "Live seismic feed (Seismic Forecast tab)."),
    # §1.5 knowledge / proofs
    "lean":        ("Lean / Mathlib community", "https://leanprover-community.github.io/", "knowledge", "Backs the proof/anatomy tabs."),
    "zenodo":      ("Zenodo (SZL DOIs)", "https://zenodo.org/", "knowledge", "GPD text cites only the 6 SZL Zenodo DOIs; never invent DOIs."),
    "asf_mag":     ("Air & Space Forces Magazine", "https://www.airandspaceforces.com/", "knowledge", "Defense-fleet trust narrative context."),
    # §1.6 arXiv literature (per-subject, real abstract URLs)
    "arx_cuas1":   ("C-UAS: State of the Art, Challenges & Future Trends", "https://arxiv.org/abs/2008.12461", "arxiv", "Counter-UAS survey (2020)."),
    "arx_cuas2":   ("Objective-Driven Test Method for Commercial DTI / Counter-UAS", "https://arxiv.org/abs/2405.04477", "arxiv", "Counter-UAS evaluation (2024)."),
    "arx_cuas3":   ("Integrating Counter-UAS Systems into UTM for Reliable Decisions", "https://arxiv.org/abs/2111.07291", "arxiv", "Counter-UAS + UTM (2021)."),
    "arx_cuas4":   ("Multi-physics Simulation for High-power Microwave Counter-UAS", "https://arxiv.org/abs/2602.08477", "arxiv", "HPM counter-UAS (2026)."),
    "arx_swarm1":  ("Advanced Drone Swarm Security via Blockchain Governance Game", "https://arxiv.org/abs/2112.15454", "arxiv", "Swarm security (2021)."),
    "arx_swarm2":  ("TriSweep: Four-Drone Swarm for EM Side-Channel Analysis", "https://arxiv.org/abs/2605.22709", "arxiv", "Swarm framework (2026)."),
    "arx_mar1":    ("Challenges in Vessel Behavior & Anomaly Detection (ML→DL)", "https://arxiv.org/abs/2004.03722", "arxiv", "Maritime anomaly (2020)."),
    "arx_mar2":    ("Context-Aware Autoencoders for Maritime Surveillance Anomaly", "https://arxiv.org/abs/2602.00124", "arxiv", "Maritime anomaly (2026)."),
    "arx_sc1":     ("SoK: Software Supply Chain Security — Secure Design Properties", "https://arxiv.org/abs/2406.10109", "arxiv", "Supply-chain SoK (2024)."),
    "arx_sc2":     ("GoSurf: Supply Chain Attack Vectors in Go", "https://arxiv.org/abs/2407.04442", "arxiv", "Supply-chain (2024)."),
    "arx_sc3":     ("Maven-Hijack: Packaging-Order Supply Chain Attack", "https://arxiv.org/abs/2407.18760", "arxiv", "Supply-chain (2024)."),
    "arx_bft1":    ("Byzantine Fault-Tolerant Distributed ML (SGD + CGE)", "https://arxiv.org/abs/2008.04699", "arxiv", "BFT consensus (2020)."),
    "arx_bft2":    ("Byzantine Fault-Tolerance under Minimal Redundancy", "https://arxiv.org/abs/2009.14763", "arxiv", "BFT consensus (2020)."),
    "arx_pqc1":    ("Signature Placement in PQ TLS Hierarchies (ML-DSA/SLH-DSA)", "https://arxiv.org/abs/2604.06100", "arxiv", "Post-quantum signatures (2026)."),
    "arx_pqc2":    ("Towards Post-Quantum Blockchain — Quantum-Resistant Crypto", "https://arxiv.org/abs/2402.00922", "arxiv", "Post-quantum review (2024)."),
    "arx_zt1":     ("Enhancing Enterprise Security with Zero Trust Architecture", "https://arxiv.org/abs/2410.18291", "arxiv", "Zero-trust (2024)."),
    "arx_zt2":     ("Intent-Aware Authorization for Zero Trust CI/CD", "https://arxiv.org/abs/2504.14777", "arxiv", "Zero-trust CI/CD (2025)."),
    "arx_zt3":     ("SecureBank: Financially-Aware Zero Trust Architecture", "https://arxiv.org/abs/2512.23124", "arxiv", "Zero-trust (2025)."),
    "arx_lean1":   ("A Formal Proof of the Ramanujan–Nagell Theorem in Lean 4", "https://arxiv.org/abs/2604.09808", "arxiv", "Lean formalization (2026)."),
    "arx_lean2":   ("Prime-Generated Formalization of Nagata's Factoriality (Lean 4)", "https://arxiv.org/abs/2604.05238", "arxiv", "Lean formalization (2026)."),
    "arx_lean3":   ("Formalizing Chemical Physics using the Lean Theorem Prover", "https://arxiv.org/abs/2210.12150", "arxiv", "Lean formalization (2022)."),
    "arx_epss":    ("Exploit Prediction Scoring System (EPSS)", "https://arxiv.org/abs/1908.04856", "arxiv", "Vulnerability prioritization (2019)."),
    "arx_k8s":     ("XI Commandments of Kubernetes Security (SoK)", "https://arxiv.org/abs/2006.15275", "arxiv", "K8s admission/policy security (2020)."),
}

# ── Per-tab explicit overrides (brief §4). Tabs not listed fall to keyword match. ─
_TAB = {
    # 4.1 Hero / Maritime & Fleet
    "hero_interdiction": ["adsb_mil", "arx_mar1", "arx_cuas1", "arx_mar2"],
    "u_maritime":        ["adsb_mil", "arx_mar1", "arx_mar2"],
    "maritime":          ["adsb_mil", "arx_mar1", "arx_mar2"],
    "u_fleet":           ["adsb_mil", "uds_core", "du_home", "asf_mag"],
    "fleet":             ["adsb_mil", "uds_core", "du_home"],
    "fleet_c2":          ["uds_core", "pepr", "arx_bft1", "adsb_mil"],
    "u_space":           ["lean", "asf_mag"],  # SDA: no live feed wired -> needs-source
    "u_swarm":           ["arx_swarm1", "arx_swarm2", "arx_cuas1"],
    "swarm":             ["arx_swarm1", "arx_swarm2", "arx_cuas1"],
    "swarmres":          ["arx_swarm1", "arx_bft1", "uds_core"],
    "swarm_intent":      ["arx_swarm1", "arx_swarm2", "arx_cuas3"],
    "u_minedops":        ["arx_cuas1", "arx_cuas4", "arx_k8s"],
    "u_melt":            ["uds_core", "arx_bft1", "slsa_dev"],
    "melt":              ["uds_core", "arx_bft1"],
    # 4.2 Amaru (Memory) intel
    "amaru_naval":        ["adsb_mil", "arx_mar1", "arx_mar2"],
    "amaru_counter_uas":  ["arx_cuas1", "arx_cuas2", "arx_cuas3", "arx_cuas4"],
    "amaru_advisories":   ["kev_mirror", "nvd", "epss", "arx_epss"],
    "amaru_procurement":  ["fed_reg"],  # SAM/SBIR: confirm-live -> federal register only
    "amaru_geopolitical": ["asf_mag", "fed_reg"],
    # 4.3 Rosie (Operator)
    "rosie_watch":      ["adsb_mil", "arx_mar1"],
    "rosie_correlate":  ["adsb_mil", "arx_sc1", "arx_mar1"],
    "rosie_entities":   ["adsb_mil", "arx_sc1"],
    "rosie_routing":    ["adsb_mil", "uds_core"],
    "rosie_digest":     ["adsb_mil", "kev_mirror"],
    # 4.4 Intel fusion / provenance
    "u_intel":      ["adsb_mil", "kev_mirror", "nvd", "arx_sc1"],
    "u_darkgraph":  ["adsb_mil", "arx_sc1", "arx_mar1"],
    "darkgraph":    ["adsb_mil", "arx_sc1", "arx_mar1"],
    "darkhunt":     ["adsb_mil", "kev_mirror", "arx_mar1"],
    "u_fusion":     ["adsb_mil", "kev_mirror", "arx_sc1", "arx_mar1"],
    "fusion":       ["adsb_mil", "kev_mirror", "arx_sc1"],
    "u_posture":    ["uds_core", "pepr", "arx_zt1", "arx_k8s"],
    "posture_drift":   ["uds_core", "pepr", "arx_zt1"],
    "topology_health": ["uds_core", "arx_k8s", "arx_zt1"],
    "attack_surface":  ["arx_k8s", "arx_zt1", "kev_mirror"],
    "zerotrust_mesh":  ["arx_zt1", "arx_zt2", "arx_zt3", "pepr"],
    "u_warhacker":  ["cosign", "in_toto", "slsa_dev", "arx_sc1"],
    "warhacker":    ["cosign", "in_toto", "slsa_dev"],
    "warboard":     ["cosign", "slsa_dev", "in_toto"],
    # UDS package / consensus / receipts / proofs / about / engage
    "uds_package":  ["zarf", "uds_core", "uds_cli", "slsa_dev"],
    "u_consensus":  ["arx_bft1", "arx_bft2", "uds_core"],
    "bft":          ["arx_bft1", "arx_bft2"],
    "u_receipts":   ["cosign", "in_toto", "slsa_dev"],
    "u_proofs":     ["lean", "arx_lean1", "arx_lean2", "zenodo"],
    "u_about":      ["uds_core", "slsa_dev", "lean", "zenodo"],
    "u_engage":     ["du_home", "uds_core", "slsa_dev"],
    "engage":       ["du_home", "uds_core"],
    # 4.5 Determinism / proofs
    "determinism_demo": ["lean", "cosign", "in_toto"],
    "tamper_demo":      ["cosign", "in_toto", "slsa_dev"],
    "lambda":           ["lean", "zenodo", "arx_lean1"],
    "putnam":           ["lean", "arx_lean1", "arx_lean2", "arx_lean3"],
    "readiness":        ["uds_core", "slsa_dev", "pepr"],
    "tracks":           ["adsb_mil", "arx_mar1"],
    "livepic":          ["adsb_mil", "arx_mar1"],
    "living_anatomy":   ["lean", "zenodo", "arx_lean3"],
    "organism":         ["lean", "zenodo", "arx_lean3"],
    "cross":            ["adsb_mil", "kev_mirror", "arx_sc1"],
    "operate":          ["uds_core", "pepr", "adsb_mil"],
    # extras seen in inventory
    "pqc":          ["arx_pqc1", "arx_pqc2", "cosign", "slsa_dev"],
    "kev":          ["kev_mirror", "nvd", "epss", "arx_epss"],
    "cve":          ["kev_mirror", "nvd", "epss"],
    "threats":      ["kev_mirror", "nvd", "arx_sc1"],
    "threatrank":   ["epss", "kev_mirror", "arx_epss"],
    "sanctions":    ["fed_reg", "asf_mag"],
    "roe":          ["fed_reg", "asf_mag"],
    "legal":        ["fed_reg"],
    "contracting":  ["fed_reg"],
    "geofence":     ["arx_cuas3", "adsb_mil"],
    "decoders":     ["arx_cuas1", "arx_swarm2"],
    "pulse":        ["usgs_quake"],
    "geoint":       ["adsb_mil", "asf_mag"],
    "constellations": ["asf_mag", "lean"],
    "audit":        ["cosign", "in_toto", "slsa_dev"],
    "chain":        ["cosign", "in_toto", "slsa_dev"],
    "research":     ["lean", "zenodo", "arx_sc1", "arx_lean1"],
    "honest":       ["slsa_dev", "lean", "zenodo"],
    "deploy":       ["zarf", "uds_core", "uds_cli"],
    "beyond":       ["lean", "zenodo", "arx_lean1"],
    "scicompute":   ["lean", "arx_lean3", "zenodo"],
    "healthtwin":   ["arx_k8s", "uds_core"],
    "edgeest":      ["arx_k8s", "arx_cuas4"],
    "telemem":      ["arx_k8s", "adsb_mil"],
    "adaptsample":  ["arx_cuas2", "adsb_mil"],
    "tacroute":     ["arx_cuas3", "adsb_mil"],
    "prioritize":   ["epss", "kev_mirror", "adsb_mil"],
    # wave910 (resilience / consensus / governance / mesh / audit / quorum)
    "w910stl":   ["uds_core", "arx_bft1"],
    "w910ci":    ["arx_zt2", "cosign", "slsa_dev"],
    "w910gg":    ["arx_swarm1", "arx_bft1"],
    "w910mesh":  ["arx_zt1", "pepr", "uds_core"],
    "w910audit": ["cosign", "in_toto", "slsa_dev"],
    "w910quorum": ["arx_bft1", "arx_bft2"],
    "evidence":  ["lean", "zenodo", "arx_sc1", "kev_mirror"],
    "live_intel": ["adsb_mil", "kev_mirror", "fed_reg"],
}

# keyword -> source ids (fallback for any tab not in _TAB). First match wins (order matters).
_KW = [
    (("maritim", "naval", "vessel", "voyage", "ais", "darkvessel", "track", "livepic", "fleet"), ["adsb_mil", "arx_mar1", "arx_mar2"]),
    (("uas", "drone", "swarm", "interdict", "counter", "geofenc", "decoder", "dronedb"), ["arx_cuas1", "arx_swarm1", "adsb_mil"]),
    (("kev", "cve", "advisor", "threat", "sanction", "osint", "darkhunt", "vuln"), ["kev_mirror", "nvd", "epss", "arx_epss"]),
    (("receipt", "consensus", "bft", "quorum", "dsse", "chain", "khipu", "ledger"), ["cosign", "in_toto", "slsa_dev", "arx_bft1"]),
    (("proof", "putnam", "lambda", "anatomy", "organism", "formula", "determin", "tamper", "scicompute", "kbformula", "gates"), ["lean", "arx_lean1", "zenodo"]),
    (("uds", "package", "posture", "topology", "zerotrust", "mesh", "attack", "airgap", "cannonico", "deploy"), ["uds_core", "pepr", "zarf", "arx_zt1", "arx_k8s"]),
    (("pqc", "quantum"), ["arx_pqc1", "arx_pqc2", "cosign"]),
    (("space", "constellation", "geoint", "orbit", "leo"), ["asf_mag", "lean"]),
    (("intel", "fusion", "darkgraph", "geopolit", "cross"), ["adsb_mil", "kev_mirror", "arx_sc1", "arx_mar1"]),
    (("mined", "edge", "telemem", "adaptsample", "tacroute", "prioritize", "healthtwin", "resweep", "swarmres"), ["arx_cuas1", "arx_k8s", "uds_core"]),
    (("legal", "roe", "contract", "procure", "sanction", "audit", "compliance"), ["fed_reg", "cosign", "slsa_dev"]),
    (("model", "atlas", "decoder", "autonomy"), ["lean", "arx_lean3", "zenodo"]),
]

# General grounding for anything that matches nothing above.
_DEFAULT = ["uds_core", "slsa_dev", "lean", "adsb_mil"]


def _ids_for_tab(tab: str) -> list:
    if tab in _TAB:
        return _TAB[tab]
    low = (tab or "").lower()
    for keys, ids in _KW:
        if any(k in low for k in keys):
            return ids
    return _DEFAULT


def _src_record(sid: str) -> dict:
    t = _SRC.get(sid)
    if not t:
        return {"id": sid, "title": sid, "url": "", "kind": "unknown", "note": ""}
    title, url, kind, note = t
    return {"id": sid, "title": title, "url": url, "kind": kind, "note": note}


def sources_for(tab: str) -> list:
    return [_src_record(s) for s in _ids_for_tab(tab)]


# ── reachability probe (HEAD -> ranged GET), cached ────────────────────────────
_CACHE = {}            # url -> (ts_epoch, dict)
_CACHE_TTL = 600.0
_PROBE_TIMEOUT = 6.0
_lock = _threading.Lock()


def _probe(url: str) -> dict:
    import time as _time
    if not url:
        return {"reachable": False, "http_status": 0, "checked_at": _now_iso(), "note": "no url"}
    now = _time.time()
    with _lock:
        hit = _CACHE.get(url)
        if hit and (now - hit[0]) < _CACHE_TTL:
            return hit[1]

    def _attempt(method: str) -> dict:
        req = _urlreq.Request(url, method=method, headers={"User-Agent": _UA, "Accept": "*/*", "Range": "bytes=0-0"})
        with _urlreq.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            return {"reachable": 200 <= code < 400, "http_status": code, "checked_at": _now_iso()}

    result = None
    for method in ("HEAD", "GET"):
        try:
            result = _attempt(method)
            if result["reachable"]:
                break
        except _urlerr.HTTPError as e:  # server answered with an error code
            code = int(getattr(e, "code", 0) or 0)
            # Many feeds 403/405 to HEAD but are otherwise alive; let GET decide.
            result = {"reachable": 200 <= code < 400, "http_status": code, "checked_at": _now_iso()}
            if method == "GET":
                break
        except Exception as e:  # noqa: BLE001
            result = {"reachable": False, "http_status": 0, "checked_at": _now_iso(), "note": str(e)[:120]}
    with _lock:
        _CACHE[url] = (now, result)
    return result


def _summary(records: list, probed: bool) -> dict:
    out = {"total": len(records)}
    if probed:
        live = sum(1 for r in records if r.get("reachable"))
        out["live"] = live
        out["unreachable"] = len(records) - live
    by_kind = {}
    for r in records:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    out["by_kind"] = by_kind
    return out


def register(app, ns: str = "killinchu") -> None:
    """Attach /api/{ns}/v1/research[/{tab}[/live]] to a FastAPI app."""
    try:
        from fastapi.responses import JSONResponse
    except Exception:  # pragma: no cover
        return

    base = "/api/%s/v1/research" % ns

    @app.get(base)
    async def _research_index():  # noqa: ANN202
        return JSONResponse({
            "layer": "%s research & sources" % ns,
            "honest": _HONEST,
            "tabs_with_overrides": sorted(_TAB.keys()),
            "source_pool": len(_SRC),
            "checked_at": _now_iso(),
        })

    @app.get(base + "/{tab}")
    async def _research_tab(tab: str):  # noqa: ANN202
        recs = sources_for(tab)
        return JSONResponse({
            "layer": "%s research sources" % ns,
            "honest": _HONEST,
            "tab": tab,
            "explicit": tab in _TAB,
            "summary": _summary(recs, probed=False),
            "sources": recs,
            "checked_at": _now_iso(),
        })

    @app.get(base + "/{tab}/live")
    async def _research_tab_live(tab: str):  # noqa: ANN202
        import asyncio
        recs = sources_for(tab)

        async def _one(r):
            res = await asyncio.to_thread(_probe, r["url"])
            merged = dict(r)
            merged.update(res)
            return merged

        probed = await asyncio.gather(*[_one(r) for r in recs])
        probed = list(probed)
        return JSONResponse({
            "layer": "%s research sources (live probe)" % ns,
            "honest": _HONEST,
            "tab": tab,
            "explicit": tab in _TAB,
            "summary": _summary(probed, probed=True),
            "sources": probed,
            "checked_at": _now_iso(),
        })
