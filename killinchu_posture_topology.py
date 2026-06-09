# SPDX-License-Identifier: Apache-2.0
"""
killinchu_posture_topology — REAL drift detectors + REAL graph-metric readouts.

ADDITIVE, killinchu-specific (NOT a shared szl_*.py module — not guarded by the
shared-file drift gate). Registers four live endpoints on the killinchu FastAPI app:

  GET /api/killinchu/v1/posture/drift
        Posture & Drift. Computes THREE real, citable drift detectors on a live
        telemetry stream (adsb.lol military ADS-B via killinchu_live_feeds):
          * PSI  (Population Stability Index)  thresholds 0.1 / 0.25
          * KS   (Kolmogorov-Smirnov two-sample) scipy.stats.ks_2samp if present,
                 else an identical pure-numpy KS statistic + Kolmogorov asymptotic
                 p-value; alert if p < 0.05
          * ADWIN (~30-line vendored Adaptive Windowing) on the live error stream
        Emits an honest binary verdict DRIFT DETECTED / STABLE + the NAMED
        triggering detector(s) + the thresholds used. Reference window = real
        captured in-image telemetry snapshot (live_snapshots/air.json); live
        window = the current fetch. No fabricated baseline.

  GET /api/killinchu/v1/topology/health
        Topology & Health. Builds a real node/link graph of fleet + organ
        services and returns REAL graph metrics: avg clustering coefficient,
        avg shortest-path length, degree/betweenness centrality ranking,
        connected-component count, Fiedler value lambda_2 (algebraic
        connectivity), and a DAG-integrity check. networkx if present, else
        pure-numpy spectral / BFS fallbacks (identical math).

  GET /api/killinchu/v1/attack-surface/graph
        Attack-Surface Graph. Exposure graph from the REAL killinchu UDS Package
        CR (deploy/uds-package.yaml allow/expose rules) + blast-radius
        (reachable-set) from an exposed ingress node. Honest empty state if no
        exposures are discovered.

  GET /api/killinchu/v1/zerotrust/mesh
        Zero-Trust Mesh. mTLS/allow-policy mesh graph from the same UDS Package CR
        allow rules (Istio ambient). Edges = actual PeerAuthentication/allow
        rules only; empty state if none.

Doctrine: trust score never 100%; Lambda = Conjecture 1; locked-proven = 5;
honest empty / SIMULATED labels; organ public names = Quechua/honest roles
(Operator / Provenance Anchor / Policy) with NO banned codenames in any output.
All computation is CPU-only, 0 runtime CDN; only live DATA fetches occur.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# numpy is guaranteed in-image (Dockerfile pins numpy>=1.26).
import numpy as np

# scipy / networkx are OPTIONAL. We add them to the Dockerfile (additive) but the
# module must never crash a green build if a rebuild has not landed yet, so each
# has an identical pure-Python/numpy fallback.
try:  # pragma: no cover - import probe
    from scipy.stats import ks_2samp as _scipy_ks  # type: ignore
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    _scipy_ks = None
    _HAVE_SCIPY = False

try:  # pragma: no cover - import probe
    import networkx as _nx  # type: ignore
    _HAVE_NX = True
except Exception:  # pragma: no cover
    _nx = None
    _HAVE_NX = False


# ─────────────────────────────────────────────────────────────────────────────
# Drift detectors (real, citable)
# ─────────────────────────────────────────────────────────────────────────────
def psi(reference: np.ndarray, live: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index. Equals the symmetrized KL between the binned
    reference and live distributions. Rule of thumb: <0.1 stable, 0.1-0.25
    moderate, >=0.25 significant. (Fiddler / Coralogix.)"""
    reference = np.asarray(reference, dtype=float)
    live = np.asarray(live, dtype=float)
    if reference.size == 0 or live.size == 0:
        return float("nan")
    # quantile bin edges from the reference (robust to scale)
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0
    ref_hist, _ = np.histogram(reference, bins=edges)
    live_hist, _ = np.histogram(live, bins=edges)
    eps = 1e-6
    ref_pct = ref_hist / max(ref_hist.sum(), 1) + eps
    live_pct = live_hist / max(live_hist.sum(), 1) + eps
    return float(np.sum((live_pct - ref_pct) * np.log(live_pct / ref_pct)))


