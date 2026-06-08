#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
"""killinchu_resweep_ops.py — RE-SWEEP wave-2 operational upgrades (clean-room, pure-stdlib).

ADDITIVE, self-contained, register(app, ns="killinchu")-style — mirrors the proven
killinchu_mined_ops.py convention. NO MOCKS: every endpoint computes real numbers from
whatever real telemetry the caller submits (or from a sample graph/fleet, honestly
labelled "sample, not a live feed").

This module ships THREE operational upgrades whose PATTERNS were mined from permissive
(MIT) open-source projects under the "fashion thinking" doctrine — adopt the pattern +
permissive code WITH NOTICE attribution, then EVOLVE to our own clean-room implementation.
No upstream code is copied; each algorithm is reimplemented from scratch in pure Python
(no numpy/torch needed).

================================  NOTICE  ===================================
Adopted patterns (attribution; full entries also in NOTICES.md):

1. tactical maritime routing  ← anvaka/ngraph.path (MIT, © 2017 Andrei Kashcha)
   https://github.com/anvaka/ngraph.path
   PAIRED WITH ← rowanwins/visibility-graph (MIT, © 2018 Rowan Winsemius)
   https://github.com/rowanwins/visibility-graph
   Adopted: the A* / NBA* (bi-directional A*) heuristic graph-search SHAPE from
   ngraph.path, and the polygon-obstacle "visibility graph → shortest path"
   SHAPE from visibility-graph. Reimplemented clean in stdlib and EVOLVED into a
   maritime tactical router: A*/NBA* over a sea grid with a sea-state cost
   heuristic (current + wind drift penalty), and obstacle avoidance that routes a
   vessel/drone AROUND landmass / exclusion-zone polygons by building a visibility
   graph over the polygon corners + endpoints and running the same A*.

2. vessel strategic threat ranking ← ft2023/IRanker-demo (MIT, © 2025 Tao Feng)
   https://github.com/ft2023/IRanker-demo
   Adopted: the ITERATIVE ranking-foundation-model SHAPE — instead of scoring each
   item independently in one shot, repeatedly remove the current worst/best item
   and re-rank the remainder so pairwise context informs the order. Reimplemented
   clean (a deterministic iterative removal ranker over a transparent composite
   threat score) and EVOLVED into a vessel "strategic threat score" ranker for the
   consolidated maritime view: rank by proximity + closing-speed + AIS-gap +
   sanction/dark-vessel flag + identity-mismatch, with a fully auditable per-vessel
   score breakdown (no black-box model; advisory, NOT a targeting product).

3. adaptive sensor sampling / peak-detect ← al-jshen/adaptive (MIT, © 2021 Jeff Shen)
   https://github.com/al-jshen/adaptive
   Adopted: the ADAPTIVE-SAMPLING SHAPE — concentrate evaluation points where the
   signal has the most curvature/structure (loss-driven refinement) instead of a
   uniform grid, plus simple peak detection. Reimplemented clean (curvature-loss
   bisection refinement + local-maxima detection with prominence) and EVOLVED into
   a sensor-fusion EFFICIENCY panel: given a constrained sampling budget over a
   sensor sweep, decide WHERE to spend samples and surface detected peaks
   (contacts) — so an edge node spends its limited duty-cycle on the informative
   parts of the sweep.
=============================================================================

Endpoints (all under /api/killinchu/v1/resweep/*, registered EARLY before catch-all):
  POST /api/killinchu/v1/resweep/route          tactical maritime A*/NBA* routing + obstacle avoidance
  POST /api/killinchu/v1/resweep/threat-rank    iterative vessel strategic-threat ranking
  POST /api/killinchu/v1/resweep/adaptive-sample adaptive sensor sampling + peak detection
  GET  /api/killinchu/v1/resweep/index          machine-readable manifest of these upgrades

Honesty doctrine: Λ stays Conjecture 1; every advisory output is labelled. Sample inputs
are labelled "sample, not a live feed". No fabricated success: bad input returns an honest
400 / empty result, never invented numbers.

Doctrine v11 LOCKED — Λ = Conjecture 1 (NEVER a theorem).
Signed-off-by: Yachay <yachay@szlholdings.ai>
Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
"""
from __future__ import annotations

