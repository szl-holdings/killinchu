"""The RAG corpus must be read from an immutable dataset commit, never "whatever main is now".

Static (AST) contract: no network, no Hub, no model load. Bumping DATASET_REVISION
is an explicit, reviewable change; an unpinned snapshot_download would silently
follow the dataset main branch. Mirrors the a11oy twin (shared source szl_rag.py).
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "szl_rag.py"


def _tree() -> ast.Module:
    return ast.parse(SRC.read_text(encoding="utf-8"))


def _module_const(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not defined at module level")


def test_dataset_revision_is_a_full_commit_sha():
    rev = _module_const(_tree(), "DATASET_REVISION")
    assert isinstance(rev, str) and len(rev) == 40 and set(rev) <= set("0123456789abcdef"), rev


def test_every_dataset_snapshot_download_passes_the_pinned_revision():
    calls = [
        n for n in ast.walk(_tree())
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", "")) == "snapshot_download"
        and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "DATASET_REPO"
    ]
    assert calls, "expected a snapshot_download(DATASET_REPO, ...) call"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "revision" in kw, f"unpinned snapshot_download at line {call.lineno}"
        assert isinstance(kw["revision"], ast.Name) and kw["revision"].id == "DATASET_REVISION"


def test_status_surface_reports_the_pinned_revision():
    assert '"dataset_revision": DATASET_REVISION' in SRC.read_text(encoding="utf-8")
