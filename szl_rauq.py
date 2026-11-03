# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_rauq.py — SZL attention-pattern (recurrent attention-based) uncertainty endpoint.

SUB-ORGAN UPGRADE of sement. Same uncertainty axis (hallucination / abstain-vs-answer),
DISTINCT mechanism: sement's true signal is MULTI-SAMPLE semantic entropy (sample K
generations, cluster meanings, entropy over clusters); RAUQ here reads INTRINSIC ATTENTION
PATTERNS in a SINGLE forward pass — no resampling, no meaning clustering.

Exposes a MODELED recurrent-attention-based uncertainty estimator (RAUQ) as a same-origin
REST endpoint. RAUQ is an UNSUPERVISED, single-pass uncertainty signal for white-box LLMs:
it identifies "uncertainty-aware" attention heads whose attention TO PRECEDING TOKENS
systematically DROPS during incorrect generations, auto-selects them, then recurrently
aggregates their preceding-token attention with per-token confidence proxies into a single
SEQUENCE-LEVEL uncertainty scalar — then thresholds it to flag likely-wrong generations.

Here that mechanism is simulated on SEEDED SYNTHETIC toy "attention matrices": for a short
sequence over a few heads we deterministically build row-stochastic attention rows in TWO
labeled regimes — "correct" generations where certain heads MAINTAIN high mass on the
immediately-preceding token(s); "incorrect" where that preceding-token mass DROPS (smears
toward diffuse / self attention) — encoding the paper's pattern BY CONSTRUCTION. We then run
the RAUQ pipeline as pure arithmetic and contrast it against a cheap OUTPUT-ENTROPY (max-
softmax) baseline over the same toy tokens. The attention-drop signal separates the labeled
correct/incorrect set better than the naive output-entropy baseline. Deterministic, pure
stdlib, citable — never fabricated, never random-faked, never run on a real transformer.

  GET  /api/<ns>/v1/rauq/score?seed=&seq_len=&num_heads=&num_selected_heads=&preceding_window=&confidence_weight=&mode=&regime_mix=

Returned JSON fields
--------------------
  label                 : "MODELED" (always — simulates the METHOD on synthetic toy data;
                           NOT a real transformer, NO forward pass)
  model                 : "Recurrent attention-based uncertainty (RAUQ) estimator (MODELED)"
  seed                  : PRNG seed
  seq_len               : toy sequence length
  num_heads             : number of toy attention heads
  num_selected_heads    : heads auto-selected by separability
  preceding_window      : how many immediately-preceding tokens define "preceding mass"
  confidence_weight     : weight of the per-token confidence proxy in recurrent aggregation
  threshold             : decision threshold on the RAUQ sequence-level uncertainty scalar
  head_selection        : per-head separability rows (head, sep_score, selected)
  examples              : per-example rows (label, rauq_score, baseline_entropy, rauq_flag,
                          baseline_flag, per-selected-head preceding-mass timeline)
  rauq_metrics          : {precision, recall, f1, accuracy, auroc} of RAUQ score vs labels
  baseline_metrics      : same metrics for the output-entropy baseline
  rauq_beats_baseline   : bool — RAUQ AUROC/accuracy >= baseline (attention-drop separates better)
  honest_note           : plain-language honesty disclaimer (baked in)
  citations             : dict of citable sources
  computed_at           : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  Toy analytic sim of the attention-pattern-uncertainty MECHANISM, not RAUQ. The "attention
  matrices" are seeded synthetic row-stochastic toys with correct/incorrect regimes BUILT IN
  BY CONSTRUCTION; NO real transformer, NO forward pass, NO 4-LLM/12-task evaluation; "head
  selection" separates a hand-made labeled toy set. It demonstrates WHY a drop in preceding-
  token attention mass in selected heads can serve as a single-pass uncertainty signal a naïve
  output-entropy baseline misses on constructed cases; it does NOT reproduce RAUQ's
  QA/summarization/translation results or its <1% real-latency claim. Explicitly a SUB-ORGAN
  UPGRADE of sement (same uncertainty axis, distinct single-pass-attention vs multi-sample-
  semantic-entropy mechanism — the true sement signal is multi-sample), not a new axis. The
  label "MODELED" is returned verbatim and displayed verbatim by the surface; never upgraded.