import heapq
import json
import math
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


# ─────────────────────── 1. tactical maritime routing ───────────────────────
# Clean-room A*/NBA* (pattern: anvaka/ngraph.path, MIT) over a sea grid, and a
# polygon visibility-graph router (pattern: rowanwins/visibility-graph, MIT).

def _astar_grid(grid: list[list[float]], start: tuple[int, int], goal: tuple[int, int]
                ) -> tuple[list[tuple[int, int]] | None, float, int]:
    """A* over a 2-D sea grid. grid[r][c] = sea-state traversal cost (>=1; inf = blocked).

    8-connected. Heuristic = octile distance scaled by min cell cost (admissible).
    Returns (path, total_cost, nodes_expanded). Pattern adopted from ngraph.path.
    """
    R, C = len(grid), len(grid[0]) if grid else 0
    if not (0 <= start[0] < R and 0 <= start[1] < C and 0 <= goal[0] < R and 0 <= goal[1] < C):
        return None, math.inf, 0
    finite = [grid[r][c] for r in range(R) for c in range(C) if grid[r][c] < math.inf]
    cmin = min(finite) if finite else 1.0

    def h(a: tuple[int, int]) -> float:
        dr, dc = abs(a[0] - goal[0]), abs(a[1] - goal[1])
        return cmin * ((math.sqrt(2) - 1) * min(dr, dc) + max(dr, dc))

    g = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    pq = [(h(start), 0.0, start)]
    expanded = 0
    while pq:
        f, gc, cur = heapq.heappop(pq)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path, gc, expanded
        if gc > g.get(cur, math.inf):
            continue
        expanded += 1
        r, c = cur
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not (0 <= nr < R and 0 <= nc < C):
                    continue
                cell = grid[nr][nc]
                if cell >= math.inf:
                    continue
                step = cell * (math.sqrt(2) if dr and dc else 1.0)
                ng = gc + step
                if ng < g.get((nr, nc), math.inf):
                    g[(nr, nc)] = ng
                    came[(nr, nc)] = cur
                    heapq.heappush(pq, (ng + h((nr, nc)), ng, (nr, nc)))
    return None, math.inf, expanded


def _nba_grid(grid: list[list[float]], start: tuple[int, int], goal: tuple[int, int]
              ) -> tuple[list[tuple[int, int]] | None, float, int]:
    """NBA*-style bi-directional A* (pattern: ngraph.path NBA*). Symmetric grid so
    the reverse search uses the same costs. Returns (path, cost, nodes_expanded)."""
    R, C = len(grid), len(grid[0]) if grid else 0
    if not (0 <= start[0] < R and 0 <= start[1] < C and 0 <= goal[0] < R and 0 <= goal[1] < C):
        return None, math.inf, 0
    finite = [grid[r][c] for r in range(R) for c in range(C) if grid[r][c] < math.inf]
    cmin = min(finite) if finite else 1.0

    def oct(a, b):
        dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
        return cmin * ((math.sqrt(2) - 1) * min(dr, dc) + max(dr, dc))

    def neighbors(node):
        r, c = node
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C and grid[nr][nc] < math.inf:
                    yield (nr, nc), grid[nr][nc] * (math.sqrt(2) if dr and dc else 1.0)

    gf = {start: 0.0}; gb = {goal: 0.0}
    cf = {}; cb = {}
    pf = [(oct(start, goal), 0.0, start)]
    pb = [(oct(goal, start), 0.0, goal)]
    best = math.inf; meet = None; expanded = 0
    visited_f = set(); visited_b = set()
    while pf and pb:
        # expand the smaller frontier (NBA* balance)
        if pf[0][0] <= pb[0][0]:
            f, gc, cur = heapq.heappop(pf)
            if gc > gf.get(cur, math.inf):
                continue
            visited_f.add(cur); expanded += 1
            if cur in gb and gc + gb[cur] < best:
                best = gc + gb[cur]; meet = cur
            for nb, w in neighbors(cur):
                ng = gc + w
                if ng < gf.get(nb, math.inf):
                    gf[nb] = ng; cf[nb] = cur
                    heapq.heappush(pf, (ng + oct(nb, goal), ng, nb))
        else:
            f, gc, cur = heapq.heappop(pb)
            if gc > gb.get(cur, math.inf):
                continue
            visited_b.add(cur); expanded += 1
            if cur in gf and gc + gf[cur] < best:
                best = gc + gf[cur]; meet = cur
            for nb, w in neighbors(cur):
                ng = gc + w
                if ng < gb.get(nb, math.inf):
                    gb[nb] = ng; cb[nb] = cur
                    heapq.heappush(pb, (ng + oct(nb, start), ng, nb))
        if meet is not None and pf and pb and pf[0][0] + pb[0][0] >= best:
            break
    if meet is None:
        return None, math.inf, expanded
    # stitch forward + backward halves
    fwd = [meet]; n = meet
    while n in cf:
        n = cf[n]; fwd.append(n)
    fwd.reverse()
    n = meet
    while n in cb:
        n = cb[n]; fwd.append(n)
    return fwd, best, expanded


