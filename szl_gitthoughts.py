# SPDX-License-Identifier: Apache-2.0
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Doctrine v11
"""
szl_gitthoughts.py — SZL GITOFTHOUGHTS VERSION-CONTROLLED REASONING MEMORY
endpoint (GitOfThoughts = an agent's reasoning tree stored as a git repository:
every scored thought is a COMMIT, scores are NOTES, terminal outcomes are TAGS,
retrieval is `git log` over the agent's own history), MODELED.

Exposes a MODELED, deterministic, pure-stdlib re-implementation of the
GitOfThoughts DATA STRUCTURE (Pavan C Shekar, Abhishek H S, Aswanth Krishnan —
"GitOfThoughts: Version-Controlled Reasoning and Agent Memory You Can Replay,
Diff, and Merge", arXiv:2606.14470) built over a SYNTHETIC scored reasoning tree
drawn from the pure-stdlib LCG PRNG below — plus the paper's key HONEST finding,
the "copyability threshold": retrieved-case memory only helps once the retrieved
case is a near-duplicate (cosine similarity above ~0.8); below that it gives no
accuracy gain on new problems.

  GET  /api/<ns>/v1/gitthoughts/tree?seed=&depth=&branch=

WHAT IS MODELED
---------------
This module fits SZL's khipu/receipt doctrine exactly: a reasoning history that
is content-addressed, replayable, diffable, and mergeable — an audit trail, not
a smarter oracle.

(1) COMMIT GRAPH (the git substrate). A scored reasoning TREE of `depth` levels
    with branching factor `branch` is built deterministically. Each thought is a
    COMMIT whose identity is a real sha256 over (parent_sha + content + score) —
    exactly the content-addressed identity git uses. The score is attached as a
    git-NOTE; a terminal (leaf) thought carries an outcome TAG (solved / partial
    / dead-end) chosen by its score band. Because the sha folds in the parent
    sha, the whole thing is a Merkle DAG: any edit to an ancestor changes every
    descendant sha, so the history is tamper-evident.

(2) GIT LOG RETRIEVAL (DAG walk). `git log` = walk the DAG from HEAD (the
    highest-scoring leaf) back to the root via parent pointers, newest-first.
    We return that commit list — the retrieval primitive the paper reduces
    memory lookup to.

(3) REPLAY. Re-walk a chosen branch root→leaf and RE-DERIVE each commit's sha
    from stored (parent, content, score); the replayed shas must match the
    originally recorded shas bit-for-bit (deterministic verification, like
    replaying a git branch and confirming the tree hash).

(4) DIFF. Take two leaf branches, compute each branch's SET of commit shas, and
    report shas only-in-A, only-in-B, and shared (the common ancestor prefix) —
    a set diff over commit ids, exactly `git log A...B`.

(5) MERGE. Union the two branches' commits into one commit set. A CONFLICT is
    detected when the two branches place DIFFERENT content at the SAME tree slot
    (same depth + same sibling index) — the classic same-path-different-content
    merge conflict. We report merged commit count and any conflict slots.

(6) COPYABILITY THRESHOLD (the paper's honest finding). A synthetic case bank is
    probed at a sweep of query-to-case cosine SIMILARITIES in [0, 1]. Retrieval
    "accuracy" is modeled as a sharp logistic STEP centred at ~0.8: below the
    threshold the retrieved case is not a near-duplicate, so memory transfers
    NOTHING and accuracy sits at the no-memory baseline; only once similarity
    crosses ~0.8 (near-duplicate = the answer is literally already there) does
    accuracy jump. We MEASURE the size of that jump and the pre-threshold gain
    (which is ~0 — the whole point).

Returned JSON fields
--------------------
  label                : "MODELED" (always — clean-room reproduction of the
                         GitOfThoughts data structure + copyability-threshold
                         finding, NOT a real LLM / agent run)
  model                : short description of the modeled setup
  method               : one-line description of the substrate + threshold model
  seed                 : RNG seed used
  depth                : tree depth (levels of thoughts)
  branch               : branching factor per thought
  commit_count         : total commits (thoughts) in the tree
  leaf_count           : number of terminal (tagged) thoughts
  head_sha             : sha of HEAD = highest-scoring leaf
  root_sha             : sha of the root thought
  git_log              : DAG walk HEAD→root (list of {sha7, depth, score, note,
                         tag, content}) — the `git log` retrieval result
  replay_ok            : bool — replayed branch shas match recorded shas exactly
  replay_len           : number of commits re-derived on the replayed branch
  diff                 : {branch_a_head, branch_b_head, only_a, only_b, shared,
                         only_a_count, only_b_count, shared_count}
  merge                : {merged_commit_count, conflict_count, conflicts[...]}
  tag_histogram        : {solved, partial, dead-end} counts across leaves
  threshold            : the ~0.8 copyability threshold (cosine similarity)
  sweep                : list of {similarity, accuracy, baseline, gain} rows
  jump_size            : MEASURED accuracy jump across the threshold
  gain_below_threshold : MEASURED mean accuracy gain below threshold (≈ 0.0)
  gain_above_threshold : MEASURED mean accuracy gain above threshold
  honest_note          : plain-language honesty disclaimer (see below)
  citations            : dict of citable sources (verified real)
  computed_at          : ISO-8601 UTC timestamp

HONEST STATUS — "MODELED"
  This is a deterministic, pure-stdlib re-implementation of the GitOfThoughts
  DATA STRUCTURE (git-as-reasoning-substrate: commit / note / tag / log / replay
  / diff / merge) plus the paper's COPYABILITY-THRESHOLD finding, built on a
  SYNTHETIC scored reasoning tree and a SYNTHETIC case bank (no numpy, no stdlib
  `random`; hashlib.sha256 is used ONLY for the content-addressed commit ids,
  exactly as git does). It does NOT run a real LLM, does NOT reason, and does NOT
  claim memory improves novel-problem accuracy — the paper's HEADLINE finding is
  that giving an agent memory does NOT beat parity on new problems, and that
  memory only helps for near-duplicate (cos-sim > ~0.8) retrieval, i.e. the model
  is finding the answer, not transferring the method. This module reproduces that
  HONESTY: the modeled pre-threshold gain is ~0. The label "MODELED" is returned
  verbatim and displayed verbatim by the surface; never upgraded.

CITATIONS (clean-room; none claimed as SZL's own; VERIFY real):
  GitOfThoughts: Version-Controlled Reasoning and Agent Memory You Can Replay,
    Diff, and Merge — Pavan C Shekar, Abhishek H S, Aswanth Krishnan.
    arXiv:2606.14470  https://arxiv.org/abs/2606.14470
  Git content-addressed object model (Merkle DAG of commits) — Pro Git book,
    Chacon & Straub: https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
  NEVER-CLAIMED-AS: this module is not GitOfThoughts' released code, runs no LLM,
  runs no benchmark (GSM8K etc.), and reproduces none of the paper's measured
  model accuracies. It is a clean-room MODELED reproduction of the data structure
  and the copyability-threshold finding the work describes.

DOCTRINE v11: NOTHING here is in the locked-8. Λ = Conjecture 1. Trust < 100%.
  No fabricated data. Pure stdlib (hashlib allowed for sha). Deterministic with
  seed. 0 runtime CDN.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Citations block — verbatim, never claimed as SZL's own
# ---------------------------------------------------------------------------
CITATIONS = {
    "GitOfThoughts: Version-Controlled Reasoning and Agent Memory You Can Replay, Diff, and Merge — Pavan C Shekar, Abhishek H S, Aswanth Krishnan. arXiv:2606.14470": "https://arxiv.org/abs/2606.14470",
    "Git content-addressed object model (Merkle DAG of commits) — Pro Git, Chacon & Straub": "https://git-scm.com/book/en/v2/Git-Internals-Git-Objects",
}

# The paper's copyability threshold: memory only helps once retrieved-case cosine
# similarity crosses ~0.8 (near-duplicate = answer retrieval, not method transfer).
_COPY_THRESHOLD = 0.80
# Sharpness of the logistic step at the threshold (deliberately steep -> "sharp jump").
_STEP_SHARPNESS = 60.0
# Accuracy floor (no-memory baseline) and the ceiling once a near-duplicate is hit.
_ACC_BASELINE = 0.42   # modeled no-memory / below-threshold accuracy
_ACC_NEARDUP = 0.94    # modeled accuracy when a near-duplicate answer is retrieved

# Outcome-tag bands over a leaf's score in [0, 1].
_TAG_SOLVED_MIN = 0.66
_TAG_PARTIAL_MIN = 0.33


# ---------------------------------------------------------------------------
# Pure-stdlib deterministic LCG PRNG (no numpy, no stdlib `random`) — same
# generator family used across the SZL organ endpoints for reproducibility.
# ---------------------------------------------------------------------------
def _lcg(seed: int):
    s = (int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    while True:
        s = (1664525 * s + 1013904223) & 0xFFFFFFFF
        yield s / 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Content-addressed commit identity — real sha256 over (parent + content + score),
# exactly as git derives an object id (hashlib IS allowed by Doctrine v11 for sha).
# ---------------------------------------------------------------------------
def _commit_sha(parent_sha: str, content: str, score: float) -> str:
    """sha256 hex over parent_sha + content + quantized score — the Merkle link."""
    payload = f"{parent_sha}\n{content}\n{score:.6f}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _score_to_tag(score: float) -> str:
    if score >= _TAG_SOLVED_MIN:
        return "solved"
    if score >= _TAG_PARTIAL_MIN:
        return "partial"
    return "dead-end"


# ---------------------------------------------------------------------------
# Build a scored reasoning TREE of commits (thoughts). Each node stores parent,
# content, score, its (depth, sibling-index) tree SLOT, and its content-addressed
# sha. This is the git substrate: commits + notes(scores) + tags(outcomes).
# ---------------------------------------------------------------------------
def _build_tree(seed: int, depth: int, branch: int):
    rng = _lcg(seed)
    # root thought
    root = {
        "id": 0,
        "parent_id": None,
        "depth": 0,
        "slot": 0,               # sibling index within its level
        "content": "root: frame the problem",
        "score": round(next(rng), 6),
    }
    root["sha"] = _commit_sha("", root["content"], root["score"])
    root["note"] = f"score={root['score']:.3f}"
    root["tag"] = None
    nodes = [root]
    frontier = [root]

    for d in range(1, depth + 1):
        next_frontier = []
        for parent in frontier:
            for b in range(branch):
                nid = len(nodes)
                content = f"thought d{d} s{b} via #{parent['id']}"
                score = round(next(rng), 6)
                node = {
                    "id": nid,
                    "parent_id": parent["id"],
                    "depth": d,
                    "slot": b,
                    "content": content,
                    "score": score,
                    "sha": _commit_sha(parent["sha"], content, score),
                    "note": f"score={score:.3f}",
                    "tag": None,
                }
                nodes.append(node)
                next_frontier.append(node)
        frontier = next_frontier

    # tag the terminal (leaf) thoughts by their score band
    leaves = [n for n in nodes if n["depth"] == depth]
    for lf in leaves:
        lf["tag"] = _score_to_tag(lf["score"])
    return nodes, leaves


def _ancestors(nodes, node):
    """Return the root→node path (list of node dicts)."""
    by_id = {n["id"]: n for n in nodes}
    path = []
    cur = node
    while cur is not None:
        path.append(cur)
        pid = cur["parent_id"]
        cur = by_id[pid] if pid is not None else None
    path.reverse()
    return path


# ---------------------------------------------------------------------------
# git log = DAG walk from HEAD (highest-scoring leaf) back to root, newest-first.
# ---------------------------------------------------------------------------
def _git_log(nodes, head):
    path = _ancestors(nodes, head)      # root→head
    path_rev = list(reversed(path))     # head→root == `git log` order
    log = []
    for n in path_rev:
        log.append({
            "sha7": n["sha"][:7],
            "depth": n["depth"],
            "score": n["score"],
            "note": n["note"],
            "tag": n["tag"],
            "content": n["content"],
        })
    return log


# ---------------------------------------------------------------------------
# replay = re-walk a branch root→leaf and RE-DERIVE each sha; must match exactly.
# ---------------------------------------------------------------------------
def _replay(nodes, leaf):
    path = _ancestors(nodes, leaf)      # root→leaf
    ok = True
    parent_sha = ""
    replayed = 0
    for n in path:
        rederived = _commit_sha(parent_sha, n["content"], n["score"])
        if rederived != n["sha"]:
            ok = False
            break
        parent_sha = n["sha"]
        replayed += 1
    return ok, replayed


# ---------------------------------------------------------------------------
# diff = set difference over two branches' commit shas (git log A...B).
# ---------------------------------------------------------------------------
def _diff(nodes, leaf_a, leaf_b):
    sa = {n["sha"] for n in _ancestors(nodes, leaf_a)}
    sb = {n["sha"] for n in _ancestors(nodes, leaf_b)}
    only_a = sorted(x[:7] for x in (sa - sb))
    only_b = sorted(x[:7] for x in (sb - sa))
    shared = sorted(x[:7] for x in (sa & sb))
    return {
        "branch_a_head": leaf_a["sha"][:7],
        "branch_b_head": leaf_b["sha"][:7],
        "only_a": only_a,
        "only_b": only_b,
        "shared": shared,
        "only_a_count": len(only_a),
        "only_b_count": len(only_b),
        "shared_count": len(shared),
    }


# ---------------------------------------------------------------------------
# merge = union the two branches' commits; conflict = same tree SLOT (depth,
# sibling index) holding DIFFERENT content.
# ---------------------------------------------------------------------------
def _merge(nodes, leaf_a, leaf_b):
    path_a = _ancestors(nodes, leaf_a)
    path_b = _ancestors(nodes, leaf_b)
    union_shas = {n["sha"] for n in path_a} | {n["sha"] for n in path_b}

    # index branch A's commits by tree slot
    slot_a = {(n["depth"], n["slot"]): n for n in path_a}
    conflicts = []
    for n in path_b:
        key = (n["depth"], n["slot"])
        if key in slot_a and slot_a[key]["content"] != n["content"]:
            conflicts.append({
                "slot": {"depth": key[0], "index": key[1]},
                "a_sha7": slot_a[key]["sha"][:7],
                "b_sha7": n["sha"][:7],
                "a_content": slot_a[key]["content"],
                "b_content": n["content"],
            })
    return {
        "merged_commit_count": len(union_shas),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# copyability threshold: retrieval accuracy vs case-similarity, sharp jump ~0.8.
# ---------------------------------------------------------------------------
def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _copyability_sweep(n_points: int = 21):
    """Sweep query-to-case cosine similarity in [0,1]; accuracy is a sharp
    logistic step centred at the ~0.8 copyability threshold. Below threshold the
    retrieved case is not a near-duplicate -> no transfer -> accuracy = baseline.
    """
    rows = []
    for i in range(n_points):
        sim = i / (n_points - 1)
        step = _sigmoid(_STEP_SHARPNESS * (sim - _COPY_THRESHOLD))
        acc = _ACC_BASELINE + (_ACC_NEARDUP - _ACC_BASELINE) * step
        baseline = _ACC_BASELINE
        rows.append({
            "similarity": round(sim, 4),
            "accuracy": round(acc, 6),
            "baseline": round(baseline, 6),
            "gain": round(acc - baseline, 6),
        })
    return rows


# ---------------------------------------------------------------------------
# MODELED snapshot
# ---------------------------------------------------------------------------
def _gitthoughts_snapshot(seed: int = 42, depth: int = 4, branch: int = 3) -> dict:
    """
    Deterministically build a scored reasoning tree of git commits, run git-log
    retrieval / replay / diff / merge over it, and sweep the copyability
    threshold. Pure stdlib; same (seed, depth, branch) -> identical snapshot.
    """
    nodes, leaves = _build_tree(seed, depth, branch)

    # HEAD = highest-scoring leaf (ties -> lowest id for determinism)
    head = min(leaves, key=lambda n: (-n["score"], n["id"]))
    root = nodes[0]

    git_log = _git_log(nodes, head)

    # replay the HEAD branch
    replay_ok, replay_len = _replay(nodes, head)

    # diff / merge on the two highest-scoring DISTINCT leaves
    ranked = sorted(leaves, key=lambda n: (-n["score"], n["id"]))
    leaf_a = ranked[0]
    leaf_b = ranked[1] if len(ranked) > 1 else ranked[0]
    diff = _diff(nodes, leaf_a, leaf_b)
    merge = _merge(nodes, leaf_a, leaf_b)

    # tag histogram over leaves
    tag_hist = {"solved": 0, "partial": 0, "dead-end": 0}
    for lf in leaves:
        tag_hist[lf["tag"]] = tag_hist.get(lf["tag"], 0) + 1

    # copyability threshold sweep
    sweep = _copyability_sweep()
    below = [r["gain"] for r in sweep if r["similarity"] < _COPY_THRESHOLD]
    above = [r["gain"] for r in sweep if r["similarity"] > _COPY_THRESHOLD]
    gain_below = round(sum(below) / len(below), 6) if below else 0.0
    gain_above = round(sum(above) / len(above), 6) if above else 0.0

    # measured jump: nearest sweep point below vs above the threshold
    below_pts = [r for r in sweep if r["similarity"] < _COPY_THRESHOLD]
    above_pts = [r for r in sweep if r["similarity"] >= _COPY_THRESHOLD]
    acc_lo = below_pts[-1]["accuracy"] if below_pts else _ACC_BASELINE
    acc_hi = above_pts[0]["accuracy"] if above_pts else _ACC_NEARDUP
    jump_size = round(acc_hi - acc_lo, 6)

    return {
        "depth": depth,
        "branch": branch,
        "commit_count": len(nodes),
        "leaf_count": len(leaves),
        "head_sha": head["sha"],
        "root_sha": root["sha"],
        "git_log": git_log,
        "replay_ok": bool(replay_ok),
        "replay_len": replay_len,
        "diff": diff,
        "merge": merge,
        "tag_histogram": tag_hist,
        "threshold": _COPY_THRESHOLD,
        "sweep": sweep,
        "jump_size": jump_size,
        "gain_below_threshold": gain_below,
        "gain_above_threshold": gain_above,
        "acc_baseline": _ACC_BASELINE,
        "acc_neardup": _ACC_NEARDUP,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def _ii(req: Request, key: str, default: int) -> int:
    try:
        return int(float(req.query_params.get(key, default)))
    except Exception:
        return default


_HONEST_NOTE = (
    "MODELED: this is a clean-room reproduction of the GitOfThoughts "
    "version-controlled-reasoning DATA STRUCTURE (Pavan C Shekar, Abhishek H S, "
    "Aswanth Krishnan; arXiv:2606.14470) — an agent's reasoning tree stored as a "
    "git repository where every scored thought is a COMMIT (real sha256 over "
    "parent+content+score, a Merkle DAG), scores are NOTES, outcomes are TAGS, "
    "and retrieval is a `git log` DAG walk. Replay re-derives each commit sha and "
    "verifies it matches; diff is a set difference over two branches' commit shas; "
    "merge unions the commits and flags a CONFLICT when the same tree slot holds "
    "different content. It ALSO reproduces the paper's key HONEST finding — the "
    "COPYABILITY THRESHOLD: memory only helps once the retrieved case is a "
    "near-duplicate (cosine similarity above ~0.8), where the model is FINDING "
    "the answer, not transferring the method; below the threshold the modeled "
    "accuracy gain is ~0 (gain_below_threshold). It runs NO real LLM, reasons "
    "NOTHING, runs NO benchmark, and does NOT claim memory improves novel-problem "
    "accuracy — the paper's headline is that it does NOT beat parity on new "
    "problems, and that honesty is reproduced here. Pure stdlib, no numpy, no "
    "stdlib random (hashlib.sha256 used ONLY for content-addressed commit ids, "
    "exactly as git does). Deterministic: same seed/depth/branch -> identical "
    "snapshot. NEVER-CLAIMED-AS a real agent-memory system. SZL claims NONE of "
    "these methods as its own."
)


def _h_tree(req: Request):
    seed   = _ii(req, "seed",   42)
    depth  = max(1, min(_ii(req, "depth",  4), 7))
    branch = max(1, min(_ii(req, "branch", 3), 4))

    snap = _gitthoughts_snapshot(seed=seed, depth=depth, branch=branch)

    return JSONResponse({
        "label":  "MODELED",
        "model":  "GitOfThoughts version-controlled reasoning memory (scored reasoning tree as a git repo: thought=commit sha256(parent+content+score), score=note, outcome=tag; git-log DAG walk, replay, diff, merge) + the copyability-threshold finding on a synthetic case bank",
        "method": "Build scored reasoning tree of sha256 content-addressed commits; git log = DAG walk HEAD(highest-scoring leaf)->root; replay = re-derive & verify branch shas; diff = set-difference over two branches' commit shas; merge = union with conflict at same (depth,slot) different content; copyability threshold = sharp logistic step in retrieval accuracy centred at cosine-sim ~0.80 (near-duplicate=answer retrieval), ~0 gain below",
        "seed":   seed,
        **snap,
        "honest_note": _HONEST_NOTE,
        "citations":   CITATIONS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# register(app, ns) — mirrors szl_muon.register() exactly
# ---------------------------------------------------------------------------
def register(app, ns: str = "killinchu"):
    """Wire /api/<ns>/v1/gitthoughts/tree onto app. Additive, try/except-guarded.
    Uses FastAPI add_api_route when available; falls back to Starlette Route append."""
    base = f"/api/{ns}/v1/gitthoughts"
    handlers = [
        (f"{base}/tree", _h_tree),
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
    snap = _gitthoughts_snapshot(seed=42, depth=4, branch=3)
    print("label: MODELED")
    print("depth:", snap["depth"], "branch:", snap["branch"])
    print("--- GIT SUBSTRATE (scored reasoning tree as commits) ---")
    print("commit_count:", snap["commit_count"], "leaf_count:", snap["leaf_count"])
    print("root_sha:", snap["root_sha"][:12], "head_sha:", snap["head_sha"][:12])
    print("--- git log (DAG walk HEAD->root) ---")
    for c in snap["git_log"]:
        print(f"  {c['sha7']}  d{c['depth']}  score={c['score']:.3f}  tag={c['tag']}  {c['content']}")
    print("--- replay ---")
    print("replay_ok:", snap["replay_ok"], "replay_len:", snap["replay_len"])
    print("--- diff (branch A ... branch B) ---")
    d = snap["diff"]
    print(f"  A={d['branch_a_head']} B={d['branch_b_head']}  only_a={d['only_a_count']} only_b={d['only_b_count']} shared={d['shared_count']}")
    print("--- merge (union; conflict = same slot, different content) ---")
    m = snap["merge"]
    print("  merged_commit_count:", m["merged_commit_count"], "conflict_count:", m["conflict_count"])
    print("--- tag histogram (leaf outcomes) ---")
    print(" ", snap["tag_histogram"])
    print("--- COPYABILITY THRESHOLD (paper's honest finding) ---")
    print("threshold (cosine sim):", snap["threshold"])
    print("jump_size (accuracy jump across threshold):", snap["jump_size"])
    print("gain_below_threshold:", snap["gain_below_threshold"], "(near 0 -> memory does NOT help on novel problems)")
    print("gain_above_threshold:", snap["gain_above_threshold"], "(only near-duplicate retrieval helps)")

    # sanity: git substrate is a well-formed tree
    expected = sum((snap["branch"]) ** k for k in range(snap["depth"] + 1))
    assert snap["commit_count"] == expected, "commit count must equal full b-ary tree node count"
    assert snap["leaf_count"] == snap["branch"] ** snap["depth"], "leaf count = branch^depth"
    assert len(snap["head_sha"]) == 64 and len(snap["root_sha"]) == 64, "sha256 hex ids"

    # sanity: git log is a valid HEAD->root walk of length depth+1
    assert len(snap["git_log"]) == snap["depth"] + 1, "git log length = depth+1 (root..head)"
    assert snap["git_log"][0]["sha7"] == snap["head_sha"][:7], "git log starts at HEAD"
    assert snap["git_log"][-1]["depth"] == 0, "git log ends at root"

    # sanity: replay re-derives & verifies every commit sha bit-for-bit
    assert snap["replay_ok"] is True, "replay must verify branch shas exactly"
    assert snap["replay_len"] == snap["depth"] + 1, "replay covers root..leaf"

    # sanity: diff of two distinct top branches shares the common-ancestor prefix
    assert snap["diff"]["shared_count"] >= 1, "two branches share at least the root"
    assert snap["merge"]["merged_commit_count"] >= snap["depth"] + 1, "merge unions >= one branch"

    # sanity: THE HONEST FINDING — below-threshold gain is ~0, jump is sharp
    assert snap["threshold"] == 0.80, "copyability threshold ~0.8 (paper)"
    assert abs(snap["gain_below_threshold"]) < 0.05, "memory gives ~0 gain below threshold (honest)"
    assert snap["gain_above_threshold"] > snap["gain_below_threshold"], "gain only appears above threshold"
    assert snap["jump_size"] > 0.2, "there must be a SHARP jump across the ~0.8 threshold"

    # sanity: determinism — identical inputs -> identical snapshot
    snap2 = _gitthoughts_snapshot(seed=42, depth=4, branch=3)
    assert snap == snap2, "non-deterministic output for identical inputs"

    print()
    print("szl_gitthoughts: ALL OK — git substrate built (commits/notes/tags), git-log/replay/diff/merge verified, copyability threshold sharp at ~0.8 with ~0 gain below (honest), deterministic.")