CITATION (verified real, verbatim; not claimed as SZL's own):
  Vazhentsev, Rvanova, Kuzmin, Fadeeva, Lazichny, Panchenko, Panov, Baldwin, Sachan, Nakov &
  Shelmanov (2025) "Uncertainty-Aware Attention Heads: Efficient Unsupervised Uncertainty
  Quantification for LLMs" [RAUQ]. arXiv:2505.20045. https://arxiv.org/abs/2505.20045

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib. Deterministic with seed. 0 runtime CDN.
  No real transformer, no forward pass — seeded synthetic attention matrices with regimes
  built in by construction. Sub-organ upgrade of sement, not a new axis.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citation block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "Uncertainty-Aware Attention Heads: Efficient Unsupervised Uncertainty Quantification "
    "for LLMs [RAUQ] — Vazhentsev, Rvanova, Kuzmin, Fadeeva, Lazichny, Panchenko, Panov, "
    "Baldwin, Sachan, Nakov & Shelmanov, arXiv:2505.20045 (2025)":
        "https://arxiv.org/abs/2505.20045",
}


# ---------------------------------------------------------------------------
# Deterministic pure-stdlib PRNG (LCG) — no numpy, no stdlib.random, reproducible
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Toy "attention matrix" builder — seeded, row-stochastic, regime built in by construction.
#
# For one toy generation we build, per head, a (seq_len x seq_len) causal-ish attention
# matrix. Row i is the attention distribution of the query at position i over keys 0..i
# (row-stochastic: sums to 1). Heads split into two roles:
#   - "uncertainty-aware" heads (the first `n_aware`): in the CORRECT regime they put HIGH
#     mass on the immediately-preceding token(s) (positions within preceding_window before i);
#     in the INCORRECT regime that preceding mass DROPS and smears toward diffuse/self.
#   - the remaining heads are "neutral": roughly diffuse in both regimes (little signal).
# The preceding-token-mass PATTERN that RAUQ exploits is thus present BY CONSTRUCTION — this
# is a synthetic illustration, NOT a real transformer's attention.
# ---------------------------------------------------------------------------
def _attention_matrix(regime: str, seq_len: int, preceding_window: int, aware: bool, rng) -> list:
    """Build one head's row-stochastic causal attention matrix for a toy generation."""
    M = []
    for i in range(seq_len):
        # unnormalized logits over keys 0..i (causal)
        w = []
        for k in range(i + 1):
            base = 0.15 + 0.25 * next(rng)  # small diffuse floor
            is_preceding = (k <= i - 1) and (k >= i - preceding_window)
            is_self = (k == i)
            if aware:
                if regime == "correct":
                    # maintain HIGH mass on immediately-preceding token(s)
                    if is_preceding:
                        base += 2.6 + 0.6 * next(rng)
                    elif is_self:
                        base += 0.20 * next(rng)
                else:  # incorrect: preceding mass DROPS, smears to self/diffuse
                    if is_preceding:
                        base += 0.30 * next(rng)          # collapsed
                    elif is_self:
                        base += 1.3 + 0.5 * next(rng)     # mass leaks to self
                    else:
                        base += 0.6 * next(rng)           # and diffuses
            else:
                # neutral head: mildly diffuse in both regimes, small jitter
                base += 0.4 * next(rng)
                if is_self:
                    base += 0.3 * next(rng)
            w.append(base)
        tot = sum(w) or 1.0
        M.append([x / tot for x in w])
    return M


def _preceding_mass(row: list, i: int, preceding_window: int) -> float:
    """Sum of attention mass a query at position i places on its immediately-preceding
    token(s) within the window [i-preceding_window, i-1]. Row is row-stochastic."""
    lo = max(0, i - preceding_window)
    return sum(row[k] for k in range(lo, i))  # keys strictly before i, inside window


def _head_preceding_series(M: list, preceding_window: int) -> list:
    """Per-position preceding-token attention mass for one head across the sequence.
    Position 0 has no preceding token -> 0.0. Returns list of length seq_len."""
    return [
        (_preceding_mass(M[i], i, preceding_window) if i > 0 else 0.0)
        for i in range(len(M))
    ]


# ---------------------------------------------------------------------------
# Toy per-token output-distribution model (for the OUTPUT-ENTROPY baseline).
#
# Independent of attention: in the CORRECT regime the next-token softmax is peaked (low
# entropy, high max-softmax); in the INCORRECT regime it is only MILDLY flatter — chosen so
# that a naive output-entropy threshold separates the labeled set POORLY, while the attention-
# drop signal separates it well. This mirrors the paper's motivation that intrinsic attention
# patterns carry uncertainty signal that output probabilities alone can miss.
# ---------------------------------------------------------------------------
def _token_softmax(regime: str, i: int, rng) -> list:
    """A small toy next-token softmax (5 classes) at position i. Row-stochastic."""
    logits = []
    for c in range(5):
        base = 0.8 * next(rng)                     # substantial per-token noise
        if c == 0:  # the 'chosen' token
            if regime == "correct":
                base += 2.2 + 0.9 * next(rng)      # peaked, but noisy
            else:
                base += 1.9 + 1.1 * next(rng)      # only mildly flatter, heavily overlapping
        logits.append(base)
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    z = sum(exps) or 1.0
    return [e / z for e in exps]