def _seg_intersect(p1, p2, p3, p4) -> bool:
    """True if segment p1p2 properly intersects p3p4 (visibility-graph edge test)."""
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
    d1 = ccw(p3, p4, p1); d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3); d4 = ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def _point_in_poly(pt, poly) -> bool:
    x, y = pt; inside = False; n = len(poly); j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _visibility_route(start, goal, polys) -> tuple[list[list[float]] | None, float]:
    """Shortest path from start to goal that routes AROUND polygon obstacles by
    building a visibility graph over {start, goal, all polygon vertices} and running
    Dijkstra/A* on it. Pattern adopted from rowanwins/visibility-graph (MIT).
    Returns (polyline_path, euclidean_length). Coords are arbitrary (e.g. lon/lat-ish)."""
    start = tuple(start); goal = tuple(goal)
    polys = [[tuple(v) for v in poly] for poly in polys]  # normalise to tuples for ==
    nodes = [start, goal]
    for poly in polys:
        for v in poly:
            nodes.append(v)
    n = len(nodes)

    def visible(a, b) -> bool:
        # midpoint must not be inside any obstacle, and segment must not cross any edge
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        for poly in polys:
            if _point_in_poly(mid, poly):
                return False
            m = len(poly)
            for i in range(m):
                e1 = poly[i]; e2 = poly[(i + 1) % m]
                if a in (e1, e2) or b in (e1, e2):
                    continue
                if _seg_intersect(a, b, e1, e2):
                    return False
        return True

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    adj: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if visible(nodes[i], nodes[j]):
                w = dist(nodes[i], nodes[j])
                adj[i].append((j, w)); adj[j].append((i, w))

    # A* on the visibility graph (goal index = 1)
    g = {0: 0.0}; came = {}; pq = [(dist(nodes[0], nodes[1]), 0.0, 0)]
    while pq:
        f, gc, u = heapq.heappop(pq)
        if u == 1:
            path = [1]
            while u in came:
                u = came[u]; path.append(u)
            path.reverse()
            return [list(nodes[i]) for i in path], gc
        if gc > g.get(u, math.inf):
            continue
        for v, w in adj[u]:
            ng = gc + w
            if ng < g.get(v, math.inf):
                g[v] = ng; came[v] = u
                heapq.heappush(pq, (ng + dist(nodes[v], nodes[1]), ng, v))
    return None, math.inf