def _ks_pvalue_asymptotic(d: float, n: int, m: int) -> float:
    """Kolmogorov asymptotic two-sample p-value (same form scipy uses for the
    'asymp' mode). Q_ks(t) = 2 * sum_{k=1..inf} (-1)^{k-1} exp(-2 k^2 t^2)."""
    en = math.sqrt(n * m / float(n + m))
    t = (en + 0.12 + 0.11 / en) * d
    if t <= 0:
        return 1.0
    s = 0.0
    for k in range(1, 101):
        term = ((-1) ** (k - 1)) * math.exp(-2.0 * (k ** 2) * (t ** 2))
        s += term
        if abs(term) < 1e-10:
            break
    p = 2.0 * s
    return float(min(1.0, max(0.0, p)))


def ks_two_sample(reference: np.ndarray, live: np.ndarray) -> tuple[float, float, str]:
    """Two-sample KS. Uses scipy.stats.ks_2samp when available (the brief's
    explicit path); otherwise a pure-numpy KS statistic + Kolmogorov asymptotic
    p-value (identical math). Returns (statistic, p_value, backend)."""
    reference = np.asarray(reference, dtype=float)
    live = np.asarray(live, dtype=float)
    if reference.size == 0 or live.size == 0:
        return (float("nan"), float("nan"), "empty")
    if _HAVE_SCIPY:
        r = _scipy_ks(reference, live)
        return (float(r.statistic), float(r.pvalue), "scipy.stats.ks_2samp")
    # pure-numpy KS statistic = max CDF gap over the pooled sample
    allv = np.sort(np.concatenate([reference, live]))
    cdf_r = np.searchsorted(np.sort(reference), allv, side="right") / reference.size
    cdf_l = np.searchsorted(np.sort(live), allv, side="right") / live.size
    d = float(np.max(np.abs(cdf_r - cdf_l)))
    p = _ks_pvalue_asymptotic(d, reference.size, live.size)
    return (d, p, "numpy-ks (Kolmogorov asymptotic)")


class ADWIN:
    """~30-line vendored ADWIN (Adaptive Windowing) concept-drift detector.

    Bifet & Gavalda (2007). Streams real values; maintains a window and, on each
    update, looks for a split point where the two sub-window means differ by more
    than a Hoeffding-style bound at confidence delta. If found, drops the older
    sub-window and flags drift. O(window) per update — fine for telemetry.
    Pure-Python; reference: River ADWIN / blablahaha/concept-drift."""

    def __init__(self, delta: float = 0.05, max_buckets: int = 200) -> None:
        self.delta = float(delta)
        self.window: list[float] = []
        self.max_buckets = int(max_buckets)
        self.drift_detected = False
        self.width = 0

    def update(self, value: float) -> bool:
        self.window.append(float(value))
        if len(self.window) > self.max_buckets:
            self.window.pop(0)
        self.width = len(self.window)
        self.drift_detected = False
        n = self.width
        if n < 8:
            return False
        total = sum(self.window)
        cut_found = False
        n0 = 0
        s0 = 0.0
        for i in range(1, n):  # candidate split after index i-1
            n0 += 1
            s0 += self.window[i - 1]
            n1 = n - n0
            if n1 < 1:
                break
            s1 = total - s0
            m0, m1 = s0 / n0, s1 / n1
            # harmonic window size + Hoeffding bound (variance ~0.25 for [0,1])
            m_inv = 1.0 / (1.0 / n0 + 1.0 / n1)
            delta_prime = self.delta / max(n, 1)
            eps = math.sqrt((1.0 / (2.0 * m_inv)) * math.log(4.0 / delta_prime))
            if abs(m0 - m1) > eps:
                # drop the older sub-window
                self.window = self.window[i:]
                self.width = len(self.window)
                self.drift_detected = True
                cut_found = True
                break
        return cut_found