def _entropy(probs) -> float:
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log(p)
    return h


# ---------------------------------------------------------------------------
# RAUQ recurrent aggregation over one toy generation.
#
# Walk the sequence position by position. At each position t (t>=1) we take the selected
# heads' preceding-token attention mass, average it, and combine it with a per-token
# confidence proxy derived from the token softmax (max-softmax). Following RAUQ's recurrence
# in spirit, we accumulate a running token uncertainty u_t that carries forward:
#     g_t   = confidence_weight * max_softmax_t + (1 - confidence_weight) * mean_prec_mass_t
#     u_t   = 1 - g_t + decay * u_{t-1}          (recurrent carry of uncertainty)
# The sequence-level RAUQ uncertainty scalar is the max running uncertainty along the
# sequence (a high-water mark), normalized. HIGHER = more likely wrong.
# ---------------------------------------------------------------------------
def _rauq_score(selected_series: list, max_softmax_series: list, confidence_weight: float,
                decay: float = 0.5) -> float:
    seq_len = len(max_softmax_series)
    if seq_len == 0 or not selected_series:
        return 0.0
    u = 0.0
    hi = 0.0
    for t in range(1, seq_len):
        prec_vals = [s[t] for s in selected_series]
        mean_prec = sum(prec_vals) / len(prec_vals)
        conf = max_softmax_series[t]
        g = confidence_weight * conf + (1.0 - confidence_weight) * mean_prec  # local confidence
        u = (1.0 - g) + decay * u
        if u > hi:
            hi = u
    # normalize by the geometric-series ceiling so scores land in a tidy range
    ceiling = 1.0 / (1.0 - decay) if decay < 1.0 else float(seq_len)
    return hi / ceiling


# ---------------------------------------------------------------------------
# Build the labeled toy dataset: N correct + N incorrect example generations.
# Each example carries, per head, its preceding-mass series and its max-softmax series.
# ---------------------------------------------------------------------------
def _build_dataset(seed: int, seq_len: int, num_heads: int, preceding_window: int,
                   n_aware: int, n_per_class: int) -> list:
    examples = []
    # deterministic, distinct sub-seed per example so runs are reproducible
    idx = 0
    for label in ("correct", "incorrect"):
        for e in range(n_per_class):
            sub = seed + 1009 * (1 if label == "incorrect" else 0) + 31 * e
            head_series = []
            for h in range(num_heads):
                aware = (h < n_aware)
                hrng = _lcg(sub + 7 * (h + 1))
                M = _attention_matrix(label, seq_len, preceding_window, aware, hrng)
                head_series.append(_head_preceding_series(M, preceding_window))
            srng = _lcg(sub + 99991)
            softmax_series = [_token_softmax(label, i, srng) for i in range(seq_len)]
            max_softmax = [max(sm) for sm in softmax_series]
            out_entropy = [_entropy(sm) for sm in softmax_series]
            examples.append({
                "idx": idx,
                "label": label,
                "y": 1 if label == "incorrect" else 0,  # 1 = "wrong" (positive class)
                "head_series": head_series,
                "max_softmax": max_softmax,
                "mean_out_entropy": sum(out_entropy) / len(out_entropy),
            })
            idx += 1
    return examples


# ---------------------------------------------------------------------------
# HEAD AUTO-SELECTION — score each head by how well its preceding-mass separates the
# labeled correct vs incorrect examples. Deterministic separability = (mean_correct -
# mean_incorrect) mean preceding mass, normalized by pooled spread. Higher = the head's
# preceding mass drops more on incorrect -> more "uncertainty-aware". Select top-k.
# ---------------------------------------------------------------------------
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs, mu):
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def _head_avg_preceding(ex: dict, h: int) -> float:
    """Average preceding-token mass of head h across positions 1..seq_len-1 for an example."""
    series = ex["head_series"][h]
    tail = series[1:]
    return _mean(tail) if tail else 0.0