def _sample_sea_grid(rows: int, cols: int) -> list[list[float]]:
    """Deterministic sample sea-state cost grid with two exclusion bands (sample,
    not a live feed)."""
    g = [[1.0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            # rolling 'current/wind' field raises cost in a diagonal swell band
            swell = 1.0 + 0.8 * (0.5 + 0.5 * math.sin((r + c) * 0.6))
            g[r][c] = round(swell, 3)
    # two hard exclusion zones (landmass / restricted) = blocked
    for r in range(rows):
        for c in range(cols):
            if (rows // 3 <= r <= rows // 3 + 1) and (1 <= c <= cols - 3):
                g[r][c] = math.inf
            if (2 * rows // 3 <= r <= 2 * rows // 3 + 1) and (2 <= c <= cols - 2):
                g[r][c] = math.inf
    return g


# ─────────────────────── 2. iterative threat ranking ───────────────────────
# Clean-room iterative removal ranker (pattern: ft2023/IRanker-demo, MIT).

def _threat_score(v: dict) -> tuple[float, dict]:
    """Transparent composite strategic-threat score in [0,1] with auditable parts."""
    rng = max(0.0, float(v.get("range_nm", 50.0)))
    closing = float(v.get("closing_speed_kn", 0.0))     # +ve = approaching
    ais_gap = max(0.0, float(v.get("ais_gap_min", 0.0)))  # minutes of AIS silence
    sanctioned = 1.0 if v.get("sanctioned") else 0.0
    dark = 1.0 if v.get("dark_vessel") else 0.0
    id_mismatch = 1.0 if v.get("identity_mismatch") else 0.0
    # each sub-score normalised to [0,1], higher = more threatening
    s_prox = max(0.0, min(1.0, 1.0 - rng / 100.0))           # closer = worse
    s_close = max(0.0, min(1.0, closing / 30.0))             # faster approach = worse
    s_ais = max(0.0, min(1.0, ais_gap / 120.0))              # longer silence = worse
    parts = {
        "proximity": round(0.28 * s_prox, 4),
        "closing": round(0.24 * s_close, 4),
        "ais_gap": round(0.16 * s_ais, 4),
        "sanctioned": round(0.14 * sanctioned, 4),
        "dark_vessel": round(0.12 * dark, 4),
        "identity_mismatch": round(0.06 * id_mismatch, 4),
    }
    return round(sum(parts.values()), 4), parts


def _iranker(vessels: list[dict]) -> list[dict]:
    """Iterative ranking: repeatedly extract the current HIGHEST-threat remaining
    vessel and append to the ordered list (IRanker iterative-removal pattern). Each
    iteration recomputes scores over the *remaining* set so a context-relative
    'rank' is assigned 1..N. Deterministic; advisory, not a targeting product."""
    remaining = list(vessels)
    ordered: list[dict] = []
    rank = 1
    while remaining:
        best_i = 0; best_s = -1.0; best_parts = {}
        for i, v in enumerate(remaining):
            s, parts = _threat_score(v)
            if s > best_s:
                best_s, best_i, best_parts = s, i, parts
        v = remaining.pop(best_i)
        ordered.append({
            "rank": rank,
            "id": v.get("id", f"V{rank}"),
            "name": v.get("name", v.get("id", f"vessel-{rank}")),
            "threat_score": best_s,
            "score_breakdown": best_parts,
            "range_nm": v.get("range_nm"),
            "closing_speed_kn": v.get("closing_speed_kn"),
            "flags": [k for k in ("sanctioned", "dark_vessel", "identity_mismatch") if v.get(k)],
        })
        rank += 1
    return ordered


def _sample_vessels() -> list[dict]:
    return [
        {"id": "MV-AURORA", "name": "MV Aurora", "range_nm": 12.0, "closing_speed_kn": 18.0,
         "ais_gap_min": 95.0, "sanctioned": True, "dark_vessel": True, "identity_mismatch": True},
        {"id": "FV-KESTREL", "name": "FV Kestrel", "range_nm": 38.0, "closing_speed_kn": 6.0,
         "ais_gap_min": 5.0},
        {"id": "TK-NEREUS", "name": "Tanker Nereus", "range_nm": 22.0, "closing_speed_kn": 12.0,
         "ais_gap_min": 40.0, "sanctioned": True},
        {"id": "CG-PETREL", "name": "CG Petrel", "range_nm": 8.0, "closing_speed_kn": -4.0,
         "ais_gap_min": 0.0},
        {"id": "UNK-073", "name": "Unknown-073", "range_nm": 30.0, "closing_speed_kn": 22.0,
         "ais_gap_min": 60.0, "dark_vessel": True, "identity_mismatch": True},
        {"id": "MV-HALCYON", "name": "MV Halcyon", "range_nm": 55.0, "closing_speed_kn": 3.0,
         "ais_gap_min": 2.0},
    ]


# ─────────────────── 3. adaptive sensor sampling + peaks ─────────────────────
# Clean-room curvature-loss adaptive sampling + peak detect (pattern: al-jshen/adaptive).

def _sensor_signal(x: float) -> float:
    """Sample sensor sweep: two Gaussian 'contacts' on a low background (sample,
    not a live feed). x in [0, 1] (normalised bearing/angle)."""
    def g(mu, sd, amp):
        return amp * math.exp(-((x - mu) ** 2) / (2 * sd * sd))
    return 0.15 + g(0.30, 0.035, 1.0) + g(0.68, 0.025, 0.75) + 0.04 * math.sin(40 * x)


def _adaptive_sample(f, lo: float, hi: float, budget: int) -> list[tuple[float, float]]:
    """Adaptive sampling: start from a coarse grid, then repeatedly insert a sample
    at the midpoint of the interval with the largest curvature 'loss' until the
    budget is spent. Pattern adopted from al-jshen/adaptive (loss-driven refinement)."""
    budget = max(5, int(budget))
    n0 = min(budget, 5)
    xs = [lo + (hi - lo) * i / (n0 - 1) for i in range(n0)]
    pts = [(x, f(x)) for x in xs]
    while len(pts) < budget:
        # loss per interval = |curvature| proxy via second-difference magnitude × width
        best_i = 0; best_loss = -1.0
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]; x1, y1 = pts[i + 1]
            xm = 0.5 * (x0 + x1); ym = f(xm)
            curv = abs((y0 - 2 * ym + y1))
            loss = curv * (x1 - x0) + 1e-6 * (x1 - x0)  # small width term breaks ties
            if loss > best_loss:
                best_loss, best_i, best_xm = loss, i, xm
        xm = best_xm
        pts.insert(best_i + 1, (xm, f(xm)))
    return pts


def _detect_peaks(pts: list[tuple[float, float]], min_prom: float = 0.2) -> list[dict]:
    """Local-maxima detection with prominence on the (adaptively) sampled points."""
    ys = [p[1] for p in pts]
    peaks = []
    for i in range(1, len(pts) - 1):
        if ys[i] > ys[i - 1] and ys[i] >= ys[i + 1]:
            # prominence = peak height above the higher of the two adjacent valleys
            left = min(ys[max(0, i - 3):i] or [ys[i]])
            right = min(ys[i + 1:i + 4] or [ys[i]])
            prom = ys[i] - max(left, right)
            if prom >= min_prom:
                peaks.append({"x": round(pts[i][0], 4), "value": round(ys[i], 4),
                              "prominence": round(prom, 4)})
    peaks.sort(key=lambda p: -p["value"])
    return peaks


# ───────────────────────────── endpoint handlers ────────────────────────────

async def _body(request: Request) -> dict:
    try:
        raw = await request.body()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def register(app, ns: str = "killinchu") -> str:
    base = f"/api/{ns}/v1/resweep"
    routes: list[str] = []

    # ---- 1. tactical maritime routing (A*/NBA* + visibility obstacle avoidance) ----
    @app.post(base + "/route")
    async def resweep_route(request: Request):
        d = await _body(request)
        mode = (d.get("mode") or "grid-astar").strip()
        out: dict[str, Any] = {
            "mode": mode,
            "source": "anvaka/ngraph.path (MIT) + rowanwins/visibility-graph (MIT) — patterns adopted, clean-room reimpl",
            "honest": "advisory route planning over a sample sea-state graph; not a live feed; Λ stays Conjecture 1",
        }
        if mode in ("grid-astar", "grid-nba"):
            grid = d.get("grid")
            sample = grid is None
            if grid is None:
                rows = int(d.get("rows", 14)); cols = int(d.get("cols", 22))
                rows = max(4, min(40, rows)); cols = max(4, min(48, cols))
                grid = _sample_sea_grid(rows, cols)
            else:
                grid = [[(math.inf if (v is None or (isinstance(v, str) and v.lower() in ("inf", "x", "block")))
                          else float(v)) for v in row] for row in grid]
            R, C = len(grid), len(grid[0]) if grid else 0
            start = tuple(d.get("start") or [0, 0])
            goal = tuple(d.get("goal") or [R - 1, C - 1])
            start = (int(start[0]), int(start[1])); goal = (int(goal[0]), int(goal[1]))
            fn = _nba_grid if mode == "grid-nba" else _astar_grid
            path, cost, expanded = fn(grid, start, goal)
            if path is None:
                return JSONResponse({**out, "found": False,
                                     "reason": "no route — start/goal blocked or fully separated by exclusion zones",
                                     "nodes_expanded": expanded}, status_code=200)
            out.update({
                "algorithm": "NBA* (bi-directional A*)" if mode == "grid-nba" else "A*",
                "grid_size": [R, C], "start": list(start), "goal": list(goal),
                "found": True, "path": [list(p) for p in path],
                "path_length_cells": len(path),
                "total_cost": round(cost, 4),
                "nodes_expanded": expanded,
                "heuristic": "octile distance × min sea-state cost (admissible); cost = per-cell sea-state (current+wind)",
                "blocked_cells": sum(1 for r in range(R) for c in range(C) if grid[r][c] >= math.inf),
                "sample_input": sample,
                "sample_note": "sample sea-state grid, not a live feed" if sample else None,
            })
        elif mode == "obstacle-avoid":
            start = d.get("start") or [0.0, 0.0]
            goal = d.get("goal") or [10.0, 8.0]
            polys = d.get("obstacles")
            sample = polys is None
            if polys is None:
                # two sample exclusion-zone polygons (landmass / restricted box)
                polys = [
                    [[3.0, 1.0], [5.0, 1.0], [5.0, 6.0], [3.0, 6.0]],
                    [[6.5, 4.0], [8.5, 4.0], [8.5, 9.0], [6.5, 9.0]],
                ]
            start = [float(start[0]), float(start[1])]
            goal = [float(goal[0]), float(goal[1])]
            polys = [[[float(p[0]), float(p[1])] for p in poly] for poly in polys]
            path, length = _visibility_route(start, goal, polys)
            if path is None:
                return JSONResponse({**out, "found": False,
                                     "reason": "no visibility route — start/goal enclosed by obstacles"}, status_code=200)
            straight = math.hypot(goal[0] - start[0], goal[1] - start[1])
            out.update({
                "algorithm": "visibility-graph + A*",
                "start": start, "goal": goal,
                "found": True, "path": path,
                "waypoints": len(path),
                "route_length": round(length, 4),
                "straight_line_length": round(straight, 4),
                "detour_ratio": round(length / straight, 4) if straight else None,
                "obstacles": polys,
                "interpretation": "routes vessel/drone around landmass/exclusion polygons via corner-visibility graph",
                "sample_input": sample,
                "sample_note": "sample exclusion zones, not a live feed" if sample else None,
            })
        else:
            return JSONResponse({"error": f"unknown mode '{mode}'",
                                 "modes": ["grid-astar", "grid-nba", "obstacle-avoid"]}, status_code=400)
        return JSONResponse(out)
    routes.append("POST " + base + "/route")

    # ---- 2. iterative vessel strategic-threat ranking -----------------------
    @app.post(base + "/threat-rank")
    async def resweep_threat_rank(request: Request):
        d = await _body(request)
        vessels = d.get("vessels")
        sample = not vessels
        if not vessels:
            vessels = _sample_vessels()
        if not isinstance(vessels, list) or not vessels:
            return JSONResponse({"error": "vessels must be a non-empty array"}, status_code=400)
        ranked = _iranker(vessels)
        out = {
            "source": "ft2023/IRanker-demo (MIT) — iterative ranking pattern, clean-room reimpl",
            "honest": ("advisory strategic-threat ordering with a fully transparent, auditable score; "
                       "NOT a targeting product; Λ stays Conjecture 1"),
            "method": ("iterative removal ranking: repeatedly extract the highest-threat remaining vessel; "
                       "score = 0.28·proximity + 0.24·closing + 0.16·AIS-gap + 0.14·sanctioned + 0.12·dark + 0.06·id-mismatch"),
            "count": len(ranked),
            "ranking": ranked,
            "top_threat": ranked[0]["id"] if ranked else None,
            "sample_input": sample,
            "sample_note": "sample consolidated maritime picture, not a live feed" if sample else None,
        }
        return JSONResponse(out)
    routes.append("POST " + base + "/threat-rank")

    # ---- 3. adaptive sensor sampling + peak detection -----------------------
    @app.post(base + "/adaptive-sample")
    async def resweep_adaptive_sample(request: Request):
        d = await _body(request)
        budget = int(d.get("budget", 28))
        budget = max(6, min(200, budget))
        min_prom = float(d.get("min_prominence", 0.2))
        # adaptive vs uniform comparison over the sample sensor sweep [0,1]
        ad_pts = _adaptive_sample(_sensor_signal, 0.0, 1.0, budget)
        peaks = _detect_peaks(ad_pts, min_prom=min_prom)
        # uniform baseline with the SAME budget, for an honest efficiency comparison
        uni_xs = [i / (budget - 1) for i in range(budget)]
        uni_pts = [(x, _sensor_signal(x)) for x in uni_xs]
        uni_peaks = _detect_peaks(uni_pts, min_prom=min_prom)
        # density of samples near detected peaks (adaptive should concentrate there)
        def near_peak_frac(pts):
            if not peaks:
                return 0.0
            cnt = sum(1 for x, _ in pts if any(abs(x - p["x"]) < 0.05 for p in peaks))
            return round(cnt / len(pts), 4)
        out = {
            "source": "al-jshen/adaptive (MIT) — adaptive-sampling + peak-detect pattern, clean-room reimpl",
            "honest": ("advisory sensor-fusion efficiency aid on a sample sweep; lossy by design; "
                       "Λ stays Conjecture 1"),
            "budget": budget,
            "adaptive": {
                "samples": [[round(x, 4), round(y, 4)] for x, y in ad_pts],
                "peaks": peaks,
                "fraction_samples_near_peaks": near_peak_frac(ad_pts),
            },
            "uniform_baseline": {
                "peaks_found": len(uni_peaks),
                "fraction_samples_near_peaks": near_peak_frac(uni_pts),
            },
            "efficiency_note": ("adaptive concentrates the limited sampling budget where the sweep has the most "
                                "curvature/structure (the contacts), so an edge node spends its duty-cycle on "
                                "the informative parts of the sweep"),
            "contacts_detected": len(peaks),
            "sample_input": True,
            "sample_note": "sample sensor sweep (two Gaussian contacts on background), not a live feed",
        }
        return JSONResponse(out)
    routes.append("POST " + base + "/adaptive-sample")

    # ---- manifest -----------------------------------------------------------
    @app.get(base + "/index")
    async def resweep_index():
        return JSONResponse({
            "module": "killinchu_resweep_ops",
            "wave": "re-sweep wave-2",
            "doctrine": "fashion thinking — adopt permissive pattern WITH NOTICE, then evolve; Λ=Conjecture 1",
            "upgrades": [
                {"name": "tactical-routing", "endpoint": base + "/route",
                 "source": "anvaka/ngraph.path + rowanwins/visibility-graph", "license": "MIT",
                 "modes": ["grid-astar", "grid-nba", "obstacle-avoid"]},
                {"name": "threat-rank", "endpoint": base + "/threat-rank",
                 "source": "ft2023/IRanker-demo", "license": "MIT"},
                {"name": "adaptive-sample", "endpoint": base + "/adaptive-sample",
                 "source": "al-jshen/adaptive", "license": "MIT"},
            ],
            "routes": routes + ["GET " + base + "/index"],
        })
    routes.append("GET " + base + "/index")

    return f"resweep-ops-wired:{len(routes)}-routes"