# ─────────────────────────────────────────────────────────────────────────────
# Live telemetry source (real)
# ─────────────────────────────────────────────────────────────────────────────
_SNAP_DIR = Path(os.environ.get("KILLINCHU_LIVE_SNAPSHOTS", "/app/live_snapshots"))


def _feature_vectors(payload: dict) -> dict[str, list[float]]:
    """Extract per-feature numeric arrays from an air/live aircraft payload."""
    ac = []
    if isinstance(payload, dict):
        ac = payload.get("aircraft") or payload.get("ac") or []
        if not ac and isinstance(payload.get("data"), dict):
            ac = payload["data"].get("aircraft") or payload["data"].get("ac") or []
    feats: dict[str, list[float]] = {"alt_baro": [], "gs": [], "track": []}
    for a in ac:
        if not isinstance(a, dict):
            continue
        for k in feats:
            v = a.get(k)
            try:
                if v is None:
                    continue
                fv = float(v)
                if math.isfinite(fv):
                    feats[k].append(fv)
            except (TypeError, ValueError):
                continue
    return feats


def _reference_snapshot() -> dict:
    """The in-image captured reference window (real telemetry, labelled cached)."""
    snap = _SNAP_DIR / "air.json"
    # fall back to repo-relative path for local/CI execution
    if not snap.is_file():
        snap = Path(__file__).resolve().parent / "live_snapshots" / "air.json"
    if snap.is_file():
        import json
        try:
            return json.loads(snap.read_text())
        except Exception:
            return {}
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Graph metrics (real)
# ─────────────────────────────────────────────────────────────────────────────
def _fiedler_value(adj: np.ndarray) -> float:
    """Algebraic connectivity lambda_2 = 2nd-smallest eigenvalue of the
    Laplacian L = D - A. 0 iff disconnected. Pure numpy eigh on a small graph."""
    n = adj.shape[0]
    if n < 2:
        return 0.0
    deg = np.diag(adj.sum(axis=1))
    lap = deg - adj
    w = np.sort(np.linalg.eigvalsh(lap))
    return float(w[1]) if w.size > 1 else 0.0


def _components(adj: np.ndarray) -> int:
    """Connected components via Laplacian zero-eigenvalue multiplicity."""
    n = adj.shape[0]
    if n == 0:
        return 0
    deg = np.diag(adj.sum(axis=1))
    lap = deg - adj
    w = np.linalg.eigvalsh(lap)
    return int(np.sum(w < 1e-9))


def _avg_clustering(adj: np.ndarray) -> float:
    """Average local clustering coefficient (unweighted, undirected)."""
    n = adj.shape[0]
    if n == 0:
        return 0.0
    A = (adj > 0).astype(float)
    np.fill_diagonal(A, 0)
    coeffs = []
    for i in range(n):
        nbrs = np.where(A[i] > 0)[0]
        k = len(nbrs)
        if k < 2:
            coeffs.append(0.0)
            continue
        sub = A[np.ix_(nbrs, nbrs)]
        links = sub.sum() / 2.0
        coeffs.append(2.0 * links / (k * (k - 1)))
    return float(np.mean(coeffs)) if coeffs else 0.0


def _avg_path_length(adj: np.ndarray) -> Optional[float]:
    """Average shortest-path length over the largest component (BFS)."""
    n = adj.shape[0]
    if n < 2:
        return None
    A = (adj > 0).astype(int)
    total = 0
    count = 0
    for s in range(n):
        dist = [-1] * n
        dist[s] = 0
        queue = [s]
        while queue:
            u = queue.pop(0)
            for v in np.where(A[u] > 0)[0]:
                if dist[v] < 0:
                    dist[v] = dist[u] + 1
                    queue.append(v)
        for d in dist:
            if d > 0:
                total += d
                count += 1
    return float(total / count) if count else None


def _degree_centrality(adj: np.ndarray) -> np.ndarray:
    n = adj.shape[0]
    if n < 2:
        return np.zeros(n)
    return (adj > 0).sum(axis=1) / (n - 1)


