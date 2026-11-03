# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_matgran.py — SZL Matryoshka Representation Granularity (matgran) endpoint,
MODELED.

Exposes a MODELED, deterministic, pure-stdlib simulation of the
NESTED-REPRESENTATION MECHANISM behind Matryoshka Representation Learning
(MRL, Kusupati et al. 2022, arXiv:2205.13147) and its 2026 refinement MIPIC
(Phung Gia Huy et al. 2026, arXiv:2604.24374), as a same-origin REST endpoint,
so the matgran surface organ has a live data source that is honest,
deterministic, and citable — never fabricated, never random-faked, never run
against a trained encoder.

  GET  /api/<ns>/v1/matgran/truncate?seed=&D=&prefixes=&num_classes=&num_points=&nesting=&distill=

WHAT IS SIMULATED
------------------
Matryoshka Representation Learning trains ONE embedding so that its LEADING
PREFIXES are each themselves usable embeddings: the first 8, 16, 32, … dims
form a coarse-to-fine family of representations. A downstream task can then
pick an operating point (dimensionality vs compute/accuracy budget) by simply
TRUNCATING the vector — no retraining, no separate models. MIPIC (2026)
refines the nesting via self-distilled intra-relational alignment and
progressive information chaining so the low-dimensional prefixes stay
competitive with the full vector. The axis is REPRESENTATION GRANULARITY: one
vector, many operating points.

THIS MODULE (clean-room, deterministic, MODELED):
  1. Builds a synthetic labeled dataset: `num_points` points in R^D drawn from
     `num_classes` seeded Gaussian class clusters (deterministic means + LCG
     noise; NO numpy, NO stdlib random).
  2. Emulates the MRL objective in CLOSED FORM instead of by SGD: it computes
     the per-axis between-class discriminability (variance of the class means
     along each raw axis) and builds a "front-loaded" orthonormal projection —
     via a BY-HAND Gram–Schmidt over discriminability-ranked seed directions —
     so the MOST DISCRIMINATIVE information is placed in the EARLIEST dims.
     Truncating to a prefix `d` therefore keeps the most useful directions.
  3. Baseline NON-NESTED control: the SAME orthonormal directions in a
     deterministically SHUFFLED order, so early prefixes are no better than a
     random slice.
  4. Evaluates a nearest-centroid classifier at each NESTED PREFIX
     d ∈ prefixes (default {2,4,8,16,32}) for both the nested and non-nested
     embeddings, reporting accuracy per prefix.
  5. Optional MIPIC-flavored one-pass self-distillation (`distill`): a single
     toy pass that nudges truncated-view centroid assignments toward the
     full-view assignments (soft agreement), lifting the low-d nested accuracy
     — a stand-in for MIPIC's self-distilled alignment, NOT the real training.
  6. Reports storage saving at each prefix (bytes at d vs bytes at D).

Honest signal: the nested embedding stays accurate under truncation
(especially at extreme-low d), while the non-nested control collapses.

Returned JSON fields
---------------------
  label            : "MODELED" (always — closed-form analytic sim of the
                     nested-representation mechanism, NOT a trained encoder)
  model            : short description of the simulated setup
  seed             : RNG seed used
  D                : full embedding dimensionality
  prefixes         : the nested prefix widths evaluated
  num_classes      : number of synthetic class clusters
  num_points       : number of synthetic points
  nesting          : whether the nested (front-loaded) projection is on
  distill          : whether the one-pass MIPIC-flavored distillation is on
  curve            : list of per-prefix rows, each with:
                       d, nested_accuracy, non_nested_accuracy,
                       bytes_d, bytes_D, storage_saving (1 - d/D)
  nested_accuracy      : per-prefix nested accuracy (mirror list, for the surface)
  non_nested_accuracy  : per-prefix non-nested accuracy (mirror list)
  storage_saving       : per-prefix storage saving fraction (mirror list)
  full_accuracy    : accuracy at the full width D (both share it)
  honest_note      : plain-language honesty disclaimer
  citations        : dict of citable sources
  computed_at      : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib TOY ANALYTIC SIM of the nested-
  representation MECHANISM — synthetic Gaussian clusters, a closed-form
  front-loaded projection built by hand-rolled Gram–Schmidt, and a
  nearest-centroid probe. There is NO trained encoder, NO SIA/PIC training,
  NO CKA self-distillation over real models. It demonstrates WHY prefix-nested
  embeddings degrade gracefully versus a non-nested control; it does NOT
  reproduce MIPIC's STS/NLI/classification results or MRL's ImageNet
  speed-ups, and the "self-distillation" step is a one-pass toy stand-in.
  The label "MODELED" is returned verbatim and displayed verbatim by the
  surface; never upgraded client-side.