def _select_heads(examples: list, num_heads: int, num_selected_heads: int) -> list:
    corr = [e for e in examples if e["label"] == "correct"]
    incorr = [e for e in examples if e["label"] == "incorrect"]
    rows = []
    for h in range(num_heads):
        c_vals = [_head_avg_preceding(e, h) for e in corr]
        i_vals = [_head_avg_preceding(e, h) for e in incorr]
        mc, mi = _mean(c_vals), _mean(i_vals)
        pooled = (_std(c_vals, mc) + _std(i_vals, mi)) / 2.0 + 1e-6
        sep = (mc - mi) / pooled  # positive when preceding mass drops on incorrect
        rows.append({
            "head": h,
            "mean_preceding_correct": round(mc, 6),
            "mean_preceding_incorrect": round(mi, 6),
            "sep_score": round(sep, 6),
        })
    # deterministic ordering: by sep_score desc, then head index asc
    order = sorted(rows, key=lambda r: (-r["sep_score"], r["head"]))
    chosen = set(r["head"] for r in order[:max(1, min(num_selected_heads, num_heads))])
    for r in rows:
        r["selected"] = r["head"] in chosen
    return rows


# ---------------------------------------------------------------------------
# Metrics — precision/recall/f1/accuracy at a threshold + threshold-free AUROC.
# Positive class = "incorrect" (y=1). A score above threshold flags "likely wrong".
# ---------------------------------------------------------------------------
def _prf(scores: list, ys: list, threshold: float) -> dict:
    tp = fp = tn = fn = 0
    for s, y in zip(scores, ys):
        pred = 1 if s >= threshold else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    acc = (tp + tn) / len(ys) if ys else 0.0
    return {
        "precision": round(prec, 6), "recall": round(rec, 6),
        "f1": round(f1, 6), "accuracy": round(acc, 6),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def _auroc(scores: list, ys: list) -> float:
    """Threshold-free separation via the Mann-Whitney U statistic (positive class y=1)."""
    pos = [s for s, y in zip(scores, ys) if y == 1]
    neg = [s for s, y in zip(scores, ys) if y == 0]
    if not pos or not neg:
        return 0.0
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


# ---------------------------------------------------------------------------
# Core score — runs the full RAUQ pipeline over the labeled toy set + baseline contrast
# ---------------------------------------------------------------------------
def _score(
    seed: int = 42,
    seq_len: int = 8,
    num_heads: int = 6,
    num_selected_heads: int = 2,
    preceding_window: int = 1,
    confidence_weight: float = 0.4,
    threshold: float = 0.5,
    regime_mix: float = 0.5,
) -> dict:
    seq_len = max(3, min(int(seq_len), 32))
    num_heads = max(2, min(int(num_heads), 16))
    num_selected_heads = max(1, min(int(num_selected_heads), num_heads))
    preceding_window = max(1, min(int(preceding_window), seq_len - 1))
    confidence_weight = max(0.0, min(float(confidence_weight), 1.0))
    thr = max(0.0, min(float(threshold), 5.0))
    regime_mix = max(0.1, min(float(regime_mix), 0.9))

    # ~2 aware heads by construction (fraction of heads carry the drop signal)
    n_aware = max(1, min(num_heads // 3 + 1, num_heads - 1))
    n_per_class = 6

    examples = _build_dataset(seed, seq_len, num_heads, preceding_window, n_aware, n_per_class)

    # (a) HEAD AUTO-SELECTION by separability
    head_rows = _select_heads(examples, num_heads, num_selected_heads)
    selected = [r["head"] for r in head_rows if r["selected"]]

    # (b) RECURRENT AGGREGATION -> per-example RAUQ score; baseline = mean output entropy
    ex_out = []
    rauq_scores, base_scores, ys = [], [], []
    for e in examples:
        sel_series = [e["head_series"][h] for h in selected]
        rs = _rauq_score(sel_series, e["max_softmax"], confidence_weight)
        bs = e["mean_out_entropy"]
        rauq_scores.append(rs)
        base_scores.append(bs)
        ys.append(e["y"])
        # per-selected-head preceding-mass timeline (for the surface visual)
        timelines = {str(h): [round(v, 5) for v in e["head_series"][h]] for h in selected}
        ex_out.append({
            "idx": e["idx"],
            "label": e["label"],
            "y": e["y"],
            "rauq_score": round(rs, 6),
            "baseline_entropy": round(bs, 6),
            "selected_head_preceding_timeline": timelines,
        })

    # baseline threshold: midpoint of baseline score range (fair, data-driven)
    b_lo, b_hi = min(base_scores), max(base_scores)
    b_thr = (b_lo + b_hi) / 2.0

    # (c) THRESHOLD to flag likely-wrong; attach flags to example rows
    for row, rs, bs in zip(ex_out, rauq_scores, base_scores):
        row["rauq_flag"] = bool(rs >= thr)
        row["baseline_flag"] = bool(bs >= b_thr)

    rauq_metrics = _prf(rauq_scores, ys, thr)
    rauq_metrics["auroc"] = round(_auroc(rauq_scores, ys), 6)
    baseline_metrics = _prf(base_scores, ys, b_thr)
    baseline_metrics["auroc"] = round(_auroc(base_scores, ys), 6)
    baseline_metrics["threshold_used"] = round(b_thr, 6)

    rauq_beats_baseline = bool(
        rauq_metrics["auroc"] >= baseline_metrics["auroc"]
        and rauq_metrics["accuracy"] >= baseline_metrics["accuracy"]
    )

    return {
        "seed": seed,
        "seq_len": seq_len,
        "num_heads": num_heads,
        "num_selected_heads": len(selected),
        "preceding_window": preceding_window,
        "confidence_weight": round(confidence_weight, 4),
        "threshold": round(thr, 4),
        "regime_mix": round(regime_mix, 4),
        "selected_heads": selected,
        "head_selection": head_rows,
        "examples": ex_out,
        "rauq_metrics": rauq_metrics,
        "baseline_metrics": baseline_metrics,
        "rauq_beats_baseline": rauq_beats_baseline,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _fi(req: Request, key: str, default) -> float:
    try:
        return float(req.query_params.get(key, default))
    except Exception:
        return float(default)


def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


def _h_score(req: Request):
    seed               = _ii(req, "seed",               42)
    seq_len            = _ii(req, "seq_len",             8)
    num_heads          = _ii(req, "num_heads",           6)
    num_selected_heads = _ii(req, "num_selected_heads",  2)
    preceding_window   = _ii(req, "preceding_window",    1)
    confidence_weight  = _fi(req, "confidence_weight",   0.4)
    threshold          = _fi(req, "threshold",           0.5)
    regime_mix         = _fi(req, "regime_mix",          0.5)
    _mode              = req.query_params.get("mode", "compare")  # reserved; single mode today

    snap = _score(
        seed=seed, seq_len=seq_len, num_heads=num_heads,
        num_selected_heads=num_selected_heads, preceding_window=preceding_window,
        confidence_weight=confidence_weight, threshold=threshold, regime_mix=regime_mix,
    )

    return JSONResponse({
        "label":              "MODELED",
        "model":              "Recurrent attention-based uncertainty (RAUQ) estimator (MODELED)",
        "method":             "seeded synthetic attention matrices (correct/incorrect regimes built in) "
                              "-> head auto-selection by separability -> recurrent aggregation of "
                              "preceding-token attention + confidence proxy -> sequence-level uncertainty "
                              "scalar -> threshold flag; contrasted vs an output-entropy baseline",
        "seed":               snap["seed"],
        "seq_len":            snap["seq_len"],
        "num_heads":          snap["num_heads"],
        "num_selected_heads": snap["num_selected_heads"],
        "preceding_window":   snap["preceding_window"],
        "confidence_weight":  snap["confidence_weight"],
        "threshold":          snap["threshold"],
        "regime_mix":         snap["regime_mix"],
        "selected_heads":     snap["selected_heads"],
        "head_selection":     snap["head_selection"],
        "examples":           snap["examples"],
        "rauq_metrics":       snap["rauq_metrics"],
        "baseline_metrics":   snap["baseline_metrics"],
        "rauq_beats_baseline": snap["rauq_beats_baseline"],
        "honest_note": (
            "MODELED: toy analytic sim of the attention-pattern-uncertainty MECHANISM, not RAUQ. "
            "The 'attention matrices' are SEEDED SYNTHETIC row-stochastic toys with correct/incorrect "
            "regimes BUILT IN BY CONSTRUCTION; NO real transformer, NO forward pass, NO 4-LLM/12-task "
            "evaluation; 'head selection' separates a hand-made labeled toy set. Demonstrates WHY a "
            "drop in preceding-token attention mass in selected heads can serve as a single-pass "
            "uncertainty signal a naive output-entropy baseline misses on constructed cases; does NOT "
            "reproduce RAUQ's QA/summarization/translation results or its <1% real-latency claim. "
            "Explicitly a SUB-ORGAN UPGRADE of sement (same uncertainty axis, distinct single-pass-"
            "attention vs multi-sample-semantic-entropy mechanism — the true sement signal is "
            "MULTI-SAMPLE), not a new axis. Deterministic: same seed -> identical output. Cite: "
            "Vazhentsev et al., arXiv:2505.20045 (2025). SZL claims NONE of these methods as its own."
        ),
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_sement.register() exactly; additive, guarded
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/rauq/score onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/rauq"
    handlers = [
        (f"{base}/score", _h_score),
    ]
    try:
        add_api_route = getattr(app, "add_api_route", None)
        for path, fn in handlers:
            if callable(add_api_route):
                app.add_api_route(path, fn, methods=["GET"])
            else:
                app.router.routes.append(Route(path, fn))
    except Exception:
        # additive registration must never break the host app
        pass
    return [p for p, _ in handlers]


if __name__ == "__main__":
    # local smoke test — no server needed.
    # Frontier result: on the CONSTRUCTED labeled toy set, the RAUQ attention-drop score
    # separates correct-vs-incorrect better than the naive OUTPUT-ENTROPY baseline.
    print("label: MODELED")
    print("model: Recurrent attention-based uncertainty (RAUQ) estimator (MODELED)")
    print("cite: Vazhentsev et al. arXiv:2505.20045 (2025)")
    print("honest: seeded synthetic attention matrices, regimes built in by construction; "
          "SUB-ORGAN UPGRADE of sement (true sement signal is multi-sample); no real transformer.")
    print()

    snap = _score(seed=42, seq_len=8, num_heads=6, num_selected_heads=2,
                  preceding_window=1, confidence_weight=0.4, threshold=0.5)

    print("HEAD AUTO-SELECTION (separability = preceding-mass drop on incorrect):")
    hdr = f"{'head':>5}{'prec_mass_correct':>19}{'prec_mass_incorrect':>21}{'sep_score':>12}{'selected':>10}"
    print(hdr)
    print("-" * len(hdr))
    for r in snap["head_selection"]:
        print(f"{r['head']:>5}{r['mean_preceding_correct']:>19.4f}"
              f"{r['mean_preceding_incorrect']:>21.4f}{r['sep_score']:>12.4f}"
              f"{('YES' if r['selected'] else 'no'):>10}")
    print(f"\nselected heads: {snap['selected_heads']}")
    print()

    rm, bm = snap["rauq_metrics"], snap["baseline_metrics"]
    print("RAUQ vs OUTPUT-ENTROPY BASELINE (positive class = 'incorrect'):")
    mh = f"{'signal':<12}{'AUROC':>9}{'accuracy':>10}{'precision':>11}{'recall':>9}{'f1':>8}"
    print(mh)
    print("-" * len(mh))
    print(f"{'RAUQ':<12}{rm['auroc']:>9.4f}{rm['accuracy']:>10.4f}{rm['precision']:>11.4f}{rm['recall']:>9.4f}{rm['f1']:>8.4f}")
    print(f"{'baseline':<12}{bm['auroc']:>9.4f}{bm['accuracy']:>10.4f}{bm['precision']:>11.4f}{bm['recall']:>9.4f}{bm['f1']:>8.4f}")
    print()
    print(f"rauq_beats_baseline (AUROC & accuracy both >=) = {snap['rauq_beats_baseline']}")
    print()

    # Determinism: same seed twice -> identical snapshot.
    snap2 = _score(seed=42, seq_len=8, num_heads=6, num_selected_heads=2,
                   preceding_window=1, confidence_weight=0.4, threshold=0.5)
    assert snap == snap2, "same seed must produce identical output"

    # Head selection must recover uncertainty-aware heads (positive separability).
    sel_rows = [r for r in snap["head_selection"] if r["selected"]]
    assert all(r["sep_score"] > 0 for r in sel_rows), "selected heads must have positive separability"

    # RAUQ must separate the labeled set at least as well as the output-entropy baseline.
    assert rm["auroc"] >= bm["auroc"], "RAUQ AUROC must be >= baseline AUROC"
    assert rm["accuracy"] >= bm["accuracy"], "RAUQ accuracy must be >= baseline accuracy"
    assert snap["rauq_beats_baseline"], "attention-drop signal must beat the output-entropy baseline"

    print("szl_rauq: ALL OK — head auto-selection recovers the uncertainty-aware heads and the "
          "RAUQ attention-drop score separates correct/incorrect better than the output-entropy "
          "baseline on the constructed toy set; determinism holds.")