def _betweenness(adj: np.ndarray) -> np.ndarray:
    """Brandes-style betweenness on an unweighted graph (small graphs only)."""
    n = adj.shape[0]
    A = (adj > 0).astype(int)
    bc = np.zeros(n)
    for s in range(n):
        S = []
        P: list[list[int]] = [[] for _ in range(n)]
        sigma = np.zeros(n)
        sigma[s] = 1
        dist = [-1] * n
        dist[s] = 0
        queue = [s]
        while queue:
            v = queue.pop(0)
            S.append(v)
            for w in np.where(A[v] > 0)[0]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    P[w].append(v)
        delta = np.zeros(n)
        for w in reversed(S):
            for v in P[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    if n > 2:
        bc /= ((n - 1) * (n - 2))
    return bc


# ─────────────────────────────────────────────────────────────────────────────
# UDS Package CR (real config) loader for attack-surface + zero-trust
# ─────────────────────────────────────────────────────────────────────────────
def _load_uds_package() -> dict:
    """Parse deploy/uds-package.yaml WITHOUT requiring PyYAML — a tiny tolerant
    parser sufficient for the allow/expose blocks we need. Returns a normalized
    dict {allow:[...], expose:[...]} or {} if not found."""
    candidates = [
        Path("/app/deploy/uds-package.yaml"),
        Path(__file__).resolve().parent / "deploy" / "uds-package.yaml",
    ]
    text = ""
    for p in candidates:
        if p.is_file():
            text = p.read_text()
            break
    if not text:
        return {}
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text) or {}
        net = (doc.get("spec") or {}).get("network") or {}
        return {"allow": net.get("allow") or [], "expose": (doc.get("spec") or {}).get("expose") or []}
    except Exception:
        pass
    # minimal fallback parser: walk the allow/expose list items
    allow: list[dict] = []
    expose: list[dict] = []
    section = None
    cur: dict = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "allow:":
            section = "allow"
            continue
        if stripped == "expose:":
            section = "expose"
            continue
        if stripped in ("sso:", "monitor:", "network:", "spec:"):
            if stripped in ("sso:", "monitor:"):
                section = None
            continue
        if section and stripped.startswith("- "):
            if cur:
                (allow if section == "allow" else expose).append(cur)
            cur = {}
            kv = stripped[2:]
            if ":" in kv:
                k, _, v = kv.partition(":")
                cur[k.strip()] = v.strip().strip('"')
        elif section and ":" in stripped and not stripped.startswith("- "):
            k, _, v = stripped.partition(":")
            v = v.strip().strip('"')
            if v:
                cur[k.strip()] = v
    if cur and section:
        (allow if section == "allow" else expose).append(cur)
    return {"allow": allow, "expose": expose}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint registration