CITATIONS (clean-room; none claimed as SZL's own):
  MIPIC (2026 anchor; refines nested representations via self-distilled
  intra-relational alignment + progressive information chaining):
    Phung Gia Huy et al. (2026) arXiv:2604.24374.
    https://arxiv.org/abs/2604.24374
  Matryoshka Representation Learning (foundational):
    Kusupati et al. (2022) arXiv:2205.13147.
    https://arxiv.org/abs/2205.13147
  NEVER-CLAIMED-AS: this module is not MIPIC, not MRL, and does not reproduce
  either project's code, trained weights, or measured benchmark numbers. It is
  a clean-room MODELED simulation of the nested-representation mechanism they
  build on.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
"""
from __future__ import annotations

from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "MIPIC (nested-representation refinement; 2026 anchor) — Phung Gia Huy et al. arXiv:2604.24374": "https://arxiv.org/abs/2604.24374",
    "Matryoshka Representation Learning (foundational) — Kusupati et al. arXiv:2205.13147": "https://arxiv.org/abs/2205.13147",
}

# Bytes-per-dimension assumed for the storage-saving arithmetic (fp32).
_BYTES_PER_DIM = 4


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


def _rand_signed(rng) -> float:
    """Draw one deterministic pseudo-random value in (-1, 1) from the LCG stream."""
    return 2.0 * next(rng) - 1.0


def _rand_gauss(rng) -> float:
    """Deterministic approx-Gaussian via a 6-sample sum of the LCG uniform stream
    (central-limit; mean 0, unit-ish variance). Pure stdlib — no numpy, no
    stdlib random, no math.sqrt tricks needed."""
    s = 0.0
    for _ in range(6):
        s += next(rng)
    # sum of 6 uniforms in [0,1): mean 3, variance 6*(1/12)=0.5 -> std ~0.707
    return (s - 3.0) / 0.7071067811865476


# ---------------------------------------------------------------------------
# Pure-stdlib vector / matrix helpers (no numpy)
# ---------------------------------------------------------------------------
def _dot(a, b) -> float:
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def _norm(a) -> float:
    return _dot(a, a) ** 0.5


def _scale(a, k):
    return [x * k for x in a]


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _matvec(mat, v):
    """mat is (out x in), v is (in,) -> (out,). Row-major nested lists."""
    return [_dot(row, v) for row in mat]


# ---------------------------------------------------------------------------
# BY-HAND Gram–Schmidt (pure stdlib) — orthonormalizes a set of seed row
# vectors in place-order. Degenerate/near-zero rows are replaced by a
# deterministic axis unit vector so the output basis is always full rank.
# ---------------------------------------------------------------------------
def _gram_schmidt(rows):
    basis = []
    n = len(rows[0]) if rows else 0
    for idx, r in enumerate(rows):
        v = list(r)
        for b in basis:
            proj = _dot(v, b)
            v = _sub(v, _scale(b, proj))
        nrm = _norm(v)
        if nrm < 1e-9:
            # deterministic fallback: unit vector along axis idx
            v = [0.0] * n
            v[idx % n] = 1.0
            for b in basis:
                proj = _dot(v, b)
                v = _sub(v, _scale(b, proj))
            nrm = _norm(v)
            if nrm < 1e-9:
                continue
        basis.append(_scale(v, 1.0 / nrm))
    return basis


# ---------------------------------------------------------------------------
# MODELED nested-representation simulation (deterministic)
# ---------------------------------------------------------------------------
def _matgran_snapshot(seed: int = 42, D: int = 32,
                      prefixes=None, num_classes: int = 6,
                      num_points: int = 240, nesting: bool = True,
                      distill: bool = True) -> dict:
    """
    Simulate MRL/MIPIC-style prefix-nested representations at toy scale.

    Pure stdlib; deterministic — same (seed, D, prefixes, num_classes,
    num_points, nesting, distill) -> identical snapshot, every time.
    """
    if prefixes is None:
        prefixes = [2, 4, 8, 16, 32]
    prefixes = sorted({int(p) for p in prefixes if 1 <= int(p) <= D})
    if not prefixes:
        prefixes = [max(1, D)]

    rng = _lcg(seed)

    # 1) Deterministic class means in R^D. Well-separated so the classification
    #    task is learnable but sensitive to how much discriminability survives
    #    truncation. Means live on a scaled hypercube-ish spread.
    means = []
    for _c in range(num_classes):
        means.append([2.6 * _rand_signed(rng) for _ in range(D)])

    # 2) Synthetic points: each point = its class mean + small Gaussian noise.
    points = []
    labels = []
    for i in range(num_points):
        c = i % num_classes
        m = means[c]
        pt = [m[j] + 0.85 * _rand_gauss(rng) for j in range(D)]
        points.append(pt)
        labels.append(c)

    # 3) Per-axis between-class discriminability = variance of the class means
    #    along each raw axis (closed-form Fisher-flavored score, no SGD).
    grand = [0.0] * D
    for m in means:
        for j in range(D):
            grand[j] += m[j]
    grand = [g / max(num_classes, 1) for g in grand]

    disc = [0.0] * D
    for m in means:
        for j in range(D):
            d = m[j] - grand[j]
            disc[j] += d * d
    # ranked axis order, most-discriminative first
    ranked_axes = sorted(range(D), key=lambda j: disc[j], reverse=True)

    # 4) Seed directions for the projection: axis-aligned unit vectors ordered
    #    by discriminability (front-loading the useful directions), lightly
    #    perturbed deterministically so Gram–Schmidt yields a rotated but
    #    still front-loaded orthonormal basis. This EMULATES MRL training
    #    (which learns to concentrate information in leading dims) in closed
    #    form — no gradient descent.
    seed_rows = []
    for rank, ax in enumerate(ranked_axes):
        row = [0.02 * _rand_signed(rng) for _ in range(D)]
        row[ax] += 1.0
        seed_rows.append(row)

    nested_basis = _gram_schmidt(seed_rows)  # (D x D) front-loaded orthonormal

    # 5) NON-NESTED control: same basis, deterministically shuffled order so
    #    early prefixes are no longer the most discriminative directions.
    order = list(range(len(nested_basis)))
    # deterministic Fisher–Yates using the LCG stream
    for i in range(len(order) - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        if j > i:
            j = i
        order[i], order[j] = order[j], order[i]
    non_nested_basis = [nested_basis[k] for k in order]

    # Precompute projected coordinates for every point under both bases.
    def _project_all(basis):
        return [_matvec(basis, p) for p in points]

    nested_coords = _project_all(nested_basis)
    non_nested_coords = _project_all(non_nested_basis)

    # Nearest-centroid classifier at a given prefix width d over given coords.
    def _accuracy_at(coords, d, do_distill):
        # centroids in the d-dim prefix space
        sums = [[0.0] * d for _ in range(num_classes)]
        counts = [0] * num_classes
        for coord, lab in zip(coords, labels):
            row = sums[lab]
            for j in range(d):
                row[j] += coord[j]
            counts[lab] += 1
        centroids = []
        for c in range(num_classes):
            k = max(counts[c], 1)
            centroids.append([sums[c][j] / k for j in range(d)])

        # Optional one-pass MIPIC-flavored self-distillation: recompute
        # centroids using the FULL-view (prefix=D) hard assignments so the
        # truncated view is nudged toward full-view agreement. Toy stand-in.
        if do_distill:
            # full-view assignment per point (using all D dims)
            full_centroids = []
            fsums = [[0.0] * D for _ in range(num_classes)]
            fcounts = [0] * num_classes
            for coord, lab in zip(coords, labels):
                for j in range(D):
                    fsums[lab][j] += coord[j]
                fcounts[lab] += 1
            for c in range(num_classes):
                k = max(fcounts[c], 1)
                full_centroids.append([fsums[c][j] / k for j in range(D)])

            fsums2 = [[0.0] * d for _ in range(num_classes)]
            fcounts2 = [0] * num_classes
            for coord in coords:
                # assign by full-view nearest centroid
                best, best_dist = 0, None
                for c in range(num_classes):
                    dd = 0.0
                    fc = full_centroids[c]
                    for j in range(D):
                        diff = coord[j] - fc[j]
                        dd += diff * diff
                    if best_dist is None or dd < best_dist:
                        best_dist, best = dd, c
                for j in range(d):
                    fsums2[best][j] += coord[j]
                fcounts2[best] += 1
            for c in range(num_classes):
                if fcounts2[c] > 0:
                    k = fcounts2[c]
                    # blend distilled centroid with the original (soft nudge)
                    dist_c = [fsums2[c][j] / k for j in range(d)]
                    centroids[c] = [0.5 * centroids[c][j] + 0.5 * dist_c[j]
                                    for j in range(d)]

        # classify each point at prefix d
        correct = 0
        for coord, lab in zip(coords, labels):
            best, best_dist = 0, None
            for c in range(num_classes):
                dd = 0.0
                cc = centroids[c]
                for j in range(d):
                    diff = coord[j] - cc[j]
                    dd += diff * diff
                if best_dist is None or dd < best_dist:
                    best_dist, best = dd, c
            if best == lab:
                correct += 1
        return correct / max(len(coords), 1)

    # If nesting is OFF, the "nested" view uses the shuffled (non-nested) basis
    # too — collapsing the front-loading advantage (ablation switch).
    nested_view = nested_coords if nesting else non_nested_coords

    curve = []
    nested_acc_list = []
    non_nested_acc_list = []
    saving_list = []
    for d in prefixes:
        n_acc = _accuracy_at(nested_view, d, distill)
        nn_acc = _accuracy_at(non_nested_coords, d, False)
        bytes_d = d * _BYTES_PER_DIM
        bytes_D = D * _BYTES_PER_DIM
        saving = 1.0 - (d / D)
        curve.append({
            "d": d,
            "nested_accuracy": round(n_acc, 6),
            "non_nested_accuracy": round(nn_acc, 6),
            "bytes_d": bytes_d,
            "bytes_D": bytes_D,
            "storage_saving": round(saving, 6),
        })
        nested_acc_list.append(round(n_acc, 6))
        non_nested_acc_list.append(round(nn_acc, 6))
        saving_list.append(round(saving, 6))

    full_accuracy = round(_accuracy_at(nested_view, D, False), 6)

    return {
        "D": D,
        "prefixes": prefixes,
        "num_classes": num_classes,
        "num_points": num_points,
        "nesting": bool(nesting),
        "distill": bool(distill),
        "curve": curve,
        "nested_accuracy": nested_acc_list,
        "non_nested_accuracy": non_nested_acc_list,
        "storage_saving": saving_list,
        "full_accuracy": full_accuracy,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _bb(req: Request, key: str, default: bool) -> bool:
    v = req.query_params.get(key, None)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _parse_prefixes(req: Request, D: int, default):
    raw = req.query_params.get("prefixes", None)
    if not raw:
        return default
    out = []
    for tok in raw.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(float(tok)))
        except Exception:
            continue
    return out or default


def _h_truncate(req: Request):
    # Clamps keep the pure-stdlib nested-list arithmetic bounded to a fast,
    # deterministic HTTP response.
    seed        = _ii(req, "seed", 42)
    D           = max(2, min(_ii(req, "D", 32), 64))
    num_classes = max(2, min(_ii(req, "num_classes", 6), 16))
    num_points  = max(num_classes, min(_ii(req, "num_points", 240), 1200))
    nesting     = _bb(req, "nesting", True)
    distill     = _bb(req, "distill", True)
    prefixes    = _parse_prefixes(req, D, [2, 4, 8, 16, 32])

    snap = _matgran_snapshot(seed=seed, D=D, prefixes=prefixes,
                             num_classes=num_classes, num_points=num_points,
                             nesting=nesting, distill=distill)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "Matryoshka Representation Granularity: prefix-nested embeddings (MRL/MIPIC-style)",
        "method": (
            "Synthetic Gaussian class clusters in R^D; a closed-form FRONT-LOADED "
            "orthonormal projection (hand-rolled Gram-Schmidt over discriminability-"
            "ranked directions) emulates MRL's information concentration in leading "
            "dims; a nearest-centroid probe is evaluated at each NESTED PREFIX "
            "d in prefixes for the nested embedding and for a NON-NESTED (shuffled-"
            "order) control; optional one-pass MIPIC-flavored self-distillation nudges "
            "truncated-view centroids toward full-view assignments. Reports accuracy-"
            "vs-dimensionality plus storage saving (1 - d/D) at each prefix."
        ),
        "seed": seed,
        **snap,
        "honest_note": (
            "MODELED: toy analytic sim of the nested-representation MECHANISM, not "
            "MRL/MIPIC. Synthetic Gaussian clusters, closed-form front-loaded "
            "projection, nearest-centroid probe -- NO trained encoder, NO SIA/PIC "
            "training, NO CKA self-distillation over real models. Demonstrates WHY "
            "prefix-nested embeddings degrade gracefully vs a non-nested control; does "
            "NOT reproduce MIPIC's STS/NLI/classification results or MRL's ImageNet "
            "speed-ups; the 'self-distillation' step is a one-pass toy stand-in. "
            "Vectors and projection directions are drawn from a deterministic LCG PRNG "
            "(no numpy, no stdlib random). Deterministic: same seed/D/prefixes/"
            "num_classes/num_points/nesting/distill -> identical snapshot. SZL claims "
            "NONE of these methods (arXiv:2604.24374, arXiv:2205.13147) as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_mla.register() / szl_ternary.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/matgran/truncate onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/matgran"
    handlers = [
        (f"{base}/truncate", _h_truncate),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed
    snap = _matgran_snapshot(seed=42, D=32, prefixes=[2, 4, 8, 16, 32],
                             num_classes=6, num_points=240,
                             nesting=True, distill=True)
    print("label: MODELED")
    print("D:", snap["D"])
    print("prefixes:", snap["prefixes"])
    print("num_classes:", snap["num_classes"])
    print("num_points:", snap["num_points"])
    print("nesting:", snap["nesting"], "distill:", snap["distill"])
    print("full_accuracy:", snap["full_accuracy"])
    print("--- ACCURACY-VS-DIMENSIONALITY (nested vs non-nested) + storage saving ---")
    print("  d  | nested_acc | non_nested_acc | storage_saving")
    for row in snap["curve"]:
        print("  {:>2} |   {:.4f}   |     {:.4f}     |    {:.4f}".format(
            row["d"], row["nested_accuracy"], row["non_nested_accuracy"],
            row["storage_saving"]))

    # sanity: prefixes evaluated as requested
    assert [r["d"] for r in snap["curve"]] == [2, 4, 8, 16, 32], "prefix set mismatch"

    # sanity: storage saving is 1 - d/D and strictly decreasing as d grows
    for row in snap["curve"]:
        assert abs(row["storage_saving"] - (1.0 - row["d"] / snap["D"])) < 1e-9, \
            "storage_saving formula mismatch"
    savings = [r["storage_saving"] for r in snap["curve"]]
    assert savings == sorted(savings, reverse=True), "storage saving must fall as d grows"

    # sanity: accuracies are valid probabilities
    for row in snap["curve"]:
        assert 0.0 <= row["nested_accuracy"] <= 1.0, "nested_accuracy out of range"
        assert 0.0 <= row["non_nested_accuracy"] <= 1.0, "non_nested_accuracy out of range"

    # sanity: HONEST SIGNAL — at the most extreme-low prefix the nested
    # embedding beats the non-nested control (front-loading pays off), and the
    # non-nested control collapses far below the nested view there.
    low = snap["curve"][0]
    assert low["nested_accuracy"] > low["non_nested_accuracy"], \
        "nested must beat non-nested at the lowest prefix (front-loading signal)"

    # sanity: nested accuracy is (weakly) higher on average than non-nested
    nested_mean = sum(r["nested_accuracy"] for r in snap["curve"]) / len(snap["curve"])
    non_mean = sum(r["non_nested_accuracy"] for r in snap["curve"]) / len(snap["curve"])
    assert nested_mean > non_mean, "nested should dominate non-nested on average"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _matgran_snapshot(seed=42, D=32, prefixes=[2, 4, 8, 16, 32],
                              num_classes=6, num_points=240,
                              nesting=True, distill=True)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_matgran: ALL OK -- deterministic, storage-saving verified, "
          "nested beats non-nested under truncation (front-loading signal).")