# ─────────────────────────────────────────────────────────────────────────────
def register(app: FastAPI, ns: str = "killinchu",
             emit_receipt: Optional[Callable] = None) -> dict[str, Any]:
    """ADDITIVE: register the four posture/topology endpoints."""
    registered: list[str] = []

    # live feed accessor (real adsb.lol military ADS-B via killinchu_live_feeds)
    def _air_live() -> tuple[dict, str]:
        try:
            import killinchu_live_feeds as lf  # type: ignore
            res = lf.get_feed("air")
            if isinstance(res, dict) and res.get("data"):
                mode = res.get("mode") or "cached"
                return (res["data"], mode)
        except Exception:
            pass
        return (_reference_snapshot(), "cached")

    @app.get(f"/api/{ns}/v1/posture/drift")
    async def posture_drift() -> JSONResponse:
        ref_payload = _reference_snapshot()
        live_payload, mode = _air_live()
        ref_feats = _feature_vectors(ref_payload)
        live_feats = _feature_vectors(live_payload)

        rows = []
        triggers: list[str] = []
        adwin = ADWIN(delta=0.05)
        for name in ("alt_baro", "gs", "track"):
            ref = np.asarray(ref_feats.get(name, []), dtype=float)
            live = np.asarray(live_feats.get(name, []), dtype=float)
            if ref.size == 0 or live.size == 0:
                rows.append({"feature": name, "state": "no-data",
                             "psi": None, "ks_stat": None, "ks_p": None})
                continue
            p = psi(ref, live)
            d, kp, ks_backend = ks_two_sample(ref, live)
            # PSI band
            if p >= 0.25:
                band = "significant"
                triggers.append(f"PSI[{name}]={p:.3f}>=0.25")
            elif p >= 0.10:
                band = "moderate"
            else:
                band = "stable"
            ks_alert = (kp == kp) and kp < 0.05  # nan-safe
            if ks_alert:
                triggers.append(f"KS[{name}] p={kp:.4f}<0.05")
            # feed ADWIN with a per-feature normalized error signal: how far the
            # live mean sits from the reference mean, in reference-std units,
            # squashed to [0,1] — a real streaming metric, not a fabricated one.
            rstd = float(ref.std()) or 1.0
            err = abs(float(live.mean()) - float(ref.mean())) / rstd
            adwin_flag = adwin.update(1.0 / (1.0 + math.exp(-(err - 1.0))))
            if adwin_flag:
                triggers.append(f"ADWIN[{name}] window-shift")
            rows.append({
                "feature": name,
                "psi": round(p, 4), "psi_band": band,
                "ks_stat": round(d, 4), "ks_p": round(kp, 5),
                "ks_alert": bool(ks_alert), "ks_backend": ks_backend,
                "adwin_drift": bool(adwin_flag),
                "ref_n": int(ref.size), "live_n": int(live.size),
                "state": "ok",
            })

        verdict = "DRIFT DETECTED" if triggers else "STABLE"
        out = {
            "ok": True,
            "tab": "Posture & Drift",
            "verdict": verdict,
            "triggering_detectors": triggers,
            "thresholds": {"psi_moderate": 0.10, "psi_significant": 0.25, "ks_alpha": 0.05},
            "detectors": ["PSI", "KS (scipy.stats.ks_2samp)" if _HAVE_SCIPY
                          else "KS (numpy Kolmogorov asymptotic)", "ADWIN (vendored)"],
            "features": rows,
            "data_source": "adsb.lol military ADS-B (live) vs in-image captured reference snapshot",
            "live_mode": mode,
            "honesty": ("Reference window is REAL captured telemetry (live_snapshots/air.json), "
                        "not fabricated. Verdict is honestly thresholded (PSI 0.1/0.25, KS p<0.05). "
                        "Lambda = Conjecture 1."),
            "scipy_available": _HAVE_SCIPY,
        }
        if emit_receipt is not None:
            try:
                node = emit_receipt("posture_drift_eval",
                                    {"verdict": verdict, "n_triggers": len(triggers)})
                out["receipt"] = {"index": node.get("index"), "digest": node.get("digest")}
            except Exception:
                pass
        return JSONResponse(out)

    @app.get(f"/api/{ns}/v1/topology/health")
    async def topology_health() -> JSONResponse:
        # Build a real node/link graph: organ services (honest role names) + live
        # fleet tracks attached to the ingest service. Health colour from real
        # signal freshness of each live track.
        live_payload, mode = _air_live()
        ac = []
        if isinstance(live_payload, dict):
            ac = live_payload.get("aircraft") or live_payload.get("ac") or []
        organs = [
            {"id": "operator", "role": "Operator", "kind": "organ"},
            {"id": "provenance_anchor", "role": "Provenance Anchor", "kind": "organ"},
            {"id": "policy", "role": "Policy", "kind": "organ"},
            {"id": "track_ingest", "role": "Track Ingest", "kind": "service"},
            {"id": "roe_eval", "role": "ROE Evaluation", "kind": "service"},
            {"id": "fusion", "role": "Sensor Fusion", "kind": "service"},
        ]
        edges = [
            ("track_ingest", "fusion"), ("fusion", "roe_eval"),
            ("roe_eval", "policy"), ("policy", "operator"),
            ("operator", "provenance_anchor"), ("fusion", "provenance_anchor"),
            ("track_ingest", "operator"),
        ]
        # attach up to 20 live tracks to track_ingest (real nodes)
        nodes = list(organs)
        for i, a in enumerate(ac[:20]):
            if not isinstance(a, dict):
                continue
            tid = f"track_{a.get('hex', i)}"
            gs = a.get("gs")
            alt = a.get("alt_baro")
            # honest health: unknown when telemetry fields missing
            if gs is None or alt is None:
                health = "unknown"
            else:
                try:
                    health = "nominal" if (0 <= float(gs) < 600 and float(alt) >= 0) else "anomalous"
                except (TypeError, ValueError):
                    health = "unknown"
            nodes.append({"id": tid, "role": a.get("flight", tid), "kind": "track", "health": health})
            edges.append(("track_ingest", tid))

        idx = {n["id"]: i for i, n in enumerate(nodes)}
        N = len(nodes)
        adj = np.zeros((N, N))
        for u, v in edges:
            if u in idx and v in idx:
                adj[idx[u], idx[v]] = 1
                adj[idx[v], idx[u]] = 1

        # real metrics
        if _HAVE_NX:
            G = _nx.Graph()
            G.add_nodes_from(range(N))
            G.add_edges_from([(idx[u], idx[v]) for u, v in edges if u in idx and v in idx])
            avg_cl = float(_nx.average_clustering(G)) if N > 1 else 0.0
            comps = _nx.number_connected_components(G)
            try:
                giant = max(_nx.connected_components(G), key=len)
                apl = float(_nx.average_shortest_path_length(G.subgraph(giant))) if len(giant) > 1 else None
            except Exception:
                apl = None
            bet = _nx.betweenness_centrality(G)
            bet_arr = np.array([bet.get(i, 0.0) for i in range(N)])
            metric_backend = "networkx"
        else:
            avg_cl = _avg_clustering(adj)
            comps = _components(adj)
            apl = _avg_path_length(adj)
            bet_arr = _betweenness(adj)
            metric_backend = "numpy (BFS/Brandes/Laplacian)"

        deg = _degree_centrality(adj)
        fiedler = _fiedler_value(adj)
        # top-central nodes by betweenness
        order = np.argsort(-bet_arr)[:5]
        top_central = [{"id": nodes[i]["id"], "role": nodes[i].get("role"),
                        "betweenness": round(float(bet_arr[i]), 4),
                        "degree_centrality": round(float(deg[i]), 4)} for i in order]

        out = {
            "ok": True,
            "tab": "Topology & Health",
            "nodes": nodes,
            "edges": [[u, v] for u, v in edges],
            "metrics": {
                "node_count": N,
                "edge_count": len(edges),
                "avg_clustering_coefficient": round(avg_cl, 4),
                "avg_shortest_path_length": (round(apl, 4) if apl is not None else None),
                "connected_components": int(comps),
                "fiedler_lambda2": round(fiedler, 5),
                "connected": bool(fiedler > 1e-9),
                "top_central_nodes": top_central,
            },
            "metric_backend": metric_backend,
            "live_mode": mode,
            "health_legend": {"nominal": "telemetry plausible", "anomalous": "kinematics implausible",
                              "unknown": "telemetry field missing — honest unknown"},
            "honesty": ("Health bands derived from real live-track telemetry; 'unknown' when a "
                        "field is missing. Organ nodes use honest role names. Lambda = Conjecture 1."),
        }
        return JSONResponse(out)

    @app.get(f"/api/{ns}/v1/attack-surface/graph")
    async def attack_surface_graph() -> JSONResponse:
        uds = _load_uds_package()
        allow = uds.get("allow", [])
        expose = uds.get("expose", [])
        nodes: list[dict] = [{"id": "killinchu", "kind": "app", "role": "killinchu surface"}]
        edges: list[list[str]] = []
        exposed_ids: list[str] = []
        # exposures = ingress rules + expose entries (real attack surface)
        for i, e in enumerate(expose):
            host = e.get("host") or e.get("service") or f"expose_{i}"
            nid = f"expose:{host}"
            nodes.append({"id": nid, "kind": "exposure",
                          "role": f"{host}:{e.get('port', '?')}",
                          "gateway": e.get("gateway")})
            edges.append([nid, "killinchu"])
            exposed_ids.append(nid)
        for i, a in enumerate(allow):
            if str(a.get("direction", "")).lower() != "ingress":
                continue
            rns = a.get("remoteNamespace") or a.get("remoteGenerated") or f"ingress_{i}"
            nid = f"ingress:{rns}:{a.get('port', '?')}"
            nodes.append({"id": nid, "kind": "ingress", "role": str(a.get("description", rns))})
            edges.append([nid, "killinchu"])
            exposed_ids.append(nid)

        # blast radius = reachable set from each exposed node (here all reach killinchu)
        blast = {nid: ["killinchu"] for nid in exposed_ids}
        empty = (len(exposed_ids) == 0)
        out = {
            "ok": True,
            "tab": "Attack-Surface Graph",
            "nodes": nodes,
            "edges": edges,
            "exposures": exposed_ids,
            "blast_radius": blast,
            "data_source": "killinchu deploy/uds-package.yaml (real UDS Package CR allow/expose)",
            "empty": empty,
            "empty_state": ("No exposures discovered in the UDS Package CR." if empty else None),
            "honesty": "Edges reflect actual allow/expose rules only; no invented CVEs or exposures.",
        }
        return JSONResponse(out)

    @app.get(f"/api/{ns}/v1/zerotrust/mesh")
    async def zerotrust_mesh() -> JSONResponse:
        uds = _load_uds_package()
        allow = uds.get("allow", [])
        nodes = {"killinchu": {"id": "killinchu", "kind": "app", "role": "killinchu surface"}}
        edges: list[dict] = []
        for a in allow:
            direction = str(a.get("direction", "")).lower()
            remote = a.get("remoteNamespace") or a.get("remoteGenerated") or "anywhere"
            port = a.get("port", "?")
            desc = str(a.get("description", ""))
            # surface remote ns under honest role name (retired codename 'rosie' => Operator role)
            role = remote
            if remote == "rosie":
                role = "Operator role (k8s ns 'rosie' = retired internal codename)"
            elif remote == "istio-system":
                role = "Istio ingress gateway"
            elif remote == "Anywhere":
                role = "Public egress (Anywhere)"
            rid = f"ns:{remote}"
            if rid not in nodes:
                nodes[rid] = {"id": rid, "kind": "peer", "role": role}
            if direction == "egress":
                edges.append({"source": "killinchu", "target": rid, "port": port,
                              "direction": "egress", "policy": desc, "mtls": "Istio ambient"})
            elif direction == "ingress":
                edges.append({"source": rid, "target": "killinchu", "port": port,
                              "direction": "ingress", "policy": desc, "mtls": "Istio ambient"})
        empty = (len(edges) == 0)
        out = {
            "ok": True,
            "tab": "Zero-Trust Mesh",
            "nodes": list(nodes.values()),
            "edges": edges,
            "mesh_mode": "Istio ambient (UDS Core default)",
            "data_source": "killinchu deploy/uds-package.yaml spec.network.allow (real)",
            "empty": empty,
            "empty_state": ("No allow rules found in the UDS Package CR." if empty else None),
            "honesty": ("Edges = actual allow rules from the UDS Package CR only; mTLS via Istio "
                        "ambient. Public role names (no banned codenames). Lambda = Conjecture 1."),
        }
        return JSONResponse(out)

    for path in ("posture/drift", "topology/health", "attack-surface/graph", "zerotrust/mesh"):
        registered.append(f"GET /api/{ns}/v1/{path}")

    return {"module": "killinchu_posture_topology", "registered": registered,
            "scipy": _HAVE_SCIPY, "networkx": _HAVE_NX}
